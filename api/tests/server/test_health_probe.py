"""`/api/health` says what is configured. It has to be able to say what works.

Two teammates reported the agent failing on every turn. `/api/health` and
`crewops health` both said the same thing to both of them, in green:

    Provider: ollama    Mode: agent    Model: deepseek-v4-flash:cloud

Both were correct. Neither had touched the provider: selection is by presence
of an environment variable, deliberately and documented, because `mode` is read
on every request and a live probe there would put a network round trip in front
of every page load. The cost of that decision is a green light in front of a
broken turn, which is worse than a red one.

So the probe is opt in. `/api/health?probe=1` and `crewops health` (the human
command, where one round trip is free) actually call the provider and report
what came back. The default request path is unchanged and still never touches
the network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crewops.server.app import create_app


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CREWOPS_LLM_PROVIDER", "none")


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as running:
        yield running


def test_health_still_answers_without_probing(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["mode"] == "deterministic"
    assert body["provider_reachable"] is None, (
        "the default path must not call the provider"
    )


def test_the_probe_is_opt_in_and_reports_offline_as_not_a_failure(
    client: TestClient,
) -> None:
    """No provider configured is a supported state, never a red light."""
    body = client.get("/api/health", params={"probe": 1}).json()
    assert body["provider_reachable"] is None
    assert "deterministic" in body["provider_detail"].lower()


def test_the_probe_reports_a_broken_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CREWOPS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    body = client.get("/api/health", params={"probe": 1}).json()
    assert body["provider_reachable"] is False
    assert body["provider_detail"], "a failure with no explanation is the old bug"


def test_the_probe_never_returns_a_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-ant-api03-DoNotLeakThisValueAnywhereInAnyResponseBody0000"
    monkeypatch.delenv("CREWOPS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    raw = client.get("/api/health", params={"probe": 1}).text
    assert secret not in raw
    assert secret[12:] not in raw
