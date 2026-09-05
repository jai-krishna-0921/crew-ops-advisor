"""The offline resolver: the same tools, the same verifier, no model.

Everything must run with no API key. Without one, this maps a question to a
tool plan by pattern, runs the plan, renders the reply from templates and puts
the result through the identical grounding check the agent path uses. The
`Reply` it produces is the same type, with `mode=DETERMINISTIC`.

It is demo insurance and a proof, not a second product. When it cannot match,
it abstains with a reason and a list of shapes it does handle, which is more
honest and more useful than a fuzzy guess.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, cast

from crewops.agent.guards import run_guards, strip_em_dashes
from crewops.agent.reply import build_reply
from crewops.agent.toolspecs import call_tool
from crewops.contracts import (
    Abstention,
    AbstentionReason,
    AnswerMode,
    Reply,
    ToolEnvelope,
    ToolSurface,
    VerificationReport,
    VerificationStatus,
)
from crewops.resolve.completeness import unmodelled_constraints
from crewops.resolve.conversation import PriorTurn, ThreadContext, merge_entities
from crewops.resolve.intents import Intent, PlannedCall, match_intent
from crewops.resolve.render import render
from crewops.resolve.triage import (
    canonical_question,
    reads_as_followup,
    refers_without_naming,
    triage_question,
)
from crewops.verify import Verifier

__all__ = ["SUPPORTED_SHAPES", "DeterministicResolver"]

#: What the offline path can answer, in the words a controller would use.
#: Shown in every abstention so a refusal is actionable.
SUPPORTED_SHAPES: tuple[str, ...] = (
    "Who is on reserve at BLR on 2026-09-15",
    "How many duty hours has C-1042 accrued, and what headroom is left",
    "Which flights depart DEL on 2026-09-15",
    "List certifications expiring within 30 days of 2026-09-15",
    "Which crew are assigned to pairing P-2291",
    "Captain C-1042 calls in sick on 15 Sep, which flights are uncrewed",
    "Can C-2087 legally cover P-2291",
    "BLR is closed 08:00 to 14:00 on 17 Sep, which flights are affected",
    "Captain C-1042 is out for P-2291, produce ranked options",
    "Draft the callout notification to C-3310 for P-2291",
)


class DeterministicResolver:
    """Answers without a model. Same tools, same verifier, same `Reply`."""

    def __init__(
        self,
        tools: ToolSurface,
        *,
        snapshot: datetime | None = None,
        verifier: Verifier | None = None,
        context: ThreadContext | None = None,
    ) -> None:
        self.tools = tools
        self.snapshot = snapshot or datetime(2026, 9, 14, 18, 0, 0)
        self.verifier = verifier or Verifier()
        #: What the previous answered turn on each thread established, so a
        #: follow-up that names nothing can still be understood. Offline
        #: there is no model to resolve a reference, and offline is the mode
        #: that has to work with no API key.
        self.threads = context or ThreadContext()

    def answer(
        self,
        question: str,
        *,
        thread_id: str,
        turn_id: str,
        asked_at: datetime,
        as_of: datetime | None = None,
    ) -> Reply:
        started = time.monotonic()
        snapshot = as_of or self.snapshot
        # Normalise once, here, so triage, intent matching and every argument
        # built downstream all see the dataset's spelling. `question` itself is
        # left alone: it becomes `Reply.question`, and the audit trail should
        # show a controller what they actually typed, not a tidied version of
        # it.
        asked = canonical_question(question)
        triage = triage_question(asked)

        # A FOLLOW-UP IS NOT AN OPENING LINE. "And what about the next day?"
        # names no crew, pairing, flight, station or rule, so triage declined
        # it as out of scope, which was correct about the words and wrong about
        # the situation. When the same thread has an answered turn behind it,
        # that turn supplies the subject and this one supplies the change.
        prior = self.threads.recall(thread_id)
        follow_up = prior is not None and (
            reads_as_followup(asked) or refers_without_naming(asked, triage.entities)
        )
        entities = triage.entities
        if follow_up and prior is not None:
            entities = merge_entities(prior.entities, triage.entities, asked)

        if not triage.in_scope and not follow_up:
            # A greeting is answered, not refused. It carries no "I cannot" and
            # nothing under "what was missing", because nothing is missing: the
            # controller has not asked for anything yet.
            greeting = triage.abstention_reason is AbstentionReason.GREETING
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                abstention=Abstention(
                    reason=triage.abstention_reason or AbstentionReason.OUT_OF_SCOPE,
                    message=(
                        triage.reason
                        if greeting
                        else "I cannot answer that reliably. " + triage.reason
                    ),
                    missing=[] if greeting else list(triage.missing) or [triage.reason],
                    suggestions=list(SUPPORTED_SHAPES[:3]),
                ),
                tier=triage.tier,
            )

        # A follow-up that has a shape of its own keeps it. "Is C-3305 legal
        # for the whole pairing?" is a legality question that happens to point
        # at the previous turn for its subject, and running the previous turn's
        # shape over it would answer the earlier question again with a new
        # crew id in it.
        #
        # A follow-up with NO shape of its own runs the one the thread was
        # already in: "what about DEL" after a flights question is a flights
        # question, and re-matching it on its own words would pick whatever
        # shape happens to read a bare station.
        intent = match_intent(asked, entities)
        if intent is None and follow_up and prior is not None:
            intent = prior.intent
        if intent is None:
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                abstention=Abstention(
                    reason=AbstentionReason.UNDERSPECIFIED,
                    message=(
                        "I cannot answer that reliably. No language model is "
                        "configured, so I am matching the question against a fixed "
                        "set of shapes and this one does not match any of them. "
                        "Rather than guess at what you meant, here is what I can "
                        "answer offline."
                    ),
                    missing=["A question shape the offline resolver recognises"],
                    suggestions=list(SUPPORTED_SHAPES),
                ),
                tier=triage.tier,
            )

        gaps = intent.missing(entities)
        if gaps and prior is not None and not follow_up:
            # AN ARGUMENT THIS QUESTION IS MISSING MAY BE ONE THE THREAD
            # ALREADY HAS. "What are my options, cheapest first?" after
            # "Captain C-1042 calls in sick on 15 Sep for P-2291" names no
            # pairing and was refused for it, one turn after the pairing was
            # established and shown on screen. Nothing is guessed: the value
            # came from an answered turn in this conversation, and the reply
            # names what it used, so the inheritance is visible and can be
            # argued with. A gap context cannot close is still a refusal.
            inherited = merge_entities(
                prior.entities, triage.entities, asked, carry_temporal=False
            )
            if not intent.missing(inherited):
                entities = inherited
                gaps = []
        if gaps:
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                abstention=Abstention(
                    reason=AbstentionReason.UNDERSPECIFIED,
                    message=(
                        "I cannot answer that reliably. I understood this as a "
                        f"'{intent.name}' question, but it does not name "
                        + " or ".join(gaps)
                        + "."
                        # `missing_hint` was a declared field that nothing read.
                        # It is where an intent puts the line a controller can
                        # copy, which is the difference between a refusal and a
                        # question worth answering.
                        + (f" {intent.missing_hint}" if intent.missing_hint else "")
                    ),
                    missing=gaps,
                    suggestions=[f"Add {gap} and ask again" for gap in gaps],
                ),
                tier=intent.tier,
            )

        plan = intent.build(entities, snapshot)

        # MATCHING A SHAPE IS NOT ANSWERING THE QUESTION. A shape has a fixed
        # argument list, and a constraint the question carries that the shape
        # cannot express used to be dropped in silence: the tools then ran over
        # the unfiltered set and the renderer stated that as the answer. Every
        # figure in it was real, so neither the verifier nor the guards saw a
        # problem. It was the answer to a different question, which is the one
        # failure this system exists to avoid.
        unmodelled = unmodelled_constraints(asked, plan)
        if unmodelled:
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                abstention=Abstention(
                    reason=AbstentionReason.UNDERSPECIFIED,
                    message=(
                        "I cannot answer that reliably. I understood this as a "
                        f"'{intent.name}' question, but that shape cannot express "
                        + unmodelled[0].split(".")[0]
                        + ". Answering without it would have reported the "
                        "unfiltered set as though it were the answer."
                    ),
                    missing=unmodelled,
                    suggestions=list(SUPPORTED_SHAPES[:3]),
                ),
                tier=intent.tier,
            )

        envelopes = self._run(plan)
        tier = max(intent.tier, triage.tier)

        failed = [envelope for envelope in envelopes if not envelope.ok]
        if failed and len(failed) == len(envelopes):
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                envelopes=envelopes,
                abstention=Abstention(
                    reason=AbstentionReason.TOOL_ERROR,
                    message=(
                        "I cannot answer that reliably. Every lookup this question "
                        "needed failed: "
                        + "; ".join(
                            f"{item.tool}: {item.error or 'no detail'}" for item in failed
                        )
                        + ". A failed lookup is not a finding of 'none'."
                    ),
                    missing=[item.tool for item in failed],
                    suggestions=["Check the identifier and ask again"],
                ),
                tier=tier,
            )

        text = strip_em_dashes(render(intent.template, envelopes, question))
        if not text.strip():
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                envelopes=envelopes,
                abstention=Abstention(
                    reason=AbstentionReason.NOT_IN_DATASET,
                    message=(
                        "I cannot answer that reliably. The tools ran and returned "
                        "nothing to report for this question."
                    ),
                    missing=["A non empty tool result"],
                    suggestions=list(SUPPORTED_SHAPES[:3]),
                ),
                tier=tier,
            )

        # The offline path is held to the same structural guards and the same
        # grounding check as the agent. It has no repair pass, because a
        # template that produces an unattested figure is a bug in the template,
        # not something to negotiate with.
        failure = run_guards(draft=text, tier=tier, envelopes=envelopes)
        if failure is not None:
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                envelopes=envelopes,
                abstention=Abstention(
                    reason=failure.abstention_reason,
                    message="I cannot answer that reliably. " + failure.reason,
                    missing=[failure.reason],
                    suggestions=list(SUPPORTED_SHAPES[:3]),
                ),
                tier=tier,
            )

        report = self.verifier.verify(text, envelopes)
        if report.status is VerificationStatus.REJECTED:
            return self._abstain(
                question,
                thread_id=thread_id,
                turn_id=turn_id,
                asked_at=asked_at,
                started=started,
                envelopes=envelopes,
                verification=report,
                abstention=Abstention(
                    reason=AbstentionReason.VERIFICATION_FAILED,
                    message=(
                        "I cannot answer that reliably. The rendered answer carried "
                        "values the tools did not return: "
                        + ", ".join(item.atom for item in report.unattested[:6])
                        + "."
                    ),
                    missing=[item.atom for item in report.unattested],
                    suggestions=list(SUPPORTED_SHAPES[:3]),
                ),
                tier=tier,
            )

        # Only an ANSWERED turn is remembered. A refusal established nothing,
        # so a follow-up to one has nothing to carry and is refused in turn.
        self.threads.remember(
            thread_id, PriorTurn(intent=intent, entities=entities, question=asked)
        )

        state: dict[str, Any] = {
            "envelopes": envelopes,
            "draft": text,
            "verification": report,
            "tier": tier,
            "abstention": None,
            "timings": {"tools_ms": self._tools_ms(envelopes)},
            "model_calls": 0,
        }
        return build_reply(
            state,
            question=question,
            thread_id=thread_id,
            turn_id=turn_id,
            asked_at=asked_at,
            total_ms=int((time.monotonic() - started) * 1000),
            mode=AnswerMode.DETERMINISTIC,
        )

    # ------------------------------------------------------------------ plumbing

    def _run(self, plan: list[PlannedCall]) -> list[ToolEnvelope]:
        envelopes: list[ToolEnvelope] = []
        for call in plan:
            started = time.monotonic()
            try:
                envelope = call_tool(cast(Any, self.tools), call.tool, call.args)
            except Exception as exc:
                envelope = ToolEnvelope(
                    tool=call.tool,
                    args=call.args,
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            if not envelope.latency_ms:
                envelope = envelope.model_copy(
                    update={"latency_ms": int((time.monotonic() - started) * 1000)}
                )
            envelopes.append(envelope)
        return envelopes

    def _tools_ms(self, envelopes: list[ToolEnvelope]) -> int:
        return sum(envelope.latency_ms for envelope in envelopes)

    def _abstain(
        self,
        question: str,
        *,
        thread_id: str,
        turn_id: str,
        asked_at: datetime,
        started: float,
        abstention: Abstention,
        tier: int,
        envelopes: list[ToolEnvelope] | None = None,
        verification: VerificationReport | None = None,
    ) -> Reply:
        state: dict[str, Any] = {
            "envelopes": envelopes or [],
            "draft": "",
            "verification": verification
            or VerificationReport(
                status=VerificationStatus.SKIPPED,
                note="The turn declined to answer, so there was nothing to ground.",
            ),
            "tier": tier,
            "abstention": abstention,
            "timings": {"tools_ms": self._tools_ms(envelopes or [])},
            "model_calls": 0,
        }
        return build_reply(
            state,
            question=question,
            thread_id=thread_id,
            turn_id=turn_id,
            asked_at=asked_at,
            total_ms=int((time.monotonic() - started) * 1000),
            mode=AnswerMode.DETERMINISTIC,
        )


def intent_names() -> list[str]:
    """Every shape the offline path knows. Used by the CLI's help output."""
    from crewops.resolve.intents import INTENTS

    return [intent.name for intent in INTENTS]


def intent_for(question: str) -> Intent | None:
    return match_intent(question)
