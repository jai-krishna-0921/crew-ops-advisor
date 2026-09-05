"""A working key must turn the agent on, wherever the developer put it.

Reported by teammates: the key is in `.env`, the chat answers in offline mode
anyway, or the console shows connection refused. Both are configuration
failures that the system had no way to explain, because nothing ever said why
it was offline. The badge in the corner read "Deterministic", which looks like
a deliberate setting rather than a key being ignored.

Three causes, all of them ours.

ONE. `load_env` looked in the repository root and nowhere else. The Python
lives in `api/`, so putting `.env.local` next to it is the obvious thing to do,
and it was silently never read. Same for `web/`, and same for running the CLI
from a subdirectory.

TWO. `resolve()` selects a provider on a variable being non-empty. A template
file with `ANTHROPIC_API_KEY=your-key-here` therefore selects Anthropic, which
then fails to authenticate on every turn, while a working `OLLAMA_API_KEY` sits
behind it in the precedence order doing nothing. The user has a key, the system
has a key, and the key it picked is a placeholder.

THREE. Nothing reported any of it. `/api/health` returned `llm_configured:
false` with `detail: null`, which is the truth and none of the explanation.

Offline remains a supported mode, and none of this makes a missing key an
error. What it stops is a *present* key being ignored in silence.
"""

from __future__ import annotations

import pytest

from crewops import env as env_module
from crewops.agent import providers

REAL = "sk-ant-api03-Zx9f2Lq7Rn4vWbT1yUoP8kEjHgFdSaCwMvBnXzQrTyUiOpAsDfGhJkL"


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_API_KEY",
        "OLLAMA_HOST",
        "CREWOPS_LLM_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)


# ------------------------------------------------------------- where it looks


@pytest.mark.parametrize("where", ["", "api", "web"])
def test_an_env_file_is_found_next_to_the_code_too(
    tmp_path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    """The repository root is not the only place a developer will put it."""
    root = tmp_path
    (root / "api").mkdir()
    (root / "web").mkdir()
    target = root / where if where else root
    (target / ".env.local").write_text(f"ANTHROPIC_API_KEY={REAL}\n", encoding="utf-8")

    loaded = env_module.load_env(root)

    assert providers.resolve() is not None, (
        f"a key in {where or 'the repository root'}/.env.local did not turn the agent on"
    )
    assert loaded, "load_env reported loading nothing"


def test_a_variable_already_set_still_wins(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`override=False` is what lets a real deployment beat a checkout."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-environment")
    (tmp_path / ".env.local").write_text("ANTHROPIC_API_KEY=from-the-file\n", encoding="utf-8")
    env_module.load_env(tmp_path)
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "from-the-environment"


def test_a_missing_file_is_not_an_error(tmp_path) -> None:
    assert env_module.load_env(tmp_path) == []


# ------------------------------------------------------------- placeholders


PLACEHOLDERS = [
    "your-key-here",
    "YOUR_API_KEY",
    "<your key>",
    "changeme",
    "xxxxxxxx",
    "sk-...",
    "replace-me",
    "todo",
    "none",
]


@pytest.mark.parametrize("value", PLACEHOLDERS)
def test_a_placeholder_does_not_select_a_provider(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """The expensive case: a template `ANTHROPIC_API_KEY` shadowing a working
    `OLLAMA_API_KEY`, because Anthropic sorts first and the string is not
    empty. Every turn then fails to authenticate."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    monkeypatch.setenv("OLLAMA_API_KEY", REAL)
    chosen = providers.resolve()
    assert chosen is not None
    assert chosen.name == providers.OLLAMA, (
        f"{value!r} was treated as a real key and shadowed a working one"
    )


def test_a_real_key_is_still_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check must not be so eager that it rejects real keys."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL)
    chosen = providers.resolve()
    assert chosen is not None and chosen.name == providers.ANTHROPIC


def test_an_explicit_provider_still_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREWOPS_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_API_KEY", REAL)
    chosen = providers.resolve()
    assert chosen is not None and chosen.name == providers.OLLAMA


# --------------------------------------------------------------- the diagnosis


def test_it_says_why_it_is_offline_when_nothing_is_set() -> None:
    report = providers.diagnose()
    assert report.provider is None
    assert "ANTHROPIC_API_KEY" in report.detail
    assert report.searched, "the report has to say where it looked"


def test_it_names_the_placeholder_it_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """The single most useful sentence this system can print for a teammate
    who is certain they have a key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-key-here")
    report = providers.diagnose()
    assert "ANTHROPIC_API_KEY" in report.detail
    assert "placeholder" in report.detail.lower()


def test_it_names_the_provider_it_chose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL)
    report = providers.diagnose()
    assert report.provider == providers.ANTHROPIC
    assert "ANTHROPIC_API_KEY" in report.detail


def test_the_diagnosis_never_prints_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL)
    report = providers.diagnose()
    assert REAL not in report.detail
    assert REAL[8:] not in report.detail
