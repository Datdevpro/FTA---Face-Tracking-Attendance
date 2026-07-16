from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.attendance import _record_to_response
from app.config import settings
from app.core.database import Base
from app.models.attendance import AttendanceRecord
from app.models.department import Department
from app.models.employee import Employee
from app.models.face_encoding import FaceEncoding
from app.services.attendance_service import AttendanceService


def make_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'attendance-test.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    employee = Employee(employee_code="T001", full_name="Test Employee")
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return session, employee


def configure_schedule(monkeypatch):
    monkeypatch.setattr(settings, "WORK_START_TIME", "08:00")
    monkeypatch.setattr(settings, "WORK_END_TIME", "17:00")
    monkeypatch.setattr(settings, "LATE_THRESHOLD_MINUTES", 15)
    monkeypatch.setattr(settings, "CHECK_OUT_WINDOW_MINUTES", 15)


def test_first_recognition_checks_in_and_workday_recognition_is_ignored(
    tmp_path, monkeypatch
):
    configure_schedule(monkeypatch)
    db, employee = make_database(tmp_path)
    service = AttendanceService(str(tmp_path / "pending.json"))

    check_in = service.process_recognition(
        db,
        employee.id,
        0.8,
        recognized_at=datetime(2026, 7, 16, 8, 10),
    )
    ignored = service.process_recognition(
        db,
        employee.id,
        0.9,
        recognized_at=datetime(2026, 7, 16, 12, 0),
    )

    record = db.query(AttendanceRecord).one()
    assert check_in["action"] == "CHECK_IN"
    assert check_in["status"] == "PRESENT"
    assert ignored is None
    assert record.check_out_time is None


def test_checkout_candidate_is_visible_but_not_persisted(tmp_path, monkeypatch):
    configure_schedule(monkeypatch)
    db, employee = make_database(tmp_path)
    service = AttendanceService(str(tmp_path / "pending.json"))
    service.process_recognition(
        db,
        employee.id,
        0.8,
        recognized_at=datetime(2026, 7, 16, 8, 20),
    )

    pending_event = service.process_recognition(
        db,
        employee.id,
        0.9,
        recognized_at=datetime(2026, 7, 16, 16, 50),
    )

    record = db.query(AttendanceRecord).one()
    response = _record_to_response(record, db, service)
    assert pending_event["action"] == "CHECK_OUT_PENDING"
    assert record.check_out_time is None
    assert response.check_out_pending is True
    assert response.check_out_time == datetime(2026, 7, 16, 16, 50)
    assert response.check_out_confidence == 0.9


def test_last_checkout_window_recognition_is_finalized_next_day(
    tmp_path, monkeypatch
):
    configure_schedule(monkeypatch)
    db, employee = make_database(tmp_path)
    state_path = tmp_path / "pending.json"
    service = AttendanceService(str(state_path))
    service.process_recognition(
        db,
        employee.id,
        0.8,
        recognized_at=datetime(2026, 7, 16, 8, 0),
    )
    service.process_recognition(
        db,
        employee.id,
        0.85,
        recognized_at=datetime(2026, 7, 16, 16, 48),
    )
    service.process_recognition(
        db,
        employee.id,
        0.92,
        recognized_at=datetime(2026, 7, 16, 16, 59),
    )

    # Reloading the service simulates an Uvicorn restart before midnight.
    reloaded_service = AttendanceService(str(state_path))
    assert reloaded_service.finalize_pending_checkouts(
        db, before_date=date(2026, 7, 17)
    ) == 1

    record = db.query(AttendanceRecord).one()
    assert record.check_out_time == datetime(2026, 7, 16, 16, 59)
    assert record.check_out_confidence == 0.92
    assert reloaded_service.get_pending_checkout(
        employee.id, date(2026, 7, 16)
    ) is None


def test_recognition_after_checkout_window_is_ignored(tmp_path, monkeypatch):
    configure_schedule(monkeypatch)
    db, employee = make_database(tmp_path)
    service = AttendanceService(str(tmp_path / "pending.json"))
    service.process_recognition(
        db,
        employee.id,
        0.8,
        recognized_at=datetime(2026, 7, 16, 8, 0),
    )

    result = service.process_recognition(
        db,
        employee.id,
        0.9,
        recognized_at=datetime(2026, 7, 16, 17, 1),
    )

    assert result is None
    assert service.get_pending_checkout(employee.id, date(2026, 7, 16)) is None
