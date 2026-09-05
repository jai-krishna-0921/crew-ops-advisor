"""Opt-in real provider checks. Never run external requests by default.

Run with CREWOPS_RUN_VOICE_SMOKE=local (VoiceKit running), sarvam, or gemini.
Cloud tests require their server key and consume provider quota. Only synthetic
speech is sent. A failure reports no provider headers or response bodies.
"""

import asyncio
import os
import struct
import time

import pytest

from crewops.agent.voice.config import VoiceConfig
from crewops.agent.voice.providers import Provider
from crewops.env import load_env


@pytest.mark.parametrize("name", ["local", "sarvam", "gemini"])
def test_real_speech_round_trip(name):
    if os.getenv("CREWOPS_RUN_VOICE_SMOKE") != name:
        pytest.skip("Real speech smoke test is opt-in for one provider")
    load_env()
    config = VoiceConfig.from_env()
    if not config.configured(name):
        pytest.skip("Selected speech provider has no configured key")

    async def run():
        provider = Provider(name, config)
        for run_number in range(2):
            start = time.monotonic()
            pcm = b"".join(
                [
                    chunk
                    async for chunk in provider.synthesize(
                        "Check the captain's duty hours at Bangalore."
                    )
                ]
            )
            assert len(pcm) > 24000
            synthesis = time.monotonic() - start
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
            # Linear interpolation is sufficient for this synthetic smoke
            # fixture. Production capture is resampled in its AudioWorklet.
            resampled = []
            for index in range((len(samples) - 1) * 2 // 3):
                position = index * 1.5
                left = int(position)
                weight = position - left
                resampled.append(round(samples[left] * (1 - weight) + samples[left + 1] * weight))
            audio = struct.pack(f"<{len(resampled)}h", *resampled) + b"\x00\x00" * 16000

            async def chunks(recording=audio):
                for offset in range(0, len(recording), 3200):
                    yield recording[offset : offset + 3200]

            async def emit(kind, text):
                pass

            text = await provider.transcribe(chunks(), emit)
            assert "duty" in text.lower()
            print(
                f"{name} run {run_number + 1}: TTS {synthesis:.2f}s; "
                f"round trip {time.monotonic() - start:.2f}s; transcript matched"
            )

    asyncio.run(run())
