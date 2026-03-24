"""
Speech-to-Text via Sarvam Saaras V3 (primary) with Groq Whisper as fallback.

Saaras V3 modes used:
  - ta / thanglish → language_code=ta-IN, mode=codemix  (handles Tamil + English code-mixing)
  - en             → language_code=en-IN, mode=transcribe

Falls back to Groq Whisper large-v3 if Saaras V3 fails or key is missing.
"""
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

# Saaras V3 language + mode per tutor language
_STT_CONFIG = {
    "ta":        {"language_code": "ta-IN", "mode": "transcribe"},
    "thanglish": {"language_code": "ta-IN", "mode": "codemix"},   # codemix handles Tamil-English mixing
    "en":        {"language_code": "en-IN", "mode": "transcribe"},
}

# Groq Whisper fallback language hints
_WHISPER_LANG = {"ta": "ta", "thanglish": "ta", "en": "en"}

_MIME_TO_EXT = {
    "audio/webm": "webm",
    "audio/wav": "wav",
    "audio/wave": "wav",
    "audio/x-wav": "wav",
    "audio/mp4": "mp4",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
}


async def _saaras_transcribe(audio_bytes: bytes, mime_type: str, language: str) -> str:
    """Transcribe using Sarvam Saaras V3."""
    cfg = _STT_CONFIG.get(language, _STT_CONFIG["en"])
    ext = _MIME_TO_EXT.get(mime_type.split(";")[0].strip(), "webm")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": settings.sarvam_api_key},
            data={"model": "saaras:v3", "language_code": cfg["language_code"], "mode": cfg["mode"]},
            files={"file": (f"audio.{ext}", audio_bytes, mime_type)},
        )
        if not resp.is_success:
            raise RuntimeError(f"Saaras STT {resp.status_code}: {resp.text[:200]}")
        return (resp.json().get("transcript") or "").strip()


async def _whisper_transcribe(audio_bytes: bytes, mime_type: str, language: str) -> str:
    """Transcribe using Groq Whisper large-v3 (fallback)."""
    from groq import AsyncGroq
    ext = _MIME_TO_EXT.get(mime_type.split(";")[0].strip(), "webm")
    whisper_lang = _WHISPER_LANG.get(language, "en")
    client = AsyncGroq(api_key=settings.groq_api_key)
    transcription = await client.audio.transcriptions.create(
        file=(f"audio.{ext}", audio_bytes, mime_type),
        model="whisper-large-v3",
        language=whisper_lang,
        response_format="text",
    )
    return str(transcription).strip()


async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    language: str = "en",
) -> str:
    """
    Transcribe audio — Saaras V3 primary, Groq Whisper fallback.

    Args:
        audio_bytes: Raw audio from MediaRecorder.
        mime_type:   MIME type of the audio blob.
        language:    'en', 'ta', or 'thanglish'.

    Returns:
        Transcript string (empty string if audio is silent/unclear).
    """
    # Primary: Sarvam Saaras V3
    if settings.sarvam_api_key:
        try:
            transcript = await _saaras_transcribe(audio_bytes, mime_type, language)
            logger.info(f"Saaras V3 transcript ({language}): {transcript[:80]!r}")
            return transcript
        except Exception as e:
            logger.warning(f"Saaras V3 STT failed, falling back to Whisper: {e}")

    # Fallback: Groq Whisper
    if settings.groq_api_key:
        try:
            transcript = await _whisper_transcribe(audio_bytes, mime_type, language)
            logger.info(f"Whisper fallback transcript ({language}): {transcript[:80]!r}")
            return transcript
        except Exception as e:
            logger.error(f"Whisper fallback also failed: {e}")
            raise

    raise RuntimeError("No STT provider available — set SARVAM_API_KEY or GROQ_API_KEY")
