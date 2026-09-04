"""The API reads the repository's env file, so a configured key is used.

THE DEFECT THIS EXISTS FOR. `.env.local` at the repository root held a real
`ANTHROPIC_API_KEY`, and the server reported `llm_configured: false` and
answered every question on the deterministic path. Nothing was misconfigured:
`load_env()` lived in `crewops.eval.runner` and was called by the eval harness
only, so `make eval` reached agent mode and the API and the CLI, the two things
a person actually uses, never did.

That failure is quiet in the worst way. The offline path answers correctly, so
there is no error to notice, and the only symptom is a badge in the corner
saying "Deterministic" that looks like a deliberate setting rather than a key
being ignored.

`override=False` throughout: a variable already in the environment beats the
file, so a deployment that sets real environment variables is not overwritten
by a developer's checkout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crewops.env import load_env


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CREWOPS_LLM_PROVIDER", raising=False)


def test_it_reads_env_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env.local").write_text("ANTHROPIC_API_KEY=sk-test-local\n")
    load_env(tmp_path)
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test-local"


def test_env_local_beats_env(tmp_path: Path) -> None:
    """`.env.local` is the developer's override and is read first."""
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-env\n")
    (tmp_path / ".env.local").write_text("ANTHROPIC_API_KEY=from-env-local\n")
    load_env(tmp_path)
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "from-env-local"


def test_a_real_environment_variable_beats_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-the-shell")
    (tmp_path / ".env.local").write_text("ANTHROPIC_API_KEY=from-the-file\n")
    load_env(tmp_path)
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "from-the-shell"


def test_no_env_file_is_not_an_error(tmp_path: Path) -> None:
    load_env(tmp_path)


def test_the_server_reports_agent_mode_when_a_key_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: a key in the file changes what /api/health says.

    This is the assertion that would have caught the defect. Health reported
    `llm_configured: false` with a real key sitting in `.env.local`, and no
    test looked at the two together.
    """
    from fastapi.testclient import TestClient

    from crewops.server.app import create_app

    (tmp_path / ".env.local").write_text("ANTHROPIC_API_KEY=sk-test-server\n")
    monkeypatch.setattr("crewops.server.app.REPO_ROOT", tmp_path)

    with TestClient(create_app()) as client:
        body = client.get("/api/health").json()

    assert body["llm_configured"] is True
    assert body["mode"] == "agent"


def test_an_explicit_opt_out_still_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`CREWOPS_LLM_PROVIDER=none` proves the offline path on a keyed machine."""
    from fastapi.testclient import TestClient

    from crewops.server.app import create_app

    (tmp_path / ".env.local").write_text("ANTHROPIC_API_KEY=sk-test-server\n")
    monkeypatch.setattr("crewops.server.app.REPO_ROOT", tmp_path)
    monkeypatch.setenv("CREWOPS_LLM_PROVIDER", "none")

    with TestClient(create_app()) as client:
        body = client.get("/api/health").json()

    assert body["llm_configured"] is False
    assert body["mode"] == "deterministic"
