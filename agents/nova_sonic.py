"""
Voice Agent — Stub Module
Amazon Nova Sonic (Bedrock) has been removed.
TTS is handled client-side by the browser's Web Speech API (window.speechSynthesis)
in VoiceMentor.jsx. STT uses the browser's SpeechRecognition API.

This module preserves the original class interfaces so that existing call-sites
(e.g. get_tts / get_stt) continue to work without errors — they simply return
empty bytes / empty string gracefully.
"""
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# ── Voice personality configs (kept for reference / future use) ────────────
VOICE_PERSONALITIES = {
    "professor": {
        "description": "Formal academic professor",
        "speed": 0.85,
    },
    "coach": {
        "description": "Motivating study coach",
        "speed": 1.05,
    },
    "friend": {
        "description": "Casual, friendly tutor",
        "speed": 0.95,
    },
}

DEFAULT_PERSONALITY = "professor"


class NovaSonicTTS:
    """
    Text-to-Speech stub.
    Browser-side TTS via window.speechSynthesis handles playback.
    Server-side synthesis is not available without Bedrock.
    """

    def __init__(self, *args, **kwargs):
        logger.info("NovaSonicTTS: server-side TTS stubbed — browser handles TTS")

    async def synthesize(self, text: str, personality: str = DEFAULT_PERSONALITY) -> bytes:
        """Returns empty bytes — TTS is handled client-side."""
        return b""

    async def stream_synthesize(self, text: str, personality: str = DEFAULT_PERSONALITY) -> AsyncIterator[bytes]:
        """Yields nothing — TTS is handled client-side."""
        return
        yield  # make this a valid async generator


class NovaSonicSTT:
    """
    Speech-to-Text stub.
    Browser-side STT via Web Speech API handles transcription.
    Server-side transcription is not available without AWS Transcribe.
    """

    def __init__(self, *args, **kwargs):
        logger.info("NovaSonicSTT: server-side STT stubbed — browser handles STT")

    async def transcribe_audio(self, audio_bytes: bytes, media_type: str = "audio/webm") -> str:
        """Returns empty string — STT is handled client-side."""
        return ""


# ── Module-level singleton factory (unchanged interface) ───────────────────
_tts_instance: NovaSonicTTS | None = None
_stt_instance: NovaSonicSTT | None = None


def get_tts(settings=None) -> NovaSonicTTS:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = NovaSonicTTS()
    return _tts_instance


def get_stt(settings=None) -> NovaSonicSTT:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = NovaSonicSTT()
    return _stt_instance
