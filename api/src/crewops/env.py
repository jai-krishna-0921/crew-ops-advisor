"""The repository's env file, loaded once, by everything that needs it.

WHY THIS IS ITS OWN MODULE. This function lived in `crewops.eval.runner`, so
the eval harness picked up `.env.local` and nothing else did. A real
`ANTHROPIC_API_KEY` could sit in that file while the API served every question
from the deterministic path and reported `llm_configured: false`, and the CLI
did the same. Nothing was misconfigured and nothing errored: the offline path
answers correctly, so the only symptom was a badge in the corner reading
"Deterministic" that looked like a deliberate setting rather than a key being
ignored.

`override=False` everywhere. A variable already in the environment beats the
file, so a deployment that sets real environment variables is never overwritten
by whatever happens to be in a developer's checkout.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["REPO_ROOT", "load_env"]

#: The repository root, four parents up from `src/crewops/env.py`.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Read in order. `.env.local` is the developer's override and wins, which is
#: only true because `override=False` means the FIRST value loaded sticks.
_FILES = (".env.local", ".env")


def load_env(root: Path | None = None) -> None:
    """Load `.env.local` then `.env` from the repository root, if present.

    Agent mode is selected by whichever provider key is present, in the
    precedence order set out in `crewops.agent.providers`. With none of them
    everything still runs, on the deterministic path. That is the point of the
    deterministic path, and it is why a missing file here is not an error.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dependency
        return

    base = root or REPO_ROOT
    for name in _FILES:
        path = base / name
        if path.is_file():
            load_dotenv(path, override=False)
