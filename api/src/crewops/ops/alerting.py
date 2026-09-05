"""Proactive alerting: which limit gets crossed in the next 48 hours.

`watchlist.py` answers "what is worth looking at on this date". This module
answers the narrower question a controller is actually exposed to: take the
running accruals in `duty_clocks.json`, add every duty that reports inside a
forward horizon, and report which crew cross RULE-DUTY-02 or RULE-FLT-03, by
how much, on which date. Certification lapses are swept over a longer horizon
because a renewal takes weeks to arrange and 48 hours of warning is useless.

Nothing here approximates. Every hour figure comes from
`WorldOverlay.window_hours`, which is the one implementation of the calendar
day window arithmetic, and every verdict comes from `LegalityEngine`, which
owns the comparison directions. This module decides *what to look at* and
*how alarming it is*. It does not do arithmetic of its own, and no language
model is reachable from here.

## Why the split between `alerts` and `closest_approaches`

On the shipped roster there are no duty or flight hour breaches in any 48 hour
horizon: the peak projected 7 day duty total is 40.96h against a 60h limit and
the peak projected 28 day block total is 71.81h against a 100h limit. That is
the correct answer, and a module that printed nothing would be indistinguishable
from a module that failed to run.

So a scan always reports the tightest margins it found on each limit rule,
carrying the same arithmetic as a real breach would, marked `breaches=False`
and ranked by margin. "Nobody is within 19 hours of the duty limit, here is who
is closest" is a checked statement. Silence is not.

Breaches on this dataset arise from a *change* to the roster, a sick call or a
cover assignment, and those run through `ops.candidates` and `rules.assess_cover`
rather than here. This module watches the roster as it stands.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from datetime import timedelta

from crewops.contracts.evidence import Fact, Provenance, TraceStep
from crewops.contracts.ops import (
    AlertedFlight,
    AlertKind,
    AlertScan,
    CertificationExposure,
    LimitProjection,
    ProactiveAlert,
    RiskSeverity,
)
from crewops.contracts.rules import RuleId, Verdict
from crewops.domain import WorldState, format_duration
from crewops.domain.models import Certification, WeekDuty
from crewops.rules import LegalityEngine

_SOURCE = "crewops.ops.alerting"

#: How far forward a limit scan looks. The problem this module was built for is
#: the next two rosters, which is what a Crew Control desk can still act on.
DEFAULT_HORIZON_HOURS = 48

#: Certifications get a longer horizon because the remedy is a booking, not a
#: swap. Matches `watchlist.CERT_HORIZON_DAYS` deliberately: two modules
#: disagreeing about when a certificate becomes urgent is a bug a controller
#: would find before we did.
DEFAULT_CERT_HORIZON_DAYS = 30

#: Margin thresholds, in hours below the limit, at which a projection stops
#: being informational and becomes an alert. A breach is CRITICAL regardless.
#:
#: The duty figures match `watchlist.TIGHT_HEADROOM_HOURS` and
#: `CRITICAL_HEADROOM_HOURS` so the two views of the same crew member agree.
#: The flight figures are the same fractions of the larger 100h limit, rounded:
#: a crew member 8 hours from a 100h block limit is in the same position as one
#: 5 hours from a 60h duty limit.
MARGIN_THRESHOLDS: dict[str, tuple[float, float]] = {
    #: rule_id -> (high severity at or below, critical severity at or below)
    "RULE-DUTY-02": (10.0, 5.0),
    "RULE-FLT-03": (17.0, 8.0),
}

#: How many closest approaches to report per limit rule when nothing crossed a
#: threshold. Enough to show the shape of the distribution, few enough to read.
CLOSEST_APPROACH_LIMIT = 3

_LIMIT_RULES: tuple[RuleId, ...] = ("RULE-DUTY-02", "RULE-FLT-03")

_SEVERITY_ORDER: dict[RiskSeverity, int] = {
    RiskSeverity.CRITICAL: 0,
    RiskSeverity.HIGH: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.LOW: 3,
}


class AlertScanner:
    """The deterministic half of proactive alerting.

    Build one per `WorldState`. `scan` is pure: the same world and the same
    arguments produce byte identical output, which is what lets the result be
    cached, diffed between runs and asserted against in a test.
    """

    def __init__(self, world: WorldState, engine: LegalityEngine | None = None) -> None:
        self.world = world
        self.engine = engine or LegalityEngine(world)

    # ------------------------------------------------------------------ entry

    def scan(
        self,
        *,
        as_of: DateTime | None = None,
        horizon_hours: int = DEFAULT_HORIZON_HOURS,
        cert_horizon_days: int = DEFAULT_CERT_HORIZON_DAYS,
    ) -> AlertScan:
        """Every crew member who crosses a limit or loses a certificate soon.

        `as_of` defaults to the dataset snapshot. The horizon is measured from
        it in real hours against each duty's **report time**, not in calendar
        days: a duty reporting at 17:00Z tomorrow is inside a 48 hour horizon
        and one reporting at 19:00Z the day after is not, and rounding either
        to a date would put the wrong duties in the window.
        """
        start = as_of or self.world.snapshot
        end = start + timedelta(hours=horizon_hours)

        horizon_duties = self._duties_in_horizon(start, end)
        alerts: list[ProactiveAlert] = []
        approaches: list[ProactiveAlert] = []

        for rule_id in _LIMIT_RULES:
            raised, closest = self._scan_limit(
                rule_id, horizon_duties, start=start, end=end, horizon_hours=horizon_hours
            )
            alerts.extend(raised)
            approaches.extend(closest)

        alerts.extend(self._scan_certifications(start, cert_horizon_days, horizon_duties))

        alerts.sort(key=self._rank)
        approaches.sort(key=self._rank)

        return AlertScan(
            as_of=start,
            horizon_hours=horizon_hours,
            horizon_end=end,
            cert_horizon_days=cert_horizon_days,
            alerts=alerts,
            closest_approaches=approaches,
            headline=self._headline(alerts, approaches, horizon_hours),
            counts={
                severity.value: sum(1 for a in alerts if a.severity is severity)
                for severity in RiskSeverity
            },
            scanned={
                "crew": len(self.world.crew),
                "crew_in_horizon": len(horizon_duties),
                "duties_in_horizon": sum(len(v) for v in horizon_duties.values()),
                "certifications": len(self.world.certifications),
            },
        )

    # -------------------------------------------------------------- the horizon

    def _duties_in_horizon(self, start: DateTime, end: DateTime) -> dict[str, tuple[WeekDuty, ...]]:
        """`crew_id -> duties reporting inside the horizon`, sorted by date.

        A duty already under way at `start` is deliberately included when its
        report time is inside the window and excluded when it is not. The
        window that matters for a limit is the calendar day one, and the report
        time only decides which duties count as "upcoming".
        """
        overlay = self.world.overlay()
        found: dict[str, list[WeekDuty]] = {}
        for member in self.world.crew:
            if not member.is_active:
                continue
            upcoming = [
                duty
                for duty in overlay.week_duties(member.crew_id)
                if start <= duty.report_utc <= end
            ]
            if upcoming:
                found[member.crew_id] = sorted(upcoming, key=lambda d: d.duty_date)
        return {cid: tuple(v) for cid, v in sorted(found.items())}

    # ---------------------------------------------------- RULE-DUTY-02 / FLT-03

    def _scan_limit(
        self,
        rule_id: RuleId,
        horizon_duties: dict[str, tuple[WeekDuty, ...]],
        *,
        start: DateTime,
        end: DateTime,
        horizon_hours: int,
    ) -> tuple[list[ProactiveAlert], list[ProactiveAlert]]:
        """One limit rule, every crew member with a duty in the horizon.

        Returns `(alerts, closest_approaches)`. A crew member with duties on
        both horizon dates is projected on each of them separately, because the
        window slides and the second date is not always the tighter one.
        """
        overlay = self.world.overlay()
        is_duty = rule_id == "RULE-DUTY-02"
        window_days = self.engine.duty_window_days if is_duty else self.engine.flight_window_days
        limit = self.engine.max_duty_7d if is_duty else self.engine.max_flight_28d
        high_at, critical_at = MARGIN_THRESHOLDS[rule_id]

        raised: list[ProactiveAlert] = []
        scored: list[tuple[float, ProactiveAlert]] = []

        for crew_id, duties in horizon_duties.items():
            for duty_date in sorted({d.duty_date for d in duties}):
                projected = overlay.window_hours(
                    crew_id, duty_date, days=window_days, kind="duty" if is_duty else "flight"
                )
                #: The duties inside the horizon that land in this window. Their
                #: contribution is what a controller can still move.
                committed = round(
                    sum(
                        d.duty_hours if is_duty else d.block_hours
                        for d in duties
                        if d.duty_date <= duty_date
                    ),
                    2,
                )
                banked = round(projected - committed, 2)

                trace = (
                    self.engine.check_duty_window(
                        crew_id=crew_id,
                        duty_date=duty_date,
                        total=projected,
                        prior=banked,
                        added=committed,
                        label=f"duties in the next {horizon_hours} hours",
                    )
                    if is_duty
                    else self.engine.check_flight_window(
                        crew_id=crew_id,
                        duty_date=duty_date,
                        total=projected,
                        prior=banked,
                        added=committed,
                        label=f"duties in the next {horizon_hours} hours",
                    )
                )
                margin = trace.margin if trace.margin is not None else round(limit - projected, 2)
                breaches = trace.verdict is Verdict.BREACH

                severity = (
                    RiskSeverity.CRITICAL
                    if breaches or margin <= critical_at
                    else RiskSeverity.HIGH
                    if margin <= high_at
                    else RiskSeverity.LOW
                )

                projection = LimitProjection(
                    rule_id=rule_id,
                    window_days=window_days,
                    window_start=duty_date - timedelta(days=window_days - 1),
                    window_end=duty_date,
                    limit_hours=limit,
                    banked_hours=banked,
                    committed_hours=committed,
                    projected_hours=projected,
                    margin_hours=margin,
                    breaches=breaches,
                    verdict=trace.verdict,
                    arithmetic=trace.arithmetic,
                )
                alert = self._limit_alert(
                    crew_id=crew_id,
                    duty_date=duty_date,
                    duties=duties,
                    projection=projection,
                    severity=severity,
                    horizon_hours=horizon_hours,
                )
                if severity is RiskSeverity.LOW:
                    scored.append((margin, alert))
                else:
                    raised.append(alert)

        scored.sort(key=lambda pair: (pair[0], pair[1].crew_id, pair[1].effective_date))
        return raised, [alert for _margin, alert in scored[:CLOSEST_APPROACH_LIMIT]]

    def _limit_alert(
        self,
        *,
        crew_id: str,
        duty_date: DateType,
        duties: Sequence[WeekDuty],
        projection: LimitProjection,
        severity: RiskSeverity,
        horizon_hours: int,
    ) -> ProactiveAlert:
        member = self.world.require_crew(crew_id)
        is_duty = projection.rule_id == "RULE-DUTY-02"
        measure = "duty" if is_duty else "block"
        contributing = [d for d in duties if d.duty_date <= duty_date]
        flights = self._flights_of(contributing)
        signal = self.world.risk_signal(crew_id)
        prefix = f"{projection.rule_id.lower()}:{crew_id}:{duty_date}"

        if projection.breaches:
            title = (
                f"{crew_id} breaches {projection.rule_id} on {duty_date} by "
                f"{format_duration(abs(projection.margin_hours))}"
            )
            action = (
                f"Move or shorten a duty before {duty_date}. The duties inside the "
                f"next {horizon_hours} hours contribute "
                f"{projection.committed_hours:.2f}h of the total, so the breach is "
                "still reachable from the roster."
            )
        else:
            title = (
                f"{crew_id} projects to {projection.projected_hours:.2f}h of "
                f"{projection.limit_hours:.0f}h {measure} hours on {duty_date}"
            )
            action = (
                f"No breach on the roster as it stands. Treat "
                f"{format_duration(projection.margin_hours)} as the room available "
                "before any extension or reassignment is offered."
            )

        detail = (
            f"{projection.arithmetic}. "
            f"{projection.banked_hours:.2f}h is already accrued and "
            f"{projection.committed_hours:.2f}h comes from "
            f"{len(contributing)} rostered {'duty' if len(contributing) == 1 else 'duties'} "
            f"inside the horizon."
        )

        return ProactiveAlert(
            alert_id=prefix,
            kind=AlertKind.DUTY_LIMIT if is_duty else AlertKind.FLIGHT_LIMIT,
            severity=severity,
            rule_id=projection.rule_id,
            crew_id=crew_id,
            crew_name=member.name,
            rank=member.rank,
            base=member.base,
            effective_date=duty_date,
            title=title,
            detail=detail,
            projection=projection,
            downstream_flights=flights,
            seats_at_risk=sum(f.seats for f in flights),
            disruption_risk_score=signal.disruption_risk_score if signal else None,
            risk_drivers=list(signal.drivers) if signal else [],
            recommended_action=action,
            suggested_question=(f"How much {measure} headroom does {crew_id} have on {duty_date}?"),
            facts=self._limit_facts(prefix, crew_id, projection, flights),
            trace=[
                TraceStep(
                    label=f"Sum the {projection.window_days} day window",
                    detail=(
                        f"daily_history plus rostered duties over "
                        f"{projection.window_start} to {projection.window_end}, "
                        f"giving {projection.projected_hours:.2f}h"
                    ),
                    fact_keys=[f"{prefix}.projected"],
                ),
                TraceStep(
                    label=f"Compare against {projection.rule_id}",
                    detail=projection.arithmetic,
                    fact_keys=[f"{prefix}.limit", f"{prefix}.margin"],
                ),
            ],
        )

    def _limit_facts(
        self,
        prefix: str,
        crew_id: str,
        projection: LimitProjection,
        flights: Sequence[AlertedFlight],
    ) -> list[Fact]:
        measure = "duty" if projection.rule_id == "RULE-DUTY-02" else "block"
        facts = [
            _computed(
                f"{prefix}.banked",
                f"{measure.capitalize()} hours already accrued in the window",
                projection.banked_hours,
                "hours",
                f"daily_history plus rostered duties over {projection.window_start} to "
                f"{projection.window_end}, excluding the duties inside the horizon",
            ),
            _computed(
                f"{prefix}.committed",
                f"{measure.capitalize()} hours from duties inside the horizon",
                projection.committed_hours,
                "hours",
                f"sum of the rostered duties for {crew_id} reporting inside the horizon "
                f"on or before {projection.window_end}",
            ),
            _computed(
                f"{prefix}.projected",
                f"Projected {projection.window_days} day {measure} hours",
                projection.projected_hours,
                "hours",
                f"{projection.banked_hours:.2f} + {projection.committed_hours:.2f} = "
                f"{projection.projected_hours:.2f}h",
            ),
            _computed(
                f"{prefix}.margin",
                f"Margin under {projection.rule_id}",
                projection.margin_hours,
                "hours",
                f"{projection.limit_hours:.2f} - {projection.projected_hours:.2f} = "
                f"{projection.margin_hours:.2f}h",
            ),
            Fact(
                key=f"{prefix}.limit",
                label=f"{projection.rule_id} limit",
                value=projection.limit_hours,
                unit="hours",
                provenance=Provenance.DATASET,
                source=f"rules.json#{projection.rule_id}",
            ),
            Fact(
                key=f"{prefix}.window_days",
                label=f"{projection.rule_id} window",
                value=projection.window_days,
                unit="days",
                provenance=Provenance.DATASET,
                source=f"rules.json#{projection.rule_id}/window_days",
            ),
        ]
        facts.extend(self._flight_facts(prefix, flights))
        return facts

    # ------------------------------------------------------------ RULE-CERT-06

    def _scan_certifications(
        self,
        start: DateTime,
        cert_horizon_days: int,
        horizon_duties: dict[str, tuple[WeekDuty, ...]],
    ) -> list[ProactiveAlert]:
        """Licences, medicals and recurrent training lapsing inside the horizon.

        A certificate expiring **on** a duty date is still valid that day: the
        test is `valid_to >= duty_date`, and `Certification.valid_on` is the one
        implementation of it. The alert is about the first duty after the
        expiry, which is the one that is already illegal on the roster.

        `valid_from` is never read. It is generated as `valid_to - 730 days` and
        was never corrected after the engineered expiries, so it is unusable.
        """
        today = start.date()
        horizon = today + timedelta(days=cert_horizon_days)
        out: list[ProactiveAlert] = []

        for cert in sorted(
            self.world.certifications, key=lambda c: (c.valid_to, c.crew_id, c.cert_type)
        ):
            if not (today <= cert.valid_to <= horizon):
                continue
            member = self.world.crew_member(cert.crew_id)
            if member is None or not member.is_active:
                continue

            invalid = [
                duty
                for duty in self.world.week_duties(cert.crew_id)
                if not cert.valid_on(duty.duty_date)
            ]
            days_left = (cert.valid_to - today).days
            in_horizon = any(
                not cert.valid_on(d.duty_date) for d in horizon_duties.get(cert.crew_id, ())
            )
            severity = (
                RiskSeverity.CRITICAL
                if invalid
                else RiskSeverity.HIGH
                if in_horizon
                else RiskSeverity.MEDIUM
            )
            out.append(self._certification_alert(cert, days_left, invalid, severity))
        return out

    def _certification_alert(
        self,
        cert: Certification,
        days_left: int,
        invalid: Sequence[WeekDuty],
        severity: RiskSeverity,
    ) -> ProactiveAlert:
        crew = self.world.require_crew(cert.crew_id)
        flights = self._flights_of(invalid)
        signal = self.world.risk_signal(cert.crew_id)
        prefix = f"rule-cert-06:{cert.crew_id}:{cert.cert_type}"
        first_invalid = invalid[0].duty_date if invalid else None
        pairings = sorted({d.pairing_id for d in invalid})

        if invalid:
            title = (
                f"{cert.crew_id} is rostered on {first_invalid} with "
                f"{cert.cert_type} expired since {cert.valid_to}"
            )
            detail = (
                f"{cert.cert_type} is valid to {cert.valid_to}, which is "
                f"{days_left} days away. {cert.crew_id} is rostered on "
                + ", ".join(f"{d.pairing_id} on {d.duty_date}" for d in invalid)
                + ". Every one of those duties breaches RULE-CERT-06, because the "
                "test is that the certificate is valid on the duty date."
            )
            action = (
                f"Renew {cert.cert_type} before {cert.valid_to} or re-crew "
                + ", ".join(pairings)
                + ". This is a breach already on the roster, not a forecast."
            )
        else:
            title = f"{cert.cert_type} lapses for {cert.crew_id} on {cert.valid_to}"
            detail = (
                f"{cert.cert_type} is valid to {cert.valid_to}, which is "
                f"{days_left} days away. No duty in the schedule week falls after "
                "the expiry, so nothing on the current roster breaches "
                "RULE-CERT-06 yet."
            )
            action = (
                f"Book the renewal. {cert.crew_id} cannot be rostered after "
                f"{cert.valid_to} until it is done, which removes a "
                f"{crew.rank} from the {crew.base} pool."
            )

        return ProactiveAlert(
            alert_id=prefix,
            kind=AlertKind.CERTIFICATION,
            severity=severity,
            rule_id="RULE-CERT-06",
            crew_id=cert.crew_id,
            crew_name=crew.name,
            rank=crew.rank,
            base=crew.base,
            effective_date=cert.valid_to,
            title=title,
            detail=detail,
            certification=CertificationExposure(
                cert_type=cert.cert_type,
                valid_to=cert.valid_to,
                days_to_expiry=days_left,
                first_invalid_duty=first_invalid,
                invalid_pairings=pairings,
            ),
            downstream_flights=flights,
            seats_at_risk=sum(f.seats for f in flights),
            disruption_risk_score=signal.disruption_risk_score if signal else None,
            risk_drivers=list(signal.drivers) if signal else [],
            recommended_action=action,
            suggested_question=(
                f"Can {cert.cert_type} for {cert.crew_id} be renewed before {cert.valid_to}?"
            ),
            facts=[
                Fact(
                    key=f"{prefix}.valid_to",
                    label=f"{cert.cert_type} expiry",
                    value=cert.valid_to.isoformat(),
                    unit="date",
                    provenance=Provenance.DATASET,
                    source=f"certifications.json#{cert.crew_id}/{cert.cert_type}",
                ),
                _computed(
                    f"{prefix}.days_to_expiry",
                    "Days until expiry",
                    days_left,
                    "days",
                    f"{cert.valid_to} - {self.world.snapshot.date()} = {days_left} days",
                ),
                _computed(
                    f"{prefix}.invalid_duties",
                    "Rostered duties after the expiry",
                    len(invalid),
                    "count",
                    "duties in the schedule week whose date is after "
                    f"{cert.valid_to}, which RULE-CERT-06 makes illegal",
                ),
                *self._flight_facts(prefix, flights),
            ],
            trace=[
                TraceStep(
                    label="Read the expiry",
                    detail=(
                        f"certifications.json gives {cert.cert_type} for "
                        f"{cert.crew_id} as valid to {cert.valid_to}"
                    ),
                    fact_keys=[f"{prefix}.valid_to"],
                ),
                TraceStep(
                    label="Test every rostered duty against it",
                    detail=(
                        f"RULE-CERT-06 requires valid_to >= duty date. "
                        f"{len(invalid)} rostered "
                        f"{'duty fails' if len(invalid) == 1 else 'duties fail'} that test."
                    ),
                    fact_keys=[f"{prefix}.invalid_duties"],
                ),
            ],
        )

    # ---------------------------------------------------------------- shared

    def _flights_of(self, duties: Sequence[WeekDuty]) -> list[AlertedFlight]:
        """The legs behind a set of duties, in departure order."""
        out: list[AlertedFlight] = []
        for duty in duties:
            pairing = self.world.pairing(duty.pairing_id)
            if pairing is None:
                continue
            day = next((d for d in pairing.days if d.date == duty.duty_date), None)
            if day is None:
                continue
            for flight_id in day.flights:
                flight = self.world.require_flight(flight_id)
                out.append(
                    AlertedFlight(
                        flight_no=flight.flight_no,
                        departure=flight.dep_utc,
                        origin=flight.dep_station,
                        destination=flight.arr_station,
                        seats=flight.seats,
                        duty_date=duty.duty_date,
                        pairing_id=duty.pairing_id,
                    )
                )
        out.sort(key=lambda f: (f.departure, f.flight_no))
        return out

    def _flight_facts(self, prefix: str, flights: Sequence[AlertedFlight]) -> list[Fact]:
        if not flights:
            return []
        seats = sum(f.seats for f in flights)
        return [
            _computed(
                f"{prefix}.flights_at_risk",
                "Flights exposed",
                len(flights),
                "count",
                "legs on the duties behind this alert: " + ", ".join(f.flight_no for f in flights),
            ),
            _computed(
                f"{prefix}.seats_at_risk",
                "Seats exposed",
                seats,
                "count",
                " + ".join(f"{f.seats}" for f in flights) + f" = {seats} seats",
            ),
            *[
                Fact(
                    key=f"{prefix}.flight.{flight.flight_no}.seats",
                    label=f"{flight.flight_no} seats",
                    value=flight.seats,
                    unit="count",
                    provenance=Provenance.DATASET,
                    source=f"flights.json#{flight.flight_no}-{flight.duty_date}",
                )
                for flight in flights
            ],
        ]

    @staticmethod
    def _rank(alert: ProactiveAlert) -> tuple[int, str, str]:
        return (_SEVERITY_ORDER[alert.severity], alert.crew_id, alert.alert_id)

    @staticmethod
    def _headline(
        alerts: Sequence[ProactiveAlert],
        approaches: Sequence[ProactiveAlert],
        horizon_hours: int,
    ) -> str:
        """One line a controller can read without opening anything.

        When nothing fired it says what was checked and what the tightest
        margin was, because "no alerts" and "the scan did not run" have to look
        different on a screen at 6 a.m.
        """
        tightest = min(
            (a for a in approaches if a.projection is not None),
            key=lambda a: a.projection.margin_hours if a.projection else 0.0,
            default=None,
        )
        clean = (
            f"No limit breaches in the next {horizon_hours} hours"
            + (
                ""
                if tightest is None or tightest.projection is None
                else (
                    f"; the tightest margin is {tightest.crew_id} at "
                    f"{format_duration(tightest.projection.margin_hours)} under "
                    f"{tightest.projection.rule_id}"
                )
            )
            + "."
        )

        if not alerts:
            if not approaches:
                return f"No crew are inside the next {horizon_hours} hours."
            return f"Nothing to raise. {clean}"

        breaches = sum(1 for a in alerts if a.severity is RiskSeverity.CRITICAL)
        rules = sorted({a.rule_id for a in alerts})
        raised = (
            f"{len(alerts)} to raise in the next {horizon_hours} hours, "
            f"{breaches} critical, across {', '.join(rules)}."
        )
        #: When the alerts are all certification work, saying so keeps the
        #: limit result visible. A controller who reads "6 to raise" and
        #: assumes duty hours are among them is reading the wrong crisis.
        limits_raised = any(
            a.kind in (AlertKind.DUTY_LIMIT, AlertKind.FLIGHT_LIMIT) for a in alerts
        )
        return raised if limits_raised else f"{raised} {clean}"


def _computed(key: str, label: str, value: object, unit: str, derivation: str) -> Fact:
    """A `Fact` this module calculated. The derivation is never optional."""
    return Fact(
        key=key,
        label=label,
        value=value,  # type: ignore[arg-type]
        unit=unit,  # type: ignore[arg-type]
        provenance=Provenance.COMPUTED,
        source=_SOURCE,
        derivation=derivation,
    )


__all__ = [
    "CLOSEST_APPROACH_LIMIT",
    "DEFAULT_CERT_HORIZON_DAYS",
    "DEFAULT_HORIZON_HOURS",
    "MARGIN_THRESHOLDS",
    "AlertScanner",
]
