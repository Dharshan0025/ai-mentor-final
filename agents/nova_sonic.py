"""
Nova Sonic Voice Agent — Amazon Bedrock
Provides Text-to-Speech and Speech-to-Text using Amazon Nova Sonic.

Amazon Nova Sonic (model: amazon.nova-sonic-v1:0) is a real-time
speech model on Bedrock. It uses bidirectional streaming for full
speech-to-speech, but we also support simple TTS via invoke_model.

Voice Personalities:
  - professor: Formal, slow, academic tone
  - coach:     Energetic, motivating tone
  - friend:    Casual, warm, conversational

Audio output: PCM 16-bit mono @ 24000 Hz (raw bytes)
We wrap it in a WAV container for browser Audio playback.
"""
import io
import json
import logging
import struct
import asyncio
import base64
from typing import AsyncIterator, Literal

logger = logging.getLogger(__name__)

# ── Voice personality configs ──────────────────────────────────────────────
VOICE_PERSONALITIES = {
    "professor": {
        "voiceId": "matthew",          # Deep, formal US male
        "description": "Formal academic professor",
        "speed": 0.85,
        "systemPrompt": "You are a formal academic professor. Speak clearly, slowly, and with authority. Use proper academic language.",
    },
    "coach": {
        "voiceId": "joanna",           # Energetic female
        "description": "Motivating study coach",
        "speed": 1.05,
        "systemPrompt": "You are an enthusiastic, motivating study coach. Speak with energy and encouragement.",
    },
    "friend": {
        "voiceId": "amy",              # Warm, friendly UK female
        "description": "Casual, friendly tutor",
        "speed": 0.95,
        "systemPrompt": "You are a friendly tutor. Speak naturally and warmly, like explaining to a good friend.",
    },
}

DEFAULT_PERSONALITY = "professor"
NOVA_SONIC_MODEL_ID = "amazon.nova-sonic-v1:0"
SAMPLE_RATE = 24000   # Nova Sonic outputs 24kHz PCM


def _build_wav_header(data_length: int, sample_rate: int = SAMPLE_RATE, channels: int = 1, bits: int = 16) -> bytes:
    """Build a minimal WAV header for PCM data."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    chunk_size = 36 + data_length

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,              # Subchunk1Size
        1,               # AudioFormat = PCM
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        data_length,
    )
    return header


def _pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Wrap raw PCM bytes in a WAV container."""
    header = _build_wav_header(len(pcm_bytes))
    return header + pcm_bytes


class NovaSonicTTS:
    """
    Text-to-Speech using Amazon Nova Sonic via Bedrock.

    Two modes:
    1. invoke_model (blocking, returns full audio as WAV bytes)
    2. Streaming chunked audio via invoke_model_with_response_stream

    Nova Sonic uses a conversation-style payload similar to ChatGPT on Bedrock.
    The audio output is returned as base64-encoded PCM in the response.
    """

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, region: str = "us-east-1"):
        self.region = region
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3
            kwargs = {"region_name": self.region}
            if self.aws_access_key_id and self.aws_secret_access_key:
                kwargs["aws_access_key_id"] = self.aws_access_key_id
                kwargs["aws_secret_access_key"] = self.aws_secret_access_key
                
            self._client = boto3.client("bedrock-runtime", **kwargs)
        return self._client

    def _build_tts_payload(self, text: str, personality: str = DEFAULT_PERSONALITY) -> dict:
        """Build the Nova Sonic TTS request payload."""
        voice_cfg = VOICE_PERSONALITIES.get(personality, VOICE_PERSONALITIES[DEFAULT_PERSONALITY])
        return {
            "schemaVersion": "bedrock-2024-06",
            "system": [{"text": voice_cfg["systemPrompt"]}],
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": text}],
                }
            ],
            "inferenceConfig": {
                "maxTokens": 2048,
                "temperature": 0.7,
            },
            "audioOutputConfig": {
                "mediaType": "audio/lpcm",
                "sampleRateHertz": SAMPLE_RATE,
                "sampleSizeBits": 16,
                "channelCount": 1,
                "voiceId": voice_cfg["voiceId"],
                "encoding": "base64",
                "audioType": "SPEECH",
            },
        }

    async def synthesize(self, text: str, personality: str = DEFAULT_PERSONALITY) -> bytes:
        """
        Call Nova Sonic and return WAV audio bytes.
        Falls back to Polly-style synthesis if Nova Sonic is unavailable.
        Returns empty bytes if TTS fails completely.
        """
        if not text or not text.strip():
            return b""

        # Truncate to 500 chars max for TTS — don't read entire lesson paragraphs
        text = text.strip()[:500]

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self._invoke_nova_sonic, text, personality)
            return result
        except Exception as e:
            logger.warning(f"Nova Sonic TTS failed ({e}), falling back to Polly")
            try:
                result = await loop.run_in_executor(None, self._invoke_polly_fallback, text, personality)
                return result
            except Exception as pe:
                logger.error(f"Polly fallback also failed: {pe}")
                return b""

    def _invoke_nova_sonic(self, text: str, personality: str) -> bytes:
        """Synchronous Nova Sonic invocation (run in executor)."""
        client = self._get_client()
        payload = self._build_tts_payload(text, personality)

        response = client.invoke_model(
            modelId=NOVA_SONIC_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload),
        )

        body = json.loads(response["body"].read())
        # Nova Sonic returns audio in output.message.content[].audio.data (base64)
        audio_b64 = None
        output_msg = body.get("output", {}).get("message", {})
        for content_item in output_msg.get("content", []):
            if "audio" in content_item:
                audio_b64 = content_item["audio"].get("data", "")
                break

        if not audio_b64:
            raise ValueError("No audio data in Nova Sonic response")

        pcm_bytes = base64.b64decode(audio_b64)
        return _pcm_to_wav(pcm_bytes)

    def _invoke_polly_fallback(self, text: str, personality: str) -> bytes:
        """Amazon Polly fallback TTS — returns WAV bytes."""
        import boto3
        voice_cfg = VOICE_PERSONALITIES.get(personality, VOICE_PERSONALITIES[DEFAULT_PERSONALITY])
        # Map Nova voice IDs → Polly voice IDs
        polly_voices = {"matthew": "Matthew", "joanna": "Joanna", "amy": "Amy"}
        polly_voice = polly_voices.get(voice_cfg["voiceId"], "Matthew")

        kwargs = {"region_name": self.region}
        if self.aws_access_key_id and self.aws_secret_access_key:
            kwargs["aws_access_key_id"] = self.aws_access_key_id
            kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        polly = boto3.client("polly", **kwargs)
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat="pcm",
            VoiceId=polly_voice,
            SampleRate=str(SAMPLE_RATE),
            Engine="neural",
        )
        pcm_bytes = response["AudioStream"].read()
        return _pcm_to_wav(pcm_bytes)

    async def stream_synthesize(self, text: str, personality: str = DEFAULT_PERSONALITY) -> AsyncIterator[bytes]:
        """
        Stream audio chunks as they arrive from Nova Sonic.
        Yields WAV header first, then PCM chunks.
        Useful for progressive audio playback in the browser.
        """
        if not text or not text.strip():
            return

        text = text.strip()[:500]
        loop = asyncio.get_event_loop()

        # Collect all PCM data (Nova Sonic streaming still collects fully due to Bedrock limits)
        audio_bytes = await self.synthesize(text, personality)
        if audio_bytes:
            # Yield in ~8KB chunks for smooth streaming
            chunk_size = 8192
            for i in range(0, len(audio_bytes), chunk_size):
                yield audio_bytes[i:i + chunk_size]


class NovaSonicSTT:
    """
    Speech-to-Text using Amazon Transcribe Streaming.
    Fallback: browser Web Speech API (handled client-side).
    """

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, region: str = "st-1"):
        self.region = region
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

    async def transcribe_audio(self, audio_bytes: bytes, media_type: str = "audio/webm") -> str:
        """
        Transcribe audio bytes using Amazon Transcribe.
        Returns transcript text.
        """
        import boto3
        loop = asyncio.get_event_loop()
        try:
            transcript = await loop.run_in_executor(None, self._transcribe_sync, audio_bytes, media_type)
            return transcript
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            return ""

    def _transcribe_sync(self, audio_bytes: bytes, media_type: str) -> str:
        """Synchronous transcription via Transcribe StartTranscriptionJob."""
        import boto3
        import uuid
        import time

        kwargs = {"region_name": self.region}
        if self.aws_access_key_id and self.aws_secret_access_key:
            kwargs["aws_access_key_id"] = self.aws_access_key_id
            kwargs["aws_secret_access_key"] = self.aws_secret_access_key

        s3 = boto3.client("s3", **kwargs)
        transcribe = boto3.client("transcribe", **kwargs)

        # Use a temp S3 to upload audio (Transcribe requires S3 URI)
        bucket = "ai-mentor-transcribe-temp"
        key = f"audio/{uuid.uuid4()}.webm"

        try:
            s3.put_object(Bucket=bucket, Key=key, Body=audio_bytes, ContentType=media_type)
        except Exception:
            # Bucket doesn't exist — create it
            try:
                s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": self.region})
                s3.put_object(Bucket=bucket, Key=key, Body=audio_bytes, ContentType=media_type)
            except Exception as ce:
                raise RuntimeError(f"Could not upload audio for transcription: {ce}")

        job_name = f"tutor-stt-{uuid.uuid4().hex[:12]}"
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{bucket}/{key}"},
            MediaFormat="webm",
            LanguageCode="en-US",
        )

        # Poll until complete (max 30s for short audio)
        for _ in range(30):
            time.sleep(1)
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if job_status == "COMPLETED":
                uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                import urllib.request
                with urllib.request.urlopen(uri) as r:
                    transcript_json = json.loads(r.read())
                text = transcript_json["results"]["transcripts"][0]["transcript"]
                return text
            elif job_status == "FAILED":
                raise RuntimeError("Transcription job failed")

        raise TimeoutError("Transcription timed out after 30 seconds")


# ── Module-level singleton factory ─────────────────────────────────────────
_tts_instance: NovaSonicTTS | None = None
_stt_instance: NovaSonicSTT | None = None


def get_tts(settings) -> NovaSonicTTS:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = NovaSonicTTS(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region=settings.aws_region,
        )
    return _tts_instance


def get_stt(settings) -> NovaSonicSTT:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = NovaSonicSTT(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region=settings.aws_region,
        )
    return _stt_instance
