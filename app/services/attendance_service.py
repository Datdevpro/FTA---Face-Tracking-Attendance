"""Attendance business logic service."""

import json
import logging
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.attendance import AttendanceRecord
from app.models.employee import Employee

logger = logging.getLogger(__name__)


class AttendanceService:
    """Manage daily check-in and deferred end-of-day check-out."""

    def __init__(self, pending_state_path: Optional[str] = None):
        self.pending_state_path = Path(
            pending_state_path or settings.ATTENDANCE_PENDING_STATE_PATH
        )
        self._state_lock = threading.RLock()
        self._pending_checkouts: Dict[str, Dict] = {}
        self._load_pending_state()

    def process_recognition(
        self,
        db: Session,
        employee_id: int,
        confidence: float,
        snapshot_path: Optional[str] = None,
        recognized_at: Optional[datetime] = None,
    ) -> Optional[Dict]:
        """Process one valid live-face recognition event."""
        now = recognized_at or datetime.now()
        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        if not employee or not employee.is_active:
            return None

        record = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date == now.date(),
            )
            .first()
        )

        if record is None:
            record = AttendanceRecord(
                employee_id=employee_id,
                attendance_date=now.date(),
                check_in_time=now,
                check_in_image=snapshot_path,
                check_in_confidence=confidence,
                status=self._determine_status(now),
                source="CAMERA_AUTO",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            result = self._build_result("CHECK_IN", employee, record, now, confidence)
            self._log_event(result)
            return result

        # Existing records are ignored during the workday. A finalized checkout,
        # including one entered manually, must never be overwritten by camera events.
        if record.check_out_time is not None:
            return None

        if not self._is_checkout_window(now):
            return None

        self._set_pending_checkout(
            employee_id=employee_id,
            attendance_date=now.date(),
            recognized_at=now,
            confidence=confidence,
            snapshot_path=snapshot_path,
        )
        result = self._build_result(
            "CHECK_OUT_PENDING", employee, record, now, confidence
        )
        self._log_event(result)
        return result

    def get_pending_checkout(
        self, employee_id: int, attendance_date: date
    ) -> Optional[Dict]:
        """Return a copy of the temporary checkout shown by the UI."""
        key = self._pending_key(employee_id, attendance_date)
        with self._state_lock:
            candidate = self._pending_checkouts.get(key)
            return dict(candidate) if candidate else None

    def clear_pending_checkout(self, employee_id: int, attendance_date: date) -> None:
        key = self._pending_key(employee_id, attendance_date)
        with self._state_lock:
            if self._pending_checkouts.pop(key, None) is not None:
                self._save_pending_state()

    def finalize_pending_checkouts(
        self, db: Session, before_date: Optional[date] = None
    ) -> int:
        """Persist candidates from completed days and remove their temporary state."""
        cutoff = before_date or date.today()
        with self._state_lock:
            candidates = [
                (key, dict(value))
                for key, value in self._pending_checkouts.items()
                if date.fromisoformat(value["attendance_date"]) < cutoff
            ]

        if not candidates:
            return 0

        finalized_keys = []
        finalized_count = 0
        try:
            for key, candidate in candidates:
                attendance_date = date.fromisoformat(candidate["attendance_date"])
                record = (
                    db.query(AttendanceRecord)
                    .filter(
                        AttendanceRecord.employee_id == candidate["employee_id"],
                        AttendanceRecord.attendance_date == attendance_date,
                    )
                    .first()
                )
                if record and record.check_out_time is None:
                    record.check_out_time = datetime.fromisoformat(
                        candidate["recognized_at"]
                    )
                    record.check_out_confidence = candidate["confidence"]
                    record.check_out_image = candidate.get("snapshot_path")
                    finalized_count += 1
                finalized_keys.append(key)

            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to finalize pending attendance checkouts")
            raise

        with self._state_lock:
            for key in finalized_keys:
                self._pending_checkouts.pop(key, None)
            self._save_pending_state()

        if finalized_count:
            logger.info("Finalized %d pending attendance checkouts", finalized_count)
        return finalized_count

    def _is_checkout_window(self, current: datetime) -> bool:
        end_parts = settings.WORK_END_TIME.split(":")
        end_time = time(int(end_parts[0]), int(end_parts[1]))
        end_at = datetime.combine(current.date(), end_time)
        start_at = end_at - timedelta(
            minutes=settings.CHECK_OUT_WINDOW_MINUTES
        )
        return start_at <= current <= end_at

    def _determine_status(self, check_in_time: datetime) -> str:
        try:
            start_parts = settings.WORK_START_TIME.split(":")
            work_start = time(int(start_parts[0]), int(start_parts[1]))
            deadline = datetime.combine(
                check_in_time.date(), work_start
            ) + timedelta(minutes=settings.LATE_THRESHOLD_MINUTES)
            return "LATE" if check_in_time > deadline else "PRESENT"
        except (TypeError, ValueError):
            logger.exception("Invalid work schedule configuration")
            return "PRESENT"

    def _set_pending_checkout(
        self,
        employee_id: int,
        attendance_date: date,
        recognized_at: datetime,
        confidence: float,
        snapshot_path: Optional[str],
    ) -> None:
        candidate = {
            "employee_id": employee_id,
            "attendance_date": attendance_date.isoformat(),
            "recognized_at": recognized_at.isoformat(),
            "confidence": float(confidence),
            "snapshot_path": snapshot_path,
        }
        with self._state_lock:
            self._pending_checkouts[
                self._pending_key(employee_id, attendance_date)
            ] = candidate
            self._save_pending_state()

    def _load_pending_state(self) -> None:
        if not self.pending_state_path.is_file():
            return
        try:
            data = json.loads(self.pending_state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("pending checkout state must be an object")
            self._pending_checkouts = data
        except (OSError, ValueError, json.JSONDecodeError):
            logger.exception(
                "Unable to load pending checkout state: %s",
                self.pending_state_path,
            )
            self._pending_checkouts = {}

    def _save_pending_state(self) -> None:
        self.pending_state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.pending_state_path.with_suffix(
            self.pending_state_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(self._pending_checkouts, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.pending_state_path)

    @staticmethod
    def _pending_key(employee_id: int, attendance_date: date) -> str:
        return f"{attendance_date.isoformat()}:{employee_id}"

    @staticmethod
    def _build_result(
        action: str,
        employee: Employee,
        record: AttendanceRecord,
        event_time: datetime,
        confidence: float,
    ) -> Dict:
        return {
            "action": action,
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "employee_name": employee.full_name,
            "time": event_time.isoformat(),
            "confidence": confidence,
            "status": record.status,
            "record_id": record.id,
            "pending": action == "CHECK_OUT_PENDING",
        }

    @staticmethod
    def _log_event(result: Dict) -> None:
        logger.info(
            "Attendance %s: %s (%s) at %s [confidence: %.2f]",
            result["action"],
            result["employee_name"],
            result["employee_code"],
            datetime.fromisoformat(result["time"]).strftime("%H:%M:%S"),
            result["confidence"],
        )

    def get_today_stats(self, db: Session) -> Dict:
        today = date.today()
        total_active = db.query(Employee).filter(Employee.is_active == True).count()
        today_records = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.attendance_date == today)
            .all()
        )
        checked_in = len(today_records)
        late = sum(1 for record in today_records if record.status == "LATE")
        on_time = sum(1 for record in today_records if record.status == "PRESENT")
        return {
            "total_employees": total_active,
            "checked_in": checked_in,
            "late": late,
            "on_time": on_time,
            "absent": total_active - checked_in,
            "date": today.isoformat(),
        }

    def clear_cooldown(self, employee_id: Optional[int] = None):
        """Backward-compatible no-op; attendance no longer uses a RAM cooldown."""
        return None
