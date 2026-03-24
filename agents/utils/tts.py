"""
Text-to-Speech via Sarvam AI bulbul:v2 — Tamil, Thanglish, and English.
Returns raw WAV bytes decoded from Sarvam's base64 response.
"""
import base64
import logging
import httpx
from config import settings

logger = logging.getLogger(__name__)

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

# bulbul:v2 language codes and matching speakers.
# Thanglish uses ta-IN so the Tamil-sounding words are pronounced correctly.
# Speaker "arya" is a clear female voice available for both ta-IN and en-IN.
_LANG_CONFIG = {
    "ta":        {"lang": "ta-IN", "speaker": "arya"},
    "thanglish": {"lang": "ta-IN", "speaker": "arya"},
    "en":        {"lang": "en-IN", "speaker": "arya"},
}
_DEFAULT_CONFIG = {"lang": "en-IN", "speaker": "arya"}

# bulbul:v2 supports up to 1,500 chars per request
_MAX_CHARS = 1500


async def synthesize(text: str, language: str = "en") -> bytes:
    """
    Convert text to speech using Sarvam AI bulbul:v2.

    Args:
        text:     Text to speak (max 500 chars — truncated if longer).
        language: 'ta' for Tamil script, 'thanglish' for Roman Tamil, 'en' for English.

    Returns:
        WAV audio bytes.

    Raises:
        RuntimeError: if API key missing, Sarvam returns error, or no audio in response.
    """
    if not settings.sarvam_api_key:
        raise RuntimeError("SARVAM_API_KEY is not set")

    text = text[:_MAX_CHARS].strip()
    if not text:
        raise ValueError("text is empty")

    cfg = _LANG_CONFIG.get(language, _DEFAULT_CONFIG)

    payload = {
        "inputs": [text],
        "target_language_code": cfg["lang"],
        "speaker": cfg["speaker"],
        "pitch": 0,
        "pace": 1.1,
        "loudness": 1.5,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "model": "bulbul:v2",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            SARVAM_TTS_URL,
            json=payload,
            headers={
                "api-subscription-key": settings.sarvam_api_key,
                "Content-Type": "application/json",
            },
        )
        if not resp.is_success:
            raise RuntimeError(
                f"Sarvam TTS {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()

    audios = data.get("audios") or []
    if not audios:
        raise RuntimeError(f"Sarvam TTS returned no audio. Response: {data}")

    return base64.b64decode(audios[0])
