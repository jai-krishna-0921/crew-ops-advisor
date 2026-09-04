"""The one module that knows which vendor is behind the model.

The graph is written against `BaseChatModel` and names no vendor anywhere. That
is what lets the same eight nodes, the same guards and the same verifier run
against Claude, against GPT, against a model served by Ollama, or against the
scripted fake in the test suite. The cost of that neutrality is that every
provider quirk has to live somewhere, and this is the somewhere.

Three quirks are handled here, and they are the reason this is a module rather
than a dict:

1. **The default model id follows the provider.** Sending `claude-sonnet-5` to
   Ollama is a 404 on the first turn, not a graceful degradation.
2. **Sampling has to be pinned per vendor.** Anthropic's current models reject
   sampling parameters outright, so that path omits them. Ollama defaults to
   temperature 0.8, which would make the same question answer differently on
   consecutive asks. A decision aid does not sample.
3. **Structured output has no portable method.** `with_structured_output` picks
   a strategy per provider, and Ollama's default (`json_schema`) is ignored by
   the tool-capable models here: they return prose and the parse fails. The
   working method is `function_calling`, and the planner node must not have to
   know that.

Selection is by environment and is deliberately cheap. `llm_configured()` is
called by `Advisor.mode` and by the server on every request, so detection may
never touch the network: an HTTP probe there would put a round trip on the
latency budget of every turn.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Final, Literal

__all__ = [
    "ANTHROPIC",
    "NAMES",
    "NONE",
    "OLLAMA",
    "OPENAI",
    "ProviderSpec",
    "UnknownProviderError",
    "build",
    "resolve",
    "spec",
    "structured_output_method",
]

ANTHROPIC: Final = "anthropic"
OPENAI: Final = "openai"
OLLAMA: Final = "ollama"

#: An explicit opt out. Useful for proving the deterministic path still stands
#: on a machine that does have a key configured.
NONE: Final = "none"


class UnknownProviderError(ValueError):
    """`CREWOPS_LLM_PROVIDER` names something that is not wired up.

    Raised rather than ignored on purpose. A typo that silently fell back to
    the deterministic path would look exactly like a passing offline run, and
    the person who set the variable would never learn their key was unused.
    """


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Everything that differs between one vendor and the next."""

    name: str

    #: Used when `CREWOPS_MODEL` is not set. Must be a model that supports tool
    #: calling: the agent node binds 24 tools and a model that cannot call them
    #: produces an answer with no evidence, which the guards then reject.
    default_model: str

    #: Environment variables whose presence selects this provider, in order of
    #: preference. Presence alone is the signal, never a live check.
    selects_on: tuple[str, ...]

    #: How `with_structured_output` should be asked to work for this vendor.
    #: None means take the LangChain default.
    structured_method: str | None = None


#: Order is precedence, and the ordering is the migration path. Ollama carries
#: the system while no hosted key exists; dropping in ANTHROPIC_API_KEY later
#: switches everything over with no config edit and nothing to remember to
#: unset. That is why the hosted providers are listed first.
_SPECS: Final[tuple[ProviderSpec, ...]] = (
    ProviderSpec(
        name=ANTHROPIC,
        default_model="claude-sonnet-5",
        selects_on=("ANTHROPIC_API_KEY",),
    ),
    ProviderSpec(
        name=OPENAI,
        # A starting point, not a considered choice: set CREWOPS_MODEL. Any
        # current tool-calling OpenAI model works, and this default is the one
        # thing here that goes stale on its own.
        default_model="gpt-4.1",
        selects_on=("OPENAI_API_KEY",),
    ),
    ProviderSpec(
        name=OLLAMA,
        # Routed through the local daemon to Ollama's cloud. Chosen by
        # measurement over four candidates, scored on Tier 1 against the
        # shipped answer keys:
        #
        #   deepseek-v4-flash  16/16, 15/16, 16/16 correct over three runs,
        #                      zero wrong, 16/16 grounded, p95 12.1s
        #   gpt-oss:120b       13/16, one wrong answer, p95 10.0s
        #   glm-5.1            13/16, three abstentions, p95 27.4s, which is
        #                      close enough to the "45s is not a decision aid"
        #                      line in the problem statement to matter
        #   qwen2.5:7b         unusable: returns an empty `tool_calls` list for
        #                      a bound schema, so the agent loop has nothing to
        #                      execute
        #
        # deepseek is the only configuration measured so far that beats the
        # deterministic path on Tier 1 (16 against 15) and it has never
        # produced a wrong answer in 48 graded questions.
        default_model="deepseek-v4-flash:cloud",
        selects_on=("OLLAMA_API_KEY", "OLLAMA_HOST"),
        structured_method="function_calling",
    ),
)

_BY_NAME: Final[dict[str, ProviderSpec]] = {s.name: s for s in _SPECS}

#: Every provider that can be selected, in precedence order.
NAMES: Final[tuple[str, ...]] = tuple(_BY_NAME)


def spec(name: str) -> ProviderSpec:
    """The spec for a provider name, or `UnknownProviderError`."""
    try:
        return _BY_NAME[name]
    except KeyError:
        raise UnknownProviderError(
            f"{name!r} is not a provider this system knows. "
            f"Set CREWOPS_LLM_PROVIDER to one of {', '.join(NAMES)}, "
            f"or {NONE!r} to force the deterministic path."
        ) from None


def structured_output_method(name: str) -> str | None:
    """How this provider should be asked for structured output."""
    return spec(name).structured_method


def resolve() -> ProviderSpec | None:
    """The provider this environment selects, or None for the offline path.

    None is a supported outcome, not a failure. Without a provider the
    deterministic core, the rules engine, the simulations and the ranked
    options all still work: the model adds language, not truth.
    """
    explicit = os.environ.get("CREWOPS_LLM_PROVIDER", "").strip().lower()
    if explicit:
        if explicit == NONE:
            return None
        return spec(explicit)

    for candidate in _SPECS:
        if any(os.environ.get(var, "").strip() for var in candidate.selects_on):
            return candidate
    return None


def missing_env() -> list[str]:
    """What to set to turn the agent on. Reported by the no-model abstention."""
    return [candidate.selects_on[0] for candidate in _SPECS]


def build(provider: ProviderSpec, *, model: str, max_tokens: int) -> Any:
    """Construct the chat client for one provider.

    Every branch is an import inside the function. The clients are heavy, and
    importing all three at module scope would make `crewops.agent` slow to
    import for a run that ends up using none of them.

    The `noqa: TID251` markers are the banned-api rule from `pyproject.toml`
    doing its job: a model client may be imported from agent code and nowhere
    else. This function is the whole of "nowhere else".
    """
    if provider.name == ANTHROPIC:
        from langchain_anthropic import ChatAnthropic  # noqa: TID251

        # Note the absence of `temperature`. Claude Sonnet 5 rejects sampling
        # parameters outright, and a decision aid has no business sampling.
        return ChatAnthropic(model=model, max_tokens=max_tokens)  # type: ignore[call-arg]

    if provider.name == OPENAI:
        from langchain_openai import ChatOpenAI  # noqa: TID251

        return ChatOpenAI(model=model, max_tokens=max_tokens, temperature=0)  # type: ignore[call-arg]

    if provider.name == OLLAMA:
        return _build_ollama(model=model, max_tokens=max_tokens)

    raise UnknownProviderError(f"No client is wired up for {provider.name!r}.")


def _build_ollama(*, model: str, max_tokens: int) -> Any:
    from langchain_ollama import ChatOllama  # noqa: TID251

    class _Chat(ChatOllama):
        """ChatOllama with the structured-output method that actually binds.

        The planner node calls `with_structured_output(TurnPlan)` with no
        method, because the graph is not allowed to know which vendor it is
        talking to. Under Ollama's default (`json_schema`) the tool-capable
        models here ignore the schema and answer in prose, and the turn dies on
        an OutputParserException. Overriding the default here keeps the quirk
        on the provider side of the boundary.

        The planner already degrades gracefully if this fails (`graph.py` wraps
        the call and falls back to a generic plan), so the cost of getting this
        wrong is a worse plan rather than a broken turn. It is still worth
        getting right: the plan is what the controller sees first.
        """

        def with_structured_output(
            self,
            schema: Any,
            *,
            method: Literal["function_calling", "json_mode", "json_schema"] = "function_calling",
            **kwargs: Any,
        ) -> Any:
            return super().with_structured_output(schema, method=method, **kwargs)

    return _Chat(
        model=model,
        # Ollama's own default is 0.8. Two identical questions must not get two
        # different answers on a crew control desk.
        temperature=0,
        # Ollama's name for max_tokens.
        num_predict=max_tokens,
        # Construction must not require the daemon to be up. The server and the
        # eval harness both build a model at start up, and a laptop with Ollama
        # stopped should fall back to the deterministic path rather than fail
        # to boot.
        validate_model_on_init=False,
    )
