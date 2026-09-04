"""The tool surface: the contract between the deterministic core and the agent.

This is the seam. `crewops.tools` implements `ToolSurface` over the rules and
ops engines. `crewops.agent` binds those methods as LangGraph tools and never
reaches past them into the core. Neither side edits this file: if a signature
needs to change, that is a conversation, not a commit.

Every method returns a `ToolEnvelope`, so every result carries its own facts,
trace and citations. There is no path by which the agent receives a number it
cannot attribute.

Design rules for anyone extending this surface:

1. A tool answers a question a controller would actually ask. It is not a thin
   wrapper over a JSON file.
2. A tool never returns free prose the model is expected to trust. It returns
   structured payloads plus facts.
3. A tool that cannot answer returns `ok=False` with a specific `error`. It
   does not return an empty result that reads like a negative finding, because
   "no crew found" and "the lookup failed" are different answers.
4. Every numeric field in a payload has a matching `Fact` in the envelope.
   The verifier only knows what the facts tell it.
5. A tool must be reachable for every file in the dataset. An unreachable file
   is a question we silently cannot answer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Protocol, runtime_checkable

from crewops.contracts.evidence import ToolEnvelope

TimeOfDay = Literal["morning", "afternoon", "evening", "night", "any"]

#: Pre-departure slides both report and release. Mid-duty extends the release
#: only, so the flight duty period grows while the report time stays put. The
#: shipped answer keys use both: scenario S4 and Q20 are pre-departure, S3 and
#: Q35 are mid-duty. A single delay model reproduces neither reliably.
DelayMode = Literal["pre_departure", "mid_duty"]

#: What a joint plan optimises for when two gaps compete for one candidate.
JointObjective = Literal["min_cost", "max_coverage", "min_delay"]


@runtime_checkable
class ToolSurface(Protocol):
    """Implemented by `crewops.tools.registry.Tools`. Consumed by the agent."""

    # ---------------------------------------------------------------- tier 1
    # Lookup and retrieval. Answerable directly from the data.

    def find_crew(
        self,
        *,
        base: str | None = None,
        rank: str | None = None,
        aircraft_type: str | None = None,
        on_reserve_date: date | None = None,
        available_on: date | None = None,
        name_contains: str | None = None,
        crew_ids: list[str] | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> ToolEnvelope:
        """Crew matching a filter set. An empty result is a finding, not an error.

        `status` filters on the dataset's own crew status. Note that candidate
        enumeration drops non-active crew silently, so a caller looking for
        eligibility should not rely on this filter to explain an exclusion.
        """
        ...

    def get_crew_detail(self, *, crew_id: str, as_of: datetime | None = None) -> ToolEnvelope:
        """One crew member, fully resolved.

        Returns roster, duty clocks with headroom, certifications with validity,
        reserve status and window, and the precomputed disruption risk signal.
        This is the tool the agent reaches for when a question names a person,
        so it must return enough that a follow up rarely needs a second call.
        """
        ...

    def find_flights(
        self,
        *,
        origin: str | None = None,
        destination: str | None = None,
        on_date: date | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        time_of_day: TimeOfDay = "any",
        flight_numbers: list[str] | None = None,
        pairing_id: str | None = None,
        aircraft_type: str | None = None,
        registration: str | None = None,
        limit: int = 200,
    ) -> ToolEnvelope:
        """Flights matching a filter set.

        `limit` is a safety cap, not a page size. It defaults above the size of
        the whole schedule so an unfiltered query is complete rather than
        quietly truncated. Set `truncated=True` on the envelope if it ever bites.

        `registration` filters by aircraft tail. Questions that name a tail
        cannot reach a pairing any other way.
        """
        ...

    def find_pairings(
        self,
        *,
        registration: str | None = None,
        on_date: date | None = None,
        base: str | None = None,
        aircraft_type: str | None = None,
        crew_id: str | None = None,
        flight_number: str | None = None,
        limit: int = 100,
    ) -> ToolEnvelope:
        """Pairings matching a filter set.

        The route from an aircraft tail or a single leg back to the pairing that
        contains it. Without this, a question naming a tail is unanswerable.
        """
        ...

    def get_duty_clocks(self, *, crew_id: str, as_of: datetime | None = None) -> ToolEnvelope:
        """Duty and flight hour state with remaining headroom under each limit.

        Must return the consumed figure and the headroom, because "how many duty
        hours does C-1042 have left" is a headroom question, not a total.
        """
        ...

    def list_reserves(
        self,
        *,
        on_date: date,
        base: str | None = None,
        aircraft_type: str | None = None,
        rank: str | None = None,
        at_time: datetime | None = None,
    ) -> ToolEnvelope:
        """Reserve crew with on-call windows and availability for a date.

        Window containment is inclusive at both ends, and it is tested against
        the required report time rather than the callout time.
        """
        ...

    def find_expiring_certifications(
        self,
        *,
        within_days: int = 30,
        as_of: date | None = None,
        certification_type: str | None = None,
        base: str | None = None,
    ) -> ToolEnvelope:
        """Licences, medicals and recurrent training lapsing inside a window.

        Validity is decided on `valid_to` alone. The `valid_from` field in the
        shipped data is unreliable and must not be used. See docs/DATA-MODEL.md.
        """
        ...

    def get_pairing(self, *, pairing_id: str) -> ToolEnvelope:
        """A pairing with every duty day, every leg, and the crew assigned."""
        ...

    def get_roster(
        self, *, crew_id: str, from_date: date | None = None, to_date: date | None = None
    ) -> ToolEnvelope:
        """One crew member's assignments across a date range."""
        ...

    def find_crew_at_risk(
        self,
        *,
        min_score: float | None = None,
        base: str | None = None,
        on_date: date | None = None,
        limit: int = 20,
    ) -> ToolEnvelope:
        """Crew ranked by the precomputed disruption risk signal.

        The risk scores are provided, not modelled by us. The problem statement
        is explicit that building a prediction model is out of scope: treat
        these like a weather forecast and reason about what to do with them.
        """
        ...

    def aggregate(
        self,
        *,
        collection: Literal["flights", "crew", "pairings", "certifications", "reserves"],
        metric: Literal["count", "sum", "max", "min", "mean", "distinct"],
        field: str | None = None,
        group_by: str | None = None,
        filters: dict[str, str | int | float | bool | None] | None = None,
        limit: int = 50,
    ) -> ToolEnvelope:
        """Counts, extrema, distinct values and grouped totals.

        Questions like "how many", "which is the longest" and "which stations do
        we serve" are aggregations. Without this the agent has to pull a whole
        collection and count it in prose, which is exactly the arithmetic it is
        forbidden from doing. Every returned figure carries a `Fact`.
        """
        ...

    def get_cost_rates(self, *, rate_key: str | None = None) -> ToolEnvelope:
        """The cost model as shipped: rates, units and currency.

        Lets the system answer "what does a callout cost" without the model
        recalling a rate from a prompt. Omit `rate_key` for the whole table.
        """
        ...

    # ---------------------------------------------------------------- tier 2
    # Consequence and simulation. Reasoning about impact, not retrieval.

    def check_legality(
        self,
        *,
        crew_id: str | None = None,
        crew_ids: list[str] | None = None,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        on_date: date | None = None,
        as_replacement_for: str | None = None,
        added_duty_hours: float | None = None,
        added_flight_hours: float | None = None,
    ) -> ToolEnvelope:
        """Evaluate all seven rules for a crew member taking an assignment.

        Pass `crew_ids` to check several people against the same assignment in
        one call. It returns exactly what the individual calls return, and
        exists because asking once per crew member is a model round trip each
        time: the six-crew version of this question used to spend most of the
        turn budget on the asking rather than the computing.

        Returns a `LegalityReport`. For a multi-day pairing that is one
        `DayLegality` per day, and the overall verdict is the worst day. Never
        collapse a multi-day check into a single verdict without the per-day
        detail: that is the `C-3305` trap, legal on day one and breaching on
        day two.

        `added_duty_hours` and `added_flight_hours` evaluate a hypothetical
        without naming a concrete assignment, for questions of the form "how
        much more could this crew member fly".

        Two behaviours the shipped answer keys require:

        - RULE-REST-04 is checked **forward as well as backward**, against the
          candidate's own next rostered duty for up to two days after the cover.
          A backward-only check wrongly passes several candidates and produces
          the wrong ranked list on the flagship scenario.
        - A double booking (the candidate is already rostered across the cover
          window) is a **feasibility** failure, not a regulatory one. Report it,
          but never give it a `RULE-` id: seven rules is the full regulatory
          scope and inventing an eighth misrepresents the rulebook.
        """
        ...

    def simulate_absence(
        self,
        *,
        crew_id: str,
        from_date: date,
        to_date: date | None = None,
        reason: str = "sick call",
    ) -> ToolEnvelope:
        """Model a crew member becoming unavailable.

        Returns an `ImpactReport`: which flights are now uncrewed, which
        pairings broke, how many passengers are exposed, and which other crew
        move closer to a limit as a result.
        """
        ...

    def simulate_reassignment(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        displacing_crew_id: str | None = None,
    ) -> ToolEnvelope:
        """Model moving a crew member onto an assignment.

        Answers "if I move FO C-2087 onto DX412, does anyone breach a duty
        limit". Must check the mover, the displaced crew, and downstream legs.
        """
        ...

    def simulate_station_closure(
        self,
        *,
        station: str,
        from_time: datetime,
        to_time: datetime,
    ) -> ToolEnvelope:
        """Model a station closing for a window and report the crew impact.

        The window is half open, `[from_time, to_time)`. The delay anchors on
        the affected station event and the recovery target is reopen plus the
        turnaround allowance. See docs/DATA-MODEL.md for the verified model.
        """
        ...

    def simulate_delay(
        self,
        *,
        flight_number: str,
        delay_minutes: int,
        on_date: date | None = None,
        mode: DelayMode = "pre_departure",
    ) -> ToolEnvelope:
        """Model a single flight running late and cascade the consequence.

        `mode` selects which of the two delay models applies, and the choice
        changes the answer:

        - `pre_departure` slides report and release together, so duty length is
          unchanged but the whole duty moves later.
        - `mid_duty` extends the release only, so the flight duty period grows
          against a fixed report time and RULE-FDP-01 can breach.

        Dropping a leg changes the sector count and therefore the FDP limit, so
        recompute the limit rather than reusing the rostered one.
        """
        ...

    def scan_duty_headroom(
        self,
        *,
        on_date: date,
        threshold_hours: float | None = None,
        base: str | None = None,
        rank: str | None = None,
        aircraft_type: str | None = None,
        limit: int = 50,
    ) -> ToolEnvelope:
        """Fleet wide sweep for crew approaching a duty or flight hour limit.

        One call, not one call per crew member. This is what makes the proactive
        watchlist and "who is close to a limit tomorrow" answerable inside a
        sensible latency budget.
        """
        ...

    def earliest_report(
        self,
        *,
        released_at: str | None = None,
        crew_id: str | None = None,
    ) -> ToolEnvelope:
        """RULE-REST-04 read forwards: when may this crew next report?

        Give a release time, or a crew member whose last release is on record.
        Returns the earliest legal report time with the arithmetic behind it.

        This exists so the answer to "a crew is released at 15:30Z, when can
        they report next" is computed rather than added up by the model. Adding
        twelve hours to a timestamp is exactly the arithmetic the boundary
        keeps out of a language model, and without a tool for it the question
        is one the system must decline.
        """
        ...

    # ---------------------------------------------------------------- tier 3
    # Recommendation. Ranking legal options against real trade-offs.

    def find_cover_options(
        self,
        *,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        for_crew_id: str | None = None,
        role: str | None = None,
        on_date: date | None = None,
        exclude_crew_ids: list[str] | None = None,
        max_options: int = 5,
        include_rejected: bool = True,
    ) -> ToolEnvelope:
        """Enumerate, check, price and rank every way to cover a gap.

        **`for_crew_id` or `role` is required.** A pairing carries a full crew
        complement, so "cover P-2291" is ambiguous until you say whose seat is
        empty. Candidate enumeration filters on an exact rank match and the
        callout rate differs by role, so without this the search returns the
        wrong candidates at the wrong price. Pass `for_crew_id` when replacing a
        named person, or `role` when the seat is known but the person is not.

        Returns a `Recommendation`. `rejected` carries the candidates that were
        found and excluded, each with the `RuleTrace` that excluded them,
        because showing the rejects is what proves the search was real.
        """
        ...

    def plan_joint_cover(
        self,
        *,
        gaps: list[dict[str, str]],
        objective: JointObjective = "min_cost",
        max_options: int = 3,
    ) -> ToolEnvelope:
        """Cover two or more simultaneous gaps as one allocation problem.

        Each entry in `gaps` names a pairing or flight set and the crew or role
        being replaced, in the same shape `find_cover_options` accepts.

        **This tool exists because solving the gaps independently is unsafe.**
        Two separate searches can return the same candidate as rank 1 for both,
        and naively composing them puts one captain on two aircraft at once.
        That is a fluent, confident, operationally wrong instruction, which is
        the single worst failure mode this system can have. A joint plan must
        enforce that no crew member is allocated twice.

        If a feasible joint allocation does not exist, say so explicitly rather
        than returning the best independent pair.
        """
        ...

    def draft_notification(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        channel: Literal["sms", "email", "app"] = "sms",
        option_rank: int | None = None,
    ) -> ToolEnvelope:
        """Draft the message to the crew member being called out.

        A deterministic template filled from computed facts. The agent may adjust
        tone. It may not introduce a time, a flight number or a report location
        the template did not supply.
        """
        ...

    # ---------------------------------------------------------- cross cutting

    def get_watchlist(self, *, for_date: date, as_of: datetime | None = None) -> ToolEnvelope:
        """The proactive brief: what is about to go wrong on this date."""
        ...

    def get_world_summary(self) -> ToolEnvelope:
        """Dataset shape, snapshot time, stations and fleet.

        Grounds scope questions and lets the system say honestly what it does
        and does not cover.
        """
        ...

    def explain_rule(self, *, rule_id: str) -> ToolEnvelope:
        """The machine readable definition of one rule, as shipped.

        Lets the system answer "why" questions about the rulebook without the
        model paraphrasing regulation from memory.
        """
        ...


#: Canonical tool names. The agent binds exactly these. Keep in sync with the
#: `ToolSurface` protocol methods: `tests/test_boundary.py` asserts they match.
TOOL_NAMES: tuple[str, ...] = (
    # tier 1, retrieval
    "find_crew",
    "get_crew_detail",
    "find_flights",
    "find_pairings",
    "get_duty_clocks",
    "list_reserves",
    "find_expiring_certifications",
    "get_pairing",
    "get_roster",
    "find_crew_at_risk",
    "aggregate",
    "get_cost_rates",
    # tier 2, consequence
    "check_legality",
    "simulate_absence",
    "simulate_reassignment",
    "simulate_station_closure",
    "simulate_delay",
    "scan_duty_headroom",
    "earliest_report",
    # tier 3, recommendation
    "find_cover_options",
    "plan_joint_cover",
    "draft_notification",
    # cross cutting
    "get_watchlist",
    "get_world_summary",
    "explain_rule",
)

#: Tools that cannot, on their own, support a Tier 2 or Tier 3 answer.
#: Retrieval establishes what is. It does not establish what follows.
RETRIEVAL_ONLY: frozenset[str] = frozenset(
    {
        "find_crew",
        "get_crew_detail",
        "find_flights",
        "find_pairings",
        "get_duty_clocks",
        "list_reserves",
        "find_expiring_certifications",
        "get_pairing",
        "get_roster",
        "find_crew_at_risk",
        "aggregate",
        "get_cost_rates",
        "get_world_summary",
        "explain_rule",
    }
)

#: Tools whose result is required before the system may assert a legality
#: verdict, a consequence, or a ranked recommendation. Enforced in the graph.
REQUIRED_FOR: dict[str, frozenset[str]] = {
    # `earliest_report` belongs here: it evaluates RULE-REST-04 and returns a
    # rule trace, so "they may report at 03:30Z" is a computed verdict on the
    # same footing as any other. Leaving it out made the guard refuse an answer
    # the rules engine had genuinely produced.
    "legality_claim": frozenset(
        {
            "check_legality",
            "find_cover_options",
            "plan_joint_cover",
            "simulate_reassignment",
            "earliest_report",
        }
    ),
    "consequence_claim": frozenset(
        {
            "simulate_absence",
            "simulate_reassignment",
            "simulate_station_closure",
            "simulate_delay",
            "scan_duty_headroom",
            "earliest_report",
        }
    ),
    "recommendation_claim": frozenset({"find_cover_options", "plan_joint_cover"}),
}

__all__ = [
    "REQUIRED_FOR",
    "RETRIEVAL_ONLY",
    "TOOL_NAMES",
    "DelayMode",
    "JointObjective",
    "TimeOfDay",
    "ToolSurface",
]
