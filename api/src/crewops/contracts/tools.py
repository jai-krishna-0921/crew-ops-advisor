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
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Protocol, runtime_checkable

from crewops.contracts.evidence import ToolEnvelope

TimeOfDay = Literal["morning", "afternoon", "evening", "night", "any"]


@runtime_checkable
class ToolSurface(Protocol):
    """Implemented by `crewops.tools.registry.Tools`. Consumed by the agent."""

    # ---------------------------------------------------------------- tier 1
    # Lookup and retrieval. Answerable directly from the dataset.

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
        limit: int = 50,
    ) -> ToolEnvelope:
        """Crew matching a filter set. Empty result is a finding, not an error."""
        ...

    def get_crew_detail(self, *, crew_id: str, as_of: datetime | None = None) -> ToolEnvelope:
        """One crew member with roster, duty clocks, certifications and reserve status.

        This is the tool the agent reaches for when a question names a person.
        It must return enough that a follow up question rarely needs a second call.
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
        limit: int = 100,
    ) -> ToolEnvelope:
        """Flights matching a filter set."""
        ...

    def get_duty_clocks(self, *, crew_id: str, as_of: datetime | None = None) -> ToolEnvelope:
        """Duty and flight hour state with remaining headroom under each limit.

        Must return both the consumed figure and the headroom, because
        "how many duty hours does C-1042 have left" is a headroom question.
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
        """Reserve crew with on-call windows and standby status for a date."""
        ...

    def find_expiring_certifications(
        self,
        *,
        within_days: int = 30,
        as_of: date | None = None,
        certification_type: str | None = None,
        base: str | None = None,
    ) -> ToolEnvelope:
        """Licences, medicals and recurrent training lapsing inside a window."""
        ...

    def get_pairing(self, *, pairing_id: str) -> ToolEnvelope:
        """A pairing with every duty day, every leg, and the crew assigned."""
        ...

    def get_roster(
        self, *, crew_id: str, from_date: date | None = None, to_date: date | None = None
    ) -> ToolEnvelope:
        """One crew member's assignments across a date range."""
        ...

    # ---------------------------------------------------------------- tier 2
    # Consequence and simulation. Reasoning about impact, not retrieval.

    def check_legality(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        on_date: date | None = None,
        as_replacement_for: str | None = None,
    ) -> ToolEnvelope:
        """Evaluate all seven rules for a crew member taking an assignment.

        Returns a `LegalityReport` payload. For a multi-day pairing this is one
        `DayLegality` per day and the overall verdict is the worst day. Never
        collapse a multi-day check into a single verdict without the per-day
        detail: that is the `C-3305` trap.
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
        """Model a station closing for a window and report the crew impact."""
        ...

    # ---------------------------------------------------------------- tier 3
    # Recommendation. Ranking legal options against real trade-offs.

    def find_cover_options(
        self,
        *,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        exclude_crew_ids: list[str] | None = None,
        max_options: int = 5,
        include_rejected: bool = True,
    ) -> ToolEnvelope:
        """Enumerate, check, price and rank every way to cover a gap.

        Returns a `Recommendation` payload. `rejected` carries the candidates
        that were found and excluded, each with the RuleTrace that excluded
        them, because showing the rejects is what proves the search was real.
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

        Deterministic template filled from computed facts. The agent may adjust
        tone. It may not introduce a time, a flight number or a report location
        the template did not supply.
        """
        ...

    # ---------------------------------------------------------- cross cutting

    def get_watchlist(self, *, for_date: date, as_of: datetime | None = None) -> ToolEnvelope:
        """The proactive brief: what is about to go wrong on this date."""
        ...

    def get_world_summary(self) -> ToolEnvelope:
        """Dataset shape and snapshot time. Used to ground scope questions and
        to let the system say honestly what it does and does not cover."""
        ...

    def explain_rule(self, *, rule_id: str) -> ToolEnvelope:
        """The machine readable definition of one rule, as shipped.

        Lets the system answer "why" questions about the rulebook without the
        model paraphrasing regulation from memory.
        """
        ...


#: Canonical tool names. The agent binds exactly these, in this order of
#: preference when several could answer. Keep in sync with `ToolSurface`.
TOOL_NAMES: tuple[str, ...] = (
    "find_crew",
    "get_crew_detail",
    "find_flights",
    "get_duty_clocks",
    "list_reserves",
    "find_expiring_certifications",
    "get_pairing",
    "get_roster",
    "check_legality",
    "simulate_absence",
    "simulate_reassignment",
    "simulate_station_closure",
    "find_cover_options",
    "draft_notification",
    "get_watchlist",
    "get_world_summary",
    "explain_rule",
)

#: Tools that must never be the only call behind a Tier 2 or Tier 3 answer.
#: Retrieval alone cannot establish a consequence.
RETRIEVAL_ONLY: frozenset[str] = frozenset(
    {
        "find_crew",
        "get_crew_detail",
        "find_flights",
        "get_duty_clocks",
        "list_reserves",
        "find_expiring_certifications",
        "get_pairing",
        "get_roster",
        "get_world_summary",
        "explain_rule",
    }
)

__all__ = ["RETRIEVAL_ONLY", "TOOL_NAMES", "TimeOfDay", "ToolSurface"]
