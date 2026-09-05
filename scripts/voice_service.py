"""Launch VoiceKit in its own Python environment with the advisor's settings."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.path.insert(0, str(ROOT / "api" / "src"))
    from crewops.env import load_env

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["serve", "download"])
    parser.add_argument("--voice-dir", type=Path, default=ROOT.parent / "voice")
    args = parser.parse_args()
    load_env(ROOT)
    runtime = args.voice_dir.resolve() / ".venv" / "bin" / "voice"
    if not runtime.is_file():
        parser.error("VoiceKit is not installed. Run make install-voice first.")
    for source, destination in {
        "CREWOPS_VOICE_LOCAL_KEY": "VOICE_API_KEY",
        "CREWOPS_VOICE_LOCAL_VOICE": "VOICE_TTS_VOICE",
    }.items():
        if source in os.environ:
            os.environ[destination] = os.environ[source]
    if args.action == "download":
        command = [str(runtime), "models", "download", "--profile", "balanced"]
    else:
        url = urlparse(os.getenv("CREWOPS_VOICE_LOCAL_URL", "http://127.0.0.1:8001"))
        if url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            parser.error("make voice only starts a localhost service.")
        command = [
            str(runtime),
            "serve",
            "--host",
            str(url.hostname),
            "--port",
            str(url.port or 8001),
        ]
    os.execv(str(runtime), command)


if __name__ == "__main__":
    main()
