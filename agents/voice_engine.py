"""
AI-Mentor — Voice Teaching Engine (Phase 11)
Real-time voice tutoring using Amazon Bedrock Nova Sonic.
Bidirectional streaming: text/audio in → audio/text out.

Model: amazon.nova-sonic-v1:0
SDK: aws_sdk_bedrock_runtime (Smithy-based async SDK)
"""
import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

from config import settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MODEL_ID = "amazon.nova-sonic-v1:0"
INPUT_SAMPLE_RATE = 16000       # Client mic → server
OUTPUT_SAMPLE_RATE = 24000      # Server → client playback
CHANNELS = 1
SAMPLE_SIZE_BITS = 16

# Available voices for Nova Sonic
VOICES = {
    "matthew": "Male, calm professor",
    "ruth": "Female, warm teacher",
    "tiffany": "Female, energetic tutor",
}
DEFAULT_VOICE = "matthew"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class VoiceEvent:
    """Event emitted by the voice engine to the WebSocket client."""
    type: str       # "audio" | "text" | "status" | "transcript" | "error"
    data: str       # base64 audio, text content, or status string


# ═══════════════════════════════════════════════════════════════════════════════
# VOICE SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

VOICE_TEACHER_PROMPT = """You are a personal academic mentor and a calm, friendly university professor speaking to a student.
You remember past lessons. You track student progress. You encourage improvement.
You adjust your teaching style to the student. You behave like a long-term professor guiding a student.

Teaching voice rules:
- Speak naturally, as if in a classroom.
- Use short sentences. Pause between ideas.
- Encourage the student: "Good thinking", "Nice attempt", "You're improving".
- Do NOT speak in long paragraphs.
- When explaining, break ideas into 2-3 sentence chunks.
- If interrupted, stop and address the question first.
- After answering an interruption, say "Now let's continue where we left off."
- Always address the student by name when you know it.
- Be patient. Never rush. Never be condescending.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# NOVA SONIC BRIDGE
# ═══════════════════════════════════════════════════════════════════════════════

class NovaSonicBridge:
    """
    Manages a bidirectional streaming session with Amazon Bedrock Nova Sonic.
    Handles session lifecycle, audio/text I/O, and interrupt detection.
    """

    def __init__(
        self,
        region: str = None,
        voice_id: str = DEFAULT_VOICE,
        system_prompt: str = VOICE_TEACHER_PROMPT,
    ):
        self.region = region or settings.aws_region or "us-east-1"
        self.voice_id = voice_id
        self.system_prompt = system_prompt
        self.model_id = MODEL_ID

        self.client = None
        self.stream = None
        self.is_active = False
        self.is_speaking = False

        # Unique IDs for this session
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

        # Output queues
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.text_queue: asyncio.Queue = asyncio.Queue()
        self.event_queue: asyncio.Queue = asyncio.Queue()

        # Response processing task
        self._response_task = None
        self._current_role = None

    def _initialize_client(self):
        """Initialize the Bedrock Runtime client using Smithy SDK."""
        from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
        from aws_sdk_bedrock_runtime.config import Config as BedrockConfig
        from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

        import os
        os.environ.setdefault("AWS_ACCESS_KEY_ID", settings.aws_access_key_id)
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", settings.aws_secret_access_key)
        os.environ.setdefault("AWS_DEFAULT_REGION", self.region)

        config = BedrockConfig(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.client = BedrockRuntimeClient(config=config)

    async def _send_event(self, event_json: str):
        """Send a JSON event to the Nova Sonic stream."""
        from aws_sdk_bedrock_runtime.models import (
            InvokeModelWithBidirectionalStreamInputChunk,
            BidirectionalInputPayloadPart,
        )
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self.stream.input_stream.send(event)

    # ── Session Lifecycle ─────────────────────────────────────────────────────

    async def start_session(self):
        """
        Open a Nova Sonic bidirectional stream and send initialization events:
        sessionStart → promptStart → system prompt → start audio input.
        """
        from aws_sdk_bedrock_runtime.client import (
            InvokeModelWithBidirectionalStreamOperationInput,
        )

        if not self.client:
            self._initialize_client()

        # Open the bidirectional stream
        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True

        # 1. Session start
        await self._send_event(json.dumps({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    }
                }
            }
        }))

        # 2. Prompt start (configure audio out)
        await self._send_event(json.dumps({
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain",
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": SAMPLE_SIZE_BITS,
                        "channelCount": CHANNELS,
                        "voiceId": self.voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        }))

        # 3. System prompt
        await self._send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {
                        "mediaType": "text/plain",
                    },
                }
            }
        }))

        await self._send_event(json.dumps({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "content": self.system_prompt,
                }
            }
        }))

        await self._send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                }
            }
        }))

        # 4. Start audio input channel
        await self._start_audio_input()

        # 5. Start response processor
        self._response_task = asyncio.create_task(self._process_responses())

        logger.info(f"Nova Sonic session started (voice={self.voice_id})")
        await self.event_queue.put(VoiceEvent(type="status", data="listening"))

    async def _start_audio_input(self):
        """Open the audio input content block."""
        await self._send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": SAMPLE_SIZE_BITS,
                        "channelCount": CHANNELS,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        }))

    # ── Audio/Text Input ──────────────────────────────────────────────────────

    async def send_audio_chunk(self, base64_audio: str):
        """Send a base64-encoded LPCM audio chunk from the client mic."""
        if not self.is_active:
            return

        await self._send_event(json.dumps({
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": base64_audio,
                }
            }
        }))

    async def send_text_input(self, text: str):
        """
        Send a text message to Nova Sonic (for text→speech conversion).
        Opens a new text content block, sends text, and closes it.
        """
        if not self.is_active:
            return

        text_name = str(uuid.uuid4())

        await self._send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": text_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "USER",
                    "textInputConfiguration": {
                        "mediaType": "text/plain",
                    },
                }
            }
        }))

        await self._send_event(json.dumps({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": text_name,
                    "content": text,
                }
            }
        }))

        await self._send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": text_name,
                }
            }
        }))

        await self.event_queue.put(VoiceEvent(type="status", data="thinking"))

    # ── Session End ───────────────────────────────────────────────────────────

    async def end_session(self):
        """Cleanly close the Nova Sonic session."""
        if not self.is_active:
            return

        self.is_active = False

        try:
            # End audio input
            await self._send_event(json.dumps({
                "event": {
                    "contentEnd": {
                        "promptName": self.prompt_name,
                        "contentName": self.audio_content_name,
                    }
                }
            }))

            # End prompt
            await self._send_event(json.dumps({
                "event": {
                    "promptEnd": {
                        "promptName": self.prompt_name,
                    }
                }
            }))

            # End session
            await self._send_event(json.dumps({
                "event": {
                    "sessionEnd": {}
                }
            }))

            # Close stream
            await self.stream.input_stream.close()

        except Exception as e:
            logger.warning(f"Error closing Nova Sonic session: {e}")

        # Cancel response task
        if self._response_task and not self._response_task.done():
            self._response_task.cancel()

        await self.event_queue.put(VoiceEvent(type="status", data="idle"))
        logger.info("Nova Sonic session ended")

    # ── Response Processing ───────────────────────────────────────────────────

    async def _process_responses(self):
        """
        Read events from the Nova Sonic output stream and dispatch them
        to the appropriate queues (audio, text, events).
        """
        try:
            while self.is_active:
                output = await self.stream.await_output()
                result = await output[1].receive()

                if not (result.value and result.value.bytes_):
                    continue

                response_data = result.value.bytes_.decode("utf-8")
                json_data = json.loads(response_data)

                if "event" not in json_data:
                    continue

                event = json_data["event"]

                # ── Content start: track role ──
                if "contentStart" in event:
                    self._current_role = event["contentStart"].get("role", "")
                    if self._current_role == "ASSISTANT":
                        self.is_speaking = True
                        await self.event_queue.put(
                            VoiceEvent(type="status", data="speaking")
                        )

                # ── Text output ──
                elif "textOutput" in event:
                    text = event["textOutput"].get("content", "")
                    if text and self._current_role == "ASSISTANT":
                        await self.event_queue.put(
                            VoiceEvent(type="text", data=text)
                        )
                    elif text and self._current_role == "USER":
                        # User transcript from STT
                        await self.event_queue.put(
                            VoiceEvent(type="transcript", data=text)
                        )

                # ── Audio output ──
                elif "audioOutput" in event:
                    audio_b64 = event["audioOutput"].get("content", "")
                    if audio_b64:
                        await self.event_queue.put(
                            VoiceEvent(type="audio", data=audio_b64)
                        )

                # ── Content end ──
                elif "contentEnd" in event:
                    if self._current_role == "ASSISTANT":
                        self.is_speaking = False
                        await self.event_queue.put(
                            VoiceEvent(type="status", data="listening")
                        )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Nova Sonic response processing error: {e}", exc_info=True)
            await self.event_queue.put(
                VoiceEvent(type="error", data=str(e))
            )

    # ── Event Generator ───────────────────────────────────────────────────────

    async def events(self) -> AsyncGenerator[VoiceEvent, None]:
        """Async generator that yields VoiceEvents for the WebSocket to forward."""
        while self.is_active or not self.event_queue.empty():
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(), timeout=0.5
                )
                yield event
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Build voice system prompt with student context
# ═══════════════════════════════════════════════════════════════════════════════

def build_voice_system_prompt(ctx: dict, topic: str = "") -> str:
    """
    Build a voice-optimized system prompt that includes student context.
    """
    profile = ctx.get("profile", {})
    student_name = profile.get("name", "Student").split()[0]
    bloom = ctx.get("bloom_level", 2)
    style = ctx.get("style", "example-based")

    prompt = VOICE_TEACHER_PROMPT + f"""
Student context:
- Name: {student_name}
- Bloom level: {bloom}/6
- Preferred learning style: {style}
"""
    if topic:
        prompt += f"- Current topic: {topic}\n"

    prompt += f"""
When speaking to {student_name}:
- Address them by name naturally.
- Match explanation depth to Bloom level {bloom}/6.
- If they interrupt, say "Good question, {student_name}. Let me address that."
- After answering, say "Now let's continue where we left off."
"""
    return prompt
