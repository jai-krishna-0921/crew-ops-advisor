"""The LangGraph agent.

    START -> route -+-> plan -> agent <-> tools      loop while the model calls tools
                    |            |
                    |            v
                    |          verify -+-> repair -> agent   one correction pass
                    |                  |
                    |                  +-> abstain -> END
                    |                  |
                    |                  +-> END
                    |
                    +-> abstain -> END               out of scope, before any spend

Why each node exists:

`route`   Deterministic triage. Costs nothing and can refuse a question that is
          plainly outside crew operations before a single token is spent. It
          refuses only when confident; anything ambiguous goes forward, because
          a wrong refusal here is unrecoverable while a wrong forward is caught
          downstream.

`plan`    One model call, no tools bound, structured output. The controller
          watches the system decide before it acts, which is the single most
          trust building moment in the turn. It is a product feature.

`agent`   The tool calling loop. The model chooses tools and arguments, and
          eventually writes prose.

`tools`   Executes against the injected `ToolSurface`. Every envelope lands in
          typed state so the verifier sees the complete fact set for the turn,
          not a summary of it.

`verify`  Structural guards first, then the grounding check. The guards ask
          whether the answer was entitled to exist; the check asks whether its
          figures are real. Both are deterministic.

`repair`  Exactly one correction pass, told precisely what was unattested.

`abstain` Builds a refusal a controller can act on.

The graph takes a `ToolSurface` and a model by constructor injection and never
imports a concrete implementation of either. Swapping the fake for the real
core is a one line change in `factory.py`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, Literal, cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from crewops.agent import providers
from crewops.agent.compact import compacts, model_view
from crewops.agent.config import AgentConfig
from crewops.agent.events import emit
from crewops.agent.guards import GuardFailure, run_guards, strip_em_dashes
from crewops.agent.prompts import (
    PLAN_SYSTEM_PROMPT,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    answer_kickoff,
    plan_user_prompt,
    policy_repair_prompt,
    repair_prompt,
)
from crewops.agent.state import TurnState
from crewops.agent.toolspecs import TOOL_SPECS, call_tool
from crewops.contracts import (
    Abstention,
    AbstentionReason,
    ToolEnvelope,
    VerificationReport,
    VerificationStatus,
)
from crewops.resolve.completeness import unmodelled_constraints
from crewops.resolve.intents import match_intent
from crewops.resolve.triage import reads_as_followup, triage_question
from crewops.verify import Verifier

__all__ = ["TurnPlan", "bind_tool_specs", "build_graph", "subjectless_ask"]

#: How much of a tool payload is handed back to the model, when the payload is
#: a shape nothing knows how to compact. The full envelope always reaches the
#: verifier and the HTTP layer; this cap only protects the prompt budget, and
#: `truncated` records that it fired.
_PAYLOAD_CHAR_BUDGET: Final = 6_000

#: The allowance for a COMPACTED payload, and larger than the raw cap on
#: purpose. `find_cover_options` with its rejects is 223,156 characters and
#: `agent/compact.py` takes it to about 11,000 by dropping the per-rule per-day
#: arithmetic the interface already draws and the prose is forbidden to
#: restate. What is left is identity, verdict, price and reason for every
#: option, complete. Truncated content is a JSON string that stops mid-object;
#: compacted content is all signal, so it is worth more room.
_COMPACT_CHAR_BUDGET: Final = 16_000


class TurnPlan(BaseModel):
    """The planner's structured output. Rendered as the `plan` stream event."""

    intent: str = Field(description="One line: what you are about to establish")
    tier: Literal[1, 2, 3] = Field(description="1 lookup, 2 consequence, 3 recommendation")
    steps: list[str] = Field(
        default_factory=list,
        description=(
            "One to five concrete steps, each naming a tool and its subject. "
            "One step is correct when one call answers the question"
        ),
    )


def bind_tool_specs() -> list[StructuredTool]:
    """The seventeen tools as bindable schemas.

    The callables never run. `tools_node` dispatches onto the injected
    `ToolSurface` itself so it can time each call, coerce arguments, accumulate
    envelopes into typed state and emit progress events. `ToolNode` would
    execute them for us but would leave the envelopes only inside message
    artifacts, which is the wrong place for the verifier to have to look.
    """

    def _unreachable(**_kwargs: Any) -> str:
        raise RuntimeError("Tool execution is owned by the graph's tools node")

    return [
        StructuredTool.from_function(
            func=_unreachable,
            name=spec.name,
            description=spec.description,
            args_schema=spec.args_model,
        )
        for spec in TOOL_SPECS
    ]


def _elapsed_ms(state: TurnState) -> int:
    started = state.get("started_at") or time.monotonic()
    return int((time.monotonic() - started) * 1000)


def _over_budget(state: TurnState, config: AgentConfig) -> bool:
    return _elapsed_ms(state) > config.turn_budget_ms


def _summarise_payload(envelope: ToolEnvelope) -> str:
    """One line for the UI chip. Never the place a number first appears."""
    if not envelope.ok:
        return f"failed: {envelope.error or 'no detail'}"
    payload = envelope.payload
    if payload is None:
        return f"{len(envelope.facts)} facts"
    if isinstance(payload, list):
        return f"{len(payload)} rows, {len(envelope.facts)} facts"
    if hasattr(payload, "__class__"):
        return f"{payload.__class__.__name__}, {len(envelope.facts)} facts"
    return f"{len(envelope.facts)} facts"


#: Requirements that name WHAT THE ANSWER IS ABOUT, as opposed to how it is
#: narrowed. A cover search with no target and a callout with no duty are not
#: underspecified questions, they are questions with no subject.
_SUBJECT_REQUIREMENTS: Final = frozenset({"cover_target", "assignment"})


def subjectless_ask(question: str, *, has_history: bool) -> str | None:
    """The hint to refuse with when a recommendation is about nothing.

    Asked cold, "What are my options, cheapest first?" was answered: the model
    found a gap in the week, reported on C-5417's seat on P-2213, and every
    figure in it was real. A true answer to a question nobody asked, and a
    controller reading that first line acts on a seat they were not asking
    about. The offline path already refuses it, because `cover_options`
    declares the target it needs.

    Deliberately narrow. All three have to hold: the shape needs a subject, the
    question names no identifier at all, and the thread has nothing behind it.
    A wrong refusal here is unrecoverable and a wrong forward is caught
    downstream, so anything short of all three goes to the model.
    """
    if has_history:
        return None
    from crewops.resolve.triage import canonical_question, extract_entities

    asked = canonical_question(question)
    entities = extract_entities(asked)
    if entities.any_identifier():
        return None
    intent = match_intent(asked, entities)
    if intent is None:
        return None
    if not _SUBJECT_REQUIREMENTS.intersection(intent.requires):
        return None
    if not intent.missing(entities):
        return None
    return (
        intent.missing_hint
        or "Name the pairing, the flight or the crew whose seat is open."
    )


def _prefetch_plan(question: str, snapshot: datetime) -> list[Any]:
    """The offline resolver's tool plan for this question, or nothing.

    Nothing is returned unless the resolver both recognises the shape and has
    every argument it needs, because a plan the resolver would have refused to
    run is a plan whose results would answer a different question. That is the
    same gate `resolve/completeness.py` applies, for the same reason.
    """
    intent = match_intent(question)
    if intent is None:
        return []
    from crewops.resolve.triage import extract_entities

    entities = extract_entities(question)
    if intent.missing(entities):
        return []
    try:
        plan = intent.build(entities, snapshot)
    except (IndexError, KeyError, ValueError):
        # A build that raises is a shape mismatch, not an error worth failing
        # the turn over. The agent's own loop still runs.
        return []
    if unmodelled_constraints(question, plan):
        return []
    return list(plan)


def _tool_message_content(envelope: ToolEnvelope) -> tuple[str, bool]:
    """What the model sees from a tool call, and whether it was truncated.

    Facts come first and are never truncated: they are the values the model is
    allowed to quote, so losing one to a budget would push the model towards
    inventing it.
    """
    if not envelope.ok:
        return (
            json.dumps(
                {
                    "ok": False,
                    "error": envelope.error or "the lookup failed",
                    "note": (
                        "A failed lookup is not a negative finding. Do not report "
                        "this as 'none found'."
                    ),
                }
            ),
            False,
        )

    facts = [
        {
            "key": fact.key,
            "label": fact.label,
            "value": fact.value,
            "unit": fact.unit,
            "derivation": fact.derivation,
        }
        for fact in envelope.facts
    ]
    trace = [{"label": step.label, "detail": step.detail} for step in envelope.trace]

    payload_json: Any
    truncated = False
    try:
        # COMPACT FIRST, CUT ONLY AS A LAST RESORT. The raw cover search is
        # 223,156 characters against a 6,000 budget, so the model used to be
        # handed rank 1, half of rank 2 and "...[truncated]" and asked to write
        # about six options. `model_view` drops the per-rule per-day arithmetic
        # that the interface draws and the prose is forbidden to restate, and
        # keeps every option's identity, verdict, price and reason. Complete,
        # and about 11,000 characters.
        payload_json = model_view(envelope.payload)
        rendered = json.dumps(payload_json, default=str)
        budget = (
            _COMPACT_CHAR_BUDGET if compacts(envelope.payload) else _PAYLOAD_CHAR_BUDGET
        )
        if len(rendered) > budget:
            payload_json = rendered[:budget] + "...[truncated]"
            truncated = True
    except (TypeError, ValueError):
        payload_json = str(envelope.payload)[:_PAYLOAD_CHAR_BUDGET]
        truncated = True

    return (
        json.dumps(
            {"ok": True, "facts": facts, "trace": trace, "payload": payload_json},
            default=str,
        ),
        truncated,
    )


def repeat_key(tool: str, args: Mapping[str, Any] | None) -> str:
    """Identity of a tool call, for spotting one asked twice in a turn.

    Key order is not a difference, and neither is an argument present as None
    against one left out: `exclude_none` on one call and not the other is a
    serialisation detail, not a different question.

    Never raises. Suppression is an optimisation, so an argument that will not
    serialise degrades to "not a repeat" rather than losing the turn.
    """
    cleaned = {k: v for k, v in (args or {}).items() if v is not None}
    try:
        return f"{tool}:{json.dumps(cleaned, sort_keys=True, default=str)}"
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return f"{tool}:{sorted(map(str, cleaned.items()))}"


def build_graph(
    *,
    tools: object,
    model: BaseChatModel | None,
    plan_model: BaseChatModel | None = None,
    config: AgentConfig | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    verifier: Verifier | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile the turn graph.

    `tools` is anything satisfying `crewops.contracts.ToolSurface`. `model` is
    any `BaseChatModel`. Neither is imported concretely anywhere in this
    package, which is what lets the whole graph run against a fake.
    """
    cfg = config or AgentConfig()
    guard = verifier or Verifier()
    planner = plan_model or model
    bound = model.bind_tools(bind_tool_specs()) if model is not None else None

    # ------------------------------------------------------------------ route

    def route_node(state: TurnState) -> dict[str, Any]:
        """Deterministic triage. No model call, no tool call, no spend."""
        verdict = triage_question(state["question"])

        # A FOLLOW-UP IS NOT AN OPENING LINE. "And what about the next day?"
        # names no crew, pairing, flight, station or rule, so triage declined
        # it before the graph reached the history that would have resolved it.
        # The checkpointer has that history in `messages`; the model reads it
        # and answers, as it already does for "which of them are captains".
        # With nothing behind it on this thread, the refusal stands.
        history = bool(state.get("messages"))
        continues = history and reads_as_followup(state["question"])
        no_subject = subjectless_ask(state["question"], has_history=history)
        in_scope = (verdict.in_scope or continues) and no_subject is None
        update: dict[str, Any] = {
            "in_scope": in_scope,
            "tier": verdict.tier,
            "triage_reason": (
                "Continues the previous turn on this thread."
                if continues and not verdict.in_scope
                else verdict.reason
            ),
        }
        if not in_scope:
            # A greeting is answered, not refused. Nothing is missing: the
            # controller has not asked for anything yet. Same treatment as the
            # offline resolver, so both paths greet identically.
            if no_subject is not None:
                update["abstention"] = Abstention(
                    reason=AbstentionReason.UNDERSPECIFIED,
                    message=(
                        "I cannot answer that reliably. That asks for a "
                        "recommendation without saying what it is about. "
                        + no_subject
                    ),
                    missing=[no_subject],
                    did_establish=[],
                    suggestions=_scope_suggestions(),
                )
                return update
            greeting = verdict.abstention_reason is AbstentionReason.GREETING
            update["abstention"] = Abstention(
                reason=verdict.abstention_reason or AbstentionReason.OUT_OF_SCOPE,
                message=(
                    verdict.reason
                    if greeting
                    else "I cannot answer that reliably. " + verdict.reason
                ),
                missing=[] if greeting else list(verdict.missing) or [verdict.reason],
                did_establish=[],
                suggestions=_scope_suggestions(),
            )
        return update

    def route_edge(state: TurnState) -> Literal["plan", "abstain"]:
        return "plan" if state.get("in_scope", True) else "abstain"

    # ------------------------------------------------------------------- plan

    def plan_node(state: TurnState) -> dict[str, Any]:
        started = time.monotonic()
        floor = state.get("tier") or 1
        as_of = _as_of_text(state)
        plan = TurnPlan(
            intent=f"Answer the question using the tier {floor} tools",
            tier=cast(Literal[1, 2, 3], floor),
            steps=[],
        )
        model_calls = 0
        if planner is not None and not _over_budget(state, cfg):
            plan_messages = [
                SystemMessage(content=PLAN_SYSTEM_PROMPT),
                HumanMessage(
                    content=plan_user_prompt(
                        state["question"], tier_floor=floor, as_of=as_of
                    )
                ),
            ]
            structured = planner.with_structured_output(TurnPlan)

            # One retry, because `with_structured_output` does not raise when
            # the model declines to emit the forced tool call: it returns None.
            # Measured on deepseek-v4-flash that is four calls in six, so
            # without this roughly half of all turns ran with no plan, and the
            # `plan` event a controller reads was the fallback text rather than
            # an intent. A turn with no steps also explores, which costs far
            # more than the one retry does.
            #
            # One retry and no more. A planner that is down must not multiply
            # the cost of every turn.
            for attempt in (1, 2):
                try:
                    result = structured.invoke(plan_messages)
                    model_calls += 1
                except Exception as exc:
                    emit("note", {"text": f"Planner unavailable, continuing: {exc}"})
                    break

                if isinstance(result, TurnPlan):
                    plan = result
                    break
                if isinstance(result, dict):
                    plan = TurnPlan.model_validate(result)
                    break
                if attempt == 2 or _over_budget(state, cfg):
                    # Visible, not silent. A turn with no plan used to look
                    # exactly like a turn whose plan happened to be terse.
                    emit(
                        "note",
                        {
                            "text": (
                                "The planner returned no plan twice, so this turn "
                                "runs without stated steps."
                            )
                        },
                    )
                    break

        # The model may raise the tier, never lower it. The deterministic
        # classifier is the floor because a question that says "what should I
        # do" is a tier 3 question whatever the model thinks.
        tier = max(int(plan.tier), floor)
        emit(
            "plan",
            {
                "intent": strip_em_dashes(plan.intent),
                "tier": tier,
                "steps": [strip_em_dashes(step) for step in plan.steps],
                "prompt_version": PROMPT_VERSION,
            },
        )
        messages: list[AnyMessage] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=answer_kickoff(
                    state["question"],
                    plan=plan.intent,
                    steps=plan.steps,
                    as_of=as_of,
                )
            ),
        ]
        prefetched: list[ToolEnvelope] = []

        # PREFETCH. The agent discovers its tools one round trip at a time, and
        # a round trip is ~4.5 seconds against a 30 second budget while the
        # tools themselves cost single-digit milliseconds. For a shape the
        # offline resolver already recognises that discovery buys nothing: the
        # call list is known, so run it here and let the agent's first call be
        # the one that writes the answer.
        #
        # The envelopes go into state exactly like the loop's own, so the
        # verifier attests them and the guards see them. Nothing about the
        # boundary changes; only the number of times the model is asked.
        if cfg.prefetch:
            for call in _prefetch_plan(state["question"], _snapshot_of(state)):
                emit(
                    "tool_call",
                    {
                        "tool": call.tool,
                        "args": call.args,
                        "label": _label_for(call.tool, call.args),
                    },
                )
                started_call = time.monotonic()
                try:
                    envelope = call_tool(cast(Any, tools), call.tool, call.args)
                except Exception as exc:
                    envelope = ToolEnvelope(
                        tool=call.tool,
                        args=call.args,
                        ok=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                if not envelope.latency_ms:
                    envelope = envelope.model_copy(
                        update={
                            "latency_ms": int((time.monotonic() - started_call) * 1000)
                        }
                    )
                prefetched.append(envelope)
                emit(
                    "tool_result",
                    {
                        "tool": envelope.tool,
                        "ok": envelope.ok,
                        "latency_ms": envelope.latency_ms,
                        "summary": _summarise_payload(envelope),
                        "envelope": envelope.model_dump(mode="json"),
                    },
                )

        if prefetched:
            # Presented as the loop would have presented them: a tool call the
            # model can see it did not have to make, and its result. A
            # ToolMessage with no matching tool_call breaks the message
            # sequence and the provider rejects the next request.
            calls = [
                {
                    "name": envelope.tool,
                    "args": envelope.args,
                    "id": f"prefetch_{index}",
                }
                for index, envelope in enumerate(prefetched)
            ]
            messages.append(AIMessage(content="", tool_calls=calls))
            for index, envelope in enumerate(prefetched):
                content, truncated = _tool_message_content(envelope)
                if truncated:
                    prefetched[index] = envelope.model_copy(
                        update={"truncated": True}
                    )
                messages.append(
                    ToolMessage(
                        content=content,
                        tool_call_id=f"prefetch_{index}",
                        name=envelope.tool,
                    )
                )

        return {
            "tier": tier,
            "plan_intent": strip_em_dashes(plan.intent),
            "plan_steps": [strip_em_dashes(step) for step in plan.steps],
            "model_calls": state.get("model_calls", 0) + model_calls,
            "envelopes": prefetched,
            "timings": {
                **state.get("timings", {}),
                "plan_ms": int((time.monotonic() - started) * 1000),
                "tools_ms": state.get("timings", {}).get("tools_ms", 0)
                + sum(e.latency_ms for e in prefetched),
            },
            "messages": messages,
        }

    # ------------------------------------------------------------------ agent

    def agent_node(state: TurnState) -> dict[str, Any]:
        if bound is None:
            return {
                "abstention": Abstention(
                    reason=AbstentionReason.TOOL_ERROR,
                    message=(
                        "No language model is configured, so the agent path cannot "
                        "run. The deterministic resolver answers the same questions "
                        "without one."
                    ),
                    missing=providers.missing_env(),
                    suggestions=["Run the same question with --offline"],
                )
            }
        if _over_budget(state, cfg):
            return {"abstention": _timeout_abstention(state, cfg)}

        message = bound.invoke(state["messages"])
        text = _text_of(message)
        return {
            "messages": [message],
            "draft": strip_em_dashes(text) if text else state.get("draft", ""),
            "model_calls": state.get("model_calls", 0) + 1,
        }

    def agent_edge(state: TurnState) -> Literal["tools", "verify", "abstain"]:
        if state.get("abstention") is not None:
            return "abstain"
        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        if isinstance(last, AIMessage) and last.tool_calls:
            if state.get("tool_iterations", 0) >= cfg.max_tool_iterations:
                return "abstain"
            return "tools"
        return "verify"

    # ------------------------------------------------------------------ tools

    def tools_node(state: TurnState) -> dict[str, Any]:
        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {}

        started = time.monotonic()
        envelopes: list[ToolEnvelope] = []
        replies: list[AnyMessage] = []

        # Every lookup already computed this turn, including earlier calls in
        # this same batch. A model that asks the same question twice gets the
        # first answer back rather than paying for it again.
        seen: dict[str, ToolEnvelope] = {}
        for prior in state.get("envelopes") or []:
            if prior.ok:
                seen.setdefault(repeat_key(prior.tool, prior.args), prior)

        for call in last.tool_calls:
            name = str(call.get("name", ""))
            args = dict(call.get("args") or {})
            call_id = str(call.get("id") or name)

            cached = seen.get(repeat_key(name, args))
            if cached is not None:
                # Reuse the result, but still emit an envelope and a reply. A
                # tool_call with no matching tool result breaks the message
                # sequence, and the provider rejects the next request rather
                # than the turn merely being slower.
                envelope = cached.model_copy(update={"latency_ms": 0})
                envelopes.append(envelope)
                cached_content, _ = _tool_message_content(envelope)
                replies.append(
                    ToolMessage(
                        content=cached_content,
                        tool_call_id=call_id,
                        name=name,
                    )
                )
                continue

            if _over_budget(state, cfg):
                envelope = ToolEnvelope(
                    tool=name,
                    args=args,
                    ok=False,
                    error="The turn ran out of its time budget before this call.",
                )
            else:
                emit(
                    "tool_call",
                    {"tool": name, "args": args, "label": _label_for(name, args)},
                )
                call_started = time.monotonic()
                try:
                    envelope = call_tool(cast(Any, tools), name, args)
                except Exception as exc:
                    envelope = ToolEnvelope(
                        tool=name, args=args, ok=False, error=f"{type(exc).__name__}: {exc}"
                    )
                if not envelope.latency_ms:
                    envelope = envelope.model_copy(
                        update={
                            "latency_ms": int((time.monotonic() - call_started) * 1000)
                        }
                    )

            content, truncated = _tool_message_content(envelope)
            if truncated:
                envelope = envelope.model_copy(update={"truncated": True})

            envelopes.append(envelope)
            if envelope.ok:
                # Within this batch too: a model that emits the same call twice
                # in one message must not run it twice either.
                seen.setdefault(repeat_key(name, args), envelope)
            emit(
                "tool_result",
                {
                    "tool": name,
                    "ok": envelope.ok,
                    "latency_ms": envelope.latency_ms,
                    "summary": _summarise_payload(envelope),
                    "envelope": envelope.model_dump(mode="json"),
                },
            )
            for step in envelope.trace:
                emit("trace", {"step": step.model_dump(mode="json")})

            replies.append(ToolMessage(content=content, tool_call_id=call_id, name=name))

        previous = state.get("timings", {})
        return {
            "messages": replies,
            "envelopes": envelopes,
            "tool_iterations": state.get("tool_iterations", 0) + 1,
            "timings": {
                **previous,
                "tools_ms": previous.get("tools_ms", 0)
                + int((time.monotonic() - started) * 1000),
            },
        }

    # ----------------------------------------------------------------- verify

    def verify_node(state: TurnState) -> dict[str, Any]:
        started = time.monotonic()
        draft = state.get("draft", "")
        envelopes = list(state.get("envelopes") or [])
        repairs = state.get("repairs", 0)

        # Structural guards run first. There is no point grounding the figures
        # in a verdict that no rules engine produced.
        failure = run_guards(draft=draft, tier=state.get("tier"), envelopes=envelopes)
        if failure is not None:
            return _guard_outcome(state, failure, repairs, started, cfg)

        outcome = guard.check(draft, envelopes, repair_attempts=repairs)
        emit("verifying", {"atom_count": outcome.report.checked_atoms})
        report = outcome.report
        if report.status is VerificationStatus.REJECTED and repairs > 0:
            report = report.model_copy(update={"note": _rejection_note(report)})
        elif report.status is VerificationStatus.VERIFIED and repairs > 0:
            report = report.model_copy(update={"status": VerificationStatus.REPAIRED})

        previous = state.get("timings", {})
        return {
            "verification": report,
            "pending_guard": None,
            "timings": {
                **previous,
                "verify_ms": previous.get("verify_ms", 0)
                + int((time.monotonic() - started) * 1000),
            },
        }

    def verify_edge(state: TurnState) -> str:
        if state.get("abstention") is not None:
            return "abstain"
        if state.get("pending_guard"):
            return "policy_repair"
        report = state.get("verification")
        if report is None:
            return "abstain"
        if report.status is VerificationStatus.REJECTED:
            if state.get("repairs", 0) < cfg.max_repairs and not _over_budget(state, cfg):
                return "repair"
            return "abstain"
        return END

    # ----------------------------------------------------------------- repair

    def repair_node(state: TurnState) -> dict[str, Any]:
        report = state.get("verification")
        unattested = [
            (item.atom, item.kind, item.context)
            for item in (report.unattested if report else [])
        ]
        return {
            "repairs": state.get("repairs", 0) + 1,
            "messages": [HumanMessage(content=repair_prompt(unattested))],
        }

    def policy_repair_node(state: TurnState) -> dict[str, Any]:
        pending = state.get("pending_guard") or {}
        reason = str(pending.get("reason", "the answer broke a structural rule"))
        required = [str(tool) for tool in pending.get("required_tools", [])]
        update: dict[str, Any] = {
            "pending_guard": None,
            "messages": [HumanMessage(content=policy_repair_prompt(reason, required))],
        }
        # A style rewrite is counted apart from a grounding one, so being asked
        # to stop enumerating never costs a turn its correction for a figure.
        if pending.get("fatal", True):
            update["repairs"] = state.get("repairs", 0) + 1
        else:
            update["style_repairs"] = state.get("style_repairs", 0) + 1
        return update

    # ---------------------------------------------------------------- abstain

    def abstain_node(state: TurnState) -> dict[str, Any]:
        abstention = state.get("abstention") or _abstention_from_verification(state)
        emit("abstain", {"abstention": abstention.model_dump(mode="json")})
        report = state.get("verification") or VerificationReport(
            status=VerificationStatus.SKIPPED,
            note="The turn declined to answer, so there was nothing to ground.",
        )
        return {"abstention": abstention, "verification": report}

    # ------------------------------------------------------------------ wire

    builder: StateGraph[Any, Any, Any, Any] = StateGraph(TurnState)
    builder.add_node("route", route_node)
    builder.add_node("plan", plan_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("verify", verify_node)
    builder.add_node("repair", repair_node)
    builder.add_node("policy_repair", policy_repair_node)
    builder.add_node("abstain", abstain_node)

    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route", route_edge, {"plan": "plan", "abstain": "abstain"}
    )
    builder.add_edge("plan", "agent")
    builder.add_conditional_edges(
        "agent",
        agent_edge,
        {"tools": "tools", "verify": "verify", "abstain": "abstain"},
    )
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "verify",
        verify_edge,
        {
            "repair": "repair",
            "policy_repair": "policy_repair",
            "abstain": "abstain",
            END: END,
        },
    )
    builder.add_edge("repair", "agent")
    builder.add_edge("policy_repair", "agent")
    builder.add_edge("abstain", END)

    return builder.compile(checkpointer=checkpointer, name="crewops-turn")


# ---------------------------------------------------------------------------
# Helpers kept out of the closure so they are testable on their own.
# ---------------------------------------------------------------------------

def _guard_outcome(
    state: TurnState,
    failure: GuardFailure,
    repairs: int,
    started: float,
    config: AgentConfig,
) -> dict[str, Any]:
    """A structural failure gets one corrective pass, then abstains.

    This is the "force a tool call or abstain" rule from the contract, spent
    out of the same single repair budget as a grounding failure so a turn can
    never loop.
    """
    previous = state.get("timings", {})
    timings = {
        **previous,
        "verify_ms": previous.get("verify_ms", 0)
        + int((time.monotonic() - started) * 1000),
    }
    report = VerificationReport(
        status=VerificationStatus.REJECTED,
        checked_atoms=0,
        attested_atoms=0,
        repair_attempts=repairs,
        note=f"Guard '{failure.guard}' rejected the answer: {failure.reason}",
    )
    # A STYLE REWRITE SPENDS ITS OWN BUDGET. Sharing one counter meant a turn
    # asked to stop enumerating had used its only pass, so the rewrite quoting
    # one unattestable figure was refused for a reason unrelated to the figure.
    # Agent abstentions went 4 to 8 on the scorecard when the guard landed.
    spent = repairs if failure.fatal else state.get("style_repairs", 0)
    if spent < config.max_repairs:
        return {
            "verification": report,
            "timings": timings,
            "pending_guard": {
                "guard": failure.guard,
                "reason": failure.reason,
                "required_tools": list(failure.required_tools),
                "fatal": failure.fatal,
            },
        }
    if not failure.fatal:
        # ONE ASK, THEN LET IT GO. A style guard has had its correction pass
        # and the answer is still merely verbose. Abstaining here would trade
        # a correct answer for a tidy refusal, which is the scoring principle
        # backwards. The draft goes on to grounding like any other.
        return {"timings": timings, "pending_guard": None}
    return {
        "verification": report,
        "timings": timings,
        "pending_guard": None,
        "abstention": Abstention(
            reason=failure.abstention_reason,
            message=(
                "I cannot answer that reliably. " + failure.reason
            ),
            missing=[failure.reason],
            did_establish=_established(state),
            suggestions=(
                [f"Ask again and I will run {tool}" for tool in failure.required_tools]
                or _scope_suggestions()
            ),
        ),
    }


def _abstention_from_verification(state: TurnState) -> Abstention:
    report = state.get("verification")
    if report is None or not report.unattested:
        return Abstention(
            reason=AbstentionReason.VERIFICATION_FAILED,
            message=(
                "I cannot answer that reliably. The draft answer could not be "
                "grounded in what the tools returned."
            ),
            did_establish=_established(state),
            suggestions=_scope_suggestions(),
        )
    atoms = ", ".join(item.atom for item in report.unattested[:6])
    return Abstention(
        reason=AbstentionReason.VERIFICATION_FAILED,
        message=(
            "I cannot answer that reliably. After one correction pass these "
            f"values still had nothing behind them: {atoms}. Rather than show you "
            "an unverified figure, I am declining."
        ),
        missing=[f"{item.atom} ({item.kind})" for item in report.unattested],
        did_establish=_established(state),
        suggestions=[
            "Ask for the specific figure on its own and I will compute it directly",
            "Ask what I did establish about this crew member or pairing",
        ],
    )


def _timeout_abstention(state: TurnState, config: AgentConfig) -> Abstention:
    return Abstention(
        reason=AbstentionReason.TOOL_ERROR,
        message=(
            "I cannot answer that reliably. The turn exceeded its "
            f"{config.turn_budget_ms} ms budget, and a slow answer on a live shift "
            "is worse than none."
        ),
        missing=["A complete tool run inside the time budget"],
        did_establish=_established(state),
        suggestions=[
            "Narrow the question to one crew member or one pairing",
            "Ask for the impact first, then the options",
        ],
    )


def _established(state: TurnState) -> list[str]:
    """What the turn managed to compute before it ran out of ground."""
    lines: list[str] = []
    for envelope in state.get("envelopes") or []:
        if not envelope.ok:
            continue
        for step in envelope.trace[:2]:
            lines.append(f"{step.label}: {step.detail}")
    return lines[:6]


def _scope_suggestions() -> list[str]:
    return [
        "Who is on reserve at BLR tomorrow",
        "How much duty headroom does C-1042 have",
        "Captain C-1042 is out for P-2291, what should I do",
    ]


def _rejection_note(report: VerificationReport) -> str:
    return (
        f"{report.note or ''} One correction pass was spent and the answer still "
        "carried unattested values, so the turn declines."
    ).strip()


def _snapshot_of(state: TurnState) -> datetime:
    """The as-of the turn is reasoning about, for building a prefetch plan.

    The dataset snapshot when the turn does not name one, which is what every
    intent's `build` already assumes.
    """
    as_of = state.get("as_of")
    if isinstance(as_of, datetime):
        return as_of.replace(tzinfo=None)
    from crewops.agent.factory import default_snapshot

    return default_snapshot()


def _as_of_text(state: TurnState) -> str:
    as_of = state.get("as_of")
    if isinstance(as_of, datetime):
        return as_of.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
    return "the dataset snapshot"


def _label_for(name: str, args: dict[str, Any]) -> str:
    from crewops.agent.toolspecs import spec_for

    spec = spec_for(name)
    if spec is None:
        return f"Calling {name}"
    try:
        return spec.label(args)
    except Exception:
        return f"Calling {name}"


def _text_of(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    return "".join(parts)


def utcnow() -> datetime:
    """Naive UTC, matching the dataset's convention of naive UTC timestamps."""
    return datetime.now(UTC).replace(tzinfo=None)
