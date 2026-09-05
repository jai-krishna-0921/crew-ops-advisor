"""Selected, configured, and 404 on every turn.

Two reports from teammates, one root cause between them:

    ResponseError: model 'deepseek-v4-flash:cloud' not found (status code: 404)
    ConnectionError: [Errno 111] Connection refused

`crewops health` said "Provider: ollama, Mode: agent, Model:
deepseek-v4-flash:cloud" for both of them, in green, because it reports what is
CONFIGURED and never touches the provider. A green light in front of a broken
turn is worse than a red one.

THE CONFIGURATION CONTRADICTS ITSELF. Ollama is selected by `OLLAMA_API_KEY`
**or** `OLLAMA_HOST`, and the default model is `deepseek-v4-flash:cloud`, which
is an Ollama Cloud model and needs the key. So a teammate with a plain local
Ollama, or merely with `OLLAMA_HOST` exported by their shell, selects Ollama
and is then handed a model their daemon has never heard of. That is a 404 the
system asked for.

`OLLAMA_HOST` without a key means a local daemon, so the default model has to
be one a local daemon could plausibly have. It is a starting point and not a
measured choice, exactly like the OpenAI default: what a local install has
pulled is not knowable from here, which is why the failure has to say so.

AND THE FAILURE HAS TO BE READABLE. "ResponseError ... 404" is the vendor's
sentence, not ours. It does not say which variable to change, which command to
run, or that the deterministic path is still answering. Every message here says
all three, and none of them can print a key.
"""

from __future__ import annotations

import pytest

from crewops.agent import providers

REAL = "sk-ant-api03-Zx9f2Lq7Rn4vWbT1yUoP8kEjHgFdSaCwMvBnXzQrTyUiOpAsDfGhJkL"
OLLAMA_KEY = "6f2a91c4d8e34b7fa1c05e9d7b2364aa.PqR7sT1uV9wX3yZ0"


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_API_KEY",
        "OLLAMA_HOST",
        "CREWOPS_LLM_PROVIDER",
        "CREWOPS_MODEL",
        "CREWOPS_PLAN_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


# ------------------------------------------------- the model must match the host


def test_a_local_ollama_is_not_handed_a_cloud_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole bug, in one assertion."""
    from crewops.agent.config import AgentConfig

    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    model = AgentConfig.from_env().model
    assert not model.endswith(":cloud"), (
        f"OLLAMA_HOST selected Ollama with no key and the default model is {model!r}, "
        "which is an Ollama Cloud model"
    )


def test_a_keyed_ollama_still_gets_the_measured_cloud_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crewops.agent.config import AgentConfig

    monkeypatch.setenv("OLLAMA_API_KEY", OLLAMA_KEY)
    assert AgentConfig.from_env().model == "deepseek-v4-flash:cloud"


def test_a_key_beside_a_host_still_means_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both set is the author's own machine: the key wins, so does its model."""
    from crewops.agent.config import AgentConfig

    monkeypatch.setenv("OLLAMA_API_KEY", OLLAMA_KEY)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert AgentConfig.from_env().model == "deepseek-v4-flash:cloud"


def test_an_explicit_model_always_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    from crewops.agent.config import AgentConfig

    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("CREWOPS_MODEL", "llama3.1:8b")
    assert AgentConfig.from_env().model == "llama3.1:8b"


def test_the_other_providers_are_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    from crewops.agent.config import AgentConfig

    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL)
    assert AgentConfig.from_env().model == "claude-sonnet-5"


# ------------------------------------------------------- the failure, in words

MODEL_404 = "ResponseError: model 'deepseek-v4-flash:cloud' not found (status code: 404)"
REFUSED = "ConnectionError: [Errno 111] Connection refused"
UNAUTHORISED = "AuthenticationError: invalid x-api-key (status code: 401)"


def test_a_missing_model_says_which_model_and_what_to_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    advice = providers.explain_failure(MODEL_404)
    assert "deepseek-v4-flash:cloud" in advice
    assert "CREWOPS_MODEL" in advice
    assert "ollama pull" in advice


def test_a_refused_connection_says_where_it_tried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    advice = providers.explain_failure(REFUSED)
    assert "http://localhost:11434" in advice
    assert "ollama serve" in advice


def test_a_rejected_key_says_so_without_printing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", REAL)
    advice = providers.explain_failure(UNAUTHORISED)
    assert "ANTHROPIC_API_KEY" in advice
    assert REAL not in advice
    assert REAL[10:] not in advice


def test_every_failure_says_the_offline_path_still_answers() -> None:
    for raw in (MODEL_404, REFUSED, UNAUTHORISED):
        assert "deterministic" in providers.explain_failure(raw).lower(), raw


def test_an_unrecognised_failure_is_passed_through_not_invented() -> None:
    advice = providers.explain_failure("TypeError: something we have never seen")
    assert "something we have never seen" in advice


# --------------------------------------------------------------- the live check


def test_preflight_is_skipped_with_no_provider() -> None:
    check = providers.preflight()
    assert check.ok is None, "offline is not a failure and must not be reported as one"


def test_preflight_reports_a_failure_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """A health check that raises is a health check nobody runs twice."""
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    check = providers.preflight(timeout_s=2.0)
    assert check.ok is False
    assert check.detail
    assert "127.0.0.1:1" in check.detail or "ollama serve" in check.detail


# --------------------------------------------- the message a broken turn shows

"""What a failed turn says to the person reading it.

    "I cannot answer that reliably. The turn failed before it could be
     checked: ResponseError: model 'deepseek-v4-flash:cloud' not found
     (status code: 404)"

Correct and useless. It is the vendor's sentence wrapped in ours, and the
reader still has to know that `:cloud` means Ollama Cloud, that Ollama Cloud
needs a key, and which variable carries it.
"""

import datetime as dt  # noqa: E402

from crewops.agent.runner import AgentRunner  # noqa: E402
from crewops.contracts import AbstentionReason  # noqa: E402


def _reply_for(error: str):
    runner = AgentRunner.__new__(AgentRunner)
    return runner._assemble(
        {},
        question="Who is on reserve at BLR?",
        thread="t-fail",
        turn="u-1",
        asked_at=dt.datetime(2026, 9, 14, 18, 0, 0),
        started=0.0,
        error=error,
    )


def test_a_failed_turn_explains_the_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    reply = _reply_for(MODEL_404)
    assert reply.abstention is not None
    message = reply.abstention.message
    assert "ollama pull" in message, message
    assert "CREWOPS_MODEL" in message, message


def test_a_failed_turn_still_says_it_could_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    reply = _reply_for(REFUSED)
    assert reply.abstention is not None
    assert reply.abstention.reason is AbstentionReason.TOOL_ERROR
    assert "cannot answer" in reply.abstention.message.lower()


def test_a_failed_turn_offers_the_offline_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    reply = _reply_for(REFUSED)
    assert reply.abstention is not None
    assert any("offline" in s for s in reply.abstention.suggestions)
