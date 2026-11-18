"""Generate greetings on save and reuse their files at recognition time."""
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess

from app.config import settings
from app.core.database import SessionLocal
from app.models.employee import Employee
from app.models.employee_greeting import EmployeeGreeting

DEFAULT_TEMPLATE = "Xin chào {tên_nhân_viên}. Chúc bạn một ngày tốt lành."
logger = logging.getLogger(__name__)
_generation_lock = asyncio.Lock()


def render(template, name):
    text = template.replace("{tên_nhân_viên}", name).replace("{name}", name)
    text = " ".join(text.split())
    if not text or len(text) > 300:
        raise ValueError("Câu chào sau khi điền tên phải có từ 1 đến 300 ký tự.")
    return text


def audio_key(text, voice):
    return hashlib.sha256(json.dumps([text, voice, "vieneu-v3-turbo"], ensure_ascii=False).encode()).hexdigest()


def audio_path(key, suffix=".wav"):
    if not re.fullmatch(r"[0-9a-f]{64}", key or "") or suffix not in (".wav", ".mp3"):
        raise ValueError("Invalid audio key")
    return Path(settings.EMPLOYEE_GREETING_DIR).resolve() / (key + suffix)


def configure(db, employee, template=None, voice=None):
    row = db.get(EmployeeGreeting, employee.id)
    template = template if template is not None else (row.template if row else DEFAULT_TEMPLATE)
    voice = voice or (row.voice if row else settings.VIENEU_VOICE)
    key = audio_key(render(template, employee.full_name), voice)
    if row is None:
        row = EmployeeGreeting(employee_id=employee.id)
        db.add(row)
    changed = row.audio_key != key
    row.template, row.voice, row.audio_key = template, voice, key
    if changed or not audio_path(key).exists() or not audio_path(key, ".mp3").exists():
        row.status, row.error = "pending", None
    return row


def info(db, employee):
    row = db.get(EmployeeGreeting, employee.id)
    template = row.template if row else DEFAULT_TEMPLATE
    voice = row.voice if row else settings.VIENEU_VOICE
    text = render(template, employee.full_name)
    valid = row and row.audio_key == audio_key(text, voice)
    ready = valid and row.status == "ready" and audio_path(row.audio_key).exists() and audio_path(row.audio_key, ".mp3").exists()
    return {"welcome_template": template, "welcome_voice": voice, "welcome_text": text,
            "welcome_status": "ready" if ready else (row.status if valid and row.status != "ready" else "pending"),
            "welcome_error": row.error if row else None,
            "welcome_audio_key": row.audio_key if ready else None}


async def generate(employee_id, force=False):
    async with _generation_lock:
        with SessionLocal() as db:
            employee = db.get(Employee, employee_id)
            if not employee or not employee.is_active:
                return
            row = configure(db, employee)
            key, voice, text = row.audio_key, row.voice, render(row.template, employee.full_name)
            if row.status == "ready" and not force:
                db.commit()
                return
            row.status = "generating"
            db.commit()
        try:
            if force:
                await asyncio.to_thread(_generate_files, key, voice, text, True)
            else:
                await asyncio.to_thread(_generate_files, key, voice, text)
            state, error = "ready", None
        except Exception as exc:
            logger.warning("Employee greeting generation failed (%s)", type(exc).__name__)
            state, error = "error", "Chưa tạo được âm thanh. Kiểm tra VieNeu và thử tạo lại."
        with SessionLocal() as db:
            row = db.get(EmployeeGreeting, employee_id)
            if row and row.audio_key == key:
                row.status, row.error = state, error
                db.commit()


def _generate_files(key, voice, text, force=False):
    from app.api.tts import _synthesize_with_vieneu
    mp3, wav = audio_path(key, ".mp3"), audio_path(key)
    if not force and mp3.is_file() and wav.is_file():
        return
    mp3.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp names also avoid concurrent readers seeing incomplete audio.
    import uuid
    tag = uuid.uuid4().hex
    temp_mp3, temp_wav = mp3.with_suffix(f".{tag}.mp3"), wav.with_suffix(f".{tag}.wav")
    try:
        temp_mp3.write_bytes(_synthesize_with_vieneu(text, voice))
        subprocess.run([settings.CAMERA_AUDIO_FFMPEG_BIN, "-nostdin", "-y", "-loglevel", "error",
                        "-i", str(temp_mp3), "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(temp_wav)],
                       capture_output=True, check=True, timeout=20,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        temp_mp3.replace(mp3)
        temp_wav.replace(wav)
    finally:
        temp_mp3.unlink(missing_ok=True)
        temp_wav.unlink(missing_ok=True)


async def prepare_existing():
    from urllib.request import build_opener, ProxyHandler
    def ready():
        try:
            with build_opener(ProxyHandler({})).open(settings.VIENEU_URL.rstrip("/") + "/health", timeout=1) as response:
                return json.load(response).get("ready", False)
        except Exception:
            return False
    for _ in range(90):
        if await asyncio.to_thread(ready):
            break
        await asyncio.sleep(1)
    else:
        logger.warning("VieNeu not ready; employee audio can be generated later from Employees")
        return
    with SessionLocal() as db:
        ids = [row.id for row in db.query(Employee).filter(Employee.is_active.is_(True)).all()]
    for employee_id in ids:
        await generate(employee_id)


def current(employee_id):
    with SessionLocal() as db:
        employee = db.get(Employee, employee_id)
        return info(db, employee) if employee and employee.is_active else None
