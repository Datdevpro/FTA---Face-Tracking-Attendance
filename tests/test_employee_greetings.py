import wave
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.employees import router
from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_greeting import EmployeeGreeting
from app.models.face_encoding import FaceEncoding
from app.models.attendance import AttendanceRecord, WorkSchedule
from app.models.user import AdminUser, SystemLog
from app.services import employee_greetings as greetings, camera_audio


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(greetings, "SessionLocal", sessions)
    monkeypatch.setattr(greetings.settings, "EMPLOYEE_GREETING_DIR", str(tmp_path))
    monkeypatch.setattr(greetings.settings, "VIENEU_VOICE", "Mai Anh")
    yield sessions
    engine.dispose()


def test_save_and_rename_invalidate_audio_but_other_edits_preserve_it(database, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    def db_dependency():
        with database() as db:
            yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: object()
    monkeypatch.setattr(greetings, "generate", AsyncMock())
    with TestClient(app) as client:
        created = client.post("/api/employees", json={"employee_code": "A1", "full_name": "An",
                              "welcome_template": "Hello {name}", "welcome_voice": "Mai Anh"})
        assert created.status_code == 201
        employee_id = created.json()["id"]
        assert created.json()["welcome_text"] == "Hello An"
        with database() as db:
            row = db.get(EmployeeGreeting, employee_id)
            old_key = row.audio_key
            greetings.audio_path(old_key).write_bytes(b"WAV")
            greetings.audio_path(old_key, ".mp3").write_bytes(b"MP3")
            row.status = "ready"
            db.commit()
        unchanged = client.put(f"/api/employees/{employee_id}", json={"position": "Engineer"})
        assert unchanged.json()["welcome_status"] == "ready"
        renamed = client.put(f"/api/employees/{employee_id}", json={"full_name": "Binh"})
        assert renamed.json()["welcome_text"] == "Hello Binh"
        assert renamed.json()["welcome_status"] == "pending"
        assert client.get(f"/api/employees/{employee_id}/welcome/audio").status_code == 409
        with database() as db:
            assert db.get(EmployeeGreeting, employee_id).audio_key != old_key
        assert client.post("/api/employees", json={"employee_code": "BAD", "full_name": "x" * 200,
                           "welcome_template": "{name}" * 3}).status_code == 400
        assert client.get("/api/employees").json()["total"] == 1


@pytest.mark.asyncio
async def test_generate_once_and_reuse_until_voice_changes(database, monkeypatch):
    with database() as db:
        employee = Employee(employee_code="A", full_name="An")
        db.add(employee)
        db.flush()
        employee_id = employee.id
        greetings.configure(db, employee)
        db.commit()
    def write_files(key, voice, text, force=False):
        greetings.audio_path(key).write_bytes(b"WAV")
        greetings.audio_path(key, ".mp3").write_bytes(b"MP3")
    generate = Mock(side_effect=write_files)
    monkeypatch.setattr(greetings, "_generate_files", generate)
    await greetings.generate(employee_id)
    await greetings.generate(employee_id)
    assert generate.call_count == 1
    with database() as db:
        employee = db.get(Employee, employee_id)
        greetings.configure(db, employee, voice="Ngoc Huyen")
        db.commit()
    await greetings.generate(employee_id)
    assert generate.call_count == 2
    assert greetings.current(employee_id)["welcome_status"] == "ready"
    await greetings.generate(employee_id, True)
    assert generate.call_count == 3
    assert generate.call_args.args[-1] is True


@pytest.mark.asyncio
async def test_generation_error_keeps_employee_and_exposes_retry_state(database, monkeypatch):
    with database() as db:
        employee = Employee(employee_code="A", full_name="An")
        db.add(employee)
        db.commit()
        employee_id = employee.id
    monkeypatch.setattr(greetings, "_generate_files", Mock(side_effect=ConnectionError()))
    await greetings.generate(employee_id)
    info = greetings.current(employee_id)
    assert info["welcome_status"] == "error"
    assert info["welcome_error"]
    with database() as db:
        assert db.get(Employee, employee_id).full_name == "An"


@pytest.mark.asyncio
async def test_cached_playback_skips_tts_and_conversion_and_keeps_file(database, monkeypatch):
    key = greetings.audio_key("Hello", "Mai Anh")
    path = greetings.audio_path(key)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\0" * 1600)
    service = camera_audio.CameraAudioService(greetings.settings)
    service._ensure_backchannel = lambda: None
    service._send_wav = AsyncMock()
    synth = AsyncMock()
    monkeypatch.setattr(camera_audio, "synthesize_welcome_audio", synth)
    await service._play("Hello", key)
    synth.assert_not_awaited()
    service._send_wav.assert_awaited_once_with(path, 0.1)
    assert path.exists()


def test_invalid_cache_key_and_oversized_render_are_rejected():
    with pytest.raises(ValueError):
        greetings.audio_path("../secret")
    with pytest.raises(ValueError):
        greetings.render("{name}" * 3, "x" * 200)


def test_recognition_reads_updated_name_without_restarting_backend(database, monkeypatch):
    from app.websocket import camera_stream
    monkeypatch.setattr(camera_stream, "SessionLocal", database)
    with database() as db:
        employee = Employee(employee_code="A", full_name="Old Name")
        db.add(employee)
        db.commit()
        employee_id = employee.id
    assert camera_stream._get_employee_info(employee_id)["name"] == "Old Name"
    with database() as db:
        employee = db.get(Employee, employee_id)
        employee.full_name = "New Name"
        greetings.configure(db, employee)
        db.commit()
    info = camera_stream._get_employee_info(employee_id)
    assert info["name"] == "New Name"
    assert "New Name" in info["welcome_text"]
