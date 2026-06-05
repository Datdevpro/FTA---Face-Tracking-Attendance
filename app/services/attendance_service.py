"""
Attendance business logic service.

Handles check-in/check-out logic, cooldown management,
late detection, and attendance record creation.
"""

import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord
from app.models.employee import Employee
from app.config import settings

logger = logging.getLogger(__name__)


class AttendanceService:
    """
    Manages attendance logic including:
    - Auto check-in/check-out via face recognition
    - Cooldown to prevent duplicate entries
    - Late detection based on work schedule
    - Attendance status determination
    """

    def __init__(self):
        # Cooldown cache: employee_id → last_action_time
        self._cooldown_cache: Dict[int, datetime] = {}

    def process_recognition(
        self,
        db: Session,
        employee_id: int,
        confidence: float,
        snapshot_path: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Process a face recognition event and create/update attendance record.

        Args:
            db: Database session.
            employee_id: Recognized employee ID.
            confidence: Recognition confidence score.
            snapshot_path: Path to the captured snapshot image.

        Returns:
            Dict with action details, or None if in cooldown.
        """
        now = datetime.now()

        # Check cooldown
        if self._is_in_cooldown(employee_id, now):
            return None

        # Get employee info
        employee = db.query(Employee).filter(Employee.id == employee_id).first()
        if not employee or not employee.is_active:
            return None

        today = now.date()

        # Find or create today's attendance record
        record = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date == today,
            )
            .first()
        )

        if record is None:
            # First recognition today → Check-in
            status = self._determine_status(now)
            record = AttendanceRecord(
                employee_id=employee_id,
                attendance_date=today,
                check_in_time=now,
                check_in_image=snapshot_path,
                check_in_confidence=confidence,
                status=status,
                source="CAMERA_AUTO",
            )
            db.add(record)
            action = "CHECK_IN"
        elif record.check_out_time is None:
            # Already checked in, no check-out yet → Check-out
            record.check_out_time = now
            record.check_out_image = snapshot_path
            record.check_out_confidence = confidence
            action = "CHECK_OUT"
        else:
            # Already has both check-in and check-out → Update check-out
            record.check_out_time = now
            record.check_out_image = snapshot_path
            record.check_out_confidence = confidence
            action = "CHECK_OUT_UPDATE"

        db.commit()
        db.refresh(record)

        # Update cooldown
        self._cooldown_cache[employee_id] = now

        result = {
            "action": action,
            "employee_id": employee_id,
            "employee_code": employee.employee_code,
            "employee_name": employee.full_name,
            "time": now.isoformat(),
            "confidence": confidence,
            "status": record.status,
            "record_id": record.id,
        }

        logger.info(
            f"Attendance {action}: {employee.full_name} "
            f"({employee.employee_code}) at {now.strftime('%H:%M:%S')} "
            f"[confidence: {confidence:.2f}]"
        )

        return result

    def _is_in_cooldown(self, employee_id: int, now: datetime) -> bool:
        """Check if employee is still in cooldown period."""
        last_action = self._cooldown_cache.get(employee_id)
        if last_action is None:
            return False

        elapsed = (now - last_action).total_seconds()
        return elapsed < settings.ATTENDANCE_COOLDOWN_SECONDS

    def _determine_status(self, check_in_time: datetime) -> str:
        """
        Determine attendance status based on check-in time.

        Returns:
            'PRESENT' if on time, 'LATE' if past threshold.
        """
        try:
            work_start_parts = settings.WORK_START_TIME.split(":")
            work_start = time(
                int(work_start_parts[0]), int(work_start_parts[1])
            )
            late_threshold = timedelta(
                minutes=settings.LATE_THRESHOLD_MINUTES
            )

            check_in_t = check_in_time.time()
            deadline = (
                datetime.combine(date.today(), work_start) + late_threshold
            ).time()

            if check_in_t > deadline:
                return "LATE"
            return "PRESENT"

        except Exception:
            return "PRESENT"

    def get_today_stats(self, db: Session) -> Dict:
        """Get attendance statistics for today."""
        today = date.today()

        total_active = (
            db.query(Employee).filter(Employee.is_active == True).count()
        )

        today_records = (
            db.query(AttendanceRecord)
            .filter(AttendanceRecord.attendance_date == today)
            .all()
        )

        checked_in = len(today_records)
        late = sum(1 for r in today_records if r.status == "LATE")
        on_time = sum(1 for r in today_records if r.status == "PRESENT")
        absent = total_active - checked_in

        return {
            "total_employees": total_active,
            "checked_in": checked_in,
            "late": late,
            "on_time": on_time,
            "absent": absent,
            "date": today.isoformat(),
        }

    def clear_cooldown(self, employee_id: Optional[int] = None):
        """Clear cooldown cache (for testing or manual override)."""
        if employee_id:
            self._cooldown_cache.pop(employee_id, None)
        else:
            self._cooldown_cache.clear()
