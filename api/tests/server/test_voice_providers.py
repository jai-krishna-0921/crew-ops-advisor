"""Wire contract tests, with no credentials or provider network requests."""

import asyncio
import base64
import json

import httpx
import pytest

from crewops.agent.voice import providers
from crewops.agent.voice.config import VoiceConfig
from crewops.agent.voice.providers import Provider, SpeechError


class Socket:
    def __init__(self, name, error=None):
        self.name = name
        self.error = error
        self.sent = []
        self.ended = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        if message.get("event") == "speech_end" or "activityEnd" in message.get(
            "realtimeInput", {}
        ):
            self.ended.set()

    async def recv(self):
        return '{"setupComplete": {}}'

    async def __aiter__(self):
        await self.ended.wait()
        if self.error:
            yield json.dumps({"event": "error", "code": self.error, "message": "secret-key"})
        elif self.name == "gemini":
            yield json.dumps({"serverContent": {"interimInputTranscription": {"text": "Check"}}})
            # Dedicated transcription does not require a generated model turn
            # or the optional finished flag to commit authoritative input text.
            yield json.dumps({"serverContent": {"inputTranscription": {"text": "Check C-1042."}}})
        else:
            yield json.dumps({"event": "transcript.partial", "text": "Check"})
            yield json.dumps({"event": "transcript.final", "text": "Check C-1042."})


async def recording():
    yield b"\x01\x00" * 1600


@pytest.mark.parametrize("name", ["sarvam", "gemini"])
def test_streaming_transcription_wire_contract(monkeypatch, name):
    async def run():
        socket = Socket(name)
        calls = []

        def connect(url, **kwargs):
            calls.append((url, kwargs))
            return socket

        monkeypatch.setattr(providers, "connect", connect)
        partials = []

        async def emit(kind, text):
            partials.append((kind, text))

        provider = Provider(name, VoiceConfig(sarvam_key="secret-key", gemini_key="secret-key"))
        assert await provider.transcribe(recording(), emit) == "Check C-1042."
        assert partials[0] == ("partial", "Check")
        assert "secret-key" not in calls[0][0]
        if name == "gemini":
            setup = socket.sent[0]["setup"]
            assert setup["generationConfig"]["responseModalities"] == ["TEXT"]
            assert setup["inputAudioTranscription"]["languageCodes"] == ["en-IN"]
            assert socket.sent[2]["realtimeInput"]["audio"]["mimeType"] == "audio/pcm;rate=16000"
        else:
            assert "endpointing=manual" in calls[0][0]
            assert socket.sent[0] == {"event": "speech_start"}
            assert base64.b64decode(socket.sent[1]["audio"]) == b"\x01\x00" * 1600
            assert socket.sent[-1] == {"event": "flush"}

    asyncio.run(run())


def test_named_upstream_error_is_sanitized(monkeypatch):
    async def run():
        monkeypatch.setattr(
            providers, "connect", lambda *a, **k: Socket("sarvam", "RATE_LIMIT_EXCEEDED")
        )
        with pytest.raises(SpeechError, match="quota or rate limit") as caught:
            await Provider("sarvam", VoiceConfig()).transcribe(recording(), None)
        assert "secret-key" not in str(caught.value)

    asyncio.run(run())


@pytest.mark.parametrize("name", ["local", "sarvam", "gemini"])
def test_streamed_speech_is_pcm_and_uses_server_headers(monkeypatch, name):
    async def run():
        requests = []
        pcm = b"\x01\x00" * 100

        def handler(request):
            requests.append(request)
            if name == "gemini":
                event = {
                    "event_type": "step.delta",
                    "delta": {"type": "audio", "data": base64.b64encode(pcm).decode()},
                }
                return httpx.Response(200, text=f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n")
            return httpx.Response(200, content=pcm)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: client)
        provider = Provider(name, VoiceConfig(sarvam_key="s", gemini_key="g", local_key="l"))
        assert b"".join([chunk async for chunk in provider.synthesize("C-1042 has 39.07h.")]) == pcm
        request = requests[0]
        body = json.loads(request.content)
        if name == "gemini":
            assert request.headers["x-goog-api-key"] == "g"
            assert body["input"].endswith("C-1042 has 39.07h.")
            assert body["generation_config"]["speech_config"] == [{"voice": "Kore"}]
        elif name == "sarvam":
            assert request.headers["api-subscription-key"] == "s"
            assert body["speech_sample_rate"] == 24000
            assert body["output_audio_codec"] == "linear16"
        else:
            assert request.headers["authorization"] == "Bearer l"
            assert body["response_format"] == "pcm"

    asyncio.run(run())


@pytest.mark.parametrize(
    "status, message", [(401, "key was rejected"), (429, "quota"), (404, "model or audio settings")]
)
def test_http_failures_are_actionable_without_upstream_body(monkeypatch, status, message):
    async def run():
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(status, text="secret-key"))
        )
        monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: client)
        with pytest.raises(SpeechError, match=message) as caught:
            _ = [chunk async for chunk in Provider("sarvam", VoiceConfig()).synthesize("Hello")]
        assert "secret-key" not in str(caught.value)

    asyncio.run(run())


def test_missing_local_models_explain_setup(monkeypatch):
    async def run():
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(503, text="private details"))
        )
        monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: client)
        with pytest.raises(SpeechError, match="make voice-download"):
            _ = [chunk async for chunk in Provider("local", VoiceConfig()).synthesize("Hello")]

    asyncio.run(run())
