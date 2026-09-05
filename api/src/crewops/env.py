"""The repository's env files, loaded once, by everything that needs it.

WHY THIS IS ITS OWN MODULE. This function lived in `crewops.eval.runner`, so
the eval harness picked up `.env.local` and nothing else did. A real
`ANTHROPIC_API_KEY` could sit in that file while the API served every question
from the deterministic path and reported `llm_configured: false`, and the CLI
did the same. Nothing was misconfigured and nothing errored: the offline path
answers correctly, so the only symptom was a badge in the corner reading
"Deterministic" that looked like a deliberate setting rather than a key being
ignored.

WHY IT SEARCHES MORE THAN ONE DIRECTORY. It used to read the repository root
and nowhere else. The Python lives in `api/`, so putting the file next to it is
the obvious thing to do, and it was silently never read. Teammates hit exactly
that: key present, chat answers offline, nothing to tell them why. A file in
`api/` or `web/`, or in the directory a command was run from, is now found.

`override=False` everywhere. A variable already in the environment beats the
file, so a deployment that sets real environment variables is never overwritten
by whatever happens to be in a developer's checkout, and the first file that
carries a variable wins.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["ENV_FILENAMES", "REPO_ROOT", "load_env", "search_paths"]

#: The repository root, four parents up from `src/crewops/env.py`.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Read in this order per directory. `.env.local` is the developer's override
#: and wins, which is only true because `override=False` means the FIRST value
#: loaded sticks.
ENV_FILENAMES = (".env.local", ".env")

#: Searched in this order. Repository root first so it keeps winning where it
#: already worked, then the two package directories, then the working
#: directory, which covers running a command from anywhere in the tree.
_SUBDIRS = ("", "api", "web")


def search_paths(root: Path | None = None) -> list[Path]:
    """Every file `load_env` will look at, in the order it looks."""
    base = (root or REPO_ROOT).resolve()
    roots: list[Path] = [base / sub if sub else base for sub in _SUBDIRS]

    cwd = Path.cwd().resolve()
    if cwd not in roots:
        roots.append(cwd)

    seen: dict[Path, None] = {}
    for directory in roots:
        for name in ENV_FILENAMES:
            seen.setdefault(directory / name, None)
    return list(seen)


def load_env(root: Path | None = None) -> list[Path]:
    """Load every env file found, and return the ones that existed.

    A missing file is not an error. Without a provider key everything still
    runs on the deterministic path, which is the point of the deterministic
    path: the model adds language, not truth.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dependency
        return []

    loaded: list[Path] = []
    for path in search_paths(root):
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path)
    return loaded
