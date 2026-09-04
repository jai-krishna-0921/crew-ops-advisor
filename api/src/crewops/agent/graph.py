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
from crewops.resolve.triage import triage_question
from crewops.verify import Verifier

__all__ = ["TurnPlan", "bind_tool_specs", "build_graph"]

#: How much of a tool payload is handed back to the model. The full envelope
#: always reaches the verifier and the HTTP layer; this cap only protects the
#: prompt budget, and `truncated` records that it fired.
_PAYLOAD_CHAR_BUDGET: Final = 6_000


class TurnPlan(BaseModel):
    """The planner's structured output. Rendered as the `plan` stream event."""

    intent: str = Field(description="One line: what you are about to establish")
    tier: Literal[1, 2, 3] = Field(description="1 lookup, 2 consequence, 3 recommendation")
    steps: list[str] = Field(
        default_factory=list,
        description="Two to five concrete steps, each naming a tool and its subject",
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
        payload_json = (
            envelope.payload.model_dump(mode="json")
            if hasattr(envelope.payload, "model_dump")
            else envelope.payload
        )
        rendered = json.dumps(payload_json, default=str)
        if len(rendered) > _PAYLOAD_CHAR_BUDGET:
            payload_json = rendered[:_PAYLOAD_CHAR_BUDGET] + "...[truncated]"
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
        update: dict[str, Any] = {
            "in_scope": verdict.in_scope,
            "tier": verdict.tier,
            "triage_reason": verdict.reason,
        }
        if not verdict.in_scope:
            # A greeting is answered, not refused. Nothing is missing: the
            # controller has not asked for anything yet. Same treatment as the
            # offline resolver, so both paths greet identically.
            greeting = verdict.abstention_reason is AbstentionReason.GREETING
            update["abstention"] = Abstention(
                reason=verdict.abstention_reason or AbstentionReason.OUT_OF_SCOPE,
                message=(
                    verdict.reason
                    if greeting
                    else "I cannot answer that reliably. " + verdict.reason
                ),
                missing=[] if greeting else [verdict.reason],
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
            try:
                structured = planner.with_structured_output(TurnPlan)
                result = structured.invoke(
                    [
                        SystemMessage(content=PLAN_SYSTEM_PROMPT),
                        HumanMessage(
                            content=plan_user_prompt(
                                state["question"], tier_floor=floor, as_of=as_of
                            )
                        ),
                    ]
                )
                model_calls = 1
                if isinstance(result, TurnPlan):
                    plan = result
                elif isinstance(result, dict):
                    plan = TurnPlan.model_validate(result)
            except Exception as exc:
                emit("note", {"text": f"Planner unavailable, continuing: {exc}"})

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
        return {
            "tier": tier,
            "plan_intent": strip_em_dashes(plan.intent),
            "plan_steps": [strip_em_dashes(step) for step in plan.steps],
            "model_calls": state.get("model_calls", 0) + model_calls,
            "timings": {
                **state.get("timings", {}),
                "plan_ms": int((time.monotonic() - started) * 1000),
            },
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=answer_kickoff(
                        state["question"],
                        plan=plan.intent,
                        steps=plan.steps,
                        as_of=as_of,
                    )
                ),
            ],
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

        for call in last.tool_calls:
            name = str(call.get("name", ""))
            args = dict(call.get("args") or {})
            call_id = str(call.get("id") or name)

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
        return {
            "repairs": state.get("repairs", 0) + 1,
            "pending_guard": None,
            "messages": [HumanMessage(content=policy_repair_prompt(reason, required))],
        }

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
    if repairs < config.max_repairs:
        return {
            "verification": report,
            "timings": timings,
            "pending_guard": {
                "guard": failure.guard,
                "reason": failure.reason,
                "required_tools": list(failure.required_tools),
            },
        }
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
