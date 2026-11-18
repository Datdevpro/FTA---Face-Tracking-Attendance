"""
Text-to-speech API endpoints.
"""

import asyncio
import json
import logging
import os
from contextlib import contextmanager
from io import BytesIO
from urllib.request import ProxyHandler, Request, build_opener

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tts", tags=["Text to Speech"])

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"


@router.get("/voices")
def tts_voices(current_user=Depends(get_current_user)):
    try:
        with build_opener(ProxyHandler({})).open(settings.VIENEU_URL.rstrip("/") + "/voices", timeout=3) as response:
            return json.load(response)
    except Exception:
        return {"voices": [{"label": settings.VIENEU_VOICE, "name": settings.VIENEU_VOICE}]}


class TTSRequest(BaseModel):
    """Request body for speech synthesis."""

    text: str = Field(..., min_length=1, max_length=300)
    voice: str = Field(default=DEFAULT_VOICE, max_length=80)
    rate: str = Field(default="-8%", max_length=12)


@router.post("/welcome")
async def welcome_tts(
    request: TTSRequest,
    current_user=Depends(get_current_user),
):
    """Generate Vietnamese welcome speech as MP3 audio."""
    audio = await synthesize_welcome_audio(request)

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


async def synthesize_welcome_audio(request: TTSRequest) -> bytes:
    """Share Vietnamese speech generation with the camera audio worker."""
    if settings.TTS_PROVIDER == "vieneu":
        try:
            audio = await asyncio.to_thread(_synthesize_with_vieneu, request.text)
            logger.info("Welcome TTS provider: VieNeu v3 Turbo")
            return audio
        except Exception as exc:
            logger.warning("VieNeu unavailable (%s); trying Edge TTS", type(exc).__name__)
    try:
        audio = await _synthesize_with_edge_tts(request)
        logger.info("Welcome TTS provider: Edge TTS")
        return audio
    except Exception:
        # gTTS performs blocking HTTP requests; keep them off the event loop.
        logger.info("Welcome TTS provider: gTTS")
        return await asyncio.to_thread(_synthesize_with_gtts, request.text)


def _synthesize_with_vieneu(text: str, voice: str | None = None) -> bytes:
    opener = build_opener(ProxyHandler({}))
    request = Request(
        settings.VIENEU_URL.rstrip("/") + "/speech",
        data=json.dumps({"text": text.strip(), "voice": voice or settings.VIENEU_VOICE}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with opener.open(request, timeout=settings.VIENEU_TIMEOUT_SECONDS) as response:
        audio = response.read(5 * 1024 * 1024 + 1)
        if response.headers.get_content_type() != "audio/mpeg" or not audio or len(audio) > 5 * 1024 * 1024:
            raise ValueError("Invalid audio from VieNeu")
        return audio


async def _synthesize_with_edge_tts(request: TTSRequest) -> bytes:
    """Use Microsoft Edge neural TTS when available."""
    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="edge-tts is not installed. Run: pip install edge-tts",
        ) from exc

    try:
        communicate = edge_tts.Communicate(
            text=request.text.strip(),
            voice=request.voice,
            rate=request.rate,
        )
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])

        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="TTS provider returned no audio",
            )

        return b"".join(chunks)
    except HTTPException:
        raise
    except Exception as exc:
        raise RuntimeError(f"edge-tts synthesis failed: {exc}") from exc


def _synthesize_with_gtts(text: str) -> bytes:
    """Use Google Translate TTS as a clearer Vietnamese fallback."""
    try:
        from gtts import gTTS
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No server TTS provider is available. Run: pip install edge-tts gTTS",
        ) from exc

    try:
        buffer = BytesIO()
        with _without_proxy_env():
            gTTS(text=text.strip(), lang="vi", slow=False).write_to_fp(buffer)
        return buffer.getvalue()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TTS synthesis failed: {exc}",
        ) from exc


@contextmanager
def _without_proxy_env():
    """Temporarily disable inherited proxy variables for public TTS calls."""
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]
    original = {key: os.environ.get(key) for key in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
