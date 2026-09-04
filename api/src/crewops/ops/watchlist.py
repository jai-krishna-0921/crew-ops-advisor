"""The proactive brief: what is about to go wrong on a given date.

A controller does not start the day with a question. They start it with a
roster, and the useful system is the one that has already looked. Everything
here is deterministic: no model is involved in deciding what matters, only in
reading it aloud later.

Four things are worth waking someone up for:

1. A certificate that lapses before or during a rostered duty.
2. A crew member close enough to a duty limit that any extension breaches it.
3. The roster exceptions the dataset itself flags as already illegal.
4. A single point of failure: a role on a pairing with no legal cover behind it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812

from crewops.contracts.evidence import Fact, Provenance
from crewops.contracts.ops import Alert, RiskSeverity, Watchlist
from crewops.domain import WorldState, format_duration
from crewops.rules import LegalityEngine

_SOURCE = "crewops.ops.watchlist"

#: Duty headroom under RULE-DUTY-02 below which an extension is a real risk.
TIGHT_HEADROOM_HOURS = 10.0
CRITICAL_HEADROOM_HOURS = 5.0

#: How far ahead to look for a lapsing certificate.
CERT_HORIZON_DAYS = 30

#: `risk_signals.json` scores are a **provided input**, never computed here.
#: There is a clean gap between 0.41 and 0.64 in the shipped data, so any
#: threshold in that range selects exactly the four engineered crew.
HIGH_RISK_THRESHOLD = 0.6


class WatchlistBuilder:
    """Builds the 6 a.m. brief. Deterministic, no model involved."""

    def __init__(self, world: WorldState, engine: LegalityEngine) -> None:
        self.world = world
        self.engine = engine

    def build(self, *, for_date: DateType, as_of: DateTime | None = None) -> Watchlist:
        alerts: list[Alert] = []
        alerts.extend(self._flagged_exceptions(for_date))
        alerts.extend(self._expiring_certifications(for_date))
        alerts.extend(self._duty_headroom(for_date))
        alerts.extend(self._single_points_of_failure(for_date))
        alerts.extend(self._provided_risk_signals(for_date))

        order = {
            RiskSeverity.CRITICAL: 0,
            RiskSeverity.HIGH: 1,
            RiskSeverity.MEDIUM: 2,
            RiskSeverity.LOW: 3,
        }
        alerts.sort(key=lambda a: (order[a.severity], a.crew_id or "", a.title))

        pairings = self.world.pairings_on(for_date)
        rostered = {m.crew_id for p in pairings for m in p.crew}
        return Watchlist(
            as_of=as_of or self.world.snapshot,
            for_date=for_date,
            alerts=alerts,
            headline=self._headline(for_date, alerts),
            scanned={
                "crew": len(self.world.crew),
                "crew_rostered": len(rostered),
                "pairings": len(pairings),
                "flights": len(self.world.flights_on(for_date)),
                "certifications": len(self.world.certifications),
                "reserves": len(self.world.reserves_on(for_date)),
            },
        )

    # ------------------------------------------------------------- sections

    def _flagged_exceptions(self, for_date: DateType) -> list[Alert]:
        """The one assignment the dataset itself admits is illegal."""
        out: list[Alert] = []
        for flagged in self.world.flagged_exceptions:
            if flagged.date < for_date:
                continue
            out.append(
                Alert(
                    severity=RiskSeverity.CRITICAL,
                    title=f"{flagged.crew_id} is rostered illegally on {flagged.date}",
                    detail=flagged.note,
                    crew_id=flagged.crew_id,
                    rule_id="RULE-CERT-06" if flagged.rule == "RULE-CERT-06" else None,
                    due_date=flagged.date,
                    suggested_question=(
                        f"Resolve {flagged.crew_id}'s assignment on {flagged.date}"
                    ),
                    facts=[
                        Fact(
                            key=f"{flagged.crew_id}.flagged.{flagged.date}",
                            label="Flagged roster exception",
                            value=flagged.rule,
                            unit="rule_id",
                            provenance=Provenance.DATASET,
                            source=f"rosters.json#flagged_exceptions/{flagged.crew_id}",
                        )
                    ],
                )
            )
        return out

    def _expiring_certifications(self, for_date: DateType) -> list[Alert]:
        """Certificates lapsing inside the horizon, worst first.

        A certificate that expires **on** a duty date is still valid that day.
        The alert is about the duty after it, which is the one that breaks.
        """
        out: list[Alert] = []
        horizon = DateType.fromordinal(for_date.toordinal() + CERT_HORIZON_DAYS)
        for cert in self.world.certifications:
            if not (for_date <= cert.valid_to <= horizon):
                continue
            member = self.world.crew_member(cert.crew_id)
            if member is None or not member.is_active:
                continue
            clashes = [
                duty
                for duty in self.world.week_duties(cert.crew_id)
                if duty.duty_date > cert.valid_to
            ]
            days_left = cert.valid_to.toordinal() - for_date.toordinal()
            severity = RiskSeverity.CRITICAL if clashes else RiskSeverity.MEDIUM
            detail = (
                f"{cert.cert_type} expires {cert.valid_to}, {days_left} days from "
                f"{for_date}. "
                + (
                    "They are rostered on "
                    + ", ".join(f"{d.pairing_id} on {d.duty_date}" for d in clashes)
                    + ", which would be illegal under RULE-CERT-06."
                    if clashes
                    else "No rostered duty falls after the expiry this week."
                )
            )
            out.append(
                Alert(
                    severity=severity,
                    title=f"{cert.cert_type} lapses for {cert.crew_id} on {cert.valid_to}",
                    detail=detail,
                    crew_id=cert.crew_id,
                    pairing_id=clashes[0].pairing_id if clashes else None,
                    rule_id="RULE-CERT-06",
                    due_date=cert.valid_to,
                    suggested_question=(
                        f"Can {cert.cert_type} for {cert.crew_id} be renewed before "
                        f"{cert.valid_to}?"
                    ),
                    facts=[
                        Fact(
                            key=f"{cert.crew_id}.cert.{cert.cert_type}.valid_to",
                            label=f"{cert.cert_type} expiry",
                            value=cert.valid_to.isoformat(),
                            unit="date",
                            provenance=Provenance.DATASET,
                            source=(
                                f"certifications.json#{cert.crew_id}/{cert.cert_type}"
                            ),
                        )
                    ],
                )
            )
        return out

    def _duty_headroom(self, for_date: DateType) -> list[Alert]:
        """Crew close enough to the 7 day limit that any extension breaches it."""
        overlay = self.world.overlay()
        out: list[Alert] = []
        for pairing in self.world.pairings_on(for_date):
            for member in pairing.crew:
                projected = overlay.duty_hours_7d(member.crew_id, for_date)
                headroom = round(self.engine.max_duty_7d - projected, 2)
                if headroom > TIGHT_HEADROOM_HOURS:
                    continue
                out.append(
                    Alert(
                        severity=(
                            RiskSeverity.CRITICAL
                            if headroom <= CRITICAL_HEADROOM_HOURS
                            else RiskSeverity.HIGH
                        ),
                        title=(
                            f"{member.crew_id} has {format_duration(max(headroom, 0.0))} "
                            f"of duty headroom on {for_date}"
                        ),
                        detail=(
                            f"{projected}h of {self.engine.max_duty_7d:.0f}h used over "
                            f"the 7 days ending {for_date}, on {pairing.pairing_id}. "
                            "Any extension or reassignment needs checking before it is "
                            "offered."
                        ),
                        crew_id=member.crew_id,
                        pairing_id=pairing.pairing_id,
                        rule_id="RULE-DUTY-02",
                        due_date=for_date,
                        suggested_question=(
                            f"How much duty headroom does {member.crew_id} have on "
                            f"{for_date}?"
                        ),
                        facts=[
                            Fact(
                                key=f"{member.crew_id}.{for_date}.duty_7d",
                                label="Duty hours in the 7 days ending this date",
                                value=projected,
                                unit="hours",
                                provenance=Provenance.COMPUTED,
                                source=_SOURCE,
                                derivation=(
                                    "daily_history plus rostered duties over "
                                    f"{overlay.window_dates(for_date, 7)[0]} to {for_date}"
                                ),
                            ),
                            Fact(
                                key=f"{member.crew_id}.{for_date}.duty_7d.headroom",
                                label="Headroom under RULE-DUTY-02",
                                value=headroom,
                                unit="hours",
                                provenance=Provenance.COMPUTED,
                                source=_SOURCE,
                                derivation=(
                                    f"{self.engine.max_duty_7d:.0f} - {projected} = "
                                    f"{headroom}h"
                                ),
                            ),
                        ],
                    )
                )
        return out

    def _single_points_of_failure(self, for_date: DateType) -> list[Alert]:
        """A role with no reserve behind it whose window covers the report.

        This is the alert that earns the brief: it is invisible on a roster and
        it is the difference between a routine sick call and a cancellation.
        """
        out: list[Alert] = []
        for pairing in self.world.pairings_on(for_date):
            day = next((d for d in pairing.days if d.date == for_date), None)
            if day is None:
                continue
            first = self.world.require_flight(day.flights[0])
            for role in sorted({m.role for m in pairing.crew}):
                available = self._reserves_covering(
                    role=role,
                    aircraft_type=first.aircraft_type,
                    station=first.dep_station,
                    report=day.report_utc,
                    for_date=for_date,
                )
                if available:
                    continue
                out.append(
                    Alert(
                        severity=RiskSeverity.HIGH,
                        title=(
                            f"No reserve {role} covers {pairing.pairing_id}'s "
                            f"{day.report_utc:%H:%M}Z report"
                        ),
                        detail=(
                            f"{pairing.pairing_id} reports at {day.report_utc:%H:%M}Z on "
                            f"{first.aircraft_type} from {first.dep_station}. No "
                            f"{role} on reserve is rated, based and inside their on-call "
                            "window for that report. A sick call in this seat goes "
                            "straight to a day-off callout or a cancellation."
                        ),
                        pairing_id=pairing.pairing_id,
                        rule_id="RULE-BASE-07",
                        due_date=for_date,
                        suggested_question=(
                            f"Who can cover the {role} on {pairing.pairing_id}?"
                        ),
                        facts=[
                            Fact(
                                key=f"{pairing.pairing_id}.{role}.reserves_available",
                                label=f"Reserve {role}s covering this report",
                                value=0,
                                unit="count",
                                provenance=Provenance.COMPUTED,
                                source=_SOURCE,
                                derivation=(
                                    f"reserves of rank {role} rated for "
                                    f"{first.aircraft_type}, based at "
                                    f"{first.dep_station}, whose window contains "
                                    f"{day.report_utc:%H:%M}Z"
                                ),
                            )
                        ],
                    )
                )
        return out

    def _reserves_covering(
        self,
        *,
        role: str,
        aircraft_type: str,
        station: str,
        report: DateTime,
        for_date: DateType,
    ) -> list[str]:
        from crewops.domain import at_clock

        out: list[str] = []
        for reserve in self.world.reserves_on(for_date):
            member = self.world.crew_member(reserve.crew_id)
            if member is None or member.rank != role or not member.is_active:
                continue
            if not member.is_rated_for(aircraft_type) or member.base != station:
                continue
            window = reserve.oncall_window_utc
            day = report.date()
            if at_clock(day, window.start) <= report <= at_clock(day, window.end):
                out.append(reserve.crew_id)
        return out

    def _provided_risk_signals(self, for_date: DateType) -> list[Alert]:
        """Scores read straight off `risk_signals.json`. Provided, never computed."""
        rostered = {
            m.crew_id for p in self.world.pairings_on(for_date) for m in p.crew
        }
        out: list[Alert] = []
        for signal in self.world.risk_signals:
            if signal.disruption_risk_score < HIGH_RISK_THRESHOLD:
                continue
            if signal.crew_id not in rostered:
                continue
            out.append(
                Alert(
                    severity=RiskSeverity.MEDIUM,
                    title=(
                        f"{signal.crew_id} carries a disruption risk score of "
                        f"{signal.disruption_risk_score}"
                    ),
                    detail=(
                        "Provided in risk_signals.json, not computed here. Drivers: "
                        + "; ".join(signal.drivers)
                        + f". They are rostered on {for_date}."
                    ),
                    crew_id=signal.crew_id,
                    due_date=for_date,
                    suggested_question=f"What is the disruption risk for {signal.crew_id}?",
                    facts=[
                        Fact(
                            key=f"{signal.crew_id}.risk.score",
                            label="Disruption risk score",
                            value=signal.disruption_risk_score,
                            unit="percent",
                            provenance=Provenance.DATASET,
                            source=f"risk_signals.json#{signal.crew_id}",
                        )
                    ],
                )
            )
        return out

    @staticmethod
    def _headline(for_date: DateType, alerts: Sequence[Alert]) -> str:
        if not alerts:
            return f"Nothing on the watchlist for {for_date}."
        critical = sum(1 for a in alerts if a.severity is RiskSeverity.CRITICAL)
        high = sum(1 for a in alerts if a.severity is RiskSeverity.HIGH)
        parts = []
        if critical:
            parts.append(f"{critical} critical")
        if high:
            parts.append(f"{high} high")
        rest = len(alerts) - critical - high
        if rest:
            parts.append(f"{rest} lower priority")
        return f"{len(alerts)} items for {for_date}: " + ", ".join(parts) + "."


__all__ = [
    "CERT_HORIZON_DAYS",
    "CRITICAL_HEADROOM_HOURS",
    "HIGH_RISK_THRESHOLD",
    "TIGHT_HEADROOM_HOURS",
    "WatchlistBuilder",
]
