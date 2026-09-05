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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

__all__ = [
    "ANTHROPIC",
    "NAMES",
    "NONE",
    "OLLAMA",
    "OPENAI",
    "ProviderCheck",
    "ProviderReport",
    "ProviderSpec",
    "UnknownProviderError",
    "build",
    "diagnose",
    "explain_failure",
    "is_placeholder",
    "model_for",
    "preflight",
    "resolve",
    "selected_var",
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

    #: A different default model when a particular variable is what selected
    #: this provider. WHY THIS EXISTS: Ollama is selected by `OLLAMA_API_KEY`
    #: **or** `OLLAMA_HOST`, and its measured default is an Ollama Cloud model
    #: that needs the key. A teammate with a plain local daemon, or merely with
    #: `OLLAMA_HOST` exported by their shell, therefore selected Ollama and was
    #: handed a model their daemon had never heard of:
    #:
    #:   ResponseError: model 'deepseek-v4-flash:cloud' not found (404)
    #:
    #: A 404 the configuration asked for. Keyed by the variable rather than by
    #: a flag, because "which variable selected this" is exactly the question
    #: whose answer differs.
    model_by_var: dict[str, str] = field(default_factory=dict)

    def model_for(self, var: str | None) -> str:
        """The default model when `var` is what selected this provider."""
        if var is not None and var in self.model_by_var:
            return self.model_by_var[var]
        return self.default_model


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
        #   kimi-k2.6          5/16, eleven abstentions, p95 63.2s, past that
        #                      line outright
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
        # `OLLAMA_HOST` with no key is a LOCAL daemon, and every ":cloud"
        # model is a 404 there. A starting point rather than a considered
        # choice, exactly like the OpenAI default above: what a local install
        # has pulled is not knowable from here, so this only has to be a real
        # tool-calling model that somebody plausibly has. When it is wrong the
        # failure now says which model was tried and how to change it, which
        # is the part that was actually missing.
        model_by_var={"OLLAMA_HOST": "qwen3:8b"},
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


#: Values that are a template rather than a key. A `.env.example` copied into
#: place with `ANTHROPIC_API_KEY=your-key-here` still selects Anthropic, because
#: the string is not empty, and then every turn fails to authenticate while a
#: working `OLLAMA_API_KEY` sits behind it in the precedence order. The user has
#: a key, the system has a key, and the one it picked is a placeholder.
#:
#: Matched on the whole value, case insensitively, so a real key containing the
#: letters "todo" is unaffected.
_PLACEHOLDER_RE: Final = re.compile(
    r"^(?:"
    r"|none|null|nil|todo|tbd|changeme|change[-_ ]me|replace[-_ ]?me"
    r"|x+|\.+|sk-\.+|your[-_ ]?(?:api[-_ ]?)?key(?:[-_ ]?here)?"
    r"|<.*>|\{.*\}|\[.*\]"
    r"|(?:my|the|a)[-_ ]?(?:api[-_ ]?)?key"
    r"|paste[-_ ]?(?:your[-_ ]?)?key(?:[-_ ]?here)?"
    r")$",
    re.IGNORECASE,
)


def is_placeholder(value: str) -> bool:
    """Is this a template value rather than a credential?"""
    return bool(_PLACEHOLDER_RE.fullmatch(value.strip()))


def _live(candidate: ProviderSpec) -> str | None:
    """The first variable of this provider that carries a usable value."""
    for var in candidate.selects_on:
        value = os.environ.get(var, "").strip()
        if value and not is_placeholder(value):
            return var
    return None


@dataclass(frozen=True, slots=True)
class ProviderReport:
    """Why the system is in the mode it is in, in words a teammate can act on.

    Written because `/api/health` said `llm_configured: false` with
    `detail: null`, which is the truth and none of the explanation. A key is
    never included: this string is printed, logged and served over HTTP.
    """

    provider: str | None
    detail: str
    searched: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


def diagnose(root: object = None) -> ProviderReport:
    """Explain the current provider selection, naming nothing secret."""
    from crewops.env import search_paths

    searched = tuple(str(path) for path in search_paths(root))  # type: ignore[arg-type]
    found = tuple(s for s in searched if Path(s).is_file())

    skipped = tuple(
        var
        for candidate in _SPECS
        for var in candidate.selects_on
        if os.environ.get(var, "").strip() and is_placeholder(os.environ.get(var, ""))
    )

    explicit = os.environ.get("CREWOPS_LLM_PROVIDER", "").strip().lower()
    chosen = resolve()

    parts: list[str] = []
    if chosen is None:
        if explicit == NONE:
            parts.append(
                "CREWOPS_LLM_PROVIDER is set to 'none', so the deterministic "
                "path is being used on purpose."
            )
        else:
            parts.append(
                "No provider key is set, so answers come from the deterministic "
                "path. Set one of "
                + ", ".join(c.selects_on[0] for c in _SPECS)
                + " to turn the agent on."
            )
    else:
        var = _live(chosen) or chosen.selects_on[0]
        why = f"CREWOPS_LLM_PROVIDER={explicit}" if explicit else f"{var} is set"
        parts.append(f"Agent mode, provider {chosen.name}, because {why}.")

    if skipped:
        parts.append(
            "Ignored as a placeholder rather than a key: "
            + ", ".join(sorted(set(skipped)))
            + ". Replace the value or remove the line."
        )
    parts.append(
        ("Env files read: " + ", ".join(found))
        if found
        else "No .env or .env.local file was found in any of the searched paths."
    )
    return ProviderReport(
        provider=chosen.name if chosen else None,
        detail=" ".join(parts),
        searched=searched,
        skipped=tuple(sorted(set(skipped))),
    )


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
        if _live(candidate) is not None:
            return candidate
    return None


def selected_var() -> str | None:
    """Which environment variable selected the current provider, if any.

    `CREWOPS_LLM_PROVIDER` forces a provider without naming a variable, so the
    first of that provider's own variables that carries a usable value is
    reported instead. None means nothing is selected and the deterministic path
    is answering, which is a supported state rather than a failure.
    """
    chosen = resolve()
    if chosen is None:
        return None
    return _live(chosen)


def model_for(chosen: ProviderSpec | None = None) -> str:
    """The default model for the current selection.

    Split out of `AgentConfig.from_env` because the answer depends on HOW the
    provider was selected, not only on which one it is.
    """
    selected = chosen if chosen is not None else resolve()
    if selected is None:
        return spec(ANTHROPIC).default_model
    return selected.model_for(_live(selected))


#: What the vendor says, mapped to what the reader has to do about it. Ordered:
#: the first pattern that matches wins, so the specific shapes come first.
_FAILURE_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"model\s+'?\"?(?P<model>[\w.:\-/]+)'?\"?\s+not found", re.I), "model"),
    (re.compile(r"\b404\b|not found|does not exist|unknown model", re.I), "model"),
    (
        re.compile(
            r"connection refused|failed to connect|ECONNREFUSED|"
            r"connection error|max retries exceeded|name or service not known|"
            r"timed out|timeout",
            re.I,
        ),
        "reach",
    ),
    (
        re.compile(r"\b401\b|\b403\b|unauthor|invalid[\s_-]*(?:x-)?api[\s_-]*key|"
                   r"authentication|permission denied|credential", re.I),
        "auth",
    ),
    (re.compile(r"\b429\b|rate.?limit|quota|insufficient[_\s]quota", re.I), "limit"),
)

#: The last line of every explanation. The single most important thing a
#: teammate staring at a stack trace does not know is that the desk still
#: works: the deterministic path answers the same questions through the same
#: tools, the same rules engine and the same grounding check.
_STILL_WORKS: Final = (
    "The deterministic path is unaffected and still answers offline, so this "
    "costs you the prose and not the analysis."
)


def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "").strip() or "http://localhost:11434"


def explain_failure(raw: str, chosen: ProviderSpec | None = None) -> str:
    """Turn a provider's exception text into something to act on.

    "ResponseError: model 'deepseek-v4-flash:cloud' not found (status code:
    404)" is the vendor's sentence. It does not say which variable to change,
    which command to run, or that the offline path is still answering. Every
    branch here says all three, and no branch can print a key: only variable
    NAMES and the model id go into these strings.

    An unrecognised failure is passed through rather than dressed up. Inventing
    advice for an error nobody has read is worse than showing the error.
    """
    selected = chosen if chosen is not None else resolve()
    provider = selected.name if selected else NONE
    kind = next((k for pattern, k in _FAILURE_PATTERNS if pattern.search(raw)), None)

    if kind == "model":
        match = _FAILURE_PATTERNS[0][0].search(raw)
        model = (
            match.group("model")
            if match
            else os.environ.get("CREWOPS_MODEL", "").strip() or model_for(selected)
        )
        fix = "Set CREWOPS_MODEL to a model this provider actually serves."
        if provider == OLLAMA:
            fix = (
                f"Run `ollama pull {model}` to fetch it, or `ollama list` to see "
                "what you already have and set CREWOPS_MODEL to one of those. "
                "A model ending in ':cloud' is served by Ollama Cloud and needs "
                "OLLAMA_API_KEY, not a local daemon."
            )
        return f"The model {model!r} is not available on provider {provider}. {fix} {_STILL_WORKS}"

    if kind == "reach":
        where = _ollama_host() if provider == OLLAMA else f"the {provider} API"
        fix = (
            f"Nothing answered at {where}. Start it with `ollama serve`, point "
            "OLLAMA_HOST somewhere that is running, or use a hosted key "
            "(ANTHROPIC_API_KEY) instead."
            if provider == OLLAMA
            else f"Could not reach {where}. Check the network and try again."
        )
        return f"{fix} {_STILL_WORKS}"

    if kind == "auth":
        var = selected.selects_on[0] if selected else "the provider key"
        return (
            f"{var} was rejected by {provider}. Replace the value with a live "
            f"key, or remove the line to fall back to the offline path. {_STILL_WORKS}"
        )

    if kind == "limit":
        return (
            f"{provider} rate limited or refused the request on quota. Wait and "
            f"retry, or switch providers with CREWOPS_LLM_PROVIDER. {_STILL_WORKS}"
        )

    return f"{raw} {_STILL_WORKS}"


@dataclass(frozen=True, slots=True)
class ProviderCheck:
    """The result of actually calling the provider.

    `ok` is tri-state on purpose. True means a real round trip succeeded, False
    means one failed, and **None means no provider is configured**, which is a
    supported state and must never be reported as a failure.
    """

    ok: bool | None
    provider: str | None
    model: str | None
    detail: str


def preflight(timeout_s: float = 10.0) -> ProviderCheck:
    """One cheap round trip to the configured provider. Never raises.

    `crewops health` reported "Provider: ollama, Mode: agent, Model:
    deepseek-v4-flash:cloud" in green to two teammates whose every turn was
    404ing, because it printed what was CONFIGURED and never touched the
    provider. A green light in front of a broken turn is worse than a red one.

    Not called on the request path. Selection stays presence-based and
    instantaneous there, exactly as `llm_configured` documents; this is for the
    human asking why.
    """
    selected = resolve()
    if selected is None:
        return ProviderCheck(
            ok=None,
            provider=None,
            model=None,
            detail="No provider configured. The deterministic path is answering.",
        )

    model = os.environ.get("CREWOPS_MODEL", "").strip() or model_for(selected)
    try:
        # No `.bind(timeout=...)`. It returns a RunnableBinding that passes
        # the kwarg through to a client that may not take one, and the
        # TypeError that comes back reads exactly like a dead provider: the
        # first version of this check reported a working local daemon as
        # unreachable. `timeout_s` is advisory and left to the client.
        client = build(selected, model=model, max_tokens=16)
        client.invoke("ping")
    except Exception as exc:
        return ProviderCheck(
            ok=False,
            provider=selected.name,
            model=model,
            detail=explain_failure(f"{type(exc).__name__}: {exc}", selected),
        )
    return ProviderCheck(
        ok=True,
        provider=selected.name,
        model=model,
        detail=f"{selected.name} answered on {model}.",
    )


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
