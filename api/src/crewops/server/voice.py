"""Voice transport. The existing chat endpoint remains the answering path."""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from websockets.exceptions import InvalidStatus

from crewops.agent.voice.config import PROVIDERS, VoiceConfig, VoiceProvider
from crewops.agent.voice.prose import SpokenReply, speech_chunks, speech_text
from crewops.agent.voice.providers import SpeechError, SpeechProvider, make_provider, provider_error

voice_router = APIRouter(prefix="/api/voice", tags=["voice"])
ProviderFactory = Callable[[VoiceProvider, VoiceConfig], SpeechProvider]
MAX_AUDIO = 16000 * 2 * 60


def _timeout_message(kind: str) -> str:
    if kind == "listen":
        return "Transcription timed out. Please try speaking again."
    return "Speech playback timed out. Please try again."


def _settings(connection: Request | WebSocket) -> VoiceConfig:
    config: VoiceConfig = getattr(connection.app.state, "voice_config", VoiceConfig())
    return config


def _factory(connection: Request | WebSocket) -> ProviderFactory:
    factory: ProviderFactory = getattr(
        connection.app.state, "voice_provider_factory", make_provider
    )
    return factory


@voice_router.get("/status")
async def voice_status(request: Request) -> dict[str, Any]:
    config = _settings(request)
    rows = []
    for name in PROVIDERS:
        status = (
            await _factory(request)(name, config).probe()
            if name == "local"
            else {
                "connected": None,
                "stt_loaded": None,
                "tts_loaded": None,
            }
        )
        rows.append(
            {
                "id": name,
                "configured": config.configured(name),
                "location": "local" if name == "local" else "cloud",
                **status,
            }
        )
    return {"default_provider": config.default_provider, "providers": rows}


async def _prefetch(provider: SpeechProvider, chunks: list[str]) -> AsyncIterator[bytes]:
    """Stream the current chunk while preparing at most one chunk ahead."""
    queues: dict[int, asyncio.Queue[bytes | Exception | None]] = {}
    tasks: dict[int, asyncio.Task[None]] = {}

    async def produce(index: int) -> None:
        try:
            async for audio in provider.synthesize(chunks[index]):
                await queues[index].put(audio)
        except Exception as exc:
            await queues[index].put(exc)
        finally:
            # Cancellation must not block while putting into a full queue.
            if not asyncio.current_task().cancelling():  # type: ignore[union-attr]
                await queues[index].put(None)

    def start(index: int) -> None:
        queues[index] = asyncio.Queue(maxsize=8)
        tasks[index] = asyncio.create_task(produce(index))

    if not chunks:
        return
    start(0)
    try:
        for index in range(len(chunks)):
            if index + 1 < len(chunks):
                start(index + 1)
            while (item := await queues[index].get()) is not None:
                if isinstance(item, Exception):
                    raise item
                yield item
            await tasks.pop(index)
            del queues[index]
    finally:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)


@voice_router.websocket("/session")
async def voice_session(ws: WebSocket, provider: VoiceProvider = "sarvam") -> None:
    # CORS middleware does not protect WebSockets. Apply the same origins.
    from crewops.server.app import ALLOWED_ORIGINS

    origin = ws.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        await ws.close(code=1008)
        return
    await ws.accept()
    config = _settings(ws)
    if not config.configured(provider):
        key_name = "SARVAM_API_KEY" if provider == "sarvam" else "GEMINI_API_KEY"
        await ws.send_json(
            {
                "type": "error",
                "request_id": "",
                "message": f"Set {key_name} on the server to use this voice provider.",
            }
        )
        await ws.close(code=1008)
        return
    adapter = _factory(ws)(provider, config)
    if provider == "local" and not (await adapter.probe())["connected"]:
        await ws.send_json(
            {
                "type": "error",
                "request_id": "",
                "message": "Start local voice with make voice, or choose a cloud provider.",
            }
        )
        await ws.close(code=1013)
        return
    await ws.send_json({"type": "ready", "provider": provider})
    task: asyncio.Task[None] | None = None
    queue: asyncio.Queue[bytes | None] | None = None
    active = ""
    byte_count = 0
    finished = False
    seen: set[str] = set()
    send_lock = asyncio.Lock()

    async def emit(kind: str, request_id: str, **payload: Any) -> None:
        async with send_lock:
            if request_id == active:
                await ws.send_json({"type": kind, "request_id": request_id, **payload})

    async def run(
        request_id: str, command: dict[str, Any], audio_queue: asyncio.Queue[bytes | None] | None
    ) -> None:
        try:
            async with asyncio.timeout(config.timeout):
                if command["type"] == "listen":

                    async def audio() -> AsyncIterator[bytes]:
                        assert audio_queue is not None
                        while (chunk := await audio_queue.get()) is not None:
                            yield chunk

                    async def transcript(kind: str, text: str) -> None:
                        await emit(kind, request_id, text=text)

                    result = await adapter.transcribe(audio(), transcript)
                    await emit("final", request_id, text=result)
                else:
                    reply = SpokenReply.model_validate(command.get("reply"))
                    detail_level = command.get("detail_level", "full")
                    if detail_level not in {"full", "summary", "details"}:
                        raise ValueError
                    prose = speech_text(reply, detail_level=detail_level)
                    if not prose:
                        raise SpeechError("This answer has no verified prose to read aloud.")
                    received = False
                    tail = b""
                    async for chunk in _prefetch(adapter, speech_chunks(prose)):
                        chunk = tail + chunk
                        count = len(chunk) // 2 * 2
                        tail = chunk[count:]
                        if count:
                            received = True
                            await emit(
                                "audio",
                                request_id,
                                data=base64.b64encode(chunk[:count]).decode(),
                                sample_rate=24000,
                            )
                    if not received or tail:
                        raise SpeechError(
                            "The voice provider returned incomplete audio. Try again."
                        )
                    complete: dict[str, Any] = {}
                    if detail_level == "summary":
                        complete["has_more"] = bool(speech_text(reply, detail_level="details"))
                    await emit("complete", request_id, **complete)
        except SpeechError as exc:
            await emit("error", request_id, message=str(exc))
        except InvalidStatus as exc:
            await emit("error", request_id, message=str(provider_error(exc.response.status_code)))
        except TimeoutError:
            await emit("error", request_id, message=_timeout_message(command["type"]))
        except Exception:
            # Never serialize upstream bodies or exceptions: URLs and headers
            # can carry API keys. Operational details stay out of voice errors.
            await emit(
                "error", request_id, message="Voice processing failed. Check the service and retry."
            )

    async def cancel() -> None:
        nonlocal task, queue
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        task = None
        queue = None

    try:
        while True:
            message = await ws.receive_text()
            try:
                if len(message) > 250000:
                    raise ValueError
                import json

                command = json.loads(message)
                request_id = command.get("request_id", "")
                if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
                    raise ValueError
                kind = command.get("type")
                if kind in {"listen", "speak"}:
                    if request_id in seen:
                        continue
                    await cancel()
                    active = request_id
                    if len(seen) >= 1000:
                        raise SpeechError("Start a new voice session to continue.")
                    seen.add(request_id)
                    byte_count, finished = 0, False
                    queue = asyncio.Queue(maxsize=650) if kind == "listen" else None
                    task = asyncio.create_task(run(request_id, command, queue))
                elif request_id == active:
                    if kind == "cancel":
                        await cancel()
                        await emit("cancelled", request_id)
                        active = ""
                    elif kind == "audio" and queue is not None and not finished:
                        chunk = base64.b64decode(command.get("data", ""), validate=True)
                        byte_count += len(chunk)
                        if (
                            not chunk
                            or len(chunk) % 2
                            or len(chunk) > 32000
                            or byte_count > MAX_AUDIO
                        ):
                            raise ValueError
                        queue.put_nowait(chunk)
                    elif kind == "finish" and queue is not None and not finished:
                        finished = True
                        queue.put_nowait(None)
                    elif kind != "finish":
                        raise ValueError
            except (
                ValueError,
                TypeError,
                AttributeError,
                binascii.Error,
                ValidationError,
                asyncio.QueueFull,
            ):
                await cancel()
                await emit(
                    "error",
                    active,
                    message="Invalid voice request or recording limit exceeded. Try again.",
                )
            except SpeechError as exc:
                await emit("error", active, message=str(exc))
    except WebSocketDisconnect:
        pass
    finally:
        await cancel()
