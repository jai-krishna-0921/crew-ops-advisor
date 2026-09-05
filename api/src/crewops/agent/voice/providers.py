"""Local and hosted speech adapters using documented HTTP and WebSocket APIs.

No provider receives a reasoning prompt or tools. Transcription feeds the
existing advisor and synthesis receives only selected final reply prose.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import wave
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import connect

from crewops.agent.voice.config import VoiceConfig, VoiceProvider

TranscriptEmitter = Callable[[str, str], Awaitable[None]]


class SpeechError(Exception):
    """A deliberately sanitized error safe to show in the browser."""


def provider_error(status: int | str) -> SpeechError:
    code = str(status).upper()
    if code.isdigit():
        status = int(code)
    elif any(word in code for word in ("QUOTA", "RATE_LIMIT", "RESOURCE_EXHAUSTED")):
        status = 429
    elif any(word in code for word in ("AUTH", "PERMISSION", "API_KEY")):
        status = 401
    elif any(word in code for word in ("MODEL", "INVALID_ARGUMENT")):
        status = 400
    if status in {401, 403}:
        return SpeechError("The voice API key was rejected. Check the server configuration.")
    if status == 429:
        return SpeechError("The voice provider reached its quota or rate limit. Retry shortly.")
    if status in {400, 404, 422}:
        return SpeechError(
            "The voice model or audio settings are unavailable. Check configuration."
        )
    return SpeechError("The voice provider could not complete the request. Please try again.")


class SpeechProvider(Protocol):
    async def probe(self) -> dict[str, Any]: ...
    async def transcribe(self, audio: AsyncIterator[bytes], emit: TranscriptEmitter) -> str: ...
    def synthesize(self, text: str) -> AsyncIterator[bytes]: ...


def pcm_wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(pcm)
    return buffer.getvalue()


class Provider:
    def __init__(self, name: VoiceProvider, config: VoiceConfig) -> None:
        self.name = name
        self.config = config

    def _error(self, status: int) -> SpeechError:
        if self.name == "local" and status == 503:
            return SpeechError(
                "Local voice models are not ready. "
                "Run make voice-download, then restart make voice."
            )
        return provider_error(status)

    async def probe(self) -> dict[str, Any]:
        if self.name != "local":
            # Credentials are tested by the actual provider connection, not by
            # an unrelated model catalogue or a billable startup request.
            return {"connected": None, "stt_loaded": None, "tts_loaded": None}
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(f"{self.config.local_url.rstrip('/')}/readyz")
                response.raise_for_status()
                models = response.json()["models"]
            return {
                "connected": True,
                "stt_loaded": models["stt"]["loaded"],
                "tts_loaded": models["tts"]["loaded"],
            }
        except (httpx.HTTPError, KeyError, ValueError):
            return {"connected": False, "stt_loaded": False, "tts_loaded": False}

    async def transcribe(self, audio: AsyncIterator[bytes], emit: TranscriptEmitter) -> str:
        if self.name == "local":
            pcm = b"".join([chunk async for chunk in audio])
            if not pcm:
                return ""
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.config.local_url.rstrip('/')}/v1/audio/transcriptions",
                    headers=self._headers(),
                    files={"file": ("utterance.wav", pcm_wav(pcm), "audio/wav")},
                    data={"model": "whisper-1", "language": "en"},
                )
                if response.is_error:
                    raise self._error(response.status_code)
                return str(response.json()["text"]).strip()
        if self.name == "sarvam":
            return await self._sarvam_transcribe(audio, emit)
        return await self._gemini_transcribe(audio, emit)

    def _headers(self) -> dict[str, str]:
        if self.name == "sarvam":
            return {"api-subscription-key": self.config.sarvam_key}
        if self.name == "gemini":
            return {"x-goog-api-key": self.config.gemini_key, "Api-Revision": "2026-05-20"}
        return {"Authorization": f"Bearer {self.config.local_key}"} if self.config.local_key else {}

    async def _sarvam_transcribe(
        self,
        audio: AsyncIterator[bytes],
        emit: TranscriptEmitter,
    ) -> str:
        query = urlencode(
            {
                "model": self.config.sarvam_stt,
                "language_code": "en-IN",
                "sample_rate": 16000,
                "encoding": "linear16",
                "endpointing": "manual",
                "stream_type": "balanced",
            }
        )
        async with connect(
            f"wss://api.sarvam.ai/speech-to-text-realtime/ws?{query}",
            additional_headers=self._headers(),
            open_timeout=15,
        ) as ws:
            await ws.send(json.dumps({"event": "speech_start"}))

            async def send() -> None:
                async for chunk in audio:
                    await ws.send(
                        json.dumps(
                            {"event": "audio_input", "audio": base64.b64encode(chunk).decode()}
                        )
                    )
                await ws.send(json.dumps({"event": "speech_end"}))
                # Manual endpointing normally finalizes on speech_end. Flush as
                # well so buffered audio cannot wait until the session timeout.
                await ws.send(json.dumps({"event": "flush"}))

            sender = asyncio.create_task(send())
            try:
                async for raw in ws:
                    message = json.loads(raw)
                    event = message.get("event")
                    if event == "error":
                        raise provider_error(message.get("code", 500))
                    if event == "transcript.partial":
                        await emit("partial", str(message.get("text", "")))
                    if event == "transcript.final":
                        await sender
                        return str(message.get("text", "")).strip()
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
        raise SpeechError("Sarvam disconnected before finishing the transcript. Please try again.")

    async def _gemini_transcribe(
        self,
        audio: AsyncIterator[bytes],
        emit: TranscriptEmitter,
    ) -> str:
        url = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        )
        async with connect(
            url, additional_headers={"x-goog-api-key": self.config.gemini_key}, open_timeout=15
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "setup": {
                            "model": f"models/{self.config.gemini_stt}",
                            "generationConfig": {"responseModalities": ["TEXT"]},
                            "inputAudioTranscription": {
                                "languageCodes": ["en-IN"],
                                "mode": "VERBATIM",
                            },
                            "realtimeInputConfig": {
                                "automaticActivityDetection": {"disabled": True}
                            },
                        }
                    }
                )
            )
            setup = json.loads(await ws.recv())
            if "setupComplete" not in setup:
                raise provider_error(setup.get("error", {}).get("code", 400))
            await ws.send(json.dumps({"realtimeInput": {"activityStart": {}}}))

            async def send() -> None:
                async for chunk in audio:
                    await ws.send(
                        json.dumps(
                            {
                                "realtimeInput": {
                                    "audio": {
                                        "data": base64.b64encode(chunk).decode(),
                                        "mimeType": "audio/pcm;rate=16000",
                                    }
                                }
                            }
                        )
                    )
                await ws.send(json.dumps({"realtimeInput": {"activityEnd": {}}}))

            sender = asyncio.create_task(send())
            final: list[str] = []
            try:
                async for raw in ws:
                    message = json.loads(raw)
                    if "error" in message:
                        raise provider_error(message["error"].get("code", 500))
                    content = message.get("serverContent", {})
                    if interim := content.get("interimInputTranscription"):
                        await emit("partial", " ".join([*final, str(interim.get("text", ""))]))
                    if transcript := content.get("inputTranscription"):
                        final.append(str(transcript.get("text", "")))
                        await emit("partial", " ".join(final))
                        # Dedicated Live transcription commits input text
                        # without a generated model turn or finished flag.
                        # Manual endpointing makes this the final segment once
                        # activityEnd has been sent. Earlier segments stay previews.
                        if sender.done():
                            await sender
                            return " ".join(final).strip()
                    if content.get("turnComplete"):
                        await sender
                        return " ".join(final).strip()
                    if "goAway" in message:
                        raise SpeechError(
                            "Gemini ended the connection. Retry to start a new session."
                        )
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
        raise SpeechError("Gemini disconnected before finishing the transcript. Please try again.")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        if self.name == "local":
            url = f"{self.config.local_url.rstrip('/')}/v1/audio/speech"
            body: dict[str, Any] = {
                "model": "tts-1",
                "input": text,
                "voice": self.config.local_voice,
                "response_format": "pcm",
            }
        elif self.name == "sarvam":
            url = "https://api.sarvam.ai/text-to-speech/stream"
            body = {
                "text": text,
                "language_code": "en-IN",
                "model": self.config.sarvam_tts,
                "speaker": self.config.sarvam_voice,
                "output_audio_codec": "linear16",
                "speech_sample_rate": 24000,
                "pace": 1.0,
            }
        else:
            url = "https://generativelanguage.googleapis.com/v1beta/interactions"
            body = {
                "model": self.config.gemini_tts,
                "input": "Synthesize speech. Read only the transcript exactly.\nTRANSCRIPT:\n"
                + text,
                "response_format": {"type": "audio"},
                "stream": True,
                "generation_config": {"speech_config": [{"voice": self.config.gemini_voice}]},
            }
        async with (
            httpx.AsyncClient(timeout=self.config.timeout) as client,
            client.stream("POST", url, headers=self._headers(), json=body) as response,
        ):
            if response.is_error:
                raise self._error(response.status_code)
            if self.name != "gemini":
                async for chunk in response.aiter_bytes(9600):
                    yield chunk
            else:
                async for line in response.aiter_lines():
                    if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                        continue
                    event = json.loads(line[5:].strip())
                    if event.get("event_type") in {"error", "interaction.failed"}:
                        raise provider_error(500)
                    delta = event.get("delta", {})
                    if event.get("event_type") == "step.delta" and delta.get("type") == "audio":
                        yield base64.b64decode(delta["data"], validate=True)


def make_provider(name: VoiceProvider, config: VoiceConfig) -> SpeechProvider:
    return Provider(name, config)
