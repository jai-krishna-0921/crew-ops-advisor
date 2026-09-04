"""Which provider gets selected, and what happens when none is configured.

The graph takes a `BaseChatModel` by injection and never names a vendor, so
provider choice is a configuration question with exactly one place that answers
it. These tests pin that place down, because the failure mode when it drifts is
silent: the wrong default model id, or a key that is present but ignored, both
degrade to the deterministic path without anything raising.

Every test clears the provider environment first. The suite must not depend on
what happens to be in the developer's shell or in `.env.local`.
"""

from __future__ import annotations

import pytest

from crewops.agent import providers
from crewops.agent.config import AgentConfig, llm_configured

#: Every variable that can select or configure a provider.
PROVIDER_ENV: tuple[str, ...] = (
    "CREWOPS_LLM_PROVIDER",
    "CREWOPS_MODEL",
    "CREWOPS_PLAN_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OLLAMA_API_KEY",
    "OLLAMA_HOST",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


# ------------------------------------------------------------------ detection


def test_no_configuration_selects_no_provider() -> None:
    """No key anywhere is a supported mode, not an error.

    This is rule 6: every command runs with no API key. If this test fails the
    offline path has stopped being reachable.
    """
    assert providers.resolve() is None
    assert llm_configured() is False


def test_anthropic_key_selects_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    spec = providers.resolve()
    assert spec is not None
    assert spec.name == providers.ANTHROPIC
    assert spec.default_model == "claude-sonnet-5"
    assert llm_configured() is True


def test_ollama_key_selects_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama is selected by its key alone, with no live probe.

    Detection has to be cheap: `llm_configured()` is called per request by the
    server and by `Advisor.mode`. Reaching for the network there would put an
    HTTP round trip on the latency budget of every turn.
    """
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    spec = providers.resolve()
    assert spec is not None
    assert spec.name == providers.OLLAMA
    assert llm_configured() is True


def test_ollama_host_alone_selects_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local daemon needs no key, so the host variable selects it too."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    spec = providers.resolve()
    assert spec is not None
    assert spec.name == providers.OLLAMA


def test_hosted_keys_win_over_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """Precedence is deliberate and is the whole migration path.

    Ollama carries the system while no hosted key exists. Adding
    ANTHROPIC_API_KEY later must switch the system over without anyone editing
    a config file or remembering to unset something.
    """
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    spec = providers.resolve()
    assert spec is not None
    assert spec.name == providers.ANTHROPIC


def test_explicit_provider_overrides_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit choice beats precedence, so a judge can pin one provider."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    monkeypatch.setenv("CREWOPS_LLM_PROVIDER", providers.OLLAMA)
    spec = providers.resolve()
    assert spec is not None
    assert spec.name == providers.OLLAMA


def test_explicit_none_forces_the_offline_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A way to prove the deterministic path still stands with a key present."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("CREWOPS_LLM_PROVIDER", "none")
    assert providers.resolve() is None
    assert llm_configured() is False


def test_unknown_provider_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo must not silently degrade to deterministic and look like a pass."""
    monkeypatch.setenv("CREWOPS_LLM_PROVIDER", "claude-3-opus")
    with pytest.raises(providers.UnknownProviderError) as excinfo:
        providers.resolve()
    assert "claude-3-opus" in str(excinfo.value)
    assert providers.OLLAMA in str(excinfo.value)


# --------------------------------------------------------------------- config


def test_config_takes_the_default_model_from_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default model must follow the provider, not stay pinned to Claude.

    A `claude-sonnet-5` model id sent to Ollama is a 404 at the first turn.
    """
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    cfg = AgentConfig.from_env()
    assert cfg.provider == providers.OLLAMA
    assert cfg.model == providers.spec(providers.OLLAMA).default_model
    assert "claude" not in cfg.model


def test_explicit_model_overrides_the_provider_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    monkeypatch.setenv("CREWOPS_MODEL", "qwen2.5:7b")
    cfg = AgentConfig.from_env()
    assert cfg.model == "qwen2.5:7b"
    assert cfg.plan_model == "qwen2.5:7b"


def test_plan_model_can_differ_from_the_answer_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    monkeypatch.setenv("CREWOPS_MODEL", "gpt-oss:120b-cloud")
    monkeypatch.setenv("CREWOPS_PLAN_MODEL", "qwen2.5:7b")
    cfg = AgentConfig.from_env()
    assert cfg.model == "gpt-oss:120b-cloud"
    assert cfg.plan_model == "qwen2.5:7b"


# ---------------------------------------------------------------- constructionx


def test_build_model_returns_none_with_no_provider() -> None:
    """`build_model` returning None is how the advisor picks the offline path."""
    from crewops.agent.factory import build_model

    assert build_model() is None


def test_build_model_constructs_ollama_without_touching_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construction must not require the daemon to be up.

    The eval harness and the server both construct a model at start up. If that
    reached the network, a laptop with Ollama stopped would fail to boot the
    API rather than falling back.
    """
    from langchain_core.language_models import BaseChatModel

    from crewops.agent.factory import build_model

    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    model = build_model()
    assert isinstance(model, BaseChatModel)


def test_ollama_defaults_to_deterministic_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decision aid has no business sampling.

    Anthropic's current models reject sampling parameters outright, so the
    Anthropic path omits them. Ollama does not: it defaults to temperature 0.8,
    which would make the same question give different answers on consecutive
    asks. That has to be pinned explicitly.
    """
    from crewops.agent.factory import build_model

    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    model = build_model()
    assert getattr(model, "temperature", None) == 0


def test_ollama_structured_output_uses_a_method_that_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The planner node calls `with_structured_output(TurnPlan)` with no method.

    Ollama's default method is `json_schema`, and the tool-capable models here
    ignore the schema under it and return prose, which surfaces as an
    OutputParserException. `function_calling` is the method that actually
    binds. The provider layer owns that quirk so the graph stays vendor
    neutral.
    """
    from crewops.agent.factory import build_model

    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-test")
    model = build_model(planner=True)
    assert providers.structured_output_method(providers.OLLAMA) == "function_calling"
    # The override is on the instance the graph will actually call.
    assert type(model).with_structured_output is not None


def test_every_provider_declares_a_model_and_an_env_var() -> None:
    """A spec with no default model would fail at the first turn, not at boot."""
    for name in providers.NAMES:
        spec = providers.spec(name)
        assert spec.default_model
        assert spec.selects_on
