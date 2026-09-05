"""The legality kernel: seven rules, each producing its arithmetic.

No language model is reachable from this module, now or ever. A controller
acts on what is computed here, so every verdict carries the full calculation
that produced it: both operands, the operator, the result and the limit.

Four comparison directions are load-bearing, and each one flips a headline
answer if written the other way round:

* FDP breach is strict `>`. A 12.0h duty against a 12.0h limit is **legal**.
* Rest breach is strict `<`. Exactly 12.0h rest is **legal**.
* Certification validity is `valid_to >= duty_date`. A certificate expiring on
  the duty date is valid **that day**.
* The 7 day and 28 day windows are **calendar UTC dates**, `[end - n + 1, end]`
  inclusive. A rolling 168 hour clock gives different and wrong answers.

Two more invariants that look like bugs and are not:

* **RULE-QUAL-05 short-circuits.** A rating failure suppresses every other
  reason for that candidate. Emitting all reasons produces text that does not
  match the shipped keys even where the verdict agrees.
* **The 7 day add is cumulative across cover days.** On day 2 of a two day
  cover, day 1's cover duty is already inside the window. This is exactly why
  C-2087 breaches on both days and why C-3305 passes day 1 and fails day 2.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from datetime import timedelta
from itertools import pairwise
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from crewops.contracts.evidence import Fact, Provenance
from crewops.contracts.rules import (
    ALL_RULE_IDS,
    DayLegality,
    LegalityReport,
    RuleId,
    RuleTrace,
    Verdict,
)
from crewops.domain import (
    COVER_PAIRING_ID,
    WeekDuty,
    WorldOverlay,
    WorldState,
    add_hours,
    format_duration,
    format_margin,
    hours_between,
)
from crewops.rules import messages
from crewops.rules.limits import (
    DUTY_WINDOW_DAYS,
    EPSILON,
    FDP_BASE_HOURS,
    FDP_FREE_SECTORS,
    FDP_REDUCTION_PER_EXTRA_SECTOR,
    FLIGHT_WINDOW_DAYS,
    MAX_DUTY_HOURS_7D,
    MAX_FLIGHT_HOURS_28D,
    MIN_REST_HOURS,
    RULE_TITLES,
    fdp_limit,
)

_SOURCE = "crewops.rules.engine.LegalityEngine"


class ProposedDuty(BaseModel):
    """One duty day being considered, whether rostered or hypothetical.

    The unit the kernel evaluates. A pairing becomes one of these per day; a
    partial re-crew becomes one with fewer legs, and therefore a different
    sector count and a different FDP limit.
    """

    model_config = ConfigDict(frozen=True)

    duty_date: DateType
    report_utc: DateTime
    release_utc: DateTime
    flight_ids: tuple[str, ...] = ()
    aircraft_type: str = ""
    origin: str = ""
    block_hours: float = 0.0
    source_pairing_id: str | None = None

    @property
    def sectors(self) -> int:
        return len(self.flight_ids)

    @property
    def duty_hours(self) -> float:
        return hours_between(self.report_utc, self.release_utc)

    def shifted(self, hours: float) -> ProposedDuty:
        """Slide the whole duty. Report and release both move, so length holds."""
        if not hours:
            return self
        return self.model_copy(
            update={
                "report_utc": add_hours(self.report_utc, hours),
                "release_utc": add_hours(self.release_utc, hours),
            }
        )


class Positioning(BaseModel):
    """A deadhead that puts a crew member at the departure station in time.

    The only positioning this dataset supports is DEL to BLR. Anything else is
    a RULE-BASE-07 exclusion.
    """

    model_config = ConfigDict(frozen=True)

    from_station: str
    to_station: str
    flight_no: str
    arrival_utc: DateTime
    delay_hours: float


class CoverAssessment(BaseModel):
    """The full result of asking whether one crew member can take one assignment.

    `issues` are the terse exclusion strings in the shipped keys' format and
    order. `report` is the structured per day, per rule evidence. They are
    produced together so they can never disagree.
    """

    model_config = ConfigDict(frozen=True)

    crew_id: str
    ok: bool
    issues: tuple[str, ...] = ()
    report: LegalityReport
    short_circuited: bool = False
    projected_duty_hours: dict[str, float] = {}

    @property
    def reason(self) -> str:
        return "; ".join(self.issues)


def proposed_duties_for_pairing(
    world: WorldState, pairing_id: str, *, days: Sequence[int] | None = None
) -> tuple[ProposedDuty, ...]:
    """Turn a rostered pairing into the duty days a cover would have to fly."""
    pairing = world.require_pairing(pairing_id)
    chosen = range(len(pairing.days)) if days is None else days
    out: list[ProposedDuty] = []
    for index in chosen:
        day = pairing.days[index]
        first = world.require_flight(day.flights[0])
        out.append(
            ProposedDuty(
                duty_date=day.date,
                report_utc=day.report_utc,
                release_utc=day.release_utc,
                flight_ids=day.flights,
                aircraft_type=first.aircraft_type,
                origin=first.dep_station,
                block_hours=world.block_hours_of(day.flights),
                source_pairing_id=pairing.pairing_id,
            )
        )
    return tuple(out)


def proposed_duty_from_flights(
    world: WorldState, flight_ids: Sequence[str]
) -> ProposedDuty:
    """Build a duty day from a bare set of legs.

    Report is the first departure minus 60 minutes and release is the last
    arrival plus 30 minutes, which is how every one of the 42 shipped duty days
    is constructed. Fewer legs means a higher FDP limit, so the sector count is
    taken from this set and never inherited.
    """
    if not flight_ids:
        raise ValueError("A duty day needs at least one leg")
    legs = sorted((world.require_flight(f) for f in flight_ids), key=lambda f: f.dep_utc)
    first, last = legs[0], legs[-1]
    return ProposedDuty(
        duty_date=first.date,
        report_utc=first.dep_utc - timedelta(minutes=60),
        release_utc=last.arr_utc + timedelta(minutes=30),
        flight_ids=tuple(leg.flight_id for leg in legs),
        aircraft_type=first.aircraft_type,
        origin=first.dep_station,
        block_hours=round(sum(leg.block_hours for leg in legs), 2),
        source_pairing_id=None,
    )


class LegalityEngine:
    """Evaluates the seven rules. Deterministic, and the only place they live."""

    def __init__(self, world: WorldState) -> None:
        self.world = world
        book = world.rules
        fdp = book.by_id("RULE-FDP-01")
        duty = book.by_id("RULE-DUTY-02")
        flight = book.by_id("RULE-FLT-03")
        rest = book.by_id("RULE-REST-04")
        self.fdp_base = fdp.param("base_fdp_hours", FDP_BASE_HOURS) if fdp else FDP_BASE_HOURS
        self.fdp_reduction = (
            fdp.param("reduction_per_extra_sector_hours", FDP_REDUCTION_PER_EXTRA_SECTOR)
            if fdp
            else FDP_REDUCTION_PER_EXTRA_SECTOR
        )
        self.fdp_free_sectors = (
            int(fdp.param("free_sectors", FDP_FREE_SECTORS)) if fdp else FDP_FREE_SECTORS
        )
        self.max_duty_7d = duty.param("max_duty_hours", MAX_DUTY_HOURS_7D) if duty else (
            MAX_DUTY_HOURS_7D
        )
        self.duty_window_days = (
            int(duty.param("window_days", DUTY_WINDOW_DAYS)) if duty else DUTY_WINDOW_DAYS
        )
        self.max_flight_28d = (
            flight.param("max_flight_hours", MAX_FLIGHT_HOURS_28D) if flight else (
                MAX_FLIGHT_HOURS_28D
            )
        )
        self.flight_window_days = (
            int(flight.param("window_days", FLIGHT_WINDOW_DAYS)) if flight else FLIGHT_WINDOW_DAYS
        )
        self.min_rest = rest.param("min_rest_hours", MIN_REST_HOURS) if rest else MIN_REST_HOURS

    # ------------------------------------------------------------- helpers

    def fdp_limit_for(self, sectors: int) -> float:
        return fdp_limit(
            sectors,
            base_hours=self.fdp_base,
            reduction=self.fdp_reduction,
            free_sectors=self.fdp_free_sectors,
        )

    def earliest_next_report(self, release: DateTime) -> DateTime:
        """RULE-REST-04 read forwards: release plus the minimum rest."""
        return add_hours(release, self.min_rest)

    @staticmethod
    def _trace(
        rule_id: RuleId,
        verdict: Verdict,
        arithmetic: str,
        *,
        duty_date: DateType | None = None,
        limit: float | None = None,
        observed: float | None = None,
        unit: str | None = None,
        margin: float | None = None,
        inputs: list[Fact] | None = None,
        note: str | None = None,
    ) -> RuleTrace:
        return RuleTrace(
            rule_id=rule_id,
            title=RULE_TITLES[rule_id],
            verdict=verdict,
            duty_date=duty_date,
            limit=limit,
            observed=observed,
            unit=unit,  # type: ignore[arg-type]
            margin=margin,
            margin_human=format_margin(margin) if margin is not None else None,
            arithmetic=arithmetic,
            inputs=inputs or [],
            note=note,
        )

    @staticmethod
    def _computed(
        key: str, label: str, value: float | str | bool, unit: str, derivation: str
    ) -> Fact:
        return Fact(
            key=key,
            label=label,
            value=value,
            unit=unit,  # type: ignore[arg-type]
            provenance=Provenance.COMPUTED,
            source=_SOURCE,
            derivation=derivation,
        )

    @staticmethod
    def _dataset(key: str, label: str, value: float | str | bool, unit: str, source: str) -> Fact:
        return Fact(
            key=key,
            label=label,
            value=value,
            unit=unit,  # type: ignore[arg-type]
            provenance=Provenance.DATASET,
            source=source,
        )

    # ---------------------------------------------------------- RULE-FDP-01

    def check_fdp(
        self,
        *,
        crew_id: str,
        duty_date: DateType,
        sectors: int,
        report: DateTime,
        release: DateTime,
    ) -> RuleTrace:
        """Flight duty period against a sector reduced limit. Breach is strict `>`."""
        observed = hours_between(report, release)
        limit = self.fdp_limit_for(sectors)
        breach = observed > limit + EPSILON
        margin = round(limit - observed, 2)
        arithmetic = (
            f"Report {report:%H:%M}Z to release {release:%H:%M}Z is {observed:.2f}h "
            f"against a {limit:.2f}h limit for {sectors} sectors "
            f"({self.fdp_base:.1f}h base minus {self.fdp_reduction:.1f}h per sector "
            f"beyond {self.fdp_free_sectors}), "
            + (f"over by {abs(margin):.2f}h" if breach else f"{margin:.2f}h spare")
        )
        return self._trace(
            "RULE-FDP-01",
            Verdict.BREACH if breach else Verdict.PASS,
            arithmetic,
            duty_date=duty_date,
            limit=limit,
            observed=observed,
            unit="hours",
            margin=margin,
            inputs=[
                self._computed(
                    f"{crew_id}.{duty_date}.fdp",
                    "Flight duty period",
                    observed,
                    "hours",
                    f"{release:%H:%M} - {report:%H:%M} = {observed:.2f}h",
                ),
                self._computed(
                    f"{crew_id}.{duty_date}.fdp_limit",
                    "FDP limit",
                    limit,
                    "hours",
                    f"{self.fdp_base:.1f} - {self.fdp_reduction:.1f} x "
                    f"max(0, {sectors} - {self.fdp_free_sectors}) = {limit:.2f}h",
                ),
            ],
        )

    # --------------------------------------------------------- RULE-DUTY-02

    def check_duty_window(
        self,
        *,
        crew_id: str,
        duty_date: DateType,
        total: float,
        prior: float,
        added: float,
        label: str = "the proposed assignment",
    ) -> RuleTrace:
        """60 duty hours per 7 calendar days. Breach is strict `>`."""
        limit = self.max_duty_7d
        breach = total > limit + EPSILON
        margin = round(limit - total, 2)
        window = WorldOverlay.window_dates(duty_date, self.duty_window_days)
        arithmetic = (
            f"{prior:.2f}h prior + {added:.2f}h from {label} = {total:.2f}h "
            f"against a {limit:.2f}h limit over {window[0]} to {window[-1]}, "
            + (
                f"over by {abs(margin):.2f}h ({format_duration(abs(margin))})"
                if breach
                else f"{margin:.2f}h spare"
            )
        )
        return self._trace(
            "RULE-DUTY-02",
            Verdict.BREACH if breach else Verdict.PASS,
            arithmetic,
            duty_date=duty_date,
            limit=limit,
            observed=total,
            unit="hours",
            margin=margin,
            inputs=[
                self._computed(
                    f"{crew_id}.{duty_date}.duty_7d.prior",
                    "Duty hours already in the 7 day window",
                    prior,
                    "hours",
                    f"daily_history plus rostered duties over {window[0]} to {window[-1]}",
                ),
                self._computed(
                    f"{crew_id}.{duty_date}.duty_7d.projected",
                    "Projected 7 day duty",
                    total,
                    "hours",
                    f"{prior:.2f} + {added:.2f} = {total:.2f}h",
                ),
            ],
        )

    # ---------------------------------------------------------- RULE-FLT-03

    def check_flight_window(
        self,
        *,
        crew_id: str,
        duty_date: DateType,
        total: float,
        prior: float,
        added: float,
        label: str = "the assignment",
    ) -> RuleTrace:
        """100 block hours per 28 calendar days.

        Correct, cheap, and inert: the peak across all 150 crew and all seven
        dates is 79.28h. It is one of the seven, so it is evaluated and
        reported rather than assumed away.

        `label` names what `added` came from, so the proactive alerting scan can
        say "duties in the next 48 hours" where a cover search says "the
        assignment". The default reproduces the string the shipped keys carry;
        do not change it.
        """
        limit = self.max_flight_28d
        breach = total > limit + EPSILON
        margin = round(limit - total, 2)
        window = WorldOverlay.window_dates(duty_date, self.flight_window_days)
        arithmetic = (
            f"{prior:.2f}h prior block + {added:.2f}h from {label} = {total:.2f}h "
            f"against a {limit:.2f}h limit over {window[0]} to {window[-1]}, "
            + (f"over by {abs(margin):.2f}h" if breach else f"{margin:.2f}h spare")
        )
        return self._trace(
            "RULE-FLT-03",
            Verdict.BREACH if breach else Verdict.PASS,
            arithmetic,
            duty_date=duty_date,
            limit=limit,
            observed=total,
            unit="hours",
            margin=margin,
            inputs=[
                self._computed(
                    f"{crew_id}.{duty_date}.flight_28d.projected",
                    "Projected 28 day block hours",
                    total,
                    "hours",
                    f"{prior:.2f} + {added:.2f} = {total:.2f}h",
                )
            ],
        )

    # --------------------------------------------------------- RULE-REST-04

    def check_rest(
        self,
        *,
        crew_id: str,
        release: DateTime,
        next_report: DateTime,
        prior_ref: str,
        next_ref: str,
        duty_date: DateType,
    ) -> RuleTrace:
        """Rest between one release and the next report. Breach is strict `<`.

        A negative value means the two duties overlap, which is a double
        booking rather than short rest, and is reported separately as well.
        """
        observed = hours_between(release, next_report)
        limit = self.min_rest
        breach = observed < limit - EPSILON
        margin = round(observed - limit, 2)
        arithmetic = (
            f"{prior_ref} releases {release:%Y-%m-%d %H:%M}Z and {next_ref} reports "
            f"{next_report:%Y-%m-%d %H:%M}Z, {observed:.2f}h apart against a "
            f"{limit:.2f}h minimum, "
            + (f"short by {abs(margin):.2f}h" if breach else f"{margin:.2f}h spare")
        )
        return self._trace(
            "RULE-REST-04",
            Verdict.BREACH if breach else Verdict.PASS,
            arithmetic,
            duty_date=duty_date,
            limit=limit,
            observed=observed,
            unit="hours",
            margin=margin,
            inputs=[
                self._computed(
                    f"{crew_id}.{duty_date}.rest.{prior_ref}_{next_ref}",
                    "Rest between duties",
                    observed,
                    "hours",
                    f"{next_report:%H:%M} - {release:%H:%M} = {observed:.2f}h",
                )
            ],
        )

    # --------------------------------------------------------- RULE-QUAL-05

    def check_qualification(
        self, *, crew_id: str, aircraft_type: str, duty_date: DateType
    ) -> RuleTrace:
        """Type rating. Checked first, and it short-circuits every other reason."""
        member = self.world.crew_member(crew_id)
        if member is None:
            return self._trace(
                "RULE-QUAL-05",
                Verdict.INSUFFICIENT_DATA,
                f"No crew record for {crew_id}, so no rating can be established",
                duty_date=duty_date,
            )
        rated = member.is_rated_for(aircraft_type)
        holds = ", ".join(member.ratings)
        arithmetic = (
            f"{crew_id} holds {holds} and the assignment is on {aircraft_type}: "
            + ("rated" if rated else f"not rated for {aircraft_type}")
        )
        return self._trace(
            "RULE-QUAL-05",
            Verdict.PASS if rated else Verdict.BREACH,
            arithmetic,
            duty_date=duty_date,
            unit="boolean",
            inputs=[
                self._dataset(
                    f"{crew_id}.ratings",
                    "Type ratings held",
                    holds,
                    "text",
                    f"crew.json#{crew_id}",
                )
            ],
        )

    # --------------------------------------------------------- RULE-CERT-06

    def check_certifications(self, *, crew_id: str, duty_date: DateType) -> RuleTrace:
        """All four certificates valid on the duty date. The test is `valid_to >= date`.

        `valid_from` is never consulted: it is generated as `valid_to - 730d`
        and never corrected after the engineered expiries, so one record has
        `valid_from > valid_to` and several show a future start for a currently
        flying crew member.
        """
        certs = self.world.certifications_for(crew_id)
        if not certs:
            return self._trace(
                "RULE-CERT-06",
                Verdict.INSUFFICIENT_DATA,
                f"No certification records for {crew_id}",
                duty_date=duty_date,
            )
        expired = [c for c in certs if not c.valid_on(duty_date)]
        if expired:
            detail = ", ".join(f"{c.cert_type} expired {c.valid_to}" for c in expired)
            arithmetic = (
                f"On {duty_date}, {len(expired)} of {len(certs)} certificates "
                f"are out of date: {detail}"
            )
            inputs = [
                self._dataset(
                    f"{crew_id}.cert.{c.cert_type}.valid_to",
                    f"{c.cert_type} expiry",
                    c.valid_to.isoformat(),
                    "date",
                    f"certifications.json#{crew_id}/{c.cert_type}",
                )
                for c in expired
            ]
            return self._trace(
                "RULE-CERT-06",
                Verdict.BREACH,
                arithmetic,
                duty_date=duty_date,
                unit="date",
                inputs=inputs,
            )
        soonest = min(certs, key=lambda c: c.valid_to)
        arithmetic = (
            f"All {len(certs)} certificates are valid on {duty_date}; "
            f"the first to lapse is {soonest.cert_type} on {soonest.valid_to}"
        )
        return self._trace(
            "RULE-CERT-06",
            Verdict.PASS,
            arithmetic,
            duty_date=duty_date,
            unit="date",
            inputs=[
                self._dataset(
                    f"{crew_id}.cert.{soonest.cert_type}.valid_to",
                    f"{soonest.cert_type} expiry",
                    soonest.valid_to.isoformat(),
                    "date",
                    f"certifications.json#{crew_id}/{soonest.cert_type}",
                )
            ],
        )

    # --------------------------------------------------------- RULE-BASE-07

    def check_base(
        self,
        *,
        crew_id: str,
        required_station: str,
        duty_date: DateType,
        positioning: Positioning | None = None,
    ) -> RuleTrace:
        """Own base, or a deadhead that gets them there. Cost applies either way."""
        member = self.world.crew_member(crew_id)
        if member is None:
            return self._trace(
                "RULE-BASE-07",
                Verdict.INSUFFICIENT_DATA,
                f"No crew record for {crew_id}, so no base can be established",
                duty_date=duty_date,
            )
        if member.base == required_station:
            return self._trace(
                "RULE-BASE-07",
                Verdict.PASS,
                f"{crew_id} is based at {member.base}, the departure station: "
                "no positioning required",
                duty_date=duty_date,
                unit="boolean",
                inputs=[
                    self._dataset(
                        f"{crew_id}.base", "Base", member.base, "station", f"crew.json#{crew_id}"
                    )
                ],
            )
        if positioning is None:
            return self._trace(
                "RULE-BASE-07",
                Verdict.BREACH,
                f"{crew_id} is based at {member.base} but the duty departs "
                f"{required_station}, and no same-day positioning flight exists",
                duty_date=duty_date,
                unit="boolean",
            )
        return self._trace(
            "RULE-BASE-07",
            Verdict.PASS,
            f"{crew_id} is based at {member.base} and positions to {required_station} "
            f"on {positioning.flight_no}, arriving {positioning.arrival_utc:%H:%M}Z, "
            f"delaying the first departure by {positioning.delay_hours:.2f}h",
            duty_date=duty_date,
            unit="hours",
            observed=positioning.delay_hours,
            inputs=[
                self._computed(
                    f"{crew_id}.{duty_date}.positioning.delay",
                    "Delay introduced by positioning",
                    positioning.delay_hours,
                    "hours",
                    f"{positioning.flight_no} arrives {positioning.arrival_utc:%H:%M}Z, "
                    f"+75 min to the new first departure",
                )
            ],
        )

    # --------------------------------------------------- the full assessment

    def assess_cover(
        self,
        overlay: WorldOverlay,
        *,
        crew_id: str,
        duties: Sequence[ProposedDuty],
        exclude_pairing: str | None = None,
        positioning: Positioning | None = None,
    ) -> CoverAssessment:
        """Can this crew member take this assignment, on every day of it?

        Evaluation order mirrors the reference implementation that produced the
        shipped answer keys, because the order determines which reason is
        reported when several apply:

        1. RULE-BASE-07, and it short-circuits when no positioning exists.
        2. RULE-QUAL-05, and it short-circuits everything below.
        3. Per cover day: RULE-CERT-06, then RULE-FDP-01.
        4. The candidate's own duties merged with the cover, sorted by report:
           RULE-REST-04 pairwise, then double bookings.
        5. Per cover day: RULE-DUTY-02 with the cumulative add, then RULE-FLT-03.
        """
        if not duties:
            raise ValueError("assess_cover needs at least one proposed duty")

        ordered = sorted(duties, key=lambda d: d.duty_date)
        member = self.world.crew_member(crew_id)
        if member is None:
            return self._insufficient(crew_id, ordered, f"No crew record for {crew_id}")

        delay_hours = positioning.delay_hours if positioning else 0.0
        origin = ordered[0].origin
        aircraft_type = ordered[0].aircraft_type

        per_day: dict[DateType, list[RuleTrace]] = {d.duty_date: [] for d in ordered}
        issues: list[str] = []

        # 1. Base and positioning.
        base_trace = self.check_base(
            crew_id=crew_id,
            required_station=origin,
            duty_date=ordered[0].duty_date,
            positioning=positioning,
        )
        if base_trace.verdict is Verdict.BREACH:
            return self._short_circuit(
                crew_id,
                ordered,
                base_trace,
                messages.no_positioning(member.base),
                skipped="RULE-BASE-07 already excludes this candidate",
            )

        # 2. Qualification, which suppresses every other reason when it fails.
        qual_trace = self.check_qualification(
            crew_id=crew_id, aircraft_type=aircraft_type, duty_date=ordered[0].duty_date
        )
        if qual_trace.verdict is not Verdict.PASS:
            return self._short_circuit(
                crew_id,
                ordered,
                qual_trace,
                messages.qualification_failure(aircraft_type),
                skipped=f"not evaluated: {crew_id} is not rated for {aircraft_type}",
            )

        for day in ordered:
            per_day[day.duty_date].append(
                base_trace.model_copy(update={"duty_date": day.duty_date})
            )
            per_day[day.duty_date].append(
                qual_trace.model_copy(update={"duty_date": day.duty_date})
            )

        # 3. Per day certification and FDP, on the delayed duty if positioning applies.
        shifted = [day.shifted(delay_hours) for day in ordered]
        for day in shifted:
            cert = self.check_certifications(crew_id=crew_id, duty_date=day.duty_date)
            per_day[day.duty_date].append(cert)
            if cert.verdict is Verdict.BREACH:
                issues.append(messages.certification_failure(day.duty_date))

            fdp = self.check_fdp(
                crew_id=crew_id,
                duty_date=day.duty_date,
                sectors=day.sectors,
                report=day.report_utc,
                release=day.release_utc,
            )
            per_day[day.duty_date].append(fdp)
            if fdp.verdict is Verdict.BREACH:
                issues.append(
                    messages.fdp_failure(
                        day.duty_hours, self.fdp_limit_for(day.sectors), day.sectors
                    )
                )

        # 4. Rest and double booking over the merged, sorted duty list.
        merged = self._merge_duties(overlay, crew_id, shifted, exclude_pairing)
        rest_traces, rest_issues, overlap_issues = self._check_sequence(crew_id, merged)
        for duty_date, trace in rest_traces:
            per_day.setdefault(duty_date, []).append(trace)
        issues.extend(rest_issues)
        issues.extend(overlap_issues)

        # 5. Per day duty and flight windows, with the cumulative add.
        projected: dict[str, float] = {}
        for day in ordered:
            duty_trace, duty_total, prior = self._duty_window_for_cover(
                overlay, crew_id, day, ordered, exclude_pairing
            )
            per_day[day.duty_date].append(duty_trace)
            projected[day.duty_date.isoformat()] = duty_total
            if duty_trace.verdict is Verdict.BREACH:
                issues.append(
                    messages.duty_window_failure(duty_total, day.duty_date, limit=self.max_duty_7d)
                )

            flight_trace, flight_total = self._flight_window_for_cover(
                overlay, crew_id, day, ordered, exclude_pairing
            )
            per_day[day.duty_date].append(flight_trace)
            if flight_trace.verdict is Verdict.BREACH:
                issues.append(
                    messages.flight_window_failure(
                        flight_total, day.duty_date, limit=self.max_flight_28d
                    )
                )
            del prior

        report = self._report(crew_id, ordered, per_day, exclude_pairing)
        return CoverAssessment(
            crew_id=crew_id,
            ok=not issues,
            issues=tuple(issues),
            report=report,
            short_circuited=False,
            projected_duty_hours=projected,
        )

    # ------------------------------------------------------------- internals

    def _merge_duties(
        self,
        overlay: WorldOverlay,
        crew_id: str,
        cover: Sequence[ProposedDuty],
        exclude_pairing: str | None,
    ) -> list[WeekDuty]:
        """The candidate's own week, minus the pairing being replaced, plus the cover."""
        merged = [
            duty
            for duty in overlay.week_duties(crew_id)
            if exclude_pairing is None or duty.pairing_id != exclude_pairing
        ]
        merged.extend(
            WeekDuty(
                crew_id=crew_id,
                duty_date=day.duty_date,
                report_utc=day.report_utc,
                release_utc=day.release_utc,
                duty_hours=day.duty_hours,
                block_hours=day.block_hours,
                pairing_id=COVER_PAIRING_ID,
                sectors=day.sectors,
                aircraft_type=day.aircraft_type,
            )
            for day in cover
        )
        merged.sort(key=lambda d: d.report_utc)
        return merged

    def _check_sequence(
        self, crew_id: str, merged: Sequence[WeekDuty]
    ) -> tuple[list[tuple[DateType, RuleTrace]], list[str], list[str]]:
        """Pairwise rest, then pairwise overlap, over the merged duty list."""
        traces: list[tuple[DateType, RuleTrace]] = []
        rest_issues: list[str] = []
        overlap_issues: list[str] = []

        for prior, following in pairwise(merged):
            trace = self.check_rest(
                crew_id=crew_id,
                release=prior.release_utc,
                next_report=following.report_utc,
                prior_ref=prior.pairing_id,
                next_ref=following.pairing_id,
                duty_date=following.duty_date,
            )
            anchor = (
                following.duty_date
                if following.is_cover
                else (prior.duty_date if prior.is_cover else following.duty_date)
            )
            traces.append((anchor, trace))
            if trace.verdict is Verdict.BREACH:
                rest_issues.append(
                    messages.rest_failure(
                        hours_between(prior.release_utc, following.report_utc),
                        following.pairing_id,
                        following.duty_date,
                        downstream=not following.is_cover and prior.is_cover,
                    )
                )

        for prior, following in pairwise(merged):
            if following.report_utc < prior.release_utc:
                overlap_issues.append(
                    messages.double_booking(
                        prior.pairing_id, following.pairing_id, following.duty_date
                    )
                )
        return traces, rest_issues, overlap_issues

    def _window_base(
        self,
        overlay: WorldOverlay,
        crew_id: str,
        day: ProposedDuty,
        exclude_pairing: str | None,
        *,
        days: int,
        kind: str,
    ) -> float:
        """The window total before the cover, with the replaced pairing removed.

        The subtraction matters for a role swap: if the candidate already holds
        a seat on the pairing being covered, their own duties on it must come
        out of the base before the cover goes in, or they are counted twice.
        """
        total = overlay.window_hours(
            crew_id, day.duty_date, days=days, kind="duty" if kind == "duty" else "flight"
        )
        if exclude_pairing is not None:
            start = day.duty_date - timedelta(days=days - 1)
            for duty in overlay.week_duties(crew_id):
                if duty.pairing_id == exclude_pairing and start <= duty.duty_date <= day.duty_date:
                    total -= duty.duty_hours if kind == "duty" else duty.block_hours
        return round(total, 2)

    def _duty_window_for_cover(
        self,
        overlay: WorldOverlay,
        crew_id: str,
        day: ProposedDuty,
        cover: Sequence[ProposedDuty],
        exclude_pairing: str | None,
    ) -> tuple[RuleTrace, float, float]:
        prior = self._window_base(
            overlay, crew_id, day, exclude_pairing, days=self.duty_window_days, kind="duty"
        )
        # Cumulative: every cover day on or before this one is already inside
        # the window. This is the whole reason C-3305 fails on day 2.
        added = round(sum(d.duty_hours for d in cover if d.duty_date <= day.duty_date), 2)
        total = round(prior + added, 2)
        label = (
            cover[0].source_pairing_id
            if cover[0].source_pairing_id
            else "the proposed assignment"
        )
        trace = self.check_duty_window(
            crew_id=crew_id,
            duty_date=day.duty_date,
            total=total,
            prior=prior,
            added=added,
            label=label,
        )
        return trace, total, prior

    def _flight_window_for_cover(
        self,
        overlay: WorldOverlay,
        crew_id: str,
        day: ProposedDuty,
        cover: Sequence[ProposedDuty],
        exclude_pairing: str | None,
    ) -> tuple[RuleTrace, float]:
        prior = self._window_base(
            overlay, crew_id, day, exclude_pairing, days=self.flight_window_days, kind="flight"
        )
        added = round(sum(d.block_hours for d in cover if d.duty_date <= day.duty_date), 2)
        total = round(prior + added, 2)
        trace = self.check_flight_window(
            crew_id=crew_id, duty_date=day.duty_date, total=total, prior=prior, added=added
        )
        return trace, total

    def _report(
        self,
        crew_id: str,
        duties: Sequence[ProposedDuty],
        per_day: dict[DateType, list[RuleTrace]],
        exclude_pairing: str | None,
    ) -> LegalityReport:
        days: list[DayLegality] = []
        for duty in duties:
            traces = self._complete(duty.duty_date, per_day.get(duty.duty_date, []))
            verdict = self._worst(traces)
            days.append(DayLegality(duty_date=duty.duty_date, verdict=verdict, traces=traces))
        return LegalityReport(
            crew_id=crew_id,
            assignment_ref=self._assignment_ref(duties, exclude_pairing),
            assignment_kind="pairing" if duties[0].source_pairing_id else "flight_set",
            overall=self._worst_day(days),
            per_day=days,
            rules_checked=list(ALL_RULE_IDS),
        )

    #: Why a rule can legitimately have nothing to evaluate on a given day.
    _NOT_APPLICABLE_NOTES: ClassVar[dict[str, str]] = {
        "RULE-REST-04": (
            "No adjacent duty on either side of this date, so there is no rest "
            "interval to measure"
        ),
    }

    def _complete(self, duty_date: DateType, traces: list[RuleTrace]) -> list[RuleTrace]:
        """Ensure all seven rules appear for the day, in rule id order.

        A rule with nothing to evaluate is NOT_APPLICABLE with the reason
        stated. It is never simply absent, because an absent rule reads as a
        passing rule and that is exactly the failure mode this system exists to
        prevent.
        """
        present = {t.rule_id for t in traces}
        filled = list(traces)
        for rule_id in ALL_RULE_IDS:
            if rule_id in present:
                continue
            note = self._NOT_APPLICABLE_NOTES.get(
                rule_id, "Nothing to evaluate for this rule on this date"
            )
            filled.append(
                self._trace(rule_id, Verdict.NOT_APPLICABLE, note, duty_date=duty_date, note=note)
            )
        order = {rule_id: index for index, rule_id in enumerate(ALL_RULE_IDS)}
        filled.sort(key=lambda t: order[t.rule_id])
        return filled

    @staticmethod
    def _assignment_ref(duties: Sequence[ProposedDuty], exclude_pairing: str | None) -> str:
        if duties[0].source_pairing_id:
            return duties[0].source_pairing_id
        if exclude_pairing:
            return exclude_pairing
        return ", ".join(f for day in duties for f in day.flight_ids)

    @staticmethod
    def _worst(traces: Sequence[RuleTrace]) -> Verdict:
        """A day is as good as its worst rule. Never an average, never a majority."""
        if any(t.verdict is Verdict.BREACH for t in traces):
            return Verdict.BREACH
        if any(t.verdict is Verdict.INSUFFICIENT_DATA for t in traces):
            return Verdict.INSUFFICIENT_DATA
        return Verdict.PASS

    @staticmethod
    def _worst_day(days: Sequence[DayLegality]) -> Verdict:
        """Legal on day one and breaching on day two is not a legal candidate."""
        if any(d.verdict is Verdict.BREACH for d in days):
            return Verdict.BREACH
        if any(d.verdict is Verdict.INSUFFICIENT_DATA for d in days):
            return Verdict.INSUFFICIENT_DATA
        return Verdict.PASS

    def _placeholder_traces(
        self, duty_date: DateType, decided: RuleTrace | None, note: str
    ) -> list[RuleTrace]:
        """Rules that were not reached, marked as unknown rather than as passing.

        Silence about a rule is not compliance with it, so these are
        INSUFFICIENT_DATA and never PASS.
        """
        traces: list[RuleTrace] = []
        for rule_id in ALL_RULE_IDS:
            if decided is not None and rule_id == decided.rule_id:
                traces.append(decided.model_copy(update={"duty_date": duty_date}))
                continue
            traces.append(
                self._trace(
                    rule_id,
                    Verdict.INSUFFICIENT_DATA,
                    note,
                    duty_date=duty_date,
                    note=note,
                )
            )
        return traces

    def _short_circuit(
        self,
        crew_id: str,
        duties: Sequence[ProposedDuty],
        decided: RuleTrace,
        message: str,
        *,
        skipped: str,
    ) -> CoverAssessment:
        per_day = {
            duty.duty_date: self._placeholder_traces(duty.duty_date, decided, skipped)
            for duty in duties
        }
        return CoverAssessment(
            crew_id=crew_id,
            ok=False,
            issues=(message,),
            report=self._report(crew_id, duties, per_day, None),
            short_circuited=True,
        )

    def _insufficient(
        self, crew_id: str, duties: Sequence[ProposedDuty], note: str
    ) -> CoverAssessment:
        per_day = {
            duty.duty_date: self._placeholder_traces(duty.duty_date, None, note) for duty in duties
        }
        return CoverAssessment(
            crew_id=crew_id,
            ok=False,
            issues=(note,),
            report=self._report(crew_id, duties, per_day, None),
            short_circuited=True,
        )


__all__ = [
    "CoverAssessment",
    "LegalityEngine",
    "Positioning",
    "ProposedDuty",
    "proposed_duties_for_pairing",
    "proposed_duty_from_flights",
]
