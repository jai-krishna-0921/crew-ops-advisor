"""`Tools`: the implementation of `ToolSurface`, and the grounding boundary.

This is the seam. The agent binds these seventeen methods and never reaches
past them into `rules/` or `ops/`. Everything below this line is deterministic;
nothing above it may produce a number.

Four rules every method here follows:

1. **Every numeric value in the payload has a matching `Fact`.** The verifier
   only knows what the facts tell it. There is a test that walks every payload
   and fails if a number is unattested.
2. **Computed facts carry the arithmetic**, written out, so a controller can
   challenge the number rather than take it on trust.
3. **`ok=False` with a specific error when a lookup fails.** An empty result is
   a finding and comes back with `ok=True`: "no crew match that filter" and
   "that crew id is not in the dataset" are different answers and must never
   look the same.
4. **Payloads stay inside a prompt budget.** When a result is capped,
   `truncated=True` and the payload still carries the total and the full id
   list, so nothing is silently lost.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from datetime import timedelta
from typing import Any, Literal, cast

from crewops.contracts.evidence import Fact, FactUnit, ToolEnvelope
from crewops.contracts.rules import ALL_RULE_IDS
from crewops.contracts.tools import DelayMode, TimeOfDay
from crewops.domain import (
    Crew,
    Flight,
    WorldState,
    at_clock,
    format_duration,
    load_world,
)
from crewops.ops import OpsEngine
from crewops.rules import (
    LegalityEngine,
    ProposedDuty,
    proposed_duties_for_pairing,
    proposed_duty_from_flights,
)
from crewops.rules.limits import RULE_TITLES
from crewops.store import DatasetStore
from crewops.tools import payloads as P  # noqa: N812  short alias, used on ~200 lines below
from crewops.tools.envelope import (
    ToolTimer,
    cite,
    computed_fact,
    dataset_fact,
    error_envelope,
    ok_envelope,
    step,
)

_SOURCE = "crewops.tools.registry.Tools"

#: Windows used by `time_of_day`, in UTC. The schedule is entirely daytime UTC,
#: so these are wide rather than clever.
TIME_OF_DAY_WINDOWS: dict[str, tuple[int, int]] = {
    "morning": (0, 12),
    "afternoon": (12, 17),
    "evening": (17, 21),
    "night": (21, 24),
}

#: Deterministic worked examples for `explain_rule`, each drawn from a case the
#: shipped answer keys settle, so the model never has to invent one.
RULE_EXAMPLES: dict[str, str] = {
    "RULE-FDP-01": (
        "P-2291 day 1 is 3 sectors, so the limit is 13.0 - 0.5 x 1 = 12.5h. The "
        "duty runs 06:00Z to 15:30Z, which is 9.50h: legal with 3.00h spare. The "
        "comparison is strict, so a 12.0h duty against a 12.0h limit is also legal."
    ),
    "RULE-DUTY-02": (
        "C-2087 covering P-2291 on 2026-09-15: 51.83h already in the window "
        "2026-09-09 to 2026-09-15, plus 9.50h from the cover, is 61.33h against "
        "60h. Over by 1h20m. On day 2 the day 1 cover is already inside the "
        "window, which is why it breaches again at 61.08h."
    ),
    "RULE-FLT-03": (
        "The highest 28 day block total anywhere in this dataset is 79.28h "
        "against a 100h limit, so this rule is checked on every assignment and "
        "binds on none of them."
    ),
    "RULE-REST-04": (
        "A crew member released at 15:30Z on 2026-09-16 may report from 03:30Z "
        "on 2026-09-17. The comparison is strict, so exactly 12.0h of rest is "
        "legal."
    ),
    "RULE-QUAL-05": (
        "C-2091 holds ATR72 only, so they are eligible for an ATR72 pairing and "
        "excluded from every A320 one. A rating failure is reported on its own: "
        "there is no point listing a duty breach for someone who cannot fly the "
        "aircraft."
    ),
    "RULE-CERT-06": (
        "C-5417's recurrent_training expires 2026-09-17. Their 2026-09-16 duty "
        "is legal and their 2026-09-19 duty is not, because the test is "
        "valid_to >= duty_date: a certificate expiring on the duty date is valid "
        "that day."
    ),
    "RULE-BASE-07": (
        "C-2210 is based at DEL and P-2291 departs BLR, so they position on "
        "DX402 arriving 08:45Z. The first departure moves to 10:00Z, 3.0h later, "
        "and the cost becomes 18,500 + 6,500 + 16,200 = INR 41,200."
    ),
}

RuleComparison: dict[str, str] = {
    "RULE-FDP-01": "breach when the duty period is strictly greater than the limit",
    "RULE-DUTY-02": "breach when the 7 day total is strictly greater than 60 hours",
    "RULE-FLT-03": "breach when the 28 day block total is strictly greater than 100 hours",
    "RULE-REST-04": "breach when rest is strictly less than 12 hours",
    "RULE-QUAL-05": "breach when the aircraft type is not in the crew member's ratings",
    "RULE-CERT-06": "breach when any certificate's valid_to is before the duty date",
    "RULE-BASE-07": (
        "breach when the crew member is based elsewhere and no same-day "
        "positioning flight exists"
    ),
}


def _apply_metric(
    metric: str, field: str | None, rows: Sequence[dict[str, Any]]
) -> float | int:
    """The one piece of arithmetic `aggregate` performs, on the caller's behalf.

    This exists precisely so the model never does it: "how many", "which is
    longest" and "which stations do we serve" are counts, extrema and distinct
    counts over a filtered collection, not free arithmetic in prose.
    """
    if metric == "count":
        return len(rows)
    values: list[Any] = [r[field] for r in rows if field in r and r[field] is not None]
    if metric == "distinct":
        return len({v for v in values})
    if not values:
        return 0
    if metric == "sum":
        return cast(float, round(sum(values), 2))
    if metric == "max":
        return cast("float | int", max(values))
    if metric == "min":
        return cast("float | int", min(values))
    if metric == "mean":
        return cast(float, round(sum(values) / len(values), 2))
    raise ValueError(f"Unknown metric {metric!r}")


def _infer_unit(metric: str, field: str | None) -> FactUnit:
    """A reasonable `Fact.unit` for a figure the caller named by field, not type.

    `aggregate` is generic across collections, so the field name is the only
    signal. This is a best effort label, not a computation: the value itself
    always comes straight from `_apply_metric`.
    """
    if metric in ("count", "distinct") or field is None:
        return "count"
    lowered = field.lower()
    if "hour" in lowered:
        return "hours"
    if "minute" in lowered:
        return "minutes"
    if "inr" in lowered or "cost" in lowered:
        return "inr"
    return "count"


class Tools:
    """The seventeen tools, over the deterministic core. No model, ever."""

    def __init__(
        self,
        world: WorldState | None = None,
        *,
        store: DatasetStore | None = None,
        ops: OpsEngine | None = None,
    ) -> None:
        self.world = world or load_world()
        self.rules = LegalityEngine(self.world)
        self.ops = ops or OpsEngine(self.world, self.rules)
        self.store = store or DatasetStore(self.world)

    def close(self) -> None:
        self.store.close()

    # ============================================================== tier 1

    def find_crew(
        self,
        *,
        base: str | None = None,
        rank: str | None = None,
        aircraft_type: str | None = None,
        on_reserve_date: DateType | None = None,
        available_on: DateType | None = None,
        name_contains: str | None = None,
        crew_ids: list[str] | None = None,
        limit: int = 50,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "base": base,
            "rank": rank,
            "aircraft_type": aircraft_type,
            "on_reserve_date": on_reserve_date,
            "available_on": available_on,
            "name_contains": name_contains,
            "crew_ids": crew_ids,
            "limit": limit,
        }
        if crew_ids:
            missing = [c for c in crew_ids if self.world.crew_member(c) is None]
            if missing:
                return error_envelope(
                    "find_crew",
                    args,
                    f"No crew record for {', '.join(missing)}. The dataset holds "
                    f"{len(self.world.crew)} crew, ids in the form C-1234.",
                    timer=timer,
                )

        matched = self.store.find_crew_ids(
            base=base,
            rank=rank,
            aircraft_type=aircraft_type,
            on_reserve_date=on_reserve_date,
            free_on=available_on,
            name_contains=name_contains,
            crew_ids=crew_ids,
        )
        shown = matched[:limit]
        payload = P.CrewList(
            crew=tuple(self._crew_summary(c) for c in shown),
            total_matched=len(matched),
            all_crew_ids=tuple(matched),
            filters={k: str(v) for k, v in args.items() if v is not None and k != "limit"},
        )
        facts = [
            computed_fact(
                "find_crew.total_matched",
                "Crew matching the filter",
                len(matched),
                "count",
                self._filter_derivation(args),
                _SOURCE,
            ),
            *self._crew_seniority_facts(shown),
            *self._crew_reachability_facts(shown),
        ]
        detail = (
            f"{len(matched)} crew match. "
            + ("No crew match that filter, which is a finding, not a failure."
               if not matched
               else f"Showing {len(shown)}.")
        )
        return ok_envelope(
            "find_crew",
            args,
            payload,
            facts=facts,
            trace=[step("Filter crew", detail, ["find_crew.total_matched"])],
            citations=[cite("crew.json", "filtered query")],
            timer=timer,
            truncated=len(shown) < len(matched),
        )

    def get_crew_detail(
        self, *, crew_id: str, as_of: DateTime | None = None
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"crew_id": crew_id, "as_of": as_of}
        member = self.world.crew_member(crew_id)
        if member is None:
            return error_envelope(
                "get_crew_detail", args, self._unknown_crew(crew_id), timer=timer
            )

        moment = as_of or self.world.snapshot
        on_date = moment.date()
        clocks = self._clock_summary(crew_id, on_date)
        duties = tuple(self._duty_summary(d) for d in self.world.week_duties(crew_id))
        certs = tuple(
            self._cert_summary(crew_id, cert_type, valid_to, on_date)
            for cert_type, valid_to in sorted(
                self.world.certification_expiry(crew_id).items(), key=lambda kv: kv[1]
            )
        )
        risk = self.world.risk_signal(crew_id)
        flagged = tuple(
            f"{f.rule} on {f.date}: {f.note}"
            for f in self.world.flagged_exceptions
            if f.crew_id == crew_id
        )
        payload = P.CrewDetail(
            crew=self._crew_summary(crew_id),
            clocks=clocks,
            duties=duties,
            certifications=certs,
            risk_score=risk.disruption_risk_score if risk else None,
            risk_drivers=risk.drivers if risk else (),
            flagged_exceptions=flagged,
        )
        facts = [
            *self._clock_facts(crew_id, clocks),
            *self._crew_seniority_facts([crew_id]),
            *self._crew_reachability_facts([crew_id]),
            *self._duty_facts(crew_id, duties),
            *self._cert_facts(crew_id, certs),
        ]
        if risk is not None:
            facts.append(
                dataset_fact(
                    f"{crew_id}.risk.score",
                    "Disruption risk score, provided not computed",
                    risk.disruption_risk_score,
                    "percent",
                    f"risk_signals.json#{crew_id}",
                )
            )
        return ok_envelope(
            "get_crew_detail",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Assemble crew record",
                    f"{crew_id} is a {member.rank} at {member.base} rated "
                    f"{', '.join(member.ratings)}, with {len(duties)} duty days this "
                    f"week and {clocks.duty_headroom_7d}h of duty headroom on {on_date}.",
                    [f"{crew_id}.{on_date}.duty_7d.headroom"],
                )
            ],
            citations=[
                cite("crew.json", crew_id),
                cite("duty_clocks.json", crew_id),
                cite("certifications.json", crew_id),
                cite("rosters.json", f"pairings holding {crew_id}"),
                cite("risk_signals.json", crew_id),
            ],
            timer=timer,
        )

    def find_flights(
        self,
        *,
        origin: str | None = None,
        destination: str | None = None,
        on_date: DateType | None = None,
        from_time: DateTime | None = None,
        to_time: DateTime | None = None,
        time_of_day: TimeOfDay = "any",
        flight_numbers: list[str] | None = None,
        pairing_id: str | None = None,
        aircraft_type: str | None = None,
        registration: str | None = None,
        limit: int = 100,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "origin": origin,
            "destination": destination,
            "on_date": on_date,
            "from_time": from_time,
            "to_time": to_time,
            "time_of_day": time_of_day if time_of_day != "any" else None,
            "flight_numbers": flight_numbers,
            "pairing_id": pairing_id,
            "aircraft_type": aircraft_type,
            "registration": registration,
            "limit": limit,
        }
        if pairing_id and self.world.pairing(pairing_id) is None:
            return error_envelope(
                "find_flights", args, self._unknown_pairing(pairing_id), timer=timer
            )

        start, end = self._time_bounds(on_date, from_time, to_time, time_of_day)
        matched = self.store.find_flight_ids(
            origin=origin,
            destination=destination,
            on_date=on_date,
            from_time=start,
            to_time=end,
            flight_numbers=flight_numbers,
            pairing_id=pairing_id,
            aircraft_type=aircraft_type,
        )
        if registration:
            # The tail is not indexed in the SQLite projection, so this filters
            # the already narrowed id list rather than widening the store's
            # query surface. `flights.aircraft` is the tail for every leg.
            matched = [
                fid for fid in matched if self.world.require_flight(fid).aircraft == registration
            ]
        shown = matched[:limit]
        flights = tuple(self._flight_summary(f) for f in shown)
        total_seats = self.world.seats_of(tuple(matched))
        payload = P.FlightList(
            flights=flights,
            total_matched=len(matched),
            all_flight_ids=tuple(matched),
            total_seats=total_seats,
            filters={
                k: str(v) for k, v in args.items() if v is not None and k != "limit"
            },
        )
        facts = [
            computed_fact(
                "find_flights.total_matched",
                "Flights matching the filter",
                len(matched),
                "count",
                self._filter_derivation(args),
                _SOURCE,
            ),
            computed_fact(
                "find_flights.total_seats",
                "Seats across the matching flights",
                total_seats,
                "count",
                f"sum of seats over {len(matched)} matching legs = {total_seats}",
                _SOURCE,
            ),
            *self._flight_facts(shown),
        ]
        return ok_envelope(
            "find_flights",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Filter flights",
                    f"{len(matched)} legs match, {total_seats} seats in total."
                    if matched
                    else "No flights match that filter, which is a finding, not a failure.",
                    ["find_flights.total_matched"],
                )
            ],
            citations=[cite("flights.json", "filtered query")],
            timer=timer,
            truncated=len(shown) < len(matched),
        )

    def find_pairings(
        self,
        *,
        registration: str | None = None,
        on_date: DateType | None = None,
        base: str | None = None,
        aircraft_type: str | None = None,
        crew_id: str | None = None,
        flight_number: str | None = None,
        limit: int = 100,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "registration": registration,
            "on_date": on_date,
            "base": base,
            "aircraft_type": aircraft_type,
            "crew_id": crew_id,
            "flight_number": flight_number,
            "limit": limit,
        }
        if crew_id and self.world.crew_member(crew_id) is None:
            return error_envelope("find_pairings", args, self._unknown_crew(crew_id), timer=timer)

        def matches(pairing: Any) -> bool:
            if registration and pairing.aircraft != registration:
                return False
            if on_date and not any(day.date == on_date for day in pairing.days):
                return False
            first_leg = (
                pairing.days[0].flights[0]
                if pairing.days and pairing.days[0].flights
                else None
            )
            first_flight = self.world.flight(first_leg) if first_leg else None
            if aircraft_type and (
                first_flight is None or first_flight.aircraft_type != aircraft_type
            ):
                return False
            if base and (first_flight is None or first_flight.dep_station != base):
                return False
            if crew_id and pairing.role_of(crew_id) is None:
                return False
            return not flight_number or any(
                self.world.require_flight(fid).flight_no == flight_number
                for day in pairing.days
                for fid in day.flights
            )

        matched = sorted((p for p in self.world.pairings if matches(p)), key=lambda p: p.pairing_id)
        shown = matched[:limit]
        summaries = tuple(self._pairing_summary(p) for p in shown)
        payload = P.PairingList(
            pairings=summaries,
            total_matched=len(matched),
            all_pairing_ids=tuple(p.pairing_id for p in matched),
            filters={k: str(v) for k, v in args.items() if v is not None and k != "limit"},
        )
        facts = [
            computed_fact(
                "find_pairings.total_matched",
                "Pairings matching the filter",
                len(matched),
                "count",
                self._filter_derivation(args),
                _SOURCE,
            ),
            *self._pairing_summary_facts(shown),
        ]
        return ok_envelope(
            "find_pairings",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Filter pairings",
                    f"{len(matched)} pairings match."
                    if matched
                    else "No pairings match that filter, which is a finding, not a failure.",
                    ["find_pairings.total_matched"],
                )
            ],
            citations=[
                cite("rosters.json", "filtered query"),
                cite("flights.json", "tail and route lookups"),
            ],
            timer=timer,
            truncated=len(shown) < len(matched),
        )

    def get_duty_clocks(
        self, *, crew_id: str, as_of: DateTime | None = None
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"crew_id": crew_id, "as_of": as_of}
        if self.world.crew_member(crew_id) is None:
            return error_envelope(
                "get_duty_clocks", args, self._unknown_crew(crew_id), timer=timer
            )
        moment = as_of or self.world.snapshot
        clocks = self._clock_summary(crew_id, moment.date())
        return ok_envelope(
            "get_duty_clocks",
            args,
            clocks,
            facts=self._clock_facts(crew_id, clocks),
            trace=[
                step(
                    "Recompute duty clocks",
                    f"Over {clocks.window_7d_start} to {clocks.as_of}, {crew_id} has "
                    f"{clocks.duty_hours_7d}h of duty against a "
                    f"{clocks.duty_limit_7d:.0f}h limit, leaving "
                    f"{clocks.duty_headroom_7d}h. Windows are calendar UTC dates, "
                    "inclusive of the duty date.",
                    [f"{crew_id}.{clocks.as_of}.duty_7d.headroom"],
                )
            ],
            citations=[
                cite("duty_clocks.json", crew_id, "daily_history, 28 entries"),
                cite("rosters.json", f"duties held by {crew_id} this week"),
            ],
            timer=timer,
        )

    def list_reserves(
        self,
        *,
        on_date: DateType,
        base: str | None = None,
        aircraft_type: str | None = None,
        rank: str | None = None,
        at_time: DateTime | None = None,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "on_date": on_date,
            "base": base,
            "aircraft_type": aircraft_type,
            "rank": rank,
            "at_time": at_time,
        }
        first, last = self.world.date_range
        if not first <= on_date <= last:
            return error_envelope(
                "list_reserves",
                args,
                f"{on_date} is outside the schedule week {first} to {last}.",
                timer=timer,
            )

        rows: list[P.ReserveSummary] = []
        for reserve in self.world.reserves_on(on_date):
            member = self.world.crew_member(reserve.crew_id)
            if member is None:
                continue
            if base and member.base != base:
                continue
            if rank and member.rank != rank:
                continue
            if aircraft_type and not member.is_rated_for(aircraft_type):
                continue
            covers: bool | None = None
            if at_time is not None:
                window = reserve.oncall_window_utc
                day = at_time.date()
                covers = (
                    at_clock(day, window.start) <= at_time <= at_clock(day, window.end)
                )
            rows.append(
                P.ReserveSummary(
                    crew_id=member.crew_id,
                    name=member.name,
                    rank=member.rank,
                    base=member.base,
                    ratings=member.ratings,
                    window_start=reserve.oncall_window_utc.start,
                    window_end=reserve.oncall_window_utc.end,
                    reachability_minutes=member.reachability_minutes,
                    covers_time=covers,
                )
            )

        covering = [r for r in rows if r.covers_time] if at_time else rows
        payload = P.ReserveList(
            on_date=on_date,
            reserves=tuple(rows),
            total_matched=len(rows),
            at_time=at_time,
            note=(
                "All 16 reserves are on call on all seven dates, so the date never "
                "narrows this list. The on-call window is the only filter, and it is "
                "inclusive at both ends. Test it against the required report time, "
                "not against the callout time."
            ),
        )
        facts = [
            computed_fact(
                "list_reserves.total_matched",
                "Reserves matching the filter",
                len(rows),
                "count",
                self._filter_derivation(args),
                _SOURCE,
            ),
            *[
                dataset_fact(
                    f"{r.crew_id}.reachability_minutes",
                    "Reachability",
                    r.reachability_minutes,
                    "minutes",
                    f"crew.json#{r.crew_id}",
                )
                for r in rows
            ],
            *[
                dataset_fact(
                    f"{r.crew_id}.seniority",
                    "Seniority",
                    self.world.require_crew(r.crew_id).seniority,
                    "count",
                    f"crew.json#{r.crew_id}",
                )
                for r in rows
            ],
        ]
        if at_time is not None:
            facts.append(
                computed_fact(
                    "list_reserves.covering_time",
                    "Reserves whose window covers the queried time",
                    len(covering),
                    "count",
                    f"window_start <= {at_time:%H:%M}Z <= window_end, inclusive",
                    _SOURCE,
                )
            )
        return ok_envelope(
            "list_reserves",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "List reserves",
                    f"{len(rows)} reserves match on {on_date}."
                    + (
                        f" {len(covering)} have a window covering {at_time:%H:%M}Z."
                        if at_time
                        else ""
                    ),
                    ["list_reserves.total_matched"],
                )
            ],
            citations=[cite("reserve_pool.json", on_date.isoformat()), cite("crew.json", "join")],
            timer=timer,
        )

    def find_expiring_certifications(
        self,
        *,
        within_days: int = 30,
        as_of: DateType | None = None,
        certification_type: str | None = None,
        base: str | None = None,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "within_days": within_days,
            "as_of": as_of,
            "certification_type": certification_type,
            "base": base,
        }
        if within_days < 0:
            return error_envelope(
                "find_expiring_certifications",
                args,
                f"within_days must not be negative, got {within_days}.",
                timer=timer,
            )
        start = as_of or self.world.snapshot.date()
        until = start + timedelta(days=within_days)
        rows = self.store.expiring_certifications(
            as_of=start,
            until=until,
            certification_type=certification_type,
            base=base,
        )
        certs = tuple(
            self._cert_summary(
                str(r["crew_id"]),
                str(r["cert_type"]),
                DateType.fromisoformat(str(r["valid_to"])),
                start,
            )
            for r in rows
        )
        payload = P.CertificationList(
            as_of=start,
            until=until,
            certifications=certs,
            total_matched=len(certs),
            note=(
                "Validity is tested as valid_to >= duty_date, so a certificate "
                "expiring on a duty date is still valid that day. valid_from is not "
                "consulted: it is unusable in this dataset."
            ),
        )
        facts = [
            computed_fact(
                "find_expiring_certifications.total_matched",
                "Certificates lapsing in the window",
                len(certs),
                "count",
                f"valid_to between {start} and {until} inclusive",
                _SOURCE,
            ),
            computed_fact(
                "find_expiring_certifications.window_days",
                "Window length",
                within_days,
                "days",
                f"{start} plus {within_days} days = {until}",
                _SOURCE,
            ),
            *[
                dataset_fact(
                    f"{c.crew_id}.cert.{c.cert_type}.valid_to",
                    f"{c.cert_type} expiry",
                    c.valid_to,
                    "date",
                    f"certifications.json#{c.crew_id}/{c.cert_type}",
                )
                for c in certs
            ],
            *[
                computed_fact(
                    f"{c.crew_id}.cert.{c.cert_type}.days_remaining",
                    f"Days until {c.cert_type} lapses",
                    c.days_remaining,
                    "days",
                    f"{c.valid_to} - {start} = {c.days_remaining} days",
                    _SOURCE,
                )
                for c in certs
            ],
        ]
        return ok_envelope(
            "find_expiring_certifications",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Scan certifications",
                    f"{len(certs)} of {len(self.world.certifications)} certificates "
                    f"lapse between {start} and {until}.",
                    ["find_expiring_certifications.total_matched"],
                )
            ],
            citations=[cite("certifications.json", f"valid_to in [{start}, {until}]")],
            timer=timer,
        )

    def get_pairing(self, *, pairing_id: str) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"pairing_id": pairing_id}
        pairing = self.world.pairing(pairing_id)
        if pairing is None:
            return error_envelope(
                "get_pairing", args, self._unknown_pairing(pairing_id), timer=timer
            )

        days: list[P.PairingDayView] = []
        for day in pairing.days:
            flights = tuple(self._flight_summary(f) for f in day.flights)
            days.append(
                P.PairingDayView(
                    duty_date=day.date,
                    report_utc=day.report_utc,
                    release_utc=day.release_utc,
                    duty_hours=day.duty_hours,
                    block_hours=self.world.block_hours_of(day.flights),
                    sectors=day.sectors,
                    fdp_limit=self.rules.fdp_limit_for(day.sectors),
                    flights=flights,
                )
            )
        first = self.world.require_flight(pairing.days[0].flights[0])
        last_arrival = self.world.require_flight(pairing.days[0].flights[-1])
        payload = P.PairingView(
            pairing_id=pairing.pairing_id,
            aircraft=pairing.aircraft,
            aircraft_type=first.aircraft_type,
            days=tuple(days),
            crew=tuple(self._crew_summary(m.crew_id) for m in pairing.crew),
            total_legs=len(pairing.flight_ids),
            total_seats=self.world.seats_of(pairing.flight_ids),
            overnights_away_from_base=len(pairing.days) > 1
            and last_arrival.arr_station != first.dep_station,
        )
        facts = [
            computed_fact(
                f"{pairing_id}.total_legs",
                "Legs in the pairing",
                len(pairing.flight_ids),
                "count",
                " + ".join(str(d.sectors) for d in pairing.days)
                + f" = {len(pairing.flight_ids)}",
                _SOURCE,
            ),
            computed_fact(
                f"{pairing_id}.total_seats",
                "Seats across the pairing",
                payload.total_seats,
                "count",
                f"{len(pairing.flight_ids)} legs x seats from flights.json",
                _SOURCE,
            ),
            *[
                f
                for day in days
                for f in (
                    computed_fact(
                        f"{pairing_id}.{day.duty_date}.duty_hours",
                        "Duty length",
                        day.duty_hours,
                        "hours",
                        f"report {day.report_utc:%H:%M}Z to release "
                        f"{day.release_utc:%H:%M}Z = {day.duty_hours}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{pairing_id}.{day.duty_date}.block_hours",
                        "Block hours",
                        day.block_hours,
                        "hours",
                        f"sum of block_hours over {day.sectors} legs = {day.block_hours}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{pairing_id}.{day.duty_date}.fdp_limit",
                        "FDP limit",
                        day.fdp_limit,
                        "hours",
                        f"13.0 - 0.5 x max(0, {day.sectors} - 2) = {day.fdp_limit}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{pairing_id}.{day.duty_date}.sectors",
                        "Sectors",
                        day.sectors,
                        "count",
                        f"{day.sectors} legs on {day.duty_date}",
                        _SOURCE,
                    ),
                )
            ],
            *self._flight_facts(list(pairing.flight_ids)),
            *self._crew_seniority_facts([m.crew_id for m in pairing.crew]),
            *self._crew_reachability_facts([m.crew_id for m in pairing.crew]),
        ]
        return ok_envelope(
            "get_pairing",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Read pairing",
                    f"{pairing_id} is {len(pairing.days)} duty day"
                    f"{'s' if len(pairing.days) != 1 else ''} on {pairing.aircraft}, "
                    f"{len(pairing.flight_ids)} legs, {len(pairing.crew)} crew."
                    + (
                        " The aircraft overnights away from base, so a cover has to "
                        "take the whole remaining pairing."
                        if payload.overnights_away_from_base
                        else ""
                    ),
                    [f"{pairing_id}.total_legs"],
                )
            ],
            citations=[
                cite("rosters.json", pairing_id),
                cite("flights.json", ", ".join(pairing.flight_ids)),
                cite("crew.json", "crew complement"),
            ],
            timer=timer,
        )

    def get_roster(
        self,
        *,
        crew_id: str,
        from_date: DateType | None = None,
        to_date: DateType | None = None,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"crew_id": crew_id, "from_date": from_date, "to_date": to_date}
        if self.world.crew_member(crew_id) is None:
            return error_envelope(
                "get_roster", args, self._unknown_crew(crew_id), timer=timer
            )
        first, last = self.world.date_range
        start = from_date or first
        end = to_date or last
        if end < start:
            return error_envelope(
                "get_roster", args, f"to_date {end} precedes from_date {start}.", timer=timer
            )

        duties = tuple(
            self._duty_summary(d)
            for d in self.world.week_duties(crew_id)
            if start <= d.duty_date <= end
        )
        worked = {d.duty_date for d in duties}
        span = [
            DateType.fromordinal(o)
            for o in range(start.toordinal(), end.toordinal() + 1)
        ]
        total_duty = round(sum(d.duty_hours for d in duties), 2)
        total_block = round(sum(d.block_hours for d in duties), 2)
        payload = P.RosterView(
            crew_id=crew_id,
            from_date=start,
            to_date=end,
            duties=duties,
            total_duty_hours=total_duty,
            total_block_hours=total_block,
            days_off=tuple(d for d in span if d not in worked),
        )
        facts = [
            computed_fact(
                f"{crew_id}.roster.total_duty_hours",
                "Duty hours rostered in the range",
                total_duty,
                "hours",
                " + ".join(str(d.duty_hours) for d in duties) + f" = {total_duty}h"
                if duties
                else "no duties in the range",
                _SOURCE,
            ),
            computed_fact(
                f"{crew_id}.roster.total_block_hours",
                "Block hours rostered in the range",
                total_block,
                "hours",
                " + ".join(str(d.block_hours) for d in duties) + f" = {total_block}h"
                if duties
                else "no duties in the range",
                _SOURCE,
            ),
            computed_fact(
                f"{crew_id}.roster.duty_days",
                "Duty days in the range",
                len(duties),
                "count",
                f"pairing days holding {crew_id} between {start} and {end}",
                _SOURCE,
            ),
            *self._duty_facts(crew_id, duties),
        ]
        return ok_envelope(
            "get_roster",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Read roster",
                    f"{crew_id} works {len(duties)} day"
                    f"{'s' if len(duties) != 1 else ''} between {start} and {end}, "
                    f"{total_duty}h of duty."
                    if duties
                    else f"{crew_id} holds no rostered duty between {start} and {end}.",
                    [f"{crew_id}.roster.total_duty_hours"],
                )
            ],
            citations=[cite("rosters.json", f"pairings holding {crew_id}")],
            timer=timer,
        )

    def find_crew_at_risk(
        self,
        *,
        min_score: float | None = None,
        base: str | None = None,
        on_date: DateType | None = None,
        limit: int = 20,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"min_score": min_score, "base": base, "on_date": on_date, "limit": limit}
        rostered_ids: set[str] | None = None
        if on_date is not None:
            rostered_ids = {
                member.crew_id
                for pairing in self.world.pairings_on(on_date)
                for member in pairing.crew
            }

        rows: list[tuple[Any, Crew]] = []
        for signal in self.world.risk_signals:
            member = self.world.crew_member(signal.crew_id)
            if member is None:
                continue
            if base and member.base != base:
                continue
            if min_score is not None and signal.disruption_risk_score < min_score:
                continue
            rows.append((signal, member))
        rows.sort(key=lambda pair: pair[0].disruption_risk_score, reverse=True)
        shown = rows[:limit]

        entries = tuple(
            P.RiskEntry(
                crew_id=signal.crew_id,
                name=member.name,
                rank=member.rank,
                base=member.base,
                score=signal.disruption_risk_score,
                drivers=signal.drivers,
                rostered_on_date=(
                    signal.crew_id in rostered_ids if rostered_ids is not None else None
                ),
            )
            for signal, member in shown
        )
        payload = P.RiskList(
            entries=entries,
            total_matched=len(rows),
            filters={k: str(v) for k, v in args.items() if v is not None and k != "limit"},
        )
        facts = [
            computed_fact(
                "find_crew_at_risk.total_matched",
                "Crew matching the filter",
                len(rows),
                "count",
                self._filter_derivation(args),
                _SOURCE,
            ),
            *[
                dataset_fact(
                    f"{signal.crew_id}.risk.score",
                    f"{signal.crew_id} disruption risk score, provided not computed",
                    signal.disruption_risk_score,
                    "percent",
                    f"risk_signals.json#{signal.crew_id}",
                )
                for signal, _ in shown
            ],
        ]
        return ok_envelope(
            "find_crew_at_risk",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Rank by disruption risk",
                    f"{len(rows)} crew match the filter, showing the top {len(shown)}."
                    if rows
                    else "No crew match that filter, which is a finding, not a failure.",
                    ["find_crew_at_risk.total_matched"],
                )
            ],
            citations=[
                cite("risk_signals.json", "provided disruption risk score, never modelled here"),
                cite("crew.json", "rank and base"),
            ],
            timer=timer,
            truncated=len(shown) < len(rows),
        )

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
        timer = ToolTimer()
        args: dict[str, Any] = {
            "collection": collection,
            "metric": metric,
            "field": field,
            "group_by": group_by,
            "filters": filters,
            "limit": limit,
        }
        if metric != "count" and field is None:
            return error_envelope(
                "aggregate",
                args,
                f"metric {metric!r} needs a field to {metric} over.",
                timer=timer,
            )
        try:
            rows = self._aggregate_rows(collection)
        except KeyError as exc:
            return error_envelope("aggregate", args, str(exc), timer=timer)

        active = {k: v for k, v in (filters or {}).items() if v is not None}
        for key, value in active.items():
            rows = [r for r in rows if r.get(key) == value]
        if not rows:
            reason = (
                f"No {collection} rows match filters {active}."
                if active
                else f"{collection} is empty."
            )
            return error_envelope("aggregate", args, reason, timer=timer)

        if group_by:
            groups: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                key = str(row.get(group_by))
                groups.setdefault(key, []).append(row)
            computed = sorted(
                (
                    (key, _apply_metric(metric, field, sub))
                    for key, sub in groups.items()
                ),
                key=lambda kv: kv[1],
                reverse=True,
            )[:limit]
            payload = P.AggregateResult(
                collection=collection,
                metric=metric,
                field=field,
                group_by=group_by,
                groups=tuple(computed),
                matched=len(rows),
                filters={k: str(v) for k, v in active.items()},
            )
            facts = [
                computed_fact(
                    f"aggregate.{collection}.{metric}.{group_by}.{key}",
                    f"{metric} of {field or collection} where {group_by}={key}",
                    value,
                    _infer_unit(metric, field),
                    f"{metric} over {len(groups[key])} rows grouped by {group_by}={key}",
                    _SOURCE,
                )
                for key, value in computed
            ]
        else:
            value = _apply_metric(metric, field, rows)
            payload = P.AggregateResult(
                collection=collection,
                metric=metric,
                field=field,
                group_by=None,
                value=value,
                matched=len(rows),
                filters={k: str(v) for k, v in active.items()},
            )
            facts = [
                computed_fact(
                    f"aggregate.{collection}.{metric}.{field or 'rows'}",
                    f"{metric} of {field or collection}",
                    value,
                    _infer_unit(metric, field),
                    f"{metric} over {len(rows)} {collection} rows"
                    + (f" filtered on {active}" if active else ""),
                    _SOURCE,
                )
            ]
        return ok_envelope(
            "aggregate",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    f"Aggregate {collection}",
                    f"{metric} over {len(rows)} rows"
                    + (f", grouped by {group_by}" if group_by else "")
                    + (f", filtered on {active}" if active else "")
                    + ".",
                    [f.key for f in facts[:3]],
                )
            ],
            citations=[cite(f"{collection}.json", "aggregated query")],
            timer=timer,
        )

    def get_cost_rates(self, *, rate_key: str | None = None) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"rate_key": rate_key}
        costs = self.world.costs
        all_rates: tuple[tuple[str, int, str], ...] = (
            (
                "reserve_callout_pilot",
                costs.reserve_callout_pilot,
                "Charged once per assignment for a reserve pilot (Captain or First Officer)",
            ),
            (
                "reserve_callout_cabin",
                costs.reserve_callout_cabin,
                "Charged once per assignment for a reserve cabin crew member",
            ),
            (
                "dayoff_callout_pilot",
                costs.dayoff_callout_pilot,
                "Charged once per assignment for a day-off pilot",
            ),
            (
                "dayoff_callout_cabin",
                costs.dayoff_callout_cabin,
                "Charged once per assignment for a day-off cabin crew member",
            ),
            (
                "deadhead_positioning",
                costs.deadhead_positioning,
                "Charged once when the candidate is not based at the required station",
            ),
            (
                "delay_cost_per_duty_hour",
                costs.delay_cost_per_duty_hour,
                "Per hour the duty's first departure is delayed",
            ),
            (
                "cancellation_per_flight",
                costs.cancellation_per_flight,
                "Per leg cancelled, not per pairing",
            ),
            (
                "hotel_overnight",
                costs.hotel_overnight,
                "Never charged in any shipped answer key, including a DEL overnight",
            ),
        )
        if rate_key:
            matched = tuple(r for r in all_rates if r[0] == rate_key)
            if not matched:
                known = ", ".join(r[0] for r in all_rates)
                return error_envelope(
                    "get_cost_rates",
                    args,
                    f"No cost rate named {rate_key!r}. Known rates: {known}.",
                    timer=timer,
                )
        else:
            matched = all_rates

        payload = P.CostRateTable(
            currency=costs.currency,
            rates=tuple(P.CostRate(key=k, value=v, unit="inr", note=n) for k, v, n in matched),
        )
        facts = [
            dataset_fact(f"costs.{key}", key.replace("_", " "), value, "inr", "costs.json")
            for key, value, _ in matched
        ]
        return ok_envelope(
            "get_cost_rates",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Read cost rates",
                    f"{len(matched)} rate{'s' if len(matched) != 1 else ''} in {costs.currency}, "
                    "as shipped in costs.json.",
                    [f.key for f in facts[:3]],
                )
            ],
            citations=[cite("costs.json", rate_key or "all rates")],
            timer=timer,
        )

    # ============================================================== tier 2

    def check_legality(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        on_date: DateType | None = None,
        as_replacement_for: str | None = None,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "crew_id": crew_id,
            "pairing_id": pairing_id,
            "flight_numbers": flight_numbers,
            "on_date": on_date,
            "as_replacement_for": as_replacement_for,
        }
        if self.world.crew_member(crew_id) is None:
            return error_envelope(
                "check_legality", args, self._unknown_crew(crew_id), timer=timer
            )
        try:
            duties, ref = self._resolve_assignment(pairing_id, flight_numbers, on_date)
        except LookupError as exc:
            return error_envelope("check_legality", args, str(exc), timer=timer)

        exclude = pairing_id
        overlay = self.world.overlay()
        if as_replacement_for:
            if self.world.crew_member(as_replacement_for) is None:
                return error_envelope(
                    "check_legality", args, self._unknown_crew(as_replacement_for), timer=timer
                )
            overlay = overlay.with_absence(as_replacement_for)

        positioning = None
        member = self.world.require_crew(crew_id)
        if member.base != duties[0].origin:
            positioning = self.ops.positioning_for(
                crew_id=crew_id,
                origin=duties[0].origin,
                on_date=duties[0].duty_date,
                first_departure_utc=self._first_departure(duties[0]),
            )

        assessment = self.rules.assess_cover(
            overlay,
            crew_id=crew_id,
            duties=duties,
            exclude_pairing=exclude,
            positioning=positioning,
        )
        facts = self._legality_facts(assessment)
        return ok_envelope(
            "check_legality",
            args,
            assessment.report,
            facts=facts,
            trace=[
                step(
                    f"Evaluate {ref} for {crew_id}",
                    f"Overall {assessment.report.overall.value} across "
                    f"{len(assessment.report.per_day)} duty day"
                    f"{'s' if len(assessment.report.per_day) != 1 else ''}. "
                    + (assessment.reason or "All seven rules pass on every day.")
                    + " A multi-day verdict is the worst day, never an average.",
                    [f.key for f in facts[:4]],
                )
            ],
            citations=[
                cite("rules.json", "all seven rules"),
                cite("duty_clocks.json", crew_id),
                cite("certifications.json", crew_id),
                cite("rosters.json", ref),
            ],
            timer=timer,
        )

    def simulate_absence(
        self,
        *,
        crew_id: str,
        from_date: DateType,
        to_date: DateType | None = None,
        reason: str = "sick call",
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "crew_id": crew_id,
            "from_date": from_date,
            "to_date": to_date,
            "reason": reason,
        }
        if self.world.crew_member(crew_id) is None:
            return error_envelope(
                "simulate_absence", args, self._unknown_crew(crew_id), timer=timer
            )
        report, _ = self.ops.simulate_absence(
            crew_id=crew_id, from_date=from_date, to_date=to_date, reason=reason
        )
        facts = [*report.facts, *self._impact_facts(report)]
        return ok_envelope(
            "simulate_absence",
            args,
            report,
            facts=facts,
            trace=[step("Cascade the absence", report.explanation, [f.key for f in facts[:3]])],
            citations=[
                cite("rosters.json", f"pairings holding {crew_id}"),
                cite("flights.json", "legs of the broken pairings"),
            ],
            timer=timer,
        )

    def simulate_reassignment(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        displacing_crew_id: str | None = None,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "crew_id": crew_id,
            "pairing_id": pairing_id,
            "flight_numbers": flight_numbers,
            "displacing_crew_id": displacing_crew_id,
        }
        if self.world.crew_member(crew_id) is None:
            return error_envelope(
                "simulate_reassignment", args, self._unknown_crew(crew_id), timer=timer
            )
        try:
            duties, ref = self._resolve_assignment(pairing_id, flight_numbers, None)
        except LookupError as exc:
            return error_envelope("simulate_reassignment", args, str(exc), timer=timer)

        report = self.ops.simulate_reassignment(
            crew_id=crew_id,
            duties=duties,
            assignment_ref=ref,
            displacing_crew_id=displacing_crew_id,
            exclude_pairing=pairing_id,
        )
        facts = [*report.facts, *self._impact_facts(report)]
        return ok_envelope(
            "simulate_reassignment",
            args,
            report,
            facts=facts,
            trace=[step("Model the move", report.explanation, [f.key for f in facts[:3]])],
            citations=[cite("rosters.json", ref), cite("rules.json", "all seven rules")],
            timer=timer,
        )

    def simulate_station_closure(
        self, *, station: str, from_time: DateTime, to_time: DateTime
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"station": station, "from_time": from_time, "to_time": to_time}
        if station not in self.world.stations:
            return error_envelope(
                "simulate_station_closure",
                args,
                f"{station} is not in this network. Stations served: "
                f"{', '.join(self.world.stations)}.",
                timer=timer,
            )
        if to_time <= from_time:
            return error_envelope(
                "simulate_station_closure",
                args,
                f"The closure window ends ({to_time}) at or before it starts ({from_time}).",
                timer=timer,
            )

        result = self.ops.simulate_station_closure(
            station=station, from_time=from_time, to_time=to_time
        )
        facts: list[Fact] = [*result.impact.facts, *self._impact_facts(result.impact)]
        for row in result.assessments:
            facts.extend(
                (
                    computed_fact(
                        f"{row.flight_id}.min_delay_hours",
                        "Minimum delay",
                        row.min_delay_hours,
                        "hours",
                        f"reopen {to_time:%H:%M}Z plus 30 minutes turnaround, "
                        f"measured from the {station} event = {row.min_delay_hours}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{row.flight_id}.crew_fdp_after_delay",
                        "Crew FDP after the delay",
                        row.crew_fdp_after_delay,
                        "hours",
                        f"the duty's original length plus {row.min_delay_hours}h, "
                        "with the report unmoved, = "
                        f"{row.crew_fdp_after_delay}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{row.flight_id}.fdp_limit",
                        "FDP limit for that duty",
                        row.fdp_limit,
                        "hours",
                        f"13.0 minus 0.5 per sector beyond 2 = {row.fdp_limit}h",
                        _SOURCE,
                    ),
                )
            )
        payload = {
            "station": station,
            "window_start": from_time,
            "window_end": to_time,
            "affected_flights": list(result.affected),
            "per_flight_assessment": [a.as_answer_key() for a in result.assessments],
            "impact": result.impact,
            "note": (
                "The window is half open: a movement exactly at the reopen time is "
                "not affected. Delays are measured to reopen plus a 30 minute "
                "turnaround."
            ),
        }
        return ok_envelope(
            "simulate_station_closure",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Model the closure",
                    result.impact.explanation,
                    ["closure." + station + ".affected"],
                )
            ],
            citations=[
                cite("flights.json", f"movements at {station}"),
                cite("rosters.json", "duties touched"),
            ],
            timer=timer,
        )

    def simulate_delay(
        self,
        *,
        flight_number: str,
        delay_minutes: int,
        on_date: DateType | None = None,
        mode: DelayMode = "pre_departure",
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "flight_number": flight_number,
            "delay_minutes": delay_minutes,
            "on_date": on_date,
            "mode": mode,
        }
        try:
            ids = self._resolve_flight_ids([flight_number], on_date)
        except LookupError as exc:
            return error_envelope("simulate_delay", args, str(exc), timer=timer)
        flight_id = ids[0]
        if self.world.pairing_for_flight(flight_id) is None:
            return error_envelope(
                "simulate_delay",
                args,
                f"{flight_id} is not covered by any pairing in the roster.",
                timer=timer,
            )

        try:
            result = self.ops.simulate_flight_delay(
                flight_id=flight_id, delay_hours=round(delay_minutes / 60.0, 4), mode=mode
            )
        except KeyError as exc:
            return error_envelope("simulate_delay", args, str(exc), timer=timer)

        facts = [
            *result.impact.facts,
            *self._impact_facts(result.impact),
            computed_fact(
                f"{result.pairing_id}.{result.duty_date}.breach",
                "RULE-FDP-01 breached",
                result.breach,
                "boolean",
                result.breach_detail,
                _SOURCE,
            ),
        ]
        payload = {
            "flight_id": flight_id,
            "pairing_id": result.pairing_id,
            "duty_date": result.duty_date,
            "mode": mode,
            "delay_hours": result.delay_hours,
            "fdp_before": result.fdp_before,
            "fdp_after_delay": result.fdp_after_delay,
            "fdp_limit": result.fdp_limit,
            "breach": result.breach,
            "breach_detail": result.breach_detail,
            "partial_duty_flights": list(result.partial_duty_flights),
            "partial_fdp": result.partial_fdp,
            "partial_fdp_limit": result.partial_fdp_limit,
            "dropped_flights": list(result.dropped_flights),
            "impact": result.impact,
        }
        return ok_envelope(
            "simulate_delay",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    f"Model the {mode.replace('_', ' ')} delay",
                    result.impact.explanation,
                    [f"{result.pairing_id}.{result.duty_date}.fdp_after_delay"],
                )
            ],
            citations=[
                cite("flights.json", flight_id),
                cite("rosters.json", result.pairing_id),
                cite("rules.json", "RULE-FDP-01"),
            ],
            timer=timer,
        )

    def scan_duty_headroom(
        self,
        *,
        on_date: DateType,
        threshold_hours: float | None = None,
        base: str | None = None,
        rank: str | None = None,
        aircraft_type: str | None = None,
        limit: int = 50,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "on_date": on_date,
            "threshold_hours": threshold_hours,
            "base": base,
            "rank": rank,
            "aircraft_type": aircraft_type,
            "limit": limit,
        }
        cutoff = threshold_hours if threshold_hours is not None else 10.0

        rows: list[tuple[Crew, P.ClockSummary]] = []
        for member in self.world.crew:
            if not member.is_active:
                continue
            if base and member.base != base:
                continue
            if rank and member.rank != rank:
                continue
            if aircraft_type and aircraft_type not in member.ratings:
                continue
            clocks = self._clock_summary(member.crew_id, on_date)
            if clocks.duty_headroom_7d <= cutoff or clocks.flight_headroom_28d <= cutoff:
                rows.append((member, clocks))
        rows.sort(key=lambda pair: min(pair[1].duty_headroom_7d, pair[1].flight_headroom_28d))
        shown = rows[:limit]

        entries = tuple(
            {
                "crew_id": member.crew_id,
                "rank": member.rank,
                "base": member.base,
                "duty_headroom_7d": clocks.duty_headroom_7d,
                "flight_headroom_28d": clocks.flight_headroom_28d,
            }
            for member, clocks in shown
        )
        payload = {
            "on_date": on_date,
            "threshold_hours": cutoff,
            "crew": list(entries),
            "total_matched": len(rows),
        }
        facts = [
            computed_fact(
                f"scan_duty_headroom.{on_date}.total_matched",
                "Crew inside the headroom threshold",
                len(rows),
                "count",
                f"active crew with 7 day duty headroom or 28 day flight headroom "
                f"at or below {cutoff}h on {on_date}",
                _SOURCE,
            ),
            *[
                fact
                for member, clocks in shown
                for fact in self._clock_facts(member.crew_id, clocks)
            ],
        ]
        return ok_envelope(
            "scan_duty_headroom",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    "Sweep duty headroom",
                    f"{len(rows)} crew are at or below {cutoff}h headroom on {on_date}."
                    if rows
                    else f"No crew are at or below {cutoff}h headroom on {on_date}.",
                    [f"scan_duty_headroom.{on_date}.total_matched"],
                )
            ],
            citations=[cite("duty_clocks.json", f"as of {on_date}")],
            timer=timer,
            truncated=len(shown) < len(rows),
        )

    # ============================================================== tier 3

    def find_cover_options(
        self,
        *,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        for_crew_id: str | None = None,
        role: str | None = None,
        on_date: DateType | None = None,
        exclude_crew_ids: list[str] | None = None,
        max_options: int = 5,
        include_rejected: bool = True,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "pairing_id": pairing_id,
            "flight_numbers": flight_numbers,
            "for_crew_id": for_crew_id,
            "role": role,
            "on_date": on_date,
            "exclude_crew_ids": exclude_crew_ids,
            "max_options": max_options,
            "include_rejected": include_rejected,
        }
        if not pairing_id and not flight_numbers and not for_crew_id:
            return error_envelope(
                "find_cover_options",
                args,
                "Name a pairing_id, a set of flight_numbers, or a for_crew_id to cover.",
                timer=timer,
            )
        forbid = list(exclude_crew_ids or [])
        resolved_role = role
        sick: str | None = None

        if for_crew_id:
            member = self.world.crew_member(for_crew_id)
            if member is None:
                return error_envelope(
                    "find_cover_options", args, self._unknown_crew(for_crew_id), timer=timer
                )
            # `for_crew_id` names the person vacating the seat, so their rank
            # decides the role directly. Guessing from the pairing (the
            # `_role_to_cover` fallback below) is only for when nobody is named.
            sick = for_crew_id
            if resolved_role is None:
                resolved_role = member.rank
            if pairing_id is None and not flight_numbers:
                lookup_date = on_date or self.world.snapshot.date()
                pairing_id = self._pairing_for_crew_on(for_crew_id, lookup_date)
                if pairing_id is None:
                    return error_envelope(
                        "find_cover_options",
                        args,
                        f"{for_crew_id} holds no pairing on {lookup_date}.",
                        timer=timer,
                    )
            if for_crew_id not in forbid:
                forbid = [*forbid, for_crew_id]

        if resolved_role is None:
            resolved_role, sick = self._role_to_cover(pairing_id, flight_numbers, forbid)
        if resolved_role is None:
            return error_envelope(
                "find_cover_options",
                args,
                "Could not determine which role needs cover. Name the crew member "
                "who is out with for_crew_id, or pass role explicitly.",
                timer=timer,
            )
        try:
            if pairing_id:
                if self.world.pairing(pairing_id) is None:
                    raise LookupError(self._unknown_pairing(pairing_id))
                search = self.ops.find_cover_for_pairing(
                    pairing_id, role=resolved_role, sick_crew_id=sick, forbid_crew=forbid
                )
            else:
                ids = self._resolve_flight_ids(flight_numbers or [], on_date)
                search = self.ops.find_cover_for_flights(
                    ids, role=resolved_role, sick_crew_id=sick, forbid_crew=forbid
                )
        except LookupError as exc:
            return error_envelope("find_cover_options", args, str(exc), timer=timer)

        recommendation = search.to_recommendation()
        kept = recommendation.options[:max_options]
        # Cancellation is always retained: it is the answer of last resort and
        # dropping it would hide the fact that there is always an option.
        if recommendation.options and recommendation.options[-1] not in kept:
            kept = [*kept, recommendation.options[-1]]
        recommendation = recommendation.model_copy(
            update={
                "options": kept,
                "rejected": recommendation.rejected if include_rejected else [],
            }
        )
        facts = [
            *recommendation.facts,
            *[f for option in kept for f in option.facts],
        ]
        best = search.best
        detail = (
            f"{search.candidates_evaluated} candidates evaluated, "
            f"{len(search.excluded)} excluded with reasons, "
            f"{len(search.options) - 1} legal crew options found. "
            + (
                f"Cheapest is {best.crew_id} at INR {best.cost_inr:,}."
                if best
                else "No legal crew option exists, so cancellation is the only answer."
            )
        )
        return ok_envelope(
            "find_cover_options",
            args,
            recommendation,
            facts=facts,
            trace=[step("Search, check, price and rank", detail, [f.key for f in facts[:3]])],
            citations=[
                cite("crew.json", f"every active {resolved_role}"),
                cite("rules.json", "all seven rules per candidate per day"),
                cite("costs.json", "callout, positioning, delay and cancellation rates"),
            ],
            timer=timer,
            truncated=len(kept) < len(search.options),
        )

    def draft_notification(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        channel: Literal["sms", "email", "app"] = "sms",
        option_rank: int | None = None,
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {
            "crew_id": crew_id,
            "pairing_id": pairing_id,
            "flight_numbers": flight_numbers,
            "channel": channel,
            "option_rank": option_rank,
        }
        member = self.world.crew_member(crew_id)
        if member is None:
            return error_envelope(
                "draft_notification", args, self._unknown_crew(crew_id), timer=timer
            )
        try:
            duties, ref = self._resolve_assignment(pairing_id, flight_numbers, None)
        except LookupError as exc:
            return error_envelope("draft_notification", args, str(exc), timer=timer)

        draft = self._build_notification(member, duties, ref, channel)
        facts = [
            *[
                computed_fact(
                    f"{crew_id}.notification.day{i + 1}.report",
                    f"Day {i + 1} report time",
                    day.report_utc,
                    "datetime",
                    f"first departure {self._first_departure(day):%H:%M}Z minus 60 minutes",
                    _SOURCE,
                )
                for i, day in enumerate(duties)
            ],
            computed_fact(
                f"{crew_id}.notification.acknowledge_by",
                "Acknowledgement deadline",
                draft.acknowledge_by_utc,
                "datetime",
                "60 minutes before the day 1 report time",
                _SOURCE,
            ),
            dataset_fact(
                f"{crew_id}.reachability_minutes",
                "Reachability",
                member.reachability_minutes,
                "minutes",
                f"crew.json#{crew_id}",
            ),
            dataset_fact(
                f"{crew_id}.seniority",
                "Seniority",
                member.seniority,
                "count",
                f"crew.json#{crew_id}",
            ),
            *[
                computed_fact(
                    f"{ref}.{day.duty_date}.sectors",
                    "Sectors that day",
                    day.sectors,
                    "count",
                    f"{day.sectors} legs on {day.duty_date}",
                    _SOURCE,
                )
                for day in duties
            ],
            *[
                computed_fact(
                    f"{ref}.{day.duty_date}.block_hours",
                    "Block hours that day",
                    day.block_hours,
                    "hours",
                    f"sum of block_hours over {day.sectors} legs = {day.block_hours}h",
                    _SOURCE,
                )
                for day in duties
            ],
            *[
                computed_fact(
                    f"{ref}.{day.duty_date}.duty_hours",
                    "Duty length that day",
                    day.duty_hours,
                    "hours",
                    f"report to release = {day.duty_hours}h",
                    _SOURCE,
                )
                for day in duties
            ],
        ]
        return ok_envelope(
            "draft_notification",
            args,
            draft,
            facts=facts,
            trace=[
                step(
                    "Fill the callout template",
                    "Every time, station and flight number comes from rosters.json "
                    "and flights.json. The template covers: "
                    + "; ".join(draft.includes),
                    [f"{crew_id}.notification.day1.report"],
                )
            ],
            citations=[cite("rosters.json", ref), cite("flights.json", "legs of the assignment")],
            timer=timer,
        )

    # ======================================================== cross cutting

    def get_watchlist(
        self, *, for_date: DateType, as_of: DateTime | None = None
    ) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"for_date": for_date, "as_of": as_of}
        first, last = self.world.date_range
        if not first <= for_date <= last:
            return error_envelope(
                "get_watchlist",
                args,
                f"{for_date} is outside the schedule week {first} to {last}.",
                timer=timer,
            )
        watchlist = self.ops.build_watchlist(for_date=for_date, as_of=as_of)
        facts = [
            *[f for alert in watchlist.alerts for f in alert.facts],
            *[
                computed_fact(
                    f"watchlist.{for_date}.scanned.{name}",
                    f"{name.replace('_', ' ').capitalize()} scanned",
                    value,
                    "count",
                    f"records examined while building the {for_date} brief",
                    _SOURCE,
                )
                for name, value in watchlist.scanned.items()
            ],
            computed_fact(
                f"watchlist.{for_date}.alerts",
                "Alerts raised",
                len(watchlist.alerts),
                "count",
                watchlist.headline,
                _SOURCE,
            ),
        ]
        return ok_envelope(
            "get_watchlist",
            args,
            watchlist,
            facts=facts,
            trace=[step("Build the brief", watchlist.headline, [f"watchlist.{for_date}.alerts"])],
            citations=[
                cite("rosters.json", "flagged_exceptions and the day's pairings"),
                cite("certifications.json", "expiries inside the horizon"),
                cite("duty_clocks.json", "duty headroom for rostered crew"),
                cite("risk_signals.json", "provided disruption scores"),
            ],
            timer=timer,
        )

    def get_world_summary(self) -> ToolEnvelope:
        timer = ToolTimer()
        first, last = self.world.date_range
        counts = self.store.counts()
        summary = P.WorldSummary(
            snapshot_utc=self.world.snapshot,
            hub="BLR",
            first_date=first,
            last_date=last,
            currency=self.world.costs.currency,
            flights=len(self.world.flights),
            crew=len(self.world.crew),
            pairings=len(self.world.pairings),
            pairing_days=counts["pairing_day"],
            reserves=len(self.world.reserves),
            certifications=len(self.world.certifications),
            rules=len(self.world.rules.rules),
            stations=self.world.stations,
            aircraft_types=tuple(sorted({f.aircraft_type for f in self.world.flights})),
            ranks=tuple(sorted({c.rank for c in self.world.crew})),
            coverage_note=(
                f"This system covers dCortex Air's {first} to {last} schedule out of "
                f"{', '.join(self.world.stations)}, as of the "
                f"{self.world.snapshot:%Y-%m-%d %H:%M}Z snapshot. It knows the seven "
                "rules in rules.json and nothing else: there is no eighth rule, no "
                "other airline, no other week, and no live operational feed. Anything "
                "outside that is out of scope and will be refused rather than guessed."
            ),
        )
        facts = [
            dataset_fact(
                f"world.{name}", label, value, "count", "dataset counts"
            )
            for name, label, value in (
                ("flights", "Flights", summary.flights),
                ("crew", "Crew", summary.crew),
                ("pairings", "Pairings", summary.pairings),
                ("pairing_days", "Pairing days", summary.pairing_days),
                ("reserves", "Reserves", summary.reserves),
                ("certifications", "Certifications", summary.certifications),
                ("rules", "Rules", summary.rules),
            )
        ]
        facts.append(
            dataset_fact(
                "world.snapshot",
                "Snapshot time",
                self.world.snapshot,
                "datetime",
                "duty_clocks.json#as_of_utc",
            )
        )
        return ok_envelope(
            "get_world_summary",
            {},
            summary,
            facts=facts,
            trace=[step("Describe the world", summary.coverage_note, ["world.crew"])],
            citations=[cite("flights.json", "all"), cite("crew.json", "all")],
            timer=timer,
        )

    def explain_rule(self, *, rule_id: str) -> ToolEnvelope:
        timer = ToolTimer()
        args = {"rule_id": rule_id}
        definition = self.world.rules.by_id(rule_id)
        if definition is None:
            return error_envelope(
                "explain_rule",
                args,
                f"{rule_id} is not one of the seven rules. The rulebook holds: "
                f"{', '.join(ALL_RULE_IDS)}. There is no eighth rule.",
                timer=timer,
            )
        params = dict(definition.params or {})
        payload = P.RuleExplanation(
            rule_id=definition.rule_id,  # type: ignore[arg-type]
            text=definition.text,
            params=params,
            title=RULE_TITLES[rule_id],
            comparison=RuleComparison[rule_id],
            applies_to=self.world.rules.time_convention,
            worked_example=RULE_EXAMPLES[rule_id],
        )
        facts = [
            dataset_fact(
                f"{rule_id}.text", "Rule text", definition.text, "text", f"rules.json#{rule_id}"
            ),
            dataset_fact(
                f"{rule_id}.id", "Rule id", rule_id, "rule_id", f"rules.json#{rule_id}"
            ),
            *[
                dataset_fact(
                    f"{rule_id}.param.{name}",
                    name.replace("_", " "),
                    value,
                    "hours" if "hour" in name else "count",
                    f"rules.json#{rule_id}/params/{name}",
                )
                for name, value in params.items()
            ],
        ]
        return ok_envelope(
            "explain_rule",
            args,
            payload,
            facts=facts,
            trace=[
                step(
                    f"Read {rule_id}",
                    f"{definition.text} The breach test is written as: "
                    f"{RuleComparison[rule_id]}.",
                    [f"{rule_id}.text"],
                )
            ],
            citations=[cite("rules.json", rule_id)],
            timer=timer,
        )

    # ========================================================== internals

    def _unknown_crew(self, crew_id: str) -> str:
        return (
            f"No crew record for {crew_id}. The dataset holds "
            f"{len(self.world.crew)} crew, with ids in the form C-1234."
        )

    def _unknown_pairing(self, pairing_id: str) -> str:
        return (
            f"No pairing {pairing_id}. The dataset holds "
            f"{len(self.world.pairings)} pairings, with ids in the form P-2291."
        )

    def _filter_derivation(self, args: dict[str, Any]) -> str:
        """Spell out which filters produced a count.

        A bare "12" is not challengeable. A controller reading
        "12 records matched base=BLR, rank=Captain" can tell at a glance
        whether we asked the question they meant, which is the difference
        between a number they trust and one they have to go and re-derive.
        """
        applied = {
            key: value
            for key, value in args.items()
            if value is not None and key not in {"limit", "as_of"}
        }
        if not applied:
            return "Counted every record in the collection, no filter applied"
        rendered = ", ".join(
            f"{key}={','.join(str(v) for v in value)}"
            if isinstance(value, (list, tuple, set))
            else f"{key}={value}"
            for key, value in sorted(applied.items())
        )
        return f"Counted records matching {rendered}"

    def _aggregate_rows(self, collection: str) -> list[dict[str, Any]]:
        """Every record of one collection, flattened to scalar fields.

        Dates and times are rendered as ISO strings so a `filters` value
        (which travels as `str | int | float | bool | None`) compares equal
        to the row without the caller needing to know the internal type.
        """
        if collection == "flights":
            return [
                {
                    "flight_id": f.flight_id,
                    "flight_no": f.flight_no,
                    "date": f.date.isoformat(),
                    "dep_station": f.dep_station,
                    "arr_station": f.arr_station,
                    "block_hours": f.block_hours,
                    "aircraft": f.aircraft,
                    "aircraft_type": f.aircraft_type,
                    "seats": f.seats,
                }
                for f in self.world.flights
            ]
        if collection == "crew":
            return [
                {
                    "crew_id": c.crew_id,
                    "name": c.name,
                    "rank": c.rank,
                    "base": c.base,
                    "seniority": c.seniority,
                    "reachability_minutes": c.reachability_minutes,
                    "status": c.status,
                }
                for c in self.world.crew
            ]
        if collection == "pairings":
            return [
                {
                    "pairing_id": p.pairing_id,
                    "aircraft": p.aircraft,
                    "aircraft_type": self.world.require_flight(
                        p.days[0].flights[0]
                    ).aircraft_type,
                    "duty_days": len(p.days),
                    "total_legs": len(p.flight_ids),
                    "total_seats": self.world.seats_of(p.flight_ids),
                }
                for p in self.world.pairings
            ]
        if collection == "certifications":
            return [
                {
                    "crew_id": c.crew_id,
                    "cert_type": c.cert_type,
                    "valid_to": c.valid_to.isoformat(),
                }
                for c in self.world.certifications
            ]
        if collection == "reserves":
            return [
                {
                    "crew_id": r.crew_id,
                    "base": r.base,
                    "window_start": r.oncall_window_utc.start,
                    "window_end": r.oncall_window_utc.end,
                }
                for r in self.world.reserves
            ]
        raise KeyError(
            f"Unknown collection {collection!r}. Choose one of flights, crew, "
            "pairings, certifications, reserves."
        )

    def _crew_summary(self, crew_id: str) -> P.CrewSummary:
        member = self.world.require_crew(crew_id)
        reserve = self.world.reserve(crew_id)
        return P.CrewSummary(
            crew_id=member.crew_id,
            name=member.name,
            rank=member.rank,
            base=member.base,
            ratings=member.ratings,
            status=member.status,
            seniority=member.seniority,
            reachability_minutes=member.reachability_minutes,
            is_reserve=reserve is not None,
            oncall_window=str(reserve.oncall_window_utc) if reserve else None,
        )

    def _crew_seniority_facts(self, crew_ids: Sequence[str]) -> list[Fact]:
        return [
            dataset_fact(
                f"{cid}.seniority",
                "Seniority",
                self.world.require_crew(cid).seniority,
                "count",
                f"crew.json#{cid}",
            )
            for cid in crew_ids
        ]

    def _crew_reachability_facts(self, crew_ids: Sequence[str]) -> list[Fact]:
        return [
            dataset_fact(
                f"{cid}.reachability_minutes",
                "Reachability, surfaced but never used in a legality or cost test",
                self.world.require_crew(cid).reachability_minutes,
                "minutes",
                f"crew.json#{cid}",
            )
            for cid in crew_ids
        ]

    def _flight_summary(self, flight_id: str) -> P.FlightSummary:
        flight = self.world.require_flight(flight_id)
        pairing = self.world.pairing_for_flight(flight_id)
        return P.FlightSummary(
            flight_id=flight.flight_id,
            flight_no=flight.flight_no,
            date=flight.date,
            dep_station=flight.dep_station,
            arr_station=flight.arr_station,
            dep_utc=flight.dep_utc,
            arr_utc=flight.arr_utc,
            block_hours=flight.block_hours,
            aircraft=flight.aircraft,
            aircraft_type=flight.aircraft_type,
            seats=flight.seats,
            pairing_id=pairing.pairing_id if pairing else None,
        )

    def _flight_facts(self, flight_ids: Sequence[str]) -> list[Fact]:
        facts: list[Fact] = []
        for fid in flight_ids:
            flight = self.world.require_flight(fid)
            facts.extend(
                (
                    dataset_fact(
                        f"{fid}.block_hours",
                        f"{flight.flight_no} block hours",
                        flight.block_hours,
                        "hours",
                        f"flights.json#{fid}",
                    ),
                    dataset_fact(
                        f"{fid}.seats",
                        f"{flight.flight_no} seats",
                        flight.seats,
                        "count",
                        f"flights.json#{fid}",
                    ),
                )
            )
        return facts

    def _pairing_summary(self, pairing: Any) -> P.PairingSummary:
        first = self.world.require_flight(pairing.days[0].flights[0])
        return P.PairingSummary(
            pairing_id=pairing.pairing_id,
            aircraft=pairing.aircraft,
            aircraft_type=first.aircraft_type,
            first_date=pairing.days[0].date,
            last_date=pairing.days[-1].date,
            duty_days=len(pairing.days),
            total_legs=len(pairing.flight_ids),
            total_seats=self.world.seats_of(pairing.flight_ids),
            crew_ids=tuple(m.crew_id for m in pairing.crew),
        )

    def _pairing_summary_facts(self, pairings: Sequence[Any]) -> list[Fact]:
        facts: list[Fact] = []
        for pairing in pairings:
            facts.extend(
                (
                    computed_fact(
                        f"{pairing.pairing_id}.total_legs",
                        "Legs in the pairing",
                        len(pairing.flight_ids),
                        "count",
                        " + ".join(str(d.sectors) for d in pairing.days)
                        + f" = {len(pairing.flight_ids)}",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{pairing.pairing_id}.total_seats",
                        "Seats across the pairing",
                        self.world.seats_of(pairing.flight_ids),
                        "count",
                        f"{len(pairing.flight_ids)} legs x seats from flights.json",
                        _SOURCE,
                    ),
                    dataset_fact(
                        f"{pairing.pairing_id}.duty_days",
                        "Duty days in the pairing",
                        len(pairing.days),
                        "count",
                        f"rosters.json#{pairing.pairing_id}",
                    ),
                )
            )
        return facts

    def _duty_summary(self, duty: Any) -> P.DutyDaySummary:
        pairing = self.world.require_pairing(duty.pairing_id)
        day = next(d for d in pairing.days if d.date == duty.duty_date)
        return P.DutyDaySummary(
            duty_date=duty.duty_date,
            pairing_id=duty.pairing_id,
            report_utc=duty.report_utc,
            release_utc=duty.release_utc,
            duty_hours=duty.duty_hours,
            block_hours=duty.block_hours,
            sectors=day.sectors,
            flight_numbers=tuple(
                self.world.require_flight(f).flight_no for f in day.flights
            ),
        )

    def _duty_facts(
        self, crew_id: str, duties: Sequence[P.DutyDaySummary]
    ) -> list[Fact]:
        facts: list[Fact] = []
        for duty in duties:
            facts.extend(
                (
                    computed_fact(
                        f"{crew_id}.{duty.duty_date}.duty_hours",
                        f"Duty length on {duty.duty_date}",
                        duty.duty_hours,
                        "hours",
                        f"report {duty.report_utc:%H:%M}Z to release "
                        f"{duty.release_utc:%H:%M}Z = {duty.duty_hours}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{crew_id}.{duty.duty_date}.block_hours",
                        f"Block hours on {duty.duty_date}",
                        duty.block_hours,
                        "hours",
                        f"sum of block_hours over {duty.sectors} legs = "
                        f"{duty.block_hours}h",
                        _SOURCE,
                    ),
                    computed_fact(
                        f"{crew_id}.{duty.duty_date}.sectors",
                        f"Sectors on {duty.duty_date}",
                        duty.sectors,
                        "count",
                        f"{duty.sectors} legs on {duty.pairing_id}",
                        _SOURCE,
                    ),
                )
            )
        return facts

    def _cert_summary(
        self, crew_id: str, cert_type: str, valid_to: DateType, as_of: DateType
    ) -> P.CertificationSummary:
        next_duty = next(
            (d for d in self.world.week_duties(crew_id) if d.duty_date >= as_of), None
        )
        return P.CertificationSummary(
            crew_id=crew_id,
            cert_type=cert_type,
            valid_to=valid_to,
            days_remaining=valid_to.toordinal() - as_of.toordinal(),
            valid_on_next_duty=(
                valid_to >= next_duty.duty_date if next_duty is not None else None
            ),
        )

    def _cert_facts(
        self, crew_id: str, certs: Sequence[P.CertificationSummary]
    ) -> list[Fact]:
        facts: list[Fact] = []
        for cert in certs:
            facts.extend(
                (
                    dataset_fact(
                        f"{crew_id}.cert.{cert.cert_type}.valid_to",
                        f"{cert.cert_type} expiry",
                        cert.valid_to,
                        "date",
                        f"certifications.json#{crew_id}/{cert.cert_type}",
                    ),
                    computed_fact(
                        f"{crew_id}.cert.{cert.cert_type}.days_remaining",
                        f"Days until {cert.cert_type} lapses",
                        cert.days_remaining,
                        "days",
                        f"{cert.valid_to} minus the reference date = "
                        f"{cert.days_remaining} days",
                        _SOURCE,
                    ),
                )
            )
        return facts

    def _clock_summary(self, crew_id: str, on_date: DateType) -> P.ClockSummary:
        overlay = self.world.overlay()
        duty = overlay.window_hours(crew_id, on_date, days=7, kind="duty")
        flight = overlay.window_hours(crew_id, on_date, days=28, kind="flight")
        clock = self.world.duty_clock(crew_id)
        last_duty = [d for d in self.world.week_duties(crew_id) if d.duty_date <= on_date]
        earliest = (
            self.rules.earliest_next_report(last_duty[-1].release_utc)
            if last_duty
            else (clock.last_rest_ended if clock else None)
        )
        return P.ClockSummary(
            crew_id=crew_id,
            as_of=on_date,
            duty_hours_7d=duty,
            duty_limit_7d=self.rules.max_duty_7d,
            duty_headroom_7d=round(self.rules.max_duty_7d - duty, 2),
            flight_hours_28d=flight,
            flight_limit_28d=self.rules.max_flight_28d,
            flight_headroom_28d=round(self.rules.max_flight_28d - flight, 2),
            window_7d_start=on_date - timedelta(days=6),
            window_28d_start=on_date - timedelta(days=27),
            last_rest_ended=clock.last_rest_ended if clock else None,
            earliest_next_report=earliest,
        )

    def _clock_facts(self, crew_id: str, clocks: P.ClockSummary) -> list[Fact]:
        return [
            computed_fact(
                f"{crew_id}.{clocks.as_of}.duty_7d",
                "Duty hours in the 7 days ending this date",
                clocks.duty_hours_7d,
                "hours",
                f"daily_history plus rostered duties over {clocks.window_7d_start} to "
                f"{clocks.as_of}, inclusive calendar dates = {clocks.duty_hours_7d}h",
                _SOURCE,
            ),
            computed_fact(
                f"{crew_id}.{clocks.as_of}.duty_7d.headroom",
                "Headroom under RULE-DUTY-02",
                clocks.duty_headroom_7d,
                "hours",
                f"{clocks.duty_limit_7d:.0f} - {clocks.duty_hours_7d} = "
                f"{clocks.duty_headroom_7d}h "
                f"({format_duration(max(clocks.duty_headroom_7d, 0.0))})",
                _SOURCE,
            ),
            dataset_fact(
                f"{crew_id}.duty_limit_7d",
                "RULE-DUTY-02 limit",
                clocks.duty_limit_7d,
                "hours",
                "rules.json#RULE-DUTY-02/params/max_duty_hours",
            ),
            computed_fact(
                f"{crew_id}.{clocks.as_of}.flight_28d",
                "Block hours in the 28 days ending this date",
                clocks.flight_hours_28d,
                "hours",
                f"daily_history plus rostered legs over {clocks.window_28d_start} to "
                f"{clocks.as_of} = {clocks.flight_hours_28d}h",
                _SOURCE,
            ),
            computed_fact(
                f"{crew_id}.{clocks.as_of}.flight_28d.headroom",
                "Headroom under RULE-FLT-03",
                clocks.flight_headroom_28d,
                "hours",
                f"{clocks.flight_limit_28d:.0f} - {clocks.flight_hours_28d} = "
                f"{clocks.flight_headroom_28d}h",
                _SOURCE,
            ),
            dataset_fact(
                f"{crew_id}.flight_limit_28d",
                "RULE-FLT-03 limit",
                clocks.flight_limit_28d,
                "hours",
                "rules.json#RULE-FLT-03/params/max_flight_hours",
            ),
        ]

    def _legality_facts(self, assessment: Any) -> list[Fact]:
        facts: list[Fact] = []
        for day in assessment.report.per_day:
            for trace in day.traces:
                facts.extend(trace.inputs)
                if trace.observed is not None:
                    facts.append(
                        computed_fact(
                            f"{assessment.crew_id}.{day.duty_date}.{trace.rule_id}.observed",
                            f"{trace.title} observed",
                            trace.observed,
                            "hours" if trace.unit == "hours" else "count",
                            trace.arithmetic,
                            _SOURCE,
                        )
                    )
                if trace.limit is not None:
                    facts.append(
                        computed_fact(
                            f"{assessment.crew_id}.{day.duty_date}.{trace.rule_id}.limit",
                            f"{trace.title} limit",
                            trace.limit,
                            "hours" if trace.unit == "hours" else "count",
                            trace.arithmetic,
                            _SOURCE,
                        )
                    )
                if trace.margin is not None:
                    facts.append(
                        computed_fact(
                            f"{assessment.crew_id}.{day.duty_date}.{trace.rule_id}.margin",
                            f"{trace.title} margin",
                            trace.margin,
                            "hours" if trace.unit == "hours" else "count",
                            trace.margin_human or trace.arithmetic,
                            _SOURCE,
                        )
                    )
        return facts

    def _impact_facts(self, report: Any) -> list[Fact]:
        return [
            computed_fact(
                "impact.passengers_affected",
                "Passengers exposed",
                report.passengers_affected,
                "count",
                "seats on the legs left uncrewed on the day of the disruption",
                _SOURCE,
            ),
            computed_fact(
                "impact.uncrewed_flights",
                "Legs left uncrewed",
                len(report.uncrewed_flights),
                "count",
                "legs of every broken pairing",
                _SOURCE,
            ),
            *[
                dataset_fact(
                    f"impact.flight.{f.flight_no}.passengers",
                    f"{f.flight_no} seats",
                    f.passengers,
                    "count",
                    f"flights.json#{f.flight_no}",
                )
                for f in report.uncrewed_flights
                if f.passengers is not None
            ],
        ]

    def _time_bounds(
        self,
        on_date: DateType | None,
        from_time: DateTime | None,
        to_time: DateTime | None,
        time_of_day: TimeOfDay,
    ) -> tuple[str | None, str | None]:
        start = from_time.isoformat(sep=" ") if from_time else None
        end = to_time.isoformat(sep=" ") if to_time else None
        if time_of_day != "any" and on_date is not None:
            low, high = TIME_OF_DAY_WINDOWS[time_of_day]
            window_start = DateTime.combine(on_date, DateTime.min.time()) + timedelta(hours=low)
            window_end = DateTime.combine(on_date, DateTime.min.time()) + timedelta(
                hours=high, minutes=-1
            )
            start = max(start, window_start.isoformat(sep=" ")) if start else (
                window_start.isoformat(sep=" ")
            )
            end = min(end, window_end.isoformat(sep=" ")) if end else (
                window_end.isoformat(sep=" ")
            )
        return start, end

    def _resolve_flight_ids(
        self, flight_numbers: Sequence[str], on_date: DateType | None
    ) -> list[str]:
        """Turn flight numbers into flight ids, refusing an ambiguous reference.

        A flight number without a date matches up to seven legs. Guessing which
        one the controller meant is exactly the kind of silent assumption this
        system exists to avoid.
        """
        resolved: list[str] = []
        for number in flight_numbers:
            if "-" in number and self.world.flight(number) is not None:
                resolved.append(number)
                continue
            candidates = self.world.flights_numbered(number)
            if not candidates:
                raise LookupError(
                    f"No flight {number} in the schedule. The network operates "
                    f"{len({f.flight_no for f in self.world.flights})} flight numbers."
                )
            if on_date is not None:
                match = self.world.flight_on(number, on_date)
                if match is None:
                    raise LookupError(f"{number} does not operate on {on_date}.")
                resolved.append(match.flight_id)
                continue
            if len(candidates) > 1:
                dates = ", ".join(str(c.date) for c in candidates)
                raise LookupError(
                    f"{number} operates on {len(candidates)} dates ({dates}). "
                    "Name the date so the right leg is used."
                )
            resolved.append(candidates[0].flight_id)
        return resolved

    def _resolve_assignment(
        self,
        pairing_id: str | None,
        flight_numbers: Sequence[str] | None,
        on_date: DateType | None,
    ) -> tuple[tuple[ProposedDuty, ...], str]:
        if pairing_id:
            if self.world.pairing(pairing_id) is None:
                raise LookupError(self._unknown_pairing(pairing_id))
            return proposed_duties_for_pairing(self.world, pairing_id), pairing_id
        if flight_numbers:
            ids = self._resolve_flight_ids(flight_numbers, on_date)
            duty = proposed_duty_from_flights(self.world, ids)
            return (duty,), ", ".join(ids)
        raise LookupError(
            "Name a pairing_id, or flight_numbers with a date, so the assignment "
            "is unambiguous."
        )

    def _pairing_for_crew_on(self, crew_id: str, on_date: DateType) -> str | None:
        """The pairing this crew member holds on a given date, if any.

        There is no reverse index from crew and date to pairing in the shipped
        data, so this scans the crew member's held pairings (there are at most
        a handful) and returns the one with a duty day on `on_date`. No crew
        appears on two pairings on the same calendar date, so at most one match
        exists.
        """
        for pairing_id in self.world.pairing_ids_for_crew(crew_id):
            pairing = self.world.pairing(pairing_id)
            if pairing is not None and any(day.date == on_date for day in pairing.days):
                return pairing_id
        return None

    def _role_to_cover(
        self,
        pairing_id: str | None,
        flight_numbers: Sequence[str] | None,
        forbid: Sequence[str],
    ) -> tuple[str | None, str | None]:
        """Work out which seat needs filling, and who is vacating it."""
        for crew_id in forbid:
            member = self.world.crew_member(crew_id)
            if member is not None:
                return member.rank, crew_id
        target = pairing_id
        if target is None and flight_numbers:
            try:
                ids = self._resolve_flight_ids(flight_numbers, None)
            except LookupError:
                return None, None
            pairing = self.world.pairing_for_flight(ids[0]) if ids else None
            target = pairing.pairing_id if pairing else None
        if target is None:
            return None, None
        pairing = self.world.pairing(target)
        if pairing is None:
            return None, None
        captains = pairing.crew_in_role("Captain")
        return ("Captain", captains[0] if captains else None)

    def _first_departure(self, duty: ProposedDuty) -> DateTime:
        if duty.flight_ids:
            return self.world.require_flight(duty.flight_ids[0]).dep_utc
        return duty.report_utc + timedelta(hours=1)

    def _build_notification(
        self,
        member: Crew,
        duties: Sequence[ProposedDuty],
        ref: str,
        channel: str,
    ) -> P.NotificationDraft:
        first = duties[0]
        origin = first.origin
        acknowledge_by = first.report_utc - timedelta(hours=1)
        lines: list[str] = [
            f"{member.rank} {member.crew_id}, you are called out for {ref}.",
            "",
        ]
        for index, duty in enumerate(duties, start=1):
            legs = " / ".join(
                self.world.require_flight(f).flight_no for f in duty.flight_ids
            )
            station = duty.origin
            label = f"Day {index} ({duty.duty_date})" if len(duties) > 1 else str(duty.duty_date)
            lines.append(
                f"{label}: report {duty.report_utc:%H:%M}Z at {station} crew room. "
                f"Flights {legs}. Release {duty.release_utc:%H:%M}Z."
            )
            if index < len(duties):
                last_leg = self.world.require_flight(duty.flight_ids[-1])
                lines.append(
                    f"  Overnight at {last_leg.arr_station}, hotel arranged."
                )
        lines.extend(
            [
                "",
                f"Please acknowledge by {acknowledge_by:%H:%M}Z on "
                f"{acknowledge_by.date()}.",
                "Questions: Crew Control desk, on the usual number.",
            ]
        )
        includes = [
            "crew_id and assignment reference",
            f"report time and place for day 1: {first.report_utc:%H:%M}Z at {origin}",
            *[
                f"flights day {i}: "
                + "/".join(
                    self.world.require_flight(f).flight_no for f in duty.flight_ids
                )
                for i, duty in enumerate(duties, start=1)
            ],
            *(
                ["overnight station and hotel"]
                if len(duties) > 1
                else []
            ),
            "acknowledgement request with a deadline",
            "contact for questions",
        ]
        return P.NotificationDraft(
            crew_id=member.crew_id,
            channel=channel,
            subject=f"Callout: {ref}, report {first.report_utc:%H:%M}Z {first.duty_date}",
            body="\n".join(lines),
            includes=tuple(includes),
            acknowledge_by_utc=acknowledge_by,
        )


def _unused_flight_type_hint(_: Flight) -> None:  # pragma: no cover
    """Keeps the `Flight` import meaningful for readers of the type hints."""


__all__ = ["RULE_EXAMPLES", "TIME_OF_DAY_WINDOWS", "Tools"]
