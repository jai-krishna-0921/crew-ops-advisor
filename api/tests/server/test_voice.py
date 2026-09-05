"""Voice transports never become a second answering path."""

import asyncio
import base64
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crewops.agent.voice.config import VoiceConfig
from crewops.agent.voice.prose import SpokenReply, speech_chunks, speech_text
from crewops.server.voice import voice_router


def reply(**changes):
    return SpokenReply.model_validate(
        {
            "headline": "C-1042 has 39.07h remaining",
            "text": "Check **P-2291** on 2026-09-15.",
            "caveats": ["Times are UTC."],
            "verification": {"status": "verified"},
            **changes,
        }
    )


def test_speech_preserves_values_and_caveats():
    """Every figure survives. The NOTATION is the part that changes.

    This used to assert the written form verbatim, which is how "39.07h" and
    "2026-09-15" reached the synthesiser to be read as "thirty nine point
    zero seven H" and a string of digits. `speech_for_voice` substitutes
    notation and never value: 39.07 is still 39.07 and 15 September 2026 is
    still 2026-09-15.
    """
    text = speech_text(reply())
    assert text == (
        "C 1042 has 39.07 hours remaining.\n\n"
        "Check P 2291 on 15 September 2026.\n\n"
        "Times are UTC."
    )
    assert "39.07" in text, "the figure itself must never move"


def test_summary_speech_reads_headline_then_offers_verified_details():
    text = speech_text(reply(), detail_level="summary")
    assert text == "C 1042 has 39.07 hours remaining.\n\nWould you like more information?"


def test_detail_speech_continues_without_repeating_summary():
    text = speech_text(reply(), detail_level="details")
    assert text == "Check P 2291 on 15 September 2026.\n\nTimes are UTC."
    assert "39.07" not in text


def test_summary_without_more_information_does_not_offer_it():
    concise = reply(headline=None, text="C-1042 is at BLR.", caveats=[])
    assert speech_text(concise, detail_level="summary") == "C 1042 is at BLR."
    assert speech_text(concise, detail_level="details") == ""


def test_markdown_cleanup_preserves_comparisons_and_omits_tables():
    text = speech_text(
        reply(
            headline=None,
            text=(
                "Duty < 60h; rest > 12h. **C-1042** is *available*.\n\n"
                "Crew | Hours\n--- | ---\nC-2087 | 61.5h\n\n"
                "Keep <strong>39.07h</strong> and <BLR> visible."
            ),
        )
    )
    assert "Duty < 60 hours; rest > 12 hours." in text
    assert "C 1042 is available." in text
    assert "C-2087" not in text
    assert "39.07 hours" in text
    assert "<BLR>" in text


def test_old_headline_is_not_read_twice():
    text = speech_text(reply(text="C-1042 has 39.07h remaining. Details follow."))
    assert text.count("39.07") == 1


def test_abstention_replaces_prose_even_when_verification_rejected():
    text = speech_text(
        reply(
            verification={"status": "rejected"},
            abstention={"message": "I cannot answer reliably.", "missing": ["A crew ID."]},
        )
    )
    assert "39.07" not in text
    assert "A crew ID." in text


@pytest.mark.parametrize("status", ["rejected", "skipped"])
def test_unverified_prose_cannot_be_spoken(status):
    assert speech_text(reply(verification={"status": status})) == ""


def test_chunking_does_not_drop_or_change_operational_tokens():
    text = "C-1042: 39.07h, P-2291, 2026-09-15. " * 200
    chunks = speech_chunks(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert " ".join(chunks).split() == text.split()


@pytest.mark.parametrize(
    "keys",
    [
        {},
        {"SARVAM_API_KEY": "sarvam-secret"},
        {"GEMINI_API_KEY": "gemini-secret"},
        {"SARVAM_API_KEY": "s", "GEMINI_API_KEY": "g"},
    ],
)
def test_key_configuration_is_independent(monkeypatch, keys):
    for key in ("SARVAM_API_KEY", "GEMINI_API_KEY", "CREWOPS_VOICE_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    for key, value in keys.items():
        monkeypatch.setenv(key, value)
    config = VoiceConfig.from_env()
    assert config.default_provider == "sarvam"
    assert config.configured("sarvam") == ("SARVAM_API_KEY" in keys)
    assert config.configured("gemini") == ("GEMINI_API_KEY" in keys)
    assert "secret" not in repr(config)


class FakeProvider:
    cancelled = False

    async def probe(self):
        return {"connected": True, "stt_loaded": True, "tts_loaded": True}

    async def transcribe(self, audio, emit):
        chunks = [chunk async for chunk in audio]
        assert chunks
        await emit("partial", "Who is on reserve")
        return "Who is on reserve at BLR?"

    async def synthesize(self, text):
        try:
            yield b"\x00\x00" * 100
            if "wait forever" in text:
                await asyncio.Event().wait()
        finally:
            self.cancelled = True


def client_for(provider=None):
    app = FastAPI()
    app.include_router(voice_router)
    app.state.voice_config = replace(VoiceConfig(), sarvam_key="secret")
    fake = provider or FakeProvider()
    app.state.voice_provider_factory = lambda name, config: fake
    return TestClient(app), fake


def test_socket_transcription_and_speech_share_provider():
    client, _ = client_for()
    with client, client.websocket_connect("/api/voice/session?provider=sarvam") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "listen", "request_id": "u1"})
        ws.send_json(
            {
                "type": "audio",
                "request_id": "u1",
                "data": base64.b64encode(b"\x00\x00" * 100).decode(),
            }
        )
        ws.send_json({"type": "finish", "request_id": "u1"})
        assert ws.receive_json()["type"] == "partial"
        assert ws.receive_json() == {
            "type": "final",
            "request_id": "u1",
            "text": "Who is on reserve at BLR?",
        }
        ws.send_json({"type": "speak", "request_id": "r1", "reply": reply().model_dump()})
        # ONE AUDIO EVENT PER PARAGRAPH. Chunks used to be repacked up to a
        # thousand characters, so a whole answer arrived as a single utterance
        # with no pause anywhere in it. A chunk boundary is where the voice
        # stops and starts again, so it now agrees with the paragraph.
        event = ws.receive_json()
        while event["type"] == "audio":
            event = ws.receive_json()
        assert event == {"type": "complete", "request_id": "r1"}


def test_socket_summary_reports_when_detail_is_available():
    client, _ = client_for()
    with client, client.websocket_connect("/api/voice/session?provider=sarvam") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "speak",
                "request_id": "r1",
                "detail_level": "summary",
                "reply": reply().model_dump(),
            }
        )
        event = ws.receive_json()
        while event["type"] == "audio":
            event = ws.receive_json()
        assert event == {
            "type": "complete",
            "request_id": "r1",
            "has_more": True,
        }


def test_cancel_discards_inflight_speech_and_allows_next_turn():
    client, fake = client_for()
    with client, client.websocket_connect("/api/voice/session?provider=local") as ws:
        ws.receive_json()
        ws.send_json(
            {"type": "speak", "request_id": "r1", "reply": reply(text="wait forever").model_dump()}
        )
        # The fake provider hangs on the chunk containing "wait forever", and
        # that is now the second paragraph rather than the whole answer, so
        # the headline's audio arrives first.
        assert ws.receive_json()["type"] == "audio"
        ws.send_json({"type": "cancel", "request_id": "r1"})
        event = ws.receive_json()
        while event["type"] == "audio":
            event = ws.receive_json()
        assert event == {"type": "cancelled", "request_id": "r1"}
        assert fake.cancelled
        ws.send_json({"type": "speak", "request_id": "r2", "reply": reply().model_dump()})
        assert ws.receive_json()["request_id"] == "r2"


def test_bad_audio_is_recoverable_and_does_not_echo_payload():
    client, _ = client_for()
    with client, client.websocket_connect("/api/voice/session?provider=local") as ws:
        ws.receive_json()
        ws.send_json({"type": "listen", "request_id": "u1"})
        ws.send_json({"type": "audio", "request_id": "u1", "data": "invalid-secret"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "secret" not in str(error)


@pytest.mark.parametrize(
    "command, expected",
    [
        ({"type": "listen"}, "Transcription timed out. Please try speaking again."),
        ({"type": "speak"}, "Speech playback timed out. Please try again."),
    ],
)
def test_voice_timeout_message_names_the_failed_stage(command, expected):
    from crewops.server.voice import _timeout_message

    assert _timeout_message(command["type"]) == expected


def test_status_never_exposes_keys_or_assumes_cloud_connectivity():
    client, _ = client_for()
    with client:
        status = client.get("/api/voice/status").json()
        assert "secret" not in str(status)
        sarvam = next(p for p in status["providers"] if p["id"] == "sarvam")
        assert sarvam["configured"] is True
        assert sarvam["connected"] is None


def test_unconfigured_cloud_session_explains_key_without_using_local():
    client, _ = client_for()
    with client, client.websocket_connect("/api/voice/session?provider=gemini") as ws:
        event = ws.receive_json()
        assert event["type"] == "error"
        assert "GEMINI_API_KEY" in event["message"]


def test_unavailable_local_service_does_not_block_configured_cloud():
    class DisconnectedLocal(FakeProvider):
        async def probe(self):
            return {"connected": False}

    client, _ = client_for(DisconnectedLocal())
    with client:
        with client.websocket_connect("/api/voice/session?provider=local") as ws:
            assert "make voice" in ws.receive_json()["message"]
        with client.websocket_connect("/api/voice/session?provider=sarvam") as ws:
            assert ws.receive_json()["type"] == "ready"


def test_reused_utterance_ids_do_not_resubmit_transcripts():
    client, _ = client_for()
    with client, client.websocket_connect("/api/voice/session?provider=sarvam") as ws:
        ws.receive_json()
        ws.send_json({"type": "listen", "request_id": "u1"})
        ws.send_json({"type": "audio", "request_id": "u1", "data": "AAA="})
        ws.send_json({"type": "finish", "request_id": "u1"})
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "listen", "request_id": "u1"})
        ws.send_json({"type": "cancel", "request_id": "u1"})
        assert ws.receive_json()["type"] == "cancelled"


def test_untrusted_origins_cannot_open_a_voice_session():
    from starlette.websockets import WebSocketDisconnect

    client, _ = client_for()
    with (
        client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/voice/session?provider=local", headers={"origin": "https://untrusted.example"}
        ),
    ):
        pytest.fail("An untrusted origin was allowed to connect")


def test_prefetch_orders_long_speech_and_cancels_queued_work():
    from crewops.server.voice import _prefetch

    async def run():
        started = []
        stopped = []

        class Chunks(FakeProvider):
            async def synthesize(self, text):
                started.append(text)
                try:
                    for _ in range(20):
                        yield text.encode()
                finally:
                    stopped.append(text)

        stream = _prefetch(Chunks(), ["one", "two", "three"])
        assert await anext(stream) == b"one"
        await asyncio.sleep(0)
        assert started == ["one", "two"]
        await asyncio.wait_for(stream.aclose(), timeout=1)
        assert set(stopped) == {"one", "two"}

    asyncio.run(run())


def test_a_deployed_origin_can_be_allowed_without_a_code_change(monkeypatch):
    """The desk does not only run on a laptop.

    ALLOWED_ORIGINS was two hardcoded localhost entries, so every browser
    WebSocket from a deployed origin was refused with 1008 while the same
    handshake succeeded under curl, which sends no Origin at all. That is the
    shape of a bug nobody finds from the terminal: HTTP kept working, because
    same-origin requests never engage CORS, and only voice broke.

    Widening this is deliberate configuration rather than a wildcard, and the
    check itself stays: an origin nobody named is still refused below.
    """
    import importlib

    from crewops.server import app as app_module

    monkeypatch.setenv("CREWOPS_ALLOWED_ORIGINS", "https://extroc.example.run.app")
    reloaded = importlib.reload(app_module)
    try:
        assert "https://extroc.example.run.app" in reloaded.ALLOWED_ORIGINS
        # The laptop origins survive, so configuring a deployment does not
        # break `make dev` for everybody else.
        assert "http://localhost:3000" in reloaded.ALLOWED_ORIGINS
        assert "https://untrusted.example" not in reloaded.ALLOWED_ORIGINS
    finally:
        monkeypatch.delenv("CREWOPS_ALLOWED_ORIGINS", raising=False)
        importlib.reload(app_module)
