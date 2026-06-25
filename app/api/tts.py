"""
Text-to-speech API endpoints.
"""

import os
from contextlib import contextmanager
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/tts", tags=["Text to Speech"])

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"


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
    try:
        audio = await _synthesize_with_edge_tts(request)
    except Exception:
        audio = _synthesize_with_gtts(request.text)

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


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
