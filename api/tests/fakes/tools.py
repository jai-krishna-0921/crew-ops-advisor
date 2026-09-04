"""A `ToolSurface` implementation over a small hand built fixture.

Values come from `docs/DATA-MODEL.md`, which verified them numerically against
the shipped dataset. The point is not to reimplement the core; it is to give
the agent, the verifier, the resolver, the CLI and the server something real
enough to be developed and tested against before the core lands, and to keep
working afterwards as a fast, deterministic stand in.

Anchor facts encoded here:

  C-1042  A. Nair, Captain, BLR, A320, seniority 22, reachability 90 min
  P-2291  two days, DX412/413/588 on 15 Sep and DX589/590/591 on 16 Sep
  C-2087  breaches RULE-DUTY-02 covering P-2291: 61.33h vs 60h, over by 1h20m
  C-3310  reserve, covers P-2291 cleanly at INR 18,500
  C-2210  DEL based, legal via deadhead at INR 41,200 with 3h delay to DX412
  C-3305  legal on day 1 (59.50h), breaches on day 2 (68.25h, over by 8h15m)
  C-2091  ATR72 only, the RULE-QUAL-05 exclusion
  C-5417  recurrent_training expired 2026-09-17, rostered 2026-09-19
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from crewops.contracts import (
    Alert,
    Citation,
    Confidence,
    CostBreakdown,
    CostLine,
    CoverKind,
    CoverOption,
    DayLegality,
    DownstreamRisk,
    Fact,
    FlightRef,
    ImpactReport,
    LegalityReport,
    Provenance,
    Recommendation,
    RiskSeverity,
    RuleTrace,
    ToolEnvelope,
    TraceStep,
    Verdict,
    Watchlist,
)

SNAPSHOT = datetime(2026, 9, 14, 18, 0, 0)

STATIONS = ("BLR", "BOM", "CCU", "COK", "DEL", "GOI", "HYD", "MAA")

CREW: dict[str, dict[str, Any]] = {
    "C-1042": {
        "name": "A. Nair", "rank": "Captain", "base": "BLR", "ratings": ["A320"],
        "seniority": 22, "reachability_minutes": 90, "status": "active",
        "duty_hours_7d": 20.93, "flight_hours_28d": 64.27, "risk_score": 0.42,
        "reserve": False,
    },
    "C-2087": {
        "name": "R. Iyer", "rank": "Captain", "base": "BLR", "ratings": ["A320"],
        "seniority": 11, "reachability_minutes": 60, "status": "active",
        "duty_hours_7d": 51.83, "flight_hours_28d": 71.5, "risk_score": 0.61,
        "reserve": False,
    },
    "C-3310": {
        "name": "S. Kapoor", "rank": "Captain", "base": "BLR", "ratings": ["A320"],
        "seniority": 8, "reachability_minutes": 45, "status": "active",
        "duty_hours_7d": 0.0, "flight_hours_28d": 9.34, "risk_score": 0.10,
        "reserve": True, "oncall": ("06:00", "18:00"),
    },
    "C-3305": {
        "name": "K. Rao", "rank": "Captain", "base": "BLR", "ratings": ["A320"],
        "seniority": 9, "reachability_minutes": 55, "status": "active",
        "duty_hours_7d": 50.0, "flight_hours_28d": 60.0, "risk_score": 0.35,
        "reserve": True, "oncall": ("00:00", "05:30"),
    },
    "C-2210": {
        "name": "P. Sharma", "rank": "Captain", "base": "DEL", "ratings": ["A320"],
        "seniority": 15, "reachability_minutes": 80, "status": "active",
        "duty_hours_7d": 18.0, "flight_hours_28d": 55.0, "risk_score": 0.22,
        "reserve": True, "oncall": ("03:00", "15:00"),
    },
    "C-2091": {
        "name": "H. Naidu", "rank": "Captain", "base": "BLR", "ratings": ["ATR72"],
        "seniority": 4, "reachability_minutes": 75, "status": "active",
        "duty_hours_7d": 12.0, "flight_hours_28d": 30.0, "risk_score": 0.18,
        "reserve": False,
    },
    "C-5417": {
        "name": "N. Verma", "rank": "Cabin Crew", "base": "BLR", "ratings": ["A320"],
        "seniority": 3, "reachability_minutes": 70, "status": "active",
        "duty_hours_7d": 22.0, "flight_hours_28d": 40.0, "risk_score": 0.55,
        "reserve": False,
    },
    "C-3311": {
        "name": "T. Menon", "rank": "First Officer", "base": "BLR", "ratings": ["A320"],
        "seniority": 6, "reachability_minutes": 50, "status": "active",
        "duty_hours_7d": 4.0, "flight_hours_28d": 20.0, "risk_score": 0.12,
        "reserve": True, "oncall": ("06:00", "18:00"),
    },
}

CERTIFICATIONS: dict[str, list[dict[str, Any]]] = {
    "C-1042": [
        {"type": "licence", "valid_to": date(2027, 3, 1)},
        {"type": "medical", "valid_to": date(2026, 12, 4)},
        {"type": "recurrent_training", "valid_to": date(2027, 1, 15)},
    ],
    "C-5417": [
        {"type": "licence", "valid_to": date(2027, 5, 9)},
        {"type": "medical", "valid_to": date(2026, 11, 30)},
        {"type": "recurrent_training", "valid_to": date(2026, 9, 17)},
    ],
}

FLIGHTS: list[dict[str, Any]] = [
    {"flight_no": "DX412", "date": date(2026, 9, 15), "dep": "BLR", "arr": "BOM",
     "dep_utc": datetime(2026, 9, 15, 7, 0), "arr_utc": datetime(2026, 9, 15, 8, 45),
     "block_hours": 1.75, "aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2291"},
    {"flight_no": "DX413", "date": date(2026, 9, 15), "dep": "BOM", "arr": "BLR",
     "dep_utc": datetime(2026, 9, 15, 9, 45), "arr_utc": datetime(2026, 9, 15, 11, 30),
     "block_hours": 1.75, "aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2291"},
    {"flight_no": "DX588", "date": date(2026, 9, 15), "dep": "BLR", "arr": "DEL",
     "dep_utc": datetime(2026, 9, 15, 12, 15), "arr_utc": datetime(2026, 9, 15, 15, 0),
     "block_hours": 2.75, "aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2291"},
    {"flight_no": "DX589", "date": date(2026, 9, 16), "dep": "DEL", "arr": "BLR",
     "dep_utc": datetime(2026, 9, 16, 5, 0), "arr_utc": datetime(2026, 9, 16, 7, 45),
     "block_hours": 2.75, "aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2291"},
    {"flight_no": "DX590", "date": date(2026, 9, 16), "dep": "BLR", "arr": "HYD",
     "dep_utc": datetime(2026, 9, 16, 9, 0), "arr_utc": datetime(2026, 9, 16, 10, 0),
     "block_hours": 1.0, "aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2291"},
    {"flight_no": "DX591", "date": date(2026, 9, 16), "dep": "HYD", "arr": "BLR",
     "dep_utc": datetime(2026, 9, 16, 13, 0), "arr_utc": datetime(2026, 9, 16, 14, 15),
     "block_hours": 1.25, "aircraft": "VT-DXC", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2291"},
    {"flight_no": "DX402", "date": date(2026, 9, 15), "dep": "DEL", "arr": "BLR",
     "dep_utc": datetime(2026, 9, 15, 6, 0), "arr_utc": datetime(2026, 9, 15, 8, 45),
     "block_hours": 2.75, "aircraft": "VT-DXA", "aircraft_type": "A320", "seats": 162,
     "pairing_id": "P-2201"},
]

PAIRINGS: dict[str, dict[str, Any]] = {
    "P-2291": {
        "aircraft": "VT-DXC",
        "aircraft_type": "A320",
        "days": [
            {"duty_date": date(2026, 9, 15), "report": datetime(2026, 9, 15, 6, 0),
             "release": datetime(2026, 9, 15, 15, 30), "duty_hours": 9.5, "sectors": 3,
             "legs": ["DX412", "DX413", "DX588"]},
            {"duty_date": date(2026, 9, 16), "report": datetime(2026, 9, 16, 4, 0),
             "release": datetime(2026, 9, 16, 14, 45), "duty_hours": 10.75, "sectors": 3,
             "legs": ["DX589", "DX590", "DX591"]},
        ],
        "crew": {"Captain": "C-1042", "First Officer": "C-3311"},
    }
}

RULES: dict[str, dict[str, Any]] = {
    "RULE-FDP-01": {"text": "Max flight duty period 13h, reduced 0.5h per sector "
                            "beyond the 2nd.",
                    "params": {"base_fdp_hours": 13.0,
                               "reduction_per_extra_sector_hours": 0.5,
                               "free_sectors": 2}},
    "RULE-DUTY-02": {"text": "Max 60 duty hours in any 7 consecutive calendar days "
                             "(inclusive of duty date).",
                     "params": {"max_duty_hours": 60, "window_days": 7}},
    "RULE-FLT-03": {"text": "Max 100 flight (block) hours in any 28 consecutive "
                            "calendar days.",
                    "params": {"max_flight_hours": 100, "window_days": 28}},
    "RULE-REST-04": {"text": "Min 12h rest between release and next report.",
                     "params": {"min_rest_hours": 12}},
    "RULE-QUAL-05": {"text": "Crew must hold a valid rating for the assigned "
                             "aircraft type.", "params": {}},
    "RULE-CERT-06": {"text": "All certifications must be valid on the duty date.",
                     "params": {}},
    "RULE-BASE-07": {"text": "Reserve callout from own base only; covering from "
                             "another base requires deadhead positioning (cost "
                             "applies).", "params": {}},
}

#: Per crew, per duty date: the 7 day duty total once P-2291 cover is added, and
#: the verdict. Verified in docs/DATA-MODEL.md section 7.
DUTY_UNDER_COVER: dict[str, dict[date, tuple[float, float, Verdict]]] = {
    "C-2087": {
        date(2026, 9, 15): (51.83, 61.33, Verdict.BREACH),
        date(2026, 9, 16): (40.83, 61.08, Verdict.BREACH),
    },
    "C-3305": {
        date(2026, 9, 15): (50.0, 59.5, Verdict.PASS),
        date(2026, 9, 16): (48.0, 68.25, Verdict.BREACH),
    },
    "C-3310": {
        date(2026, 9, 15): (0.0, 9.5, Verdict.PASS),
        date(2026, 9, 16): (9.5, 20.25, Verdict.PASS),
    },
    "C-2210": {
        date(2026, 9, 15): (18.0, 27.5, Verdict.PASS),
        date(2026, 9, 16): (27.5, 38.25, Verdict.PASS),
    },
    "C-2091": {
        date(2026, 9, 15): (12.0, 21.5, Verdict.PASS),
        date(2026, 9, 16): (21.5, 32.25, Verdict.PASS),
    },
}


def _fmt_hm(hours: float) -> str:
    total = round(hours * 60)
    h, m = divmod(abs(total), 60)
    sign = "-" if total < 0 else ""
    if h and m:
        return f"{sign}{h}h{m:02d}m"
    return f"{sign}{h}h" if h else f"{sign}{m}m"


def _fact(
    key: str,
    label: str,
    value: Any,
    unit: str,
    *,
    source: str,
    provenance: Provenance = Provenance.DATASET,
    derivation: str | None = None,
) -> Fact:
    return Fact(
        key=key,
        label=label,
        value=value,
        unit=unit,  # type: ignore[arg-type]
        provenance=provenance,
        source=source,
        derivation=derivation,
    )


@dataclass
class FakeTools:
    """Implements `crewops.contracts.ToolSurface`."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail: set[str] = field(default_factory=set)
    latency_ms: int = 3

    # ------------------------------------------------------------- plumbing

    def _record(self, name: str, args: dict[str, Any]) -> None:
        self.calls.append((name, args))

    def tools_called(self) -> list[str]:
        return [name for name, _ in self.calls]

    def _fail(self, name: str, args: dict[str, Any], message: str) -> ToolEnvelope:
        return ToolEnvelope(
            tool=name, args=args, ok=False, error=message, latency_ms=self.latency_ms
        )

    def _ok(
        self,
        name: str,
        args: dict[str, Any],
        payload: Any,
        facts: list[Fact],
        trace: list[TraceStep],
        citations: list[Citation],
    ) -> ToolEnvelope:
        return ToolEnvelope(
            tool=name,
            args=args,
            ok=True,
            payload=payload,
            facts=facts,
            trace=trace,
            citations=citations,
            latency_ms=self.latency_ms,
        )

    # --------------------------------------------------------------- tier 1

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
        args = {
            k: v
            for k, v in {
                "base": base, "rank": rank, "aircraft_type": aircraft_type,
                "on_reserve_date": on_reserve_date, "available_on": available_on,
                "name_contains": name_contains, "crew_ids": crew_ids, "limit": limit,
            }.items()
            if v is not None
        }
        self._record("find_crew", args)
        if "find_crew" in self.fail:
            return self._fail("find_crew", args, "injected failure")

        rows = []
        for crew_id, record in CREW.items():
            if base and record["base"] != base:
                continue
            if rank and record["rank"] != rank:
                continue
            if aircraft_type and aircraft_type not in record["ratings"]:
                continue
            if on_reserve_date and not record.get("reserve"):
                continue
            if crew_ids and crew_id not in crew_ids:
                continue
            if name_contains and name_contains.lower() not in record["name"].lower():
                continue
            rows.append({"crew_id": crew_id, **record})

        facts = [
            _fact("find_crew.count", "Crew matching the filter", len(rows), "count",
                  source="crew.json", provenance=Provenance.COMPUTED,
                  derivation=f"{len(rows)} of {len(CREW)} crew match the filter set")
        ]
        for row in rows:
            facts.append(
                _fact(f"{row['crew_id']}.rank", f"{row['crew_id']} rank",
                      row["rank"], "rank", source=f"crew.json#{row['crew_id']}")
            )
            facts.append(
                _fact(f"{row['crew_id']}.base", f"{row['crew_id']} base",
                      row["base"], "station", source=f"crew.json#{row['crew_id']}")
            )
        return self._ok(
            "find_crew", args, rows, facts,
            [TraceStep(label="Filtered crew",
                       detail=f"{len(rows)} of {len(CREW)} crew match")],
            [Citation(file="crew.json", pointer="filter")],
        )

    def get_crew_detail(
        self, *, crew_id: str, as_of: datetime | None = None
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"crew_id": crew_id}
        if as_of:
            args["as_of"] = as_of
        self._record("get_crew_detail", args)
        if "get_crew_detail" in self.fail:
            return self._fail("get_crew_detail", args, "injected failure")
        record = CREW.get(crew_id)
        if record is None:
            return self._fail(
                "get_crew_detail", args,
                f"No crew member {crew_id} in the dataset. The lookup failed; this "
                "is not a finding that the crew member is unavailable.",
            )
        payload = {"crew_id": crew_id, **record,
                   "certifications": CERTIFICATIONS.get(crew_id, [])}
        facts = [
            _fact(f"{crew_id}.name", "Name", record["name"], "text",
                  source=f"crew.json#{crew_id}"),
            _fact(f"{crew_id}.rank", "Rank", record["rank"], "rank",
                  source=f"crew.json#{crew_id}"),
            _fact(f"{crew_id}.base", "Base", record["base"], "station",
                  source=f"crew.json#{crew_id}"),
            _fact(f"{crew_id}.rating", "Rating", record["ratings"][0], "aircraft_type",
                  source=f"crew.json#{crew_id}"),
            _fact(f"{crew_id}.seniority", "Seniority", record["seniority"], "count",
                  source=f"crew.json#{crew_id}"),
            _fact(f"{crew_id}.reachability", "Reachability",
                  record["reachability_minutes"], "minutes",
                  source=f"crew.json#{crew_id}"),
            _fact(f"{crew_id}.duty_7d", "Duty hours, 7 days to 2026-09-14",
                  record["duty_hours_7d"], "hours",
                  source=f"duty_clocks.json#{crew_id}"),
            _fact(f"{crew_id}.flight_28d", "Block hours, 28 days to 2026-09-14",
                  record["flight_hours_28d"], "hours",
                  source=f"duty_clocks.json#{crew_id}"),
            _fact(f"{crew_id}.risk", "Disruption risk score", record["risk_score"],
                  "percent", source=f"risk_signals.json#{crew_id}"),
        ]
        if record.get("oncall"):
            start, end = record["oncall"]
            facts.append(
                _fact(f"{crew_id}.oncall_start", "On-call window start", start,
                      "datetime", source=f"reserve_pool.json#{crew_id}")
            )
            facts.append(
                _fact(f"{crew_id}.oncall_end", "On-call window end", end, "datetime",
                      source=f"reserve_pool.json#{crew_id}")
            )
        return self._ok(
            "get_crew_detail", args, payload, facts,
            [TraceStep(
                label=f"Read {crew_id}",
                detail=(
                    f"{record['name']}, {record['rank']}, base {record['base']}, "
                    f"rated {'/'.join(record['ratings'])}"
                ),
            )],
            [Citation(file="crew.json", pointer=crew_id),
             Citation(file="duty_clocks.json", pointer=crew_id)],
        )

    def find_flights(
        self,
        *,
        origin: str | None = None,
        destination: str | None = None,
        on_date: date | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        time_of_day: str = "any",
        flight_numbers: list[str] | None = None,
        pairing_id: str | None = None,
        aircraft_type: str | None = None,
        limit: int = 100,
    ) -> ToolEnvelope:
        args = {
            k: v
            for k, v in {
                "origin": origin, "destination": destination, "on_date": on_date,
                "from_time": from_time, "to_time": to_time,
                "flight_numbers": flight_numbers, "pairing_id": pairing_id,
                "aircraft_type": aircraft_type,
            }.items()
            if v is not None
        }
        self._record("find_flights", args)
        if "find_flights" in self.fail:
            return self._fail("find_flights", args, "injected failure")

        rows = []
        for flight in FLIGHTS:
            if origin and flight["dep"] != origin:
                continue
            if destination and flight["arr"] != destination:
                continue
            if on_date and flight["date"] != on_date:
                continue
            if flight_numbers and flight["flight_no"] not in flight_numbers:
                continue
            if pairing_id and flight["pairing_id"] != pairing_id:
                continue
            if aircraft_type and flight["aircraft_type"] != aircraft_type:
                continue
            rows.append(flight)

        facts = [
            _fact("find_flights.count", "Flights matching", len(rows), "count",
                  source="flights.json", provenance=Provenance.COMPUTED,
                  derivation=f"{len(rows)} legs match the filter set")
        ]
        for flight in rows:
            facts.extend(
                [
                    _fact(f"{flight['flight_no']}.route", "Route",
                          f"{flight['dep']}-{flight['arr']}", "text",
                          source=f"flights.json#{flight['flight_no']}"),
                    _fact(f"{flight['flight_no']}.dep", "Departure",
                          flight["dep_utc"].isoformat() + "Z", "datetime",
                          source=f"flights.json#{flight['flight_no']}"),
                    _fact(f"{flight['flight_no']}.arr", "Arrival",
                          flight["arr_utc"].isoformat() + "Z", "datetime",
                          source=f"flights.json#{flight['flight_no']}"),
                    _fact(f"{flight['flight_no']}.block", "Block hours",
                          flight["block_hours"], "hours",
                          source=f"flights.json#{flight['flight_no']}"),
                    _fact(f"{flight['flight_no']}.seats", "Seats", flight["seats"],
                          "count", source=f"flights.json#{flight['flight_no']}"),
                    _fact(f"{flight['flight_no']}.tail", "Aircraft",
                          flight["aircraft"], "text",
                          source=f"flights.json#{flight['flight_no']}"),
                ]
            )
        return self._ok(
            "find_flights", args, rows, facts,
            [TraceStep(label="Searched the schedule",
                       detail=f"{len(rows)} legs match")],
            [Citation(file="flights.json", pointer="filter")],
        )

    def get_duty_clocks(
        self, *, crew_id: str, as_of: datetime | None = None
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"crew_id": crew_id}
        if as_of:
            args["as_of"] = as_of
        self._record("get_duty_clocks", args)
        if "get_duty_clocks" in self.fail:
            return self._fail("get_duty_clocks", args, "injected failure")
        record = CREW.get(crew_id)
        if record is None:
            return self._fail("get_duty_clocks", args, f"No crew member {crew_id}")

        duty = float(record["duty_hours_7d"])
        block = float(record["flight_hours_28d"])
        duty_headroom = round(60.0 - duty, 2)
        block_headroom = round(100.0 - block, 2)
        payload = {
            "crew_id": crew_id,
            "duty_hours_7d": duty,
            "duty_headroom_hours": duty_headroom,
            "flight_hours_28d": block,
            "flight_headroom_hours": block_headroom,
            "as_of": SNAPSHOT.isoformat() + "Z",
        }
        facts = [
            _fact(f"{crew_id}.duty_7d", "Duty hours, 7 days to 2026-09-14", duty,
                  "hours", source=f"duty_clocks.json#{crew_id}"),
            _fact(f"{crew_id}.duty_headroom", "Duty headroom under RULE-DUTY-02",
                  duty_headroom, "hours", provenance=Provenance.COMPUTED,
                  source="crewops.rules.duty.headroom",
                  derivation=f"60.00h limit minus {duty:.2f}h accrued "
                             f"= {duty_headroom:.2f}h spare"),
            _fact(f"{crew_id}.flight_28d", "Block hours, 28 days to 2026-09-14",
                  block, "hours", source=f"duty_clocks.json#{crew_id}"),
            _fact(f"{crew_id}.flight_headroom", "Block headroom under RULE-FLT-03",
                  block_headroom, "hours", provenance=Provenance.COMPUTED,
                  source="crewops.rules.flight.headroom",
                  derivation=f"100.00h limit minus {block:.2f}h accrued "
                             f"= {block_headroom:.2f}h spare"),
        ]
        return self._ok(
            "get_duty_clocks", args, payload, facts,
            [TraceStep(
                label="Duty clock",
                detail=f"{crew_id} has {duty:.2f}h of 60.00h used, "
                       f"{duty_headroom:.2f}h spare",
                fact_keys=[f"{crew_id}.duty_7d", f"{crew_id}.duty_headroom"],
            )],
            [Citation(file="duty_clocks.json", pointer=crew_id)],
        )

    def list_reserves(
        self,
        *,
        on_date: date,
        base: str | None = None,
        aircraft_type: str | None = None,
        rank: str | None = None,
        at_time: datetime | None = None,
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"on_date": on_date}
        for key, value in (("base", base), ("aircraft_type", aircraft_type),
                           ("rank", rank), ("at_time", at_time)):
            if value is not None:
                args[key] = value
        self._record("list_reserves", args)
        if "list_reserves" in self.fail:
            return self._fail("list_reserves", args, "injected failure")

        rows = []
        for crew_id, record in CREW.items():
            if not record.get("reserve"):
                continue
            if base and record["base"] != base:
                continue
            if rank and record["rank"] != rank:
                continue
            if aircraft_type and aircraft_type not in record["ratings"]:
                continue
            start, end = record["oncall"]
            covers = True
            if at_time is not None:
                clock = f"{at_time.hour:02d}:{at_time.minute:02d}"
                covers = start <= clock <= end
            rows.append({"crew_id": crew_id, "rank": record["rank"],
                         "base": record["base"], "window_start": start,
                         "window_end": end,
                         "reachability_minutes": record["reachability_minutes"],
                         "covers_report_time": covers})

        facts = [
            _fact("list_reserves.count", "Reserves on this date", len(rows), "count",
                  source="reserve_pool.json", provenance=Provenance.COMPUTED,
                  derivation=f"{len(rows)} reserves match the filter set"),
            _fact("list_reserves.date", "Date", on_date.isoformat(), "date",
                  source="reserve_pool.json"),
        ]
        for row in rows:
            cid = row["crew_id"]
            facts.extend([
                _fact(f"{cid}.oncall_start", f"{cid} window start",
                      row["window_start"], "datetime",
                      source=f"reserve_pool.json#{cid}"),
                _fact(f"{cid}.oncall_end", f"{cid} window end", row["window_end"],
                      "datetime", source=f"reserve_pool.json#{cid}"),
                _fact(f"{cid}.rank", f"{cid} rank", row["rank"], "rank",
                      source=f"crew.json#{cid}"),
                _fact(f"{cid}.reachability", f"{cid} reachability",
                      row["reachability_minutes"], "minutes",
                      source=f"crew.json#{cid}"),
            ])
        return self._ok(
            "list_reserves", args, rows, facts,
            [TraceStep(label="Reserve pool",
                       detail=f"{len(rows)} reserves on {on_date.isoformat()}")],
            [Citation(file="reserve_pool.json", pointer=on_date.isoformat())],
        )

    def find_expiring_certifications(
        self,
        *,
        within_days: int = 30,
        as_of: date | None = None,
        certification_type: str | None = None,
        base: str | None = None,
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"within_days": within_days}
        for key, value in (("as_of", as_of), ("certification_type", certification_type),
                           ("base", base)):
            if value is not None:
                args[key] = value
        self._record("find_expiring_certifications", args)
        if "find_expiring_certifications" in self.fail:
            return self._fail(
                "find_expiring_certifications", args, "injected failure"
            )
        anchor = as_of or SNAPSHOT.date()
        rows = []
        for crew_id, certs in CERTIFICATIONS.items():
            if base and CREW[crew_id]["base"] != base:
                continue
            for cert in certs:
                if certification_type and cert["type"] != certification_type:
                    continue
                days = (cert["valid_to"] - anchor).days
                if 0 <= days <= within_days:
                    rows.append({"crew_id": crew_id, "type": cert["type"],
                                 "valid_to": cert["valid_to"].isoformat(),
                                 "days_remaining": days})
        facts = [
            _fact("expiring.count", "Certifications expiring in the window",
                  len(rows), "count", provenance=Provenance.COMPUTED,
                  source="crewops.rules.cert.expiring",
                  derivation=f"{len(rows)} certifications expire within "
                             f"{within_days} days of {anchor.isoformat()}"),
            _fact("expiring.window", "Window", within_days, "days",
                  source="certifications.json"),
        ]
        for row in rows:
            facts.append(
                _fact(f"{row['crew_id']}.{row['type']}.valid_to",
                      f"{row['crew_id']} {row['type']} expires",
                      row["valid_to"], "date",
                      source=f"certifications.json#{row['crew_id']}")
            )
            facts.append(
                _fact(f"{row['crew_id']}.{row['type']}.days",
                      f"{row['crew_id']} {row['type']} days remaining",
                      row["days_remaining"], "days", provenance=Provenance.COMPUTED,
                      source="crewops.rules.cert.expiring",
                      derivation=f"{row['valid_to']} minus {anchor.isoformat()} "
                                 f"= {row['days_remaining']} days")
            )
        return self._ok(
            "find_expiring_certifications", args, rows, facts,
            [TraceStep(label="Certification scan",
                       detail=f"{len(rows)} expiring within {within_days} days of "
                              f"{anchor.isoformat()}")],
            [Citation(file="certifications.json", pointer="scan",
                      note="valid_from is unusable in this dataset; only valid_to "
                           "is checked")],
        )

    def get_pairing(self, *, pairing_id: str) -> ToolEnvelope:
        args = {"pairing_id": pairing_id}
        self._record("get_pairing", args)
        if "get_pairing" in self.fail:
            return self._fail("get_pairing", args, "injected failure")
        pairing = PAIRINGS.get(pairing_id)
        if pairing is None:
            return self._fail("get_pairing", args, f"No pairing {pairing_id}")
        facts = [
            _fact(f"{pairing_id}.days", "Duty days", len(pairing["days"]), "count",
                  source=f"rosters.json#{pairing_id}"),
            _fact(f"{pairing_id}.aircraft", "Aircraft", pairing["aircraft"], "text",
                  source=f"rosters.json#{pairing_id}"),
            _fact(f"{pairing_id}.aircraft_type", "Aircraft type",
                  pairing["aircraft_type"], "aircraft_type",
                  source=f"rosters.json#{pairing_id}"),
        ]
        for day in pairing["days"]:
            iso = day["duty_date"].isoformat()
            facts.extend([
                _fact(f"{pairing_id}.{iso}.report", f"Report {iso}",
                      day["report"].isoformat() + "Z", "datetime",
                      source=f"rosters.json#{pairing_id}"),
                _fact(f"{pairing_id}.{iso}.release", f"Release {iso}",
                      day["release"].isoformat() + "Z", "datetime",
                      source=f"rosters.json#{pairing_id}"),
                _fact(f"{pairing_id}.{iso}.duty_hours", f"Duty length {iso}",
                      day["duty_hours"], "hours", provenance=Provenance.COMPUTED,
                      source="crewops.rules.duty.period",
                      derivation=f"release {day['release'].time()} minus report "
                                 f"{day['report'].time()} = {day['duty_hours']:.2f}h"),
                _fact(f"{pairing_id}.{iso}.sectors", f"Sectors {iso}",
                      day["sectors"], "count", source=f"rosters.json#{pairing_id}"),
            ])
            for leg in day["legs"]:
                facts.append(
                    _fact(f"{pairing_id}.{leg}", "Leg", leg, "flight_no",
                          source=f"rosters.json#{pairing_id}")
                )
        for role, crew_id in pairing["crew"].items():
            facts.append(
                _fact(f"{pairing_id}.crew.{role}", f"{role}", crew_id, "crew_id",
                      source=f"rosters.json#{pairing_id}")
            )
        return self._ok(
            "get_pairing", args, {"pairing_id": pairing_id, **pairing}, facts,
            [TraceStep(
                label=f"Opened {pairing_id}",
                detail=(
                    f"{len(pairing['days'])} duty days on {pairing['aircraft']}, "
                    + "; ".join(
                        f"{d['duty_date'].isoformat()} "
                        f"{'/'.join(d['legs'])} ({d['duty_hours']:.2f}h)"
                        for d in pairing["days"]
                    )
                ),
            )],
            [Citation(file="rosters.json", pointer=pairing_id)],
        )

    def get_roster(
        self,
        *,
        crew_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"crew_id": crew_id}
        for key, value in (("from_date", from_date), ("to_date", to_date)):
            if value is not None:
                args[key] = value
        self._record("get_roster", args)
        if "get_roster" in self.fail:
            return self._fail("get_roster", args, "injected failure")
        if crew_id not in CREW:
            return self._fail("get_roster", args, f"No crew member {crew_id}")
        rows = []
        for pairing_id, pairing in PAIRINGS.items():
            if crew_id not in pairing["crew"].values():
                continue
            for day in pairing["days"]:
                rows.append({"pairing_id": pairing_id,
                             "duty_date": day["duty_date"].isoformat(),
                             "legs": day["legs"],
                             "duty_hours": day["duty_hours"]})
        facts = [
            _fact(f"{crew_id}.roster.count", "Rostered duty days", len(rows), "count",
                  source=f"rosters.json#{crew_id}")
        ]
        for row in rows:
            facts.append(
                _fact(f"{crew_id}.roster.{row['duty_date']}", "Rostered",
                      row["pairing_id"], "pairing_id",
                      source=f"rosters.json#{crew_id}")
            )
        return self._ok(
            "get_roster", args, rows, facts,
            [TraceStep(label=f"Roster for {crew_id}",
                       detail=f"{len(rows)} duty days this week")],
            [Citation(file="rosters.json", pointer=crew_id)],
        )

    # --------------------------------------------------------------- tier 2

    def check_legality(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        on_date: date | None = None,
        as_replacement_for: str | None = None,
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"crew_id": crew_id}
        for key, value in (("pairing_id", pairing_id),
                           ("flight_numbers", flight_numbers),
                           ("on_date", on_date),
                           ("as_replacement_for", as_replacement_for)):
            if value is not None:
                args[key] = value
        self._record("check_legality", args)
        if "check_legality" in self.fail:
            return self._fail("check_legality", args, "injected failure")
        if crew_id not in CREW:
            return self._fail("check_legality", args, f"No crew member {crew_id}")

        pairing = PAIRINGS.get(pairing_id or "P-2291")
        if pairing is None:
            return self._fail("check_legality", args, f"No pairing {pairing_id}")
        report = _legality_for(crew_id, pairing_id or "P-2291", pairing, on_date)
        facts = [
            _fact(f"{crew_id}.legality.overall", "Overall verdict",
                  report.overall.value, "text", provenance=Provenance.COMPUTED,
                  source="crewops.rules.evaluate",
                  derivation="the worst day across the assignment"),
        ]
        for day in report.per_day:
            for trace in day.traces:
                if trace.observed is not None:
                    facts.append(
                        _fact(
                            f"{crew_id}.{trace.rule_id}.{day.duty_date}.observed",
                            f"{trace.rule_id} observed on {day.duty_date}",
                            trace.observed, trace.unit or "hours",
                            provenance=Provenance.COMPUTED,
                            source=f"crewops.rules.{trace.rule_id.lower()}",
                            derivation=trace.arithmetic,
                        )
                    )
                if trace.limit is not None:
                    facts.append(
                        _fact(
                            f"{crew_id}.{trace.rule_id}.{day.duty_date}.limit",
                            f"{trace.rule_id} limit", trace.limit,
                            trace.unit or "hours",
                            source=f"rules.json#{trace.rule_id}",
                        )
                    )
                if trace.margin is not None:
                    facts.append(
                        _fact(
                            f"{crew_id}.{trace.rule_id}.{day.duty_date}.margin",
                            f"{trace.rule_id} margin", trace.margin,
                            trace.unit or "hours", provenance=Provenance.COMPUTED,
                            source=f"crewops.rules.{trace.rule_id.lower()}",
                            derivation=trace.margin_human or trace.arithmetic,
                        )
                    )
        trace_steps = [
            TraceStep(
                label=f"{t.rule_id} on {day.duty_date}",
                detail=f"{t.verdict.value}: {t.arithmetic}",
            )
            for day in report.per_day
            for t in day.traces
        ]
        return self._ok(
            "check_legality", args, report, facts, trace_steps,
            [Citation(file="rules.json", pointer="all"),
             Citation(file="duty_clocks.json", pointer=crew_id)],
        )

    def simulate_absence(
        self,
        *,
        crew_id: str,
        from_date: date,
        to_date: date | None = None,
        reason: str = "sick call",
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"crew_id": crew_id, "from_date": from_date,
                                "reason": reason}
        if to_date is not None:
            args["to_date"] = to_date
        self._record("simulate_absence", args)
        if "simulate_absence" in self.fail:
            return self._fail("simulate_absence", args, "injected failure")
        if crew_id not in CREW:
            return self._fail("simulate_absence", args, f"No crew member {crew_id}")

        pairing_id = next(
            (pid for pid, p in PAIRINGS.items() if crew_id in p["crew"].values()),
            None,
        )
        if pairing_id is None:
            payload = ImpactReport(
                trigger=f"{crew_id} unavailable from {from_date} ({reason})",
                trigger_kind="crew_absence",
                as_of=SNAPSHOT,
                explanation=f"{crew_id} has no rostered duty from {from_date}, so no "
                            "flight is uncrewed by this absence.",
                facts=[],
            )
            return self._ok("simulate_absence", args, payload, [], [], [])

        pairing = PAIRINGS[pairing_id]
        day_one = pairing["days"][0]
        legs = [f for f in FLIGHTS if f["flight_no"] in day_one["legs"]]
        passengers = sum(f["seats"] for f in legs)
        uncrewed = [
            FlightRef(
                flight_no=f["flight_no"], origin=f["dep"], destination=f["arr"],
                departure=f["dep_utc"], arrival=f["arr_utc"],
                aircraft_type=f["aircraft_type"], passengers=f["seats"],
                pairing_id=f["pairing_id"],
            )
            for f in legs
        ]
        risks = []
        for candidate in ("C-2087", "C-3305"):
            table = DUTY_UNDER_COVER.get(candidate, {})
            for duty_date, (_base, total, verdict) in sorted(table.items()):
                if verdict is Verdict.BREACH:
                    over = round(total - 60.0, 2)
                    risks.append(
                        DownstreamRisk(
                            crew_id=candidate, pairing_id=pairing_id,
                            rule_id="RULE-DUTY-02", severity=RiskSeverity.HIGH,
                            detail=f"Would exceed 60h/7d by {_fmt_hm(over)} "
                                   f"({total:.2f}h against a 60.00h limit)",
                            duty_date=duty_date,
                        )
                    )
                    break
        facts = [
            _fact("impact.uncrewed_count", "Uncrewed legs", len(uncrewed), "count",
                  provenance=Provenance.COMPUTED, source="crewops.ops.impact",
                  derivation=f"{len(uncrewed)} legs on {pairing_id} day 1 lose their "
                             f"{CREW[crew_id]['rank']}"),
            _fact("impact.passengers_affected", "Passengers exposed", passengers,
                  "count", provenance=Provenance.COMPUTED,
                  source="crewops.ops.impact",
                  derivation=f"{len(uncrewed)} legs x 162 seats = {passengers}"),
            _fact("impact.pairing", "Pairing broken", pairing_id, "pairing_id",
                  source=f"rosters.json#{pairing_id}"),
        ]
        for flight in legs:
            facts.append(
                _fact(f"impact.{flight['flight_no']}", "Uncrewed leg",
                      flight["flight_no"], "flight_no",
                      source=f"flights.json#{flight['flight_no']}")
            )
        payload = ImpactReport(
            trigger=f"{crew_id} unavailable from {from_date} ({reason})",
            trigger_kind="crew_absence",
            as_of=SNAPSHOT,
            uncrewed_flights=uncrewed,
            pairings_broken=[pairing_id],
            crew_affected=[crew_id],
            stations_affected=sorted({f["dep"] for f in legs} | {f["arr"] for f in legs}),
            passengers_affected=passengers,
            downstream_risks=risks,
            explanation=(
                f"{crew_id} operates {pairing_id}, day 1 on "
                f"{day_one['duty_date'].isoformat()}: "
                f"{'/'.join(day_one['legs'])}. All {len(uncrewed)} legs are now "
                f"uncrewed and {passengers} passengers are exposed. Day 2 on "
                f"{pairing['days'][1]['duty_date'].isoformat()} is also at risk "
                "because the aircraft overnights away from base."
            ),
            facts=facts,
        )
        return self._ok(
            "simulate_absence", args, payload, facts,
            [TraceStep(label="Absence modelled",
                       detail=payload.explanation)],
            [Citation(file="rosters.json", pointer=pairing_id),
             Citation(file="flights.json", pointer="day 1 legs")],
        )

    def simulate_reassignment(
        self,
        *,
        crew_id: str,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        displacing_crew_id: str | None = None,
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"crew_id": crew_id}
        for key, value in (("pairing_id", pairing_id),
                           ("flight_numbers", flight_numbers),
                           ("displacing_crew_id", displacing_crew_id)):
            if value is not None:
                args[key] = value
        self._record("simulate_reassignment", args)
        if "simulate_reassignment" in self.fail:
            return self._fail("simulate_reassignment", args, "injected failure")
        target = pairing_id or "P-2291"
        pairing = PAIRINGS.get(target)
        if pairing is None or crew_id not in CREW:
            return self._fail(
                "simulate_reassignment", args, f"Cannot resolve {crew_id} on {target}"
            )
        legality = _legality_for(crew_id, target, pairing, None)
        risks = [
            DownstreamRisk(
                crew_id=crew_id, pairing_id=target, rule_id=trace.rule_id,
                severity=RiskSeverity.CRITICAL, detail=trace.arithmetic,
                duty_date=trace.duty_date,
            )
            for trace in legality.breaches
        ]
        facts = [
            _fact("reassign.verdict", "Verdict for the move", legality.overall.value,
                  "text", provenance=Provenance.COMPUTED,
                  source="crewops.rules.evaluate",
                  derivation="the worst day across the assignment"),
        ]
        for trace in legality.breaches:
            facts.append(
                _fact(f"reassign.{trace.rule_id}.{trace.duty_date}", trace.title,
                      trace.observed, trace.unit or "hours",
                      provenance=Provenance.COMPUTED,
                      source=f"crewops.rules.{trace.rule_id.lower()}",
                      derivation=trace.arithmetic)
            )
        payload = ImpactReport(
            trigger=f"Move {crew_id} onto {target}",
            trigger_kind="reassignment",
            as_of=SNAPSHOT,
            crew_affected=[crew_id] + ([displacing_crew_id] if displacing_crew_id else []),
            pairings_broken=[],
            downstream_risks=risks,
            explanation=(
                f"Moving {crew_id} onto {target} is {legality.overall.value}. "
                + (
                    " ".join(trace.arithmetic for trace in legality.breaches)
                    if legality.breaches
                    else "No rule is breached on any day of the assignment."
                )
            ),
            facts=facts,
        )
        return self._ok(
            "simulate_reassignment", args, payload, facts,
            [TraceStep(label="Reassignment modelled", detail=payload.explanation)],
            [Citation(file="rules.json", pointer="all")],
        )

    def simulate_station_closure(
        self, *, station: str, from_time: datetime, to_time: datetime
    ) -> ToolEnvelope:
        args = {"station": station, "from_time": from_time, "to_time": to_time}
        self._record("simulate_station_closure", args)
        if "simulate_station_closure" in self.fail:
            return self._fail("simulate_station_closure", args, "injected failure")
        if station not in STATIONS:
            return self._fail(
                "simulate_station_closure", args,
                f"{station} is not a station in this network. Stations: "
                + ", ".join(STATIONS),
            )
        # Half open window: a departure exactly at the reopen time is unaffected.
        affected = [
            f for f in FLIGHTS
            if (f["dep"] == station and from_time <= f["dep_utc"] < to_time)
            or (f["arr"] == station and from_time <= f["arr_utc"] < to_time)
        ]
        refs = [
            FlightRef(
                flight_no=f["flight_no"], origin=f["dep"], destination=f["arr"],
                departure=f["dep_utc"], arrival=f["arr_utc"],
                aircraft_type=f["aircraft_type"], passengers=f["seats"],
                pairing_id=f["pairing_id"],
            )
            for f in affected
        ]
        passengers = sum(f["seats"] for f in affected)
        facts = [
            _fact("closure.count", "Flights affected", len(affected), "count",
                  provenance=Provenance.COMPUTED, source="crewops.ops.closure",
                  derivation=f"{len(affected)} legs touch {station} inside "
                             f"[{from_time.time()}, {to_time.time()})"),
            _fact("closure.passengers", "Passengers exposed", passengers, "count",
                  provenance=Provenance.COMPUTED, source="crewops.ops.closure",
                  derivation=f"sum of seats across {len(affected)} legs = {passengers}"),
            _fact("closure.station", "Station", station, "station",
                  source="flights.json"),
            _fact("closure.from", "Closure start", from_time.isoformat() + "Z",
                  "datetime", source="input"),
            _fact("closure.to", "Closure end", to_time.isoformat() + "Z", "datetime",
                  source="input"),
        ]
        for flight in affected:
            facts.append(
                _fact(f"closure.{flight['flight_no']}", "Affected leg",
                      flight["flight_no"], "flight_no",
                      source=f"flights.json#{flight['flight_no']}")
            )
        payload = ImpactReport(
            trigger=f"{station} closed {from_time.isoformat()}Z to "
                    f"{to_time.isoformat()}Z",
            trigger_kind="station_closure",
            as_of=SNAPSHOT,
            uncrewed_flights=refs,
            stations_affected=[station],
            passengers_affected=passengers,
            explanation=(
                f"{station} closed from {from_time.isoformat()}Z to "
                f"{to_time.isoformat()}Z affects {len(affected)} legs and "
                f"{passengers} passengers. The window is half open, so a departure "
                "exactly at the reopen time is not affected."
            ),
            facts=facts,
        )
        return self._ok(
            "simulate_station_closure", args, payload, facts,
            [TraceStep(label="Closure modelled", detail=payload.explanation)],
            [Citation(file="flights.json", pointer=station)],
        )

    # --------------------------------------------------------------- tier 3

    def find_cover_options(
        self,
        *,
        pairing_id: str | None = None,
        flight_numbers: list[str] | None = None,
        exclude_crew_ids: list[str] | None = None,
        max_options: int = 5,
        include_rejected: bool = True,
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"max_options": max_options,
                                "include_rejected": include_rejected}
        for key, value in (("pairing_id", pairing_id),
                           ("flight_numbers", flight_numbers),
                           ("exclude_crew_ids", exclude_crew_ids)):
            if value is not None:
                args[key] = value
        self._record("find_cover_options", args)
        if "find_cover_options" in self.fail:
            return self._fail("find_cover_options", args, "injected failure")

        target = pairing_id or "P-2291"
        pairing = PAIRINGS.get(target)
        if pairing is None:
            return self._fail("find_cover_options", args, f"No pairing {target}")
        excluded = set(exclude_crew_ids or [])

        options: list[CoverOption] = []
        rejected: list[CoverOption] = []
        evaluated = 0
        covered = [leg for day in pairing["days"] for leg in day["legs"]]

        for crew_id in ("C-3310", "C-2210", "C-3305", "C-2087", "C-2091"):
            if crew_id in excluded:
                continue
            evaluated += 1
            legality = _legality_for(crew_id, target, pairing, None)
            deadhead = CREW[crew_id]["base"] != "BLR"
            lines = [
                CostLine(
                    label="Reserve callout, pilot" if CREW[crew_id].get("reserve")
                    else "Day off callout, pilot",
                    amount_inr=18500.0 if CREW[crew_id].get("reserve") else 24000.0,
                    basis="charged once per assignment, not per duty day",
                    rule_ref="reserve_callout_pilot" if CREW[crew_id].get("reserve")
                    else "dayoff_callout_pilot",
                )
            ]
            delay_minutes = 0
            if deadhead:
                delay_minutes = 180
                lines.append(
                    CostLine(label="Deadhead positioning", amount_inr=6500.0,
                             basis="DX402 arrives BLR 08:45Z, report moves to 09:00Z",
                             rule_ref="deadhead_positioning")
                )
                lines.append(
                    CostLine(label="Delay cost", amount_inr=16200.0,
                             basis="3.0 delay hours x INR 5,400 per hour",
                             rule_ref="delay_cost_per_duty_hour")
                )
            total = sum(line.amount_inr for line in lines)
            option = CoverOption(
                rank=0, kind=CoverKind.DEADHEAD if deadhead else CoverKind.RESERVE,
                action=f"Assign {'reserve ' if CREW[crew_id].get('reserve') else ''}"
                       f"{crew_id}" + (" from DEL via deadhead" if deadhead else ""),
                crew_id=crew_id, crew_name=CREW[crew_id]["name"],
                crew_base=CREW[crew_id]["base"], crew_rank=CREW[crew_id]["rank"],
                legal=legality.is_legal, legality=legality,
                rules_checked=list(legality.rules_checked),
                cost=CostBreakdown(line_items=lines, total_inr=total),
                coverage_summary=f"all {len(covered)} flights",
                covered_flights=covered,
                reachable=True,
                reachability_minutes=CREW[crew_id]["reachability_minutes"],
                delay_minutes=delay_minutes,
                reasoning=_reasoning_for(crew_id, legality, deadhead),
                tradeoffs=(
                    ["Introduces a 180 minute delay to DX412"] if deadhead else []
                ),
                confidence=Confidence.HIGH,
                facts=[
                    _fact(f"{crew_id}.cost", f"{crew_id} cover cost", total, "inr",
                          provenance=Provenance.COMPUTED, source="crewops.ops.cost",
                          derivation=" + ".join(
                              f"{line.label} INR {line.amount_inr:,.0f}"
                              for line in lines
                          ) + f" = INR {total:,.0f}"),
                    _fact(f"{crew_id}.legal", f"{crew_id} legal", legality.is_legal,
                          "boolean", provenance=Provenance.COMPUTED,
                          source="crewops.rules.evaluate",
                          derivation=f"overall verdict {legality.overall.value}"),
                ],
            )
            if legality.is_legal:
                options.append(option)
            elif include_rejected:
                rejected.append(option)

        options.sort(key=lambda o: (o.cost.total_inr, o.crew_id))
        for index, option in enumerate(options[:max_options], 1):
            option.rank = index
        options = options[:max_options]

        facts: list[Fact] = [
            _fact("cover.candidates", "Candidates evaluated", evaluated, "count",
                  provenance=Provenance.COMPUTED, source="crewops.ops.candidates",
                  derivation=f"{evaluated} candidates enumerated, "
                             f"{len(options)} legal, {len(rejected)} rejected"),
            _fact("cover.legal_count", "Legal options", len(options), "count",
                  provenance=Provenance.COMPUTED, source="crewops.ops.candidates",
                  derivation=f"{len(options)} of {evaluated} candidates pass all "
                             "seven rules on every day"),
        ]
        for option in options:
            facts.extend(option.facts)
            facts.append(
                _fact(f"{option.crew_id}.rank", f"{option.crew_id} rank", option.rank,
                      "count", provenance=Provenance.COMPUTED,
                      source="crewops.ops.rank",
                      derivation="ranked by cost ascending, then crew id")
            )
        for option in rejected:
            facts.extend(option.facts)

        payload = Recommendation(
            situation=f"Cover needed for {target}: "
                      f"{len(covered)} legs across {len(pairing['days'])} duty days.",
            options=options,
            rejected=rejected,
            candidates_evaluated=evaluated,
            ranking_basis="cost ascending, then crew id; cancellation always last",
            facts=facts,
        )
        return self._ok(
            "find_cover_options", args, payload, facts,
            [
                TraceStep(label="Cover search",
                          detail=f"{evaluated} candidates, {len(options)} legal, "
                                 f"{len(rejected)} rejected"),
                *[
                    TraceStep(label=f"Option {o.rank}",
                              detail=f"{o.action}, INR {o.cost.total_inr:,.0f}, "
                                     f"{o.coverage_summary}")
                    for o in options
                ],
            ],
            [Citation(file="reserve_pool.json", pointer=target),
             Citation(file="costs.json", pointer="rates")],
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
        args: dict[str, Any] = {"crew_id": crew_id, "channel": channel}
        for key, value in (("pairing_id", pairing_id),
                           ("flight_numbers", flight_numbers),
                           ("option_rank", option_rank)):
            if value is not None:
                args[key] = value
        self._record("draft_notification", args)
        if "draft_notification" in self.fail:
            return self._fail("draft_notification", args, "injected failure")
        if crew_id not in CREW:
            return self._fail("draft_notification", args, f"No crew member {crew_id}")
        target = pairing_id or "P-2291"
        pairing = PAIRINGS.get(target)
        if pairing is None:
            return self._fail("draft_notification", args, f"No pairing {target}")
        day_one = pairing["days"][0]
        text = (
            f"Crew Control callout. {CREW[crew_id]['name']} ({crew_id}), you are "
            f"assigned {target} from {day_one['duty_date'].isoformat()}. Report BLR "
            f"at {day_one['report'].strftime('%H:%M')}Z for "
            f"{'/'.join(day_one['legs'])}. Release "
            f"{day_one['release'].strftime('%H:%M')}Z. Confirm receipt."
        )
        facts = [
            _fact("notify.crew", "Crew notified", crew_id, "crew_id",
                  source=f"crew.json#{crew_id}"),
            _fact("notify.pairing", "Pairing", target, "pairing_id",
                  source=f"rosters.json#{target}"),
            _fact("notify.report", "Report time",
                  day_one["report"].isoformat() + "Z", "datetime",
                  source=f"rosters.json#{target}"),
            _fact("notify.release", "Release time",
                  day_one["release"].isoformat() + "Z", "datetime",
                  source=f"rosters.json#{target}"),
            _fact("notify.text", "Draft", text, "text",
                  provenance=Provenance.COMPUTED, source="crewops.ops.notify",
                  derivation="template filled from the pairing's own report and "
                             "release times"),
        ]
        return self._ok(
            "draft_notification", args, text, facts,
            [TraceStep(label="Notification drafted",
                       detail=f"{channel} to {crew_id} for {target}")],
            [Citation(file="rosters.json", pointer=target)],
        )

    # ---------------------------------------------------------- cross cutting

    def get_watchlist(
        self, *, for_date: date, as_of: datetime | None = None
    ) -> ToolEnvelope:
        args: dict[str, Any] = {"for_date": for_date}
        if as_of:
            args["as_of"] = as_of
        self._record("get_watchlist", args)
        if "get_watchlist" in self.fail:
            return self._fail("get_watchlist", args, "injected failure")
        alerts = [
            Alert(
                severity=RiskSeverity.CRITICAL,
                title="Certification expires before a rostered duty",
                detail="C-5417 recurrent_training is valid to 2026-09-17 and they "
                       "are rostered on 2026-09-19.",
                crew_id="C-5417", rule_id="RULE-CERT-06",
                due_date=date(2026, 9, 17),
                suggested_question="Can C-5417 legally operate their 19 Sep duty",
                facts=[
                    _fact("C-5417.recurrent_training.valid_to",
                          "C-5417 recurrent training expires", "2026-09-17", "date",
                          source="certifications.json#C-5417"),
                    _fact("C-5417.rostered", "C-5417 rostered", "2026-09-19", "date",
                          source="rosters.json#C-5417"),
                ],
            ),
            Alert(
                severity=RiskSeverity.HIGH,
                title="Duty headroom under 10 hours",
                detail="C-2087 has 51.83h of 60.00h used, leaving 8.17h spare.",
                crew_id="C-2087", rule_id="RULE-DUTY-02",
                suggested_question="How much duty headroom does C-2087 have",
                facts=[
                    _fact("C-2087.duty_7d", "C-2087 duty hours", 51.83, "hours",
                          source="duty_clocks.json#C-2087"),
                    _fact("C-2087.duty_headroom", "C-2087 headroom", 8.17, "hours",
                          provenance=Provenance.COMPUTED,
                          source="crewops.rules.duty.headroom",
                          derivation="60.00h limit minus 51.83h accrued = 8.17h spare"),
                ],
            ),
        ]
        payload = Watchlist(
            as_of=as_of or SNAPSHOT,
            for_date=for_date,
            alerts=alerts,
            headline=f"{len(alerts)} items need attention on {for_date.isoformat()}.",
            scanned={"crew": len(CREW), "pairings": len(PAIRINGS),
                     "flights": len(FLIGHTS)},
        )
        facts = [
            _fact("watchlist.count", "Alerts", len(alerts), "count",
                  provenance=Provenance.COMPUTED, source="crewops.brief",
                  derivation=f"{len(alerts)} alerts raised for "
                             f"{for_date.isoformat()}"),
            *[fact for alert in alerts for fact in alert.facts],
        ]
        return self._ok(
            "get_watchlist", args, payload, facts,
            [TraceStep(label="Watchlist", detail=payload.headline)],
            [Citation(file="certifications.json", pointer="scan")],
        )

    def get_world_summary(self) -> ToolEnvelope:
        self._record("get_world_summary", {})
        if "get_world_summary" in self.fail:
            return self._fail("get_world_summary", {}, "injected failure")
        payload = {
            "airline": "dCortex Air",
            "hub": "BLR",
            "snapshot": SNAPSHOT.isoformat() + "Z",
            "week_start": "2026-09-14",
            "week_end": "2026-09-20",
            "currency": "INR",
            "stations": list(STATIONS),
            "counts": {"flights": 147, "crew": 150, "pairings": 39, "reserves": 16,
                       "rules": 7, "certifications": 600},
        }
        facts = [
            _fact("world.hub", "Hub", "BLR", "station", source="flights.json"),
            _fact("world.snapshot", "Snapshot", SNAPSHOT.isoformat() + "Z",
                  "datetime", source="duty_clocks.json#as_of_utc"),
            _fact("world.week_start", "Week start", "2026-09-14", "date",
                  source="flights.json"),
            _fact("world.week_end", "Week end", "2026-09-20", "date",
                  source="flights.json"),
            _fact("world.flights", "Flights", 147, "count", source="flights.json"),
            _fact("world.crew", "Crew", 150, "count", source="crew.json"),
            _fact("world.pairings", "Pairings", 39, "count", source="rosters.json"),
            _fact("world.reserves", "Reserves", 16, "count",
                  source="reserve_pool.json"),
            _fact("world.rules", "Rules", 7, "count", source="rules.json"),
            _fact("world.stations", "Stations", len(STATIONS), "count",
                  source="flights.json"),
            *[
                _fact(f"world.station.{s}", "Station", s, "station",
                      source="flights.json")
                for s in STATIONS
            ],
        ]
        return self._ok(
            "get_world_summary", {}, payload, facts,
            [TraceStep(label="Dataset",
                       detail="dCortex Air, hub BLR, 2026-09-14 to 2026-09-20, "
                              "147 flights, 150 crew, 39 pairings, 7 rules")],
            [Citation(file="flights.json", pointer="all")],
        )

    def explain_rule(self, *, rule_id: str) -> ToolEnvelope:
        args = {"rule_id": rule_id}
        self._record("explain_rule", args)
        if "explain_rule" in self.fail:
            return self._fail("explain_rule", args, "injected failure")
        rule = RULES.get(rule_id.upper())
        if rule is None:
            return self._fail(
                "explain_rule", args,
                f"{rule_id} is not one of the seven rules: " + ", ".join(RULES),
            )
        facts = [
            _fact(f"{rule_id}.text", "Rule text", rule["text"], "text",
                  source=f"rules.json#{rule_id}"),
            _fact(f"{rule_id}.id", "Rule id", rule_id.upper(), "rule_id",
                  source=f"rules.json#{rule_id}"),
        ]
        for key, value in rule["params"].items():
            facts.append(
                _fact(f"{rule_id}.{key}", key.replace("_", " "), value,
                      "hours" if "hours" in key else "count",
                      source=f"rules.json#{rule_id}")
            )
        return self._ok(
            "explain_rule", args, {"rule_id": rule_id.upper(), **rule}, facts,
            [TraceStep(label=rule_id.upper(), detail=rule["text"])],
            [Citation(file="rules.json", pointer=rule_id.upper())],
        )


# ---------------------------------------------------------------------------
# Rule evaluation for the fixture. Numbers from docs/DATA-MODEL.md section 7.
# ---------------------------------------------------------------------------


def _legality_for(
    crew_id: str, pairing_id: str, pairing: dict[str, Any], on_date: date | None
) -> LegalityReport:
    days: list[DayLegality] = []
    rated = pairing["aircraft_type"] in CREW[crew_id]["ratings"]
    cumulative = 0.0

    for day in pairing["days"]:
        duty_date = day["duty_date"]
        if on_date is not None and duty_date != on_date:
            continue
        cumulative += day["duty_hours"]
        traces: list[RuleTrace] = []

        # RULE-QUAL-05 short circuits: a rating failure suppresses every other
        # reason, matching the shipped exclusion strings.
        if not rated:
            traces.append(
                RuleTrace(
                    rule_id="RULE-QUAL-05",
                    title="Aircraft rating",
                    verdict=Verdict.BREACH,
                    duty_date=duty_date,
                    unit="boolean",
                    arithmetic=(
                        f"{crew_id} is rated "
                        f"{'/'.join(CREW[crew_id]['ratings'])} and "
                        f"{pairing_id} is {pairing['aircraft_type']}: no rating"
                    ),
                    margin_human="no valid rating for the type",
                )
            )
            days.append(
                DayLegality(duty_date=duty_date, verdict=Verdict.BREACH, traces=traces)
            )
            continue

        # RULE-FDP-01
        limit = 13.0 - 0.5 * max(0, day["sectors"] - 2)
        observed = day["duty_hours"]
        traces.append(
            RuleTrace(
                rule_id="RULE-FDP-01", title="Flight duty period",
                verdict=Verdict.PASS if observed <= limit else Verdict.BREACH,
                duty_date=duty_date, limit=limit, observed=observed, unit="hours",
                margin=round(limit - observed, 2),
                margin_human=f"{_fmt_hm(limit - observed)} spare",
                arithmetic=(
                    f"{observed:.2f}h duty against a {limit:.2f}h limit "
                    f"(13.00h base, reduced 0.50h for each sector beyond 2, "
                    f"{day['sectors']} sectors)"
                ),
            )
        )

        # RULE-DUTY-02
        table = DUTY_UNDER_COVER.get(crew_id, {})
        base_total = table.get(duty_date)
        if base_total is None:
            prior = CREW[crew_id]["duty_hours_7d"]
            total = round(prior + cumulative, 2)
            verdict = Verdict.PASS if total <= 60.0 else Verdict.BREACH
        else:
            prior, total, verdict = base_total
        margin = round(60.0 - total, 2)
        traces.append(
            RuleTrace(
                rule_id="RULE-DUTY-02", title="Duty hours in 7 days",
                verdict=verdict, duty_date=duty_date, limit=60.0, observed=total,
                unit="hours", margin=margin,
                margin_human=(
                    f"{_fmt_hm(-margin)} over the limit" if margin < 0
                    else f"{_fmt_hm(margin)} spare"
                ),
                arithmetic=(
                    f"{prior:.2f}h prior + {cumulative:.2f}h from {pairing_id} "
                    f"= {total:.2f}h against a 60.00h limit"
                    + (f", over by {abs(margin):.2f}h" if margin < 0 else "")
                ),
                inputs=[
                    _fact(f"{crew_id}.duty_prior.{duty_date}", "Prior duty in window",
                          prior, "hours", source=f"duty_clocks.json#{crew_id}"),
                    _fact(f"{pairing_id}.cover_duty.{duty_date}",
                          "Duty added by the cover", round(cumulative, 2), "hours",
                          provenance=Provenance.COMPUTED,
                          source="crewops.rules.duty.window",
                          derivation="cumulative across every day of the cover"),
                ],
            )
        )

        # RULE-FLT-03. Inert in this dataset: the maximum across all 150 crew is
        # 79.28h against a 100h limit. Implemented, never breached.
        block = CREW[crew_id]["flight_hours_28d"]
        traces.append(
            RuleTrace(
                rule_id="RULE-FLT-03", title="Block hours in 28 days",
                verdict=Verdict.PASS, duty_date=duty_date, limit=100.0,
                observed=block, unit="hours", margin=round(100.0 - block, 2),
                margin_human=f"{_fmt_hm(100.0 - block)} spare",
                arithmetic=f"{block:.2f}h block against a 100.00h limit",
            )
        )

        # RULE-REST-04
        traces.append(
            RuleTrace(
                rule_id="RULE-REST-04", title="Rest before duty",
                verdict=Verdict.PASS, duty_date=duty_date, limit=12.0,
                observed=12.0, unit="hours", margin=0.0,
                margin_human="exactly at the limit, which is legal",
                arithmetic="12.00h rest against a 12.00h minimum; the comparison "
                           "is inclusive",
            )
        )

        traces.append(
            RuleTrace(
                rule_id="RULE-QUAL-05", title="Aircraft rating",
                verdict=Verdict.PASS, duty_date=duty_date, unit="boolean",
                arithmetic=f"{crew_id} holds {pairing['aircraft_type']}",
            )
        )

        # RULE-CERT-06
        certs = CERTIFICATIONS.get(crew_id, [])
        lapsed = [c for c in certs if c["valid_to"] < duty_date]
        traces.append(
            RuleTrace(
                rule_id="RULE-CERT-06", title="Certification validity",
                verdict=Verdict.BREACH if lapsed else Verdict.PASS,
                duty_date=duty_date, unit="date",
                arithmetic=(
                    f"{lapsed[0]['type']} valid to "
                    f"{lapsed[0]['valid_to'].isoformat()} against a duty date of "
                    f"{duty_date.isoformat()}"
                    if lapsed
                    else f"every certification is valid on {duty_date.isoformat()}"
                ),
            )
        )

        # RULE-BASE-07
        away = CREW[crew_id]["base"] != "BLR"
        traces.append(
            RuleTrace(
                rule_id="RULE-BASE-07", title="Base and positioning",
                verdict=Verdict.PASS, duty_date=duty_date, unit="boolean",
                arithmetic=(
                    f"{crew_id} is based {CREW[crew_id]['base']} and the assignment "
                    "starts BLR: deadhead positioning applies and its cost is "
                    "charged"
                    if away
                    else f"{crew_id} is based BLR, the assignment's own base"
                ),
            )
        )

        worst = (
            Verdict.BREACH
            if any(t.verdict is Verdict.BREACH for t in traces)
            else Verdict.PASS
        )
        days.append(DayLegality(duty_date=duty_date, verdict=worst, traces=traces))

    overall = (
        Verdict.BREACH
        if any(day.verdict is Verdict.BREACH for day in days)
        else Verdict.PASS
    )
    return LegalityReport(
        crew_id=crew_id,
        assignment_ref=pairing_id,
        assignment_kind="pairing",
        overall=overall,
        per_day=days,
        rules_checked=[
            "RULE-FDP-01", "RULE-DUTY-02", "RULE-FLT-03", "RULE-REST-04",
            "RULE-QUAL-05", "RULE-CERT-06", "RULE-BASE-07",
        ],
    )


def _reasoning_for(crew_id: str, legality: LegalityReport, deadhead: bool) -> str:
    record = CREW[crew_id]
    parts = [
        f"{record['base']} based" if not deadhead else f"{record['base']} based, "
        "positioned to BLR",
        f"{record['ratings'][0]} rated",
    ]
    if record.get("oncall"):
        parts.append(f"on call {record['oncall'][0]} to {record['oncall'][1]}Z")
    parts.append(f"reachable in {record['reachability_minutes']} minutes")
    if legality.is_legal:
        parts.append("clears every rule on every day of the assignment")
    else:
        breach = legality.breaches[0]
        parts.append(f"{breach.rule_id}: {breach.arithmetic}")
    return ", ".join(parts) + "."
