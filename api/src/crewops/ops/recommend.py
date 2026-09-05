"""The Tier 3 orchestration macro-tool: one deterministic pipeline, no model.

A ranked recommendation used to be several tool calls the agent had to sequence
correctly: enumerate the pool, rule check each candidate, price each survivor,
then order the result. Sequencing is planning, which is the model's job, but
*this particular* sequence has exactly one correct order and no judgement in it,
so leaving it to a planner bought nothing and cost a turn every time a step was
dropped. A dropped step is not a visible failure either: an answer that priced
three candidates and never checked the other twenty reads exactly like an answer
that checked all twenty three.

So the sequence lives here, in code, and runs as one call:

1. **Enumerate.** Every active crew member whose rank matches the seat, which
   includes but is not limited to the reserve pool. `CandidateSearcher` owns
   this and the order of its filters is load-bearing (see `CLAUDE.md`).
2. **Rule check.** All seven rules against every candidate, on every day of the
   cover. Not the first rule that fails: `rules_per_candidate` is stated on the
   payload so a consumer can assert the set was complete.
3. **Price.** `costs.json`, cross referenced per candidate: the reserve callout
   rate or the day-off rate by rank, plus deadhead positioning and the delay it
   introduces when the candidate is not based at the departure station.
4. **Rank.** The heuristic below, applied to what survived.

Nothing here recomputes any of that. Each step is the existing engine, called
in the one order that is correct, and this module's own work is the projection:
lifting the breaching `RuleTrace` onto every reject so the exclusion is stated
rather than merely reachable, and emitting a `Fact` for every figure the answer
is allowed to quote.

**No language model is reachable from this module at any depth**, which is the
whole point of putting the orchestration here rather than in the graph.
"""

from __future__ import annotations

from crewops.contracts.evidence import Fact, Provenance
from crewops.contracts.ops import (
    CostBreakdown,
    CoverKind,
    CoverOption,
    RankedRecommendation,
    RejectedCandidate,
)
from crewops.contracts.rules import (
    ALL_RULE_IDS,
    DayLegality,
    LegalityReport,
    RuleTrace,
    Verdict,
)
from crewops.domain import WorldState
from crewops.ops.candidates import (
    RULES_CHECKED,
    CoverSearch,
    ExcludedCandidate,
    RankedOption,
    option_to_cover_option,
)

__all__ = ["RANKING_HEURISTIC", "SOURCE", "build_ranked_recommendation"]

SOURCE = "crewops.ops.recommend.build_ranked_recommendation"

#: How the surviving options are ordered, stated plainly so it can be argued
#: with. This is the contract's `ranking_basis` for this payload.
#:
#: Cost dominates, exactly as `CandidateSearcher` orders its own list, so the
#: cheapest legal cover is rank 1 here for the same reason it is rank 1 there.
#: What differs is the tie break: where two options cost the same rupee, this
#: prefers the one the desk can actually get hold of soonest. That is a real
#: operational discriminator and it costs nothing, because the shipped S6 note
#: says in its own words that equal cost mirror assignments are equally correct,
#: so ordering them by crew id was never carrying information either.
#:
#: Cancellation is appended last regardless of its price. It is a last resort,
#: not a cheap one, and at INR 250,000 a leg it would otherwise sort itself into
#: the middle of a list a controller reads top down.
RANKING_HEURISTIC = (
    "Legal options ordered by cost ascending, ties broken by reachability in "
    "minutes and then by crew id. The cancellation option is appended last "
    "regardless of its cost, because cancelling is a last resort rather than a "
    "cheap one."
)


def build_ranked_recommendation(
    search: CoverSearch,
    *,
    covering_for: str | None = None,
    max_options: int | None = None,
) -> RankedRecommendation:
    """Run the projection over a completed cover search.

    `search` has already done steps 1 to 3. This applies step 4 and states the
    result in the shape a ranking guard can assert on.
    """
    world = search.world

    crew_options = [option for option in search.options if option.crew_id]
    fallbacks = [option for option in search.options if not option.crew_id]
    ordered = sorted(crew_options, key=lambda o: _ranking_key(world, o))
    if max_options is not None:
        ordered = ordered[:max_options]
    # Cancellation is never truncated away. It is the answer of last resort and
    # dropping it would hide the fact that an answer always exists.
    ordered = [*ordered, *fallbacks]

    legal_options = [
        option_to_cover_option(world, search, option.model_copy(update={"rank": i + 1}))
        for i, option in enumerate(ordered)
    ]
    rejected_options = [
        _reject(world, search, excluded)
        for excluded in sorted(search.excluded, key=lambda e: e.crew_id)
    ]

    return RankedRecommendation(
        situation=search.situation or f"Cover required for {search.assignment_ref}",
        impact=search.impact,
        options=legal_options,
        rejected=list(rejected_options),
        legal_options=legal_options,
        rejected_options=rejected_options,
        candidates_evaluated=search.candidates_evaluated,
        ranking_basis=RANKING_HEURISTIC,
        covering_for=covering_for,
        role=search.role,
        rules_per_candidate=list(ALL_RULE_IDS),
        costs_source="costs.json",
        facts=_facts(search, legal_options, rejected_options),
    )


# ------------------------------------------------------------------- ranking


#: What a crew member's reachability sorts as when the dataset does not record
#: one. Last among equals: an unknown response time is not a fast one, and
#: guessing a number here would put an invented figure into a ranking decision.
_UNKNOWN_REACHABILITY = 10_000


def _ranking_key(world: WorldState, option: RankedOption) -> tuple[int, int, str]:
    """`(cost, reachability, crew_id)`. See `RANKING_HEURISTIC`."""
    member = world.crew_member(option.crew_id) if option.crew_id else None
    reach = getattr(member, "reachability_minutes", None)
    return (
        option.cost_inr,
        _UNKNOWN_REACHABILITY if reach is None else int(reach),
        option.crew_id or "",
    )


# ---------------------------------------------------------------- exclusions


def _reject(
    world: WorldState, search: CoverSearch, excluded: ExcludedCandidate
) -> RejectedCandidate:
    """One reject, with the rule that excluded it lifted to the surface."""
    member = world.crew_member(excluded.crew_id)
    report = (
        excluded.assessment.report
        if excluded.assessment is not None
        else _no_report(search, excluded.crew_id)
    )
    trace = _breaching_trace(report)
    blocking = [issue for issue in report.feasibility_issues if issue.blocking]

    return RejectedCandidate(
        rank=0,
        kind=CoverKind.REASSIGN,
        action=f"Rejected: {excluded.crew_id}",
        crew_id=excluded.crew_id,
        crew_name=member.name if member else excluded.crew_id,
        crew_base=member.base if member else "",
        crew_rank=member.rank if member else search.role,
        legal=False,
        legality=report,
        rules_checked=list(RULES_CHECKED),
        cost=CostBreakdown(
            line_items=[],
            total_inr=0.0,
            note="Not priced: excluded before costing.",
        ),
        coverage_summary="not available",
        covered_flights=[],
        uncovered_flights=list(search.all_flight_ids),
        reachable=member is not None,
        reachability_minutes=member.reachability_minutes if member else None,
        reasoning=excluded.reason,
        tradeoffs=[excluded.reason],
        rule_id=trace.rule_id if trace is not None else None,
        rule_trace=trace,
        feasibility=blocking,
        exclusion_reason=excluded.reason,
    )


def _breaching_trace(report: LegalityReport) -> RuleTrace | None:
    """The first rule that breached, in the engine's own evaluation order.

    First, not worst. When two rules breach for the same person the engine
    evaluated them in the order `rules.json` lists them, and that order is what
    a controller sees on the card beside this text. Picking a different one here
    would put two different reasons on screen for the same exclusion.
    """
    for trace in report.breaches:
        if trace.verdict is Verdict.BREACH:
            return trace
    return None


def _no_report(search: CoverSearch, crew_id: str) -> LegalityReport:
    """A report for an exclusion that happened before the rules engine ran.

    A wrong-base candidate with no positioning flight, or a reserve whose
    on-call window misses the required report, is excluded at step 2 or 3 and
    never reaches the seven rule assessment. Reporting that as seven passes
    would be a lie; reporting it as seven breaches would invent six. Every rule
    is INSUFFICIENT_DATA, which is the contract's own word for "silence about a
    rule is not compliance with it".
    """
    return LegalityReport(
        crew_id=crew_id,
        assignment_ref=search.assignment_ref,
        assignment_kind="pairing",
        overall=Verdict.INSUFFICIENT_DATA,
        per_day=[
            DayLegality(
                duty_date=duty.duty_date,
                verdict=Verdict.INSUFFICIENT_DATA,
                traces=[],
            )
            for duty in search.duties
        ],
        rules_checked=[],
    )


# --------------------------------------------------------------------- facts


def _facts(
    search: CoverSearch,
    legal_options: list[CoverOption],
    rejected_options: list[RejectedCandidate],
) -> list[Fact]:
    """A `Fact` for every figure the rendered answer is allowed to quote.

    The verifier only knows what the facts tell it, so a per-candidate cost that
    the template prints and no fact carries is a number nobody checked. The
    template for this intent prints every candidate's id, cost and rule set, so
    every one of those is attested here rather than left to the payload channel.
    """
    ref = search.assignment_ref
    facts: list[Fact] = [
        Fact(
            key=f"{ref}.candidates_evaluated",
            label="Candidates evaluated",
            value=search.candidates_evaluated,
            unit="count",
            provenance=Provenance.COMPUTED,
            source=SOURCE,
            derivation=(
                f"every active {search.role} in crew.json except the crew member "
                "being replaced, each checked against all seven rules"
            ),
        ),
        Fact(
            key=f"{ref}.legal_options",
            label="Legal options",
            value=len([o for o in legal_options if o.crew_id]),
            unit="count",
            provenance=Provenance.COMPUTED,
            source=SOURCE,
            derivation="candidates clearing all seven rules on every day of the cover",
        ),
        Fact(
            key=f"{ref}.rejected_options",
            label="Rejected candidates",
            value=len(rejected_options),
            unit="count",
            provenance=Provenance.COMPUTED,
            source=SOURCE,
            derivation="candidates found and excluded, each with the rule that excluded it",
        ),
    ]

    for option in legal_options:
        slot = option.crew_id or f"cancel.{option.rank}"
        facts.append(
            Fact(
                key=f"{ref}.option.{slot}.cost",
                label=f"Cost of option {option.rank}",
                value=round(option.cost.total_inr),
                unit="inr",
                provenance=Provenance.COMPUTED,
                source=SOURCE,
                derivation=" + ".join(line.basis for line in option.cost.line_items)
                or "no cost lines",
            )
        )
        if option.crew_id:
            facts.append(
                Fact(
                    key=f"{ref}.option.{slot}.crew_id",
                    label=f"Option {option.rank} crew",
                    value=option.crew_id,
                    unit="crew_id",
                    provenance=Provenance.DATASET,
                    source=f"crew.json#{option.crew_id}",
                )
            )
        if option.reachability_minutes is not None:
            facts.append(
                Fact(
                    key=f"{ref}.option.{slot}.reachability",
                    label=f"Option {option.rank} reachability",
                    value=option.reachability_minutes,
                    unit="minutes",
                    provenance=Provenance.DATASET,
                    source=f"crew.json#{option.crew_id}",
                )
            )

    for reject in rejected_options:
        facts.append(
            Fact(
                key=f"{ref}.rejected.{reject.crew_id}.rule",
                label=f"Rule excluding {reject.crew_id}",
                # The exclusion reason when no rule breached: a feasibility
                # issue is a real exclusion and stating it as a rule id would
                # invent an eighth rule.
                value=reject.rule_id or reject.exclusion_reason,
                unit="text",
                provenance=Provenance.COMPUTED,
                source=SOURCE,
                derivation=(
                    reject.rule_trace.arithmetic
                    if reject.rule_trace is not None
                    else reject.exclusion_reason
                ),
            )
        )
    return facts
