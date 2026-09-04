"""`OpsEngine`: one object that owns the operations layer.

The tool registry holds one of these and reaches for nothing else. Keeping the
composition here rather than in `tools/` means the operations engine is usable
and testable without the tool surface, which is what lets the golden tests
compare directly against the shipped answer keys.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812

from crewops.contracts.ops import ImpactReport, Watchlist
from crewops.domain import WorldOverlay, WorldState
from crewops.ops.candidates import CandidateSearcher, CoverSearch
from crewops.ops.disruption import ClosureResult, DelayResult, DisruptionSimulator
from crewops.ops.joint import JointPlan, allocate
from crewops.ops.positioning import plan_positioning
from crewops.ops.watchlist import WatchlistBuilder
from crewops.rules import (
    LegalityEngine,
    Positioning,
    ProposedDuty,
    proposed_duties_for_pairing,
    proposed_duty_from_flights,
)


class OpsEngine:
    """Candidate search, costing, ranking, simulation and the watchlist."""

    def __init__(self, world: WorldState, engine: LegalityEngine | None = None) -> None:
        self.world = world
        self.rules = engine or LegalityEngine(world)
        self.searcher = CandidateSearcher(world, self.rules)
        self.simulator = DisruptionSimulator(world, self.rules)
        self.watchlist = WatchlistBuilder(world, self.rules)

    # ------------------------------------------------------------ cover search

    def find_cover_for_pairing(
        self,
        pairing_id: str,
        *,
        role: str,
        sick_crew_id: str | None = None,
        overlay: WorldOverlay | None = None,
        forbid_crew: Iterable[str] = (),
        situation: str = "",
        impact: ImpactReport | None = None,
    ) -> CoverSearch:
        """Every way to cover a pairing in one role, checked, priced and ranked.

        `sick_crew_id` defaults to the crew member currently holding that role
        on the pairing, because that is what a controller means when they name
        a pairing and a role without naming a person.
        """
        pairing = self.world.require_pairing(pairing_id)
        if sick_crew_id is None:
            holders = pairing.crew_in_role(role)
            sick_crew_id = holders[0] if holders else None
        duties = proposed_duties_for_pairing(self.world, pairing_id)
        return self.searcher.search(
            duties,
            role=role,
            sick_crew_id=sick_crew_id,
            exclude_pairing=pairing_id,
            overlay=overlay,
            forbid_crew=forbid_crew,
            situation=situation
            or f"{role} cover required for {pairing_id} on {pairing.days[0].date}",
            impact=impact,
        )

    def find_cover_for_flights(
        self,
        flight_ids: Sequence[str],
        *,
        role: str,
        sick_crew_id: str | None = None,
        overlay: WorldOverlay | None = None,
        forbid_crew: Iterable[str] = (),
    ) -> CoverSearch:
        """Cover for a bare set of legs, for example one leg of a broken duty.

        The sector count comes from this set, so the FDP limit is recomputed
        rather than inherited from the original duty.
        """
        duty = proposed_duty_from_flights(self.world, flight_ids)
        pairing = self.world.pairing_for_flight(flight_ids[0])
        return self.searcher.search(
            [duty],
            role=role,
            sick_crew_id=sick_crew_id,
            exclude_pairing=pairing.pairing_id if pairing else None,
            overlay=overlay,
            forbid_crew=forbid_crew,
            situation=f"{role} cover required for {', '.join(flight_ids)}",
        )

    # ----------------------------------------------------------- positioning

    def positioning_for(
        self,
        *,
        crew_id: str,
        origin: str,
        on_date: DateType,
        first_departure_utc: DateTime,
    ) -> Positioning | None:
        return plan_positioning(
            self.world,
            crew_id=crew_id,
            required_station=origin,
            on_date=on_date,
            first_departure_utc=first_departure_utc,
        )

    # ------------------------------------------------------ joint allocation

    def allocate_jointly(
        self,
        gaps: Sequence[tuple[str, str, str | None]],
        *,
        forbid_crew: Iterable[str] = (),
    ) -> JointPlan:
        """Fill several simultaneous gaps at once, never using the same person twice.

        Each gap is `(pairing_id, role, sick_crew_id)`. The searches run
        independently and the allocation is solved across their results,
        because two sick calls competing for one reserve is a single problem,
        not two.
        """
        searches = [
            self.find_cover_for_pairing(
                pairing_id, role=role, sick_crew_id=sick, forbid_crew=forbid_crew
            )
            for pairing_id, role, sick in gaps
        ]
        return allocate(searches)

    # --------------------------------------------------------- simulation

    def simulate_absence(
        self,
        *,
        crew_id: str,
        from_date: DateType,
        to_date: DateType | None = None,
        reason: str = "sick call",
        as_of: DateTime | None = None,
    ) -> tuple[ImpactReport, WorldOverlay]:
        return self.simulator.absence(
            crew_id=crew_id, from_date=from_date, to_date=to_date, reason=reason, as_of=as_of
        )

    def simulate_station_closure(
        self, *, station: str, from_time: DateTime, to_time: DateTime
    ) -> ClosureResult:
        return self.simulator.station_closure(
            station=station, from_time=from_time, to_time=to_time
        )

    def simulate_delay(
        self, *, pairing_id: str, on_date: DateType, delay_hours: float
    ) -> DelayResult:
        return self.simulator.whole_duty_delay(
            pairing_id=pairing_id, on_date=on_date, delay_hours=delay_hours
        )

    def simulate_reassignment(
        self,
        *,
        crew_id: str,
        duties: Sequence[ProposedDuty],
        assignment_ref: str,
        displacing_crew_id: str | None = None,
        exclude_pairing: str | None = None,
    ) -> ImpactReport:
        return self.simulator.reassignment(
            crew_id=crew_id,
            duties=duties,
            assignment_ref=assignment_ref,
            displacing_crew_id=displacing_crew_id,
            exclude_pairing=exclude_pairing,
        )

    # ---------------------------------------------------------- watchlist

    def build_watchlist(
        self, *, for_date: DateType, as_of: DateTime | None = None
    ) -> Watchlist:
        return self.watchlist.build(for_date=for_date, as_of=as_of)


__all__ = ["OpsEngine"]
