"""Server-owned speech settings, independent of the reasoning provider."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

VoiceProvider = Literal["local", "sarvam", "gemini"]
# Local VoiceKit remains available for development compatibility, but is not
# advertised or included in hosted voice status. Production voice uses Sarvam.
PROVIDERS: tuple[VoiceProvider, ...] = ("sarvam", "gemini")


@dataclass(frozen=True)
class VoiceConfig:
    default_provider: VoiceProvider = "sarvam"
    local_url: str = "http://127.0.0.1:8001"
    local_key: str = field(default="", repr=False)
    sarvam_key: str = field(default="", repr=False)
    gemini_key: str = field(default="", repr=False)
    sarvam_stt: str = "saaras:v3-realtime"
    sarvam_tts: str = "bulbul:v3"
    sarvam_voice: str = "shubh"
    gemini_stt: str = "gemini-3.5-transcribe-live"
    gemini_tts: str = "gemini-3.1-flash-tts-preview"
    gemini_voice: str = "Kore"
    local_voice: str = "af_heart"
    timeout: float = 120.0

    def configured(self, provider: VoiceProvider) -> bool:
        return provider == "local" or bool(
            self.sarvam_key if provider == "sarvam" else self.gemini_key
        )

    @classmethod
    def from_env(cls) -> VoiceConfig:
        selected = os.getenv("CREWOPS_VOICE_PROVIDER", "sarvam").strip().lower()
        provider: VoiceProvider = "sarvam"
        for candidate in (*PROVIDERS, "local"):
            if candidate == selected:
                provider = candidate
        values: dict[str, Any] = {
            name: os.environ[env].strip()
            for name, env in {
                "local_url": "CREWOPS_VOICE_LOCAL_URL",
                "local_key": "CREWOPS_VOICE_LOCAL_KEY",
                "local_voice": "CREWOPS_VOICE_LOCAL_VOICE",
                "sarvam_key": "SARVAM_API_KEY",
                "gemini_key": "GEMINI_API_KEY",
                "sarvam_stt": "CREWOPS_SARVAM_STT_MODEL",
                "sarvam_tts": "CREWOPS_SARVAM_TTS_MODEL",
                "sarvam_voice": "CREWOPS_SARVAM_VOICE",
                "gemini_stt": "CREWOPS_GEMINI_STT_MODEL",
                "gemini_tts": "CREWOPS_GEMINI_TTS_MODEL",
                "gemini_voice": "CREWOPS_GEMINI_VOICE",
            }.items()
            if os.getenv(env, "").strip()
        }
        return cls(default_provider=provider, **values)
