/**
 * Reply fixtures.
 *
 * Six shapes, chosen so that every component in `components/answer/` is
 * exercised before the API exists:
 *
 *   1  Tier 1 table          reserves at BLR
 *   2  Tier 1 headroom       duty clocks for C-1042, with rule traces
 *   3  Tier 2 impact         C-1042 sick call on 15 Sep
 *   4  Tier 3 recommendation cover for P-2291, three options and four rejects
 *   5  Abstention            a question the dataset cannot answer
 *   6  Verification failure  a draft the guard rejected, ending in a refusal
 *
 * House rule these fixtures follow, and the reason they read slightly oddly
 * in places: every digit in a reply's prose is carried by a Fact in the same
 * reply. Where no tool would produce a figure, the prose spells the number as
 * a word instead. Figures are written the way `Fact.rendered()` writes them,
 * trailing zeros trimmed, so "48.5h" and never "48.50h". That is exactly the
 * discipline the real verifier enforces, so the fixtures should not cheat it.
 */

import type {
  Fact,
  FlightRef,
  ImpactReport,
  Recommendation,
  Reply,
  Table,
  ToolEnvelope,
  TraceStep,
} from "@/lib/contracts";
import { computed, dataset } from "@/mocks/facts";
import {
  LEGALITY_C2087,
  LEGALITY_C2091,
  LEGALITY_C2210,
  LEGALITY_C3305,
  LEGALITY_C3310,
  LEGALITY_C3312,
  LEGALITY_C4188,
} from "@/mocks/legality";
import { SNAPSHOT } from "@/mocks/world";

/* ---------------------------------------------------------------- shared */

const F = {
  c1042: dataset("C-1042.identity", "Crew", "C-1042", "crew_id", "crew.json#C-1042"),
  c1042Name: dataset(
    "C-1042.name",
    "Name",
    "A. Nair",
    "text",
    "crew.json#C-1042",
  ),
  p2291: dataset(
    "P-2291.identity",
    "Pairing",
    "P-2291",
    "pairing_id",
    "rosters.json#P-2291",
  ),
  day1: dataset(
    "P-2291.day1.date",
    "Pairing day 1",
    "2026-09-15",
    "date",
    "rosters.json#P-2291/day1",
  ),
  day2: dataset(
    "P-2291.day2.date",
    "Pairing day 2",
    "2026-09-16",
    "date",
    "rosters.json#P-2291/day2",
  ),
  blr: dataset("station.BLR", "Hub", "BLR", "station", "flights.json#stations"),
  del: dataset("station.DEL", "Station", "DEL", "station", "flights.json#stations"),
  hyd: dataset("station.HYD", "Station", "HYD", "station", "flights.json#stations"),
  a320: dataset(
    "P-2291.aircraft",
    "Aircraft type",
    "A320",
    "aircraft_type",
    "flights.json#DX412",
  ),
  dx412: dataset("DX412.identity", "Flight", "DX412", "flight_no", "flights.json#DX412"),
  dx413: dataset("DX413.identity", "Flight", "DX413", "flight_no", "flights.json#DX413"),
  dx588: dataset("DX588.identity", "Flight", "DX588", "flight_no", "flights.json#DX588"),
  dx589: dataset("DX589.identity", "Flight", "DX589", "flight_no", "flights.json#DX589"),
  dx590: dataset("DX590.identity", "Flight", "DX590", "flight_no", "flights.json#DX590"),
  dx591: dataset("DX591.identity", "Flight", "DX591", "flight_no", "flights.json#DX591"),
  c2087: dataset("C-2087.identity", "Crew", "C-2087", "crew_id", "crew.json#C-2087"),
  c3310: dataset("C-3310.identity", "Crew", "C-3310", "crew_id", "crew.json#C-3310"),
  c2210: dataset("C-2210.identity", "Crew", "C-2210", "crew_id", "crew.json#C-2210"),
  c3312: dataset("C-3312.identity", "Crew", "C-3312", "crew_id", "crew.json#C-3312"),
  c3305: dataset("C-3305.identity", "Crew", "C-3305", "crew_id", "crew.json#C-3305"),
  c2091: dataset("C-2091.identity", "Crew", "C-2091", "crew_id", "crew.json#C-2091"),
  c4188: dataset("C-4188.identity", "Crew", "C-4188", "crew_id", "crew.json#C-4188"),
  dutyLimit: dataset(
    "RULE-DUTY-02.limit",
    "Rolling duty limit",
    60,
    "hours",
    "rules.json#RULE-DUTY-02",
  ),
  fltLimit: dataset(
    "RULE-FLT-03.limit",
    "Rolling flight hour limit",
    100,
    "hours",
    "rules.json#RULE-FLT-03",
  ),
  restLimit: dataset(
    "RULE-REST-04.limit",
    "Minimum rest",
    12,
    "hours",
    "rules.json#RULE-REST-04",
  ),
  ruleDuty: dataset(
    "RULE-DUTY-02.id",
    "Rule",
    "RULE-DUTY-02",
    "rule_id",
    "rules.json#RULE-DUTY-02",
  ),
  ruleFlt: dataset(
    "RULE-FLT-03.id",
    "Rule",
    "RULE-FLT-03",
    "rule_id",
    "rules.json#RULE-FLT-03",
  ),
  ruleQual: dataset(
    "RULE-QUAL-05.id",
    "Rule",
    "RULE-QUAL-05",
    "rule_id",
    "rules.json#RULE-QUAL-05",
  ),
};

function envelope(
  tool: string,
  args: Record<string, unknown>,
  latency_ms: number,
  facts: Fact[],
  trace: TraceStep[],
  citations: { file: string; pointer: string; note?: string }[],
  payloadNote: string,
): ToolEnvelope {
  return {
    tool,
    args,
    ok: true,
    payload: { note: payloadNote },
    facts,
    trace,
    citations,
    latency_ms,
    truncated: false,
  };
}

const VERIFIED = (checked: number) => ({
  status: "verified" as const,
  checked_atoms: checked,
  attested_atoms: checked,
  unattested: [],
  repair_attempts: 0,
  note: null,
});

/* ------------------------------------------------------- 1  Tier 1 table */

const RESERVE_TABLE: Table = {
  title: "Reserve register, BLR, 15 Sep 2026",
  columns: [
    "Crew",
    "Name",
    "Rank",
    "Ratings",
    "On call",
    "Standby",
    "Reachable in",
  ],
  rows: [
    ["C-3310", "R. Menon", "Captain", "A320", "06:00-18:00", "Home", "45m"],
    ["C-3318", "P. Varghese", "First Officer", "A320", "06:00-18:00", "Home", "55m"],
    ["C-3327", "N. Balakrishnan", "Captain", "A320", "10:00-22:00", "Airport", "15m"],
    ["C-3341", "S. Kulkarni", "First Officer", "A320", "12:00-23:59", "Home", "70m"],
    ["C-2091", "T. Fernandes", "Captain", "ATR72", "06:00-18:00", "Home", "50m"],
    ["C-3352", "A. D'Cruz", "First Officer", "ATR72", "14:00-23:59", "Home", "65m"],
  ],
  row_ids: ["C-3310", "C-3318", "C-3327", "C-3341", "C-2091", "C-3352"],
  caption:
    "Read from reserve_pool.json. On call windows and reachability are as recorded, not estimated. All times UTC.",
};

const RESERVES_FACTS: Fact[] = [
  F.blr,
  F.day1,
  F.a320,
  F.c3310,
  dataset(
    "reserve.C-3310.window",
    "On call window",
    "06:00-18:00",
    "text",
    "reserve_pool.json#C-3310",
  ),
  dataset(
    "reserve.C-3310.reachable",
    "Reachable in",
    45,
    "minutes",
    "crew.json#C-3310",
  ),
  dataset(
    "C-2091.ratings",
    "Type ratings held",
    "ATR72",
    "aircraft_type",
    "crew.json#C-2091",
  ),
];

export const REPLY_RESERVES: Reply = {
  thread_id: "T-mock-1",
  turn_id: "U-mock-1",
  question: "Who is on reserve at BLR tomorrow?",
  asked_at: SNAPSHOT,
  kind: "answer",
  mode: "agent",
  tier: 1,
  headline: "Six reserves on call at BLR on 15 Sep, four of them A320 rated.",
  text:
    "Six crew are on the reserve register at BLR for 15 Sep. Four hold an A320 rating and two are ATR72 only, so the usable pool for a narrowbody pairing is four.\n\n" +
    "C-3310 is on call 06:00-18:00 and reachable in 45 minutes, which is the earliest and closest of the six.",
  facts: RESERVES_FACTS,
  traces: [
    {
      label: "Filtered the reserve register",
      detail:
        "reserve_pool.json for 2026-09-15, base BLR, standby status active or home.",
      fact_keys: ["station.BLR", "P-2291.day1.date"],
    },
    {
      label: "Joined ratings from the crew file",
      detail:
        "Each reserve was matched to crew.json to attach rank, ratings and reachability.",
      fact_keys: ["reserve.C-3310.reachable"],
    },
  ],
  rule_traces: [],
  tables: [RESERVE_TABLE],
  citations: [
    { file: "reserve_pool.json", pointer: "date=2026-09-15,base=BLR" },
    { file: "crew.json", pointer: "6 records", note: "Ratings and reachability" },
  ],
  tool_calls: [
    envelope(
      "list_reserves",
      { on_date: "2026-09-15", base: "BLR" },
      42,
      RESERVES_FACTS,
      [
        {
          label: "Filtered the reserve register",
          detail: "6 of 16 reserves match base BLR on 2026-09-15.",
          fact_keys: ["station.BLR"],
        },
      ],
      [{ file: "reserve_pool.json", pointer: "date=2026-09-15,base=BLR" }],
      "6 reserve records with on call windows and standby status.",
    ),
  ],
  confidence: "high",
  verification: VERIFIED(9),
  timings: {
    total_ms: 1840,
    plan_ms: 610,
    tools_ms: 42,
    verify_ms: 38,
    model_calls: 2,
    tool_calls: 1,
  },
  caveats: [
    "On call windows are as recorded in the register. They do not account for a reserve already used earlier in the day.",
  ],
  follow_ups: [
    "Which of these are legal for P-2291?",
    "How many duty hours does C-3310 have left this week?",
  ],
};

/* --------------------------------------------------- 2  Tier 1 headroom */

const CLOCKS_FACTS: Fact[] = [
  F.c1042,
  F.c1042Name,
  F.dutyLimit,
  F.fltLimit,
  dataset(
    "C-1042.duty_7d.used",
    "Duty used, 7 days to 20 Sep",
    48.5,
    "hours",
    "duty_clocks.json#C-1042",
  ),
  computed(
    "C-1042.duty_7d.headroom",
    "Duty headroom",
    11.5,
    "hours",
    "crewops.rules.duty.headroom",
    "60h limit less 48.5h used = 11.5h remaining in the seven days to 20 Sep.",
  ),
  dataset(
    "C-1042.flight_28d.used",
    "Flight hours used, 28 days to 20 Sep",
    82,
    "hours",
    "duty_clocks.json#C-1042",
  ),
  computed(
    "C-1042.flight_28d.headroom",
    "Flight hour headroom",
    18,
    "hours",
    "crewops.rules.flight.headroom",
    "100h limit less 82h used = 18h remaining in the 28 days to 20 Sep.",
  ),
  dataset(
    "week.end",
    "Roster week ends",
    "2026-09-20",
    "date",
    "flights.json#date_range",
  ),
];

export const REPLY_CLOCKS: Reply = {
  thread_id: "T-mock-2",
  turn_id: "U-mock-2",
  question: "How many duty hours does C-1042 have left this week?",
  asked_at: SNAPSHOT,
  kind: "answer",
  mode: "agent",
  tier: 1,
  headline: "C-1042 has 11.5h of duty headroom left in the week to 20 Sep 2026.",
  text:
    "C-1042 has used 48.5h of duty in the seven days to 20 Sep 2026, against a 60h limit. That leaves 11.5h.\n\n" +
    "Flight hours are the easier constraint here: 82h against a 100h limit over the 28 day window, so 18h spare.\n\n" +
    "Both figures count the roster as it currently stands. Anything assigned on top of it moves them.",
  facts: CLOCKS_FACTS,
  traces: [
    {
      label: "Read the recorded clocks",
      detail:
        "duty_clocks.json carries the running accruals for C-1042 as at the snapshot.",
      fact_keys: ["C-1042.duty_7d.used", "C-1042.flight_28d.used"],
    },
    {
      label: "Computed headroom against each limit",
      detail:
        "Headroom is the limit less the window total. It is not a forecast.",
      fact_keys: ["C-1042.duty_7d.headroom", "C-1042.flight_28d.headroom"],
    },
  ],
  rule_traces: [
    {
      rule_id: "RULE-DUTY-02",
      title: "Rolling duty hours",
      verdict: "pass",
      duty_date: "2026-09-20",
      limit: 60,
      observed: 48.5,
      unit: "hours",
      margin: 11.5,
      margin_human: "11h30m spare",
      arithmetic:
        "48.50h in the 7 days to 2026-09-20 against a 60.00h limit, 11.50h spare.",
      inputs: [
        CLOCKS_FACTS[4],
        CLOCKS_FACTS[5],
        F.dutyLimit,
      ],
    },
    {
      rule_id: "RULE-FLT-03",
      title: "Rolling flight hours",
      verdict: "pass",
      duty_date: "2026-09-20",
      limit: 100,
      observed: 82,
      unit: "hours",
      margin: 18,
      margin_human: "18h spare",
      arithmetic:
        "82.00h in the 28 days to 2026-09-20 against a 100.00h limit, 18.00h spare.",
      inputs: [CLOCKS_FACTS[6], CLOCKS_FACTS[7], F.fltLimit],
    },
  ],
  tables: [],
  citations: [
    { file: "duty_clocks.json", pointer: "C-1042" },
    { file: "rosters.json", pointer: "C-1042", note: "Rostered duty for the week" },
  ],
  tool_calls: [
    envelope(
      "get_duty_clocks",
      { crew_id: "C-1042", as_of: SNAPSHOT },
      31,
      CLOCKS_FACTS,
      [
        {
          label: "Summed the seven day window",
          detail:
            "Recorded daily history plus rostered duty length for each day in the window.",
          fact_keys: ["C-1042.duty_7d.used"],
        },
      ],
      [{ file: "duty_clocks.json", pointer: "C-1042" }],
      "Duty and flight hour state with headroom under each limit.",
    ),
  ],
  confidence: "high",
  verification: VERIFIED(11),
  timings: {
    total_ms: 1520,
    plan_ms: 520,
    tools_ms: 31,
    verify_ms: 29,
    model_calls: 2,
    tool_calls: 1,
  },
  caveats: [
    "The seven day window is the one ending on the roster week end. A window ending on a different date gives a different figure.",
  ],
  follow_ups: [
    "Is C-1042 legal for P-2291?",
    "Which crew at BLR are inside five hours of the duty limit?",
  ],
};

/* ----------------------------------------------------- 3  Tier 2 impact */

const DAY_1_FLIGHTS: FlightRef[] = [
  {
    flight_no: "DX412",
    origin: "BLR",
    destination: "DEL",
    departure: "2026-09-15T06:40:00",
    arrival: "2026-09-15T08:35:00",
    aircraft_type: "A320",
    passengers: 180,
    pairing_id: "P-2291",
  },
  {
    flight_no: "DX413",
    origin: "DEL",
    destination: "BLR",
    departure: "2026-09-15T09:30:00",
    arrival: "2026-09-15T11:27:00",
    aircraft_type: "A320",
    passengers: 174,
    pairing_id: "P-2291",
  },
  {
    flight_no: "DX588",
    origin: "BLR",
    destination: "HYD",
    departure: "2026-09-15T13:15:00",
    arrival: "2026-09-15T14:35:00",
    aircraft_type: "A320",
    passengers: 132,
    pairing_id: "P-2291",
  },
];

export const DAY_2_FLIGHTS: FlightRef[] = [
  {
    flight_no: "DX589",
    origin: "HYD",
    destination: "BLR",
    departure: "2026-09-16T07:10:00",
    arrival: "2026-09-16T08:48:00",
    aircraft_type: "A320",
    passengers: 128,
    pairing_id: "P-2291",
  },
  {
    flight_no: "DX590",
    origin: "BLR",
    destination: "COK",
    departure: "2026-09-16T09:40:00",
    arrival: "2026-09-16T11:18:00",
    aircraft_type: "A320",
    passengers: 176,
    pairing_id: "P-2291",
  },
  {
    flight_no: "DX591",
    origin: "COK",
    destination: "BLR",
    departure: "2026-09-16T11:57:00",
    arrival: "2026-09-16T13:35:00",
    aircraft_type: "A320",
    passengers: 171,
    pairing_id: "P-2291",
  },
];

const IMPACT_FACTS: Fact[] = [
  F.c1042,
  F.c1042Name,
  F.p2291,
  F.day1,
  F.day2,
  F.dx412,
  F.dx413,
  F.dx588,
  F.dx589,
  F.dx590,
  F.dx591,
  F.blr,
  F.del,
  F.hyd,
  F.c2087,
  F.ruleDuty,
  F.dutyLimit,
  computed(
    "impact.passengers_affected",
    "Passengers on the uncrewed legs",
    486,
    "count",
    "crewops.ops.impact.passengers",
    "180 on DX412 plus 174 on DX413 plus 132 on DX588 = 486.",
  ),
  computed(
    "C-2087.duty_7d.projected",
    "Projected 7 day duty",
    61.33,
    "hours",
    "crewops.rules.duty.window",
    "48.50h prior + 12.83h added by P-2291 = 61.33h against a 60.00h limit.",
  ),
  computed(
    "C-2087.duty_7d.overage",
    "Overage against the duty limit",
    1.33,
    "hours",
    "crewops.rules.duty.window",
    "61.33h projected less the 60.00h limit = 1.33h over.",
  ),
];

export const IMPACT: ImpactReport = {
  trigger: "C-1042 unavailable from 2026-09-15, sick call",
  trigger_kind: "crew_absence",
  as_of: SNAPSHOT,
  uncrewed_flights: DAY_1_FLIGHTS,
  pairings_broken: ["P-2291"],
  crew_affected: ["C-1042", "C-2087"],
  stations_affected: ["BLR", "DEL", "HYD"],
  passengers_affected: 486,
  downstream_risks: [
    {
      crew_id: "C-2087",
      pairing_id: "P-2291",
      rule_id: "RULE-DUTY-02",
      severity: "critical",
      detail:
        "Would exceed the 7 day duty limit by 1.33h if used as the substitution.",
      duty_date: "2026-09-16",
    },
    {
      flight_no: "DX589",
      pairing_id: "P-2291",
      severity: "high",
      detail:
        "Day 2 of P-2291 does not resume without a captain positioned at HYD overnight.",
      duty_date: "2026-09-16",
    },
    {
      crew_id: "C-3305",
      pairing_id: "P-2291",
      rule_id: "RULE-FLT-03",
      severity: "medium",
      detail:
        "Legal on 15 Sep and breaches on 16 Sep, so a single day check would clear them wrongly.",
      duty_date: "2026-09-16",
    },
    {
      flight_no: "DX588",
      severity: "low",
      detail:
        "The aircraft night stops at HYD. A cancellation here displaces the 16 Sep rotation as well.",
      duty_date: "2026-09-15",
    },
  ],
  explanation:
    "C-1042 operates P-2291. All three legs on 15 Sep are now uncrewed and the pairing is broken.",
  facts: IMPACT_FACTS,
};

export const REPLY_IMPACT: Reply = {
  thread_id: "T-mock-3",
  turn_id: "U-mock-3",
  question:
    "Captain C-1042 just called in sick for tomorrow, which flights are now uncrewed?",
  asked_at: SNAPSHOT,
  kind: "answer",
  mode: "agent",
  tier: 2,
  headline:
    "P-2291 breaks. DX412, DX413 and DX588 are uncrewed on 15 Sep, 486 passengers affected.",
  text:
    "C-1042 operates pairing P-2291. Day one, on 15 Sep, is DX412 BLR to DEL, DX413 DEL to BLR and DX588 BLR to HYD. With C-1042 unavailable all three legs are uncrewed and the pairing is broken.\n\n" +
    "486 passengers are booked across those three legs.\n\n" +
    "Day two of the same pairing, DX589, DX590 and DX591 on 16 Sep, is exposed as well: the pairing does not resume without a captain positioned at HYD overnight.\n\n" +
    "The nearest substitution, C-2087, does not work. Taking P-2291 would put them at 61.33h of duty in the seven days to 16 Sep against a 60h limit, over by 1.33h. That is a RULE-DUTY-02 breach, not a warning.",
  facts: IMPACT_FACTS,
  traces: [
    {
      label: "Resolved the roster for C-1042",
      detail: "C-1042 is assigned to P-2291 across 15 and 16 Sep.",
      fact_keys: ["C-1042.identity", "P-2291.identity"],
    },
    {
      label: "Expanded the pairing to its legs",
      detail:
        "P-2291 covers six legs over two duty days. Removing the captain uncrews all of them.",
      fact_keys: ["DX412.identity", "DX413.identity", "DX588.identity"],
    },
    {
      label: "Summed booked passengers on the affected legs",
      detail: "180 plus 174 plus 132 across the three legs on 15 Sep.",
      fact_keys: ["impact.passengers_affected"],
    },
    {
      label: "Checked the nearest substitution against all seven rules",
      detail:
        "C-2087 passes six rules and breaches RULE-DUTY-02 on the second duty day.",
      fact_keys: ["C-2087.duty_7d.projected", "RULE-DUTY-02.limit"],
    },
  ],
  rule_traces: LEGALITY_C2087.per_day[1].traces.filter(
    (t) => t.rule_id === "RULE-DUTY-02",
  ),
  tables: [],
  impact: IMPACT,
  citations: [
    { file: "rosters.json", pointer: "C-1042", note: "Assignment to P-2291" },
    { file: "flights.json", pointer: "DX412, DX413, DX588" },
    { file: "duty_clocks.json", pointer: "C-2087" },
    { file: "rules.json", pointer: "RULE-DUTY-02" },
  ],
  tool_calls: [
    envelope(
      "get_crew_detail",
      { crew_id: "C-1042" },
      28,
      [F.c1042, F.c1042Name, F.p2291],
      [
        {
          label: "Loaded crew record and roster",
          detail: "C-1042, A. Nair, Captain, BLR, A320 rated.",
          fact_keys: ["C-1042.identity"],
        },
      ],
      [{ file: "crew.json", pointer: "C-1042" }],
      "Crew record with roster, clocks, certifications and reserve status.",
    ),
    envelope(
      "simulate_absence",
      { crew_id: "C-1042", from_date: "2026-09-15", reason: "sick call" },
      184,
      IMPACT_FACTS,
      [
        {
          label: "Modelled the absence",
          detail:
            "Three legs uncrewed, one pairing broken, 486 passengers exposed.",
          fact_keys: ["impact.passengers_affected"],
        },
      ],
      [
        { file: "rosters.json", pointer: "P-2291" },
        { file: "flights.json", pointer: "DX412, DX413, DX588" },
      ],
      "ImpactReport with uncrewed flights, broken pairings and downstream risks.",
    ),
    envelope(
      "check_legality",
      { crew_id: "C-2087", pairing_id: "P-2291", as_replacement_for: "C-1042" },
      96,
      [F.c2087, F.dutyLimit, IMPACT_FACTS[18], IMPACT_FACTS[19]],
      [
        {
          label: "Evaluated all seven rules per duty day",
          detail:
            "Pass on 15 Sep. RULE-DUTY-02 breach on 16 Sep at 61.33h against 60.00h.",
          fact_keys: ["C-2087.duty_7d.projected"],
        },
      ],
      [{ file: "duty_clocks.json", pointer: "C-2087" }],
      "LegalityReport, overall breach, worst day 2026-09-16.",
    ),
  ],
  confidence: "high",
  verification: VERIFIED(24),
  timings: {
    total_ms: 4310,
    plan_ms: 780,
    tools_ms: 308,
    verify_ms: 91,
    model_calls: 3,
    tool_calls: 3,
  },
  caveats: [
    "Passenger counts are the booked figures in the dataset. They are not a live load.",
    "Only the substitution nearest on the reserve list was checked here. Ask for cover options to search the whole pool.",
  ],
  follow_ups: [
    "Captain C-1042 is out, what should I do?",
    "Is C-3305 legal to operate the whole of P-2291?",
    "How many passengers are affected across both days?",
  ],
};

/* --------------------------------------------- 4  Tier 3 recommendation */

const REC_FACTS: Fact[] = [
  F.c1042,
  F.p2291,
  F.day1,
  F.day2,
  F.blr,
  F.del,
  F.a320,
  F.dx412,
  F.dx413,
  F.dx588,
  F.dx589,
  F.dx590,
  F.dx591,
  F.c3310,
  F.c2210,
  F.c3312,
  F.c2087,
  F.c3305,
  F.c2091,
  F.c4188,
  F.dutyLimit,
  F.restLimit,
  F.ruleFlt,
  F.ruleDuty,
  computed(
    "cover.candidates_evaluated",
    "Candidates evaluated",
    14,
    "count",
    "crewops.ops.candidates.enumerate",
    "16 reserves and rostered crew at BLR and DEL, less 2 already assigned on 15 Sep, = 14 evaluated.",
  ),
  dataset(
    "reserve.C-3310.window",
    "On call window",
    "06:00-18:00",
    "text",
    "reserve_pool.json#C-3310",
  ),
  dataset(
    "reserve.C-3310.reachable",
    "Reachable in",
    45,
    "minutes",
    "crew.json#C-3310",
  ),
  computed(
    "cover.C-3310.total",
    "Total cost, option 1",
    18500,
    "inr",
    "crewops.ops.cost.total",
    "Reserve callout INR 12,000 plus duty premium INR 6,500 = INR 18,500.",
  ),
  computed(
    "cover.C-2210.total",
    "Total cost, option 2",
    41200,
    "inr",
    "crewops.ops.cost.total",
    "Positioning INR 22,000 plus callout INR 12,000 plus delay penalty INR 7,200 = INR 41,200.",
  ),
  computed(
    "cover.C-2210.deadhead",
    "Positioning cost",
    22000,
    "inr",
    "crewops.ops.cost.deadhead",
    "1 positioning sector DEL to BLR at the INR 22,000 deadhead rate.",
  ),
  dataset(
    "cover.C-2210.delay",
    "Delay to DX412",
    180,
    "minutes",
    "costs.json#deadhead.DEL-BLR",
  ),
  computed(
    "cover.C-3312.total",
    "Total cost, option 3",
    26900,
    "inr",
    "crewops.ops.cost.total",
    "Re-roster premium INR 9,400 plus overtime INR 8,500 plus backfill callout INR 9,000 = INR 26,900.",
  ),
  dataset(
    "P-2304.identity",
    "Pairing left open by the swap",
    "P-2304",
    "pairing_id",
    "rosters.json#P-2304",
  ),
  computed(
    "C-2087.duty_7d.projected",
    "Projected 7 day duty",
    61.33,
    "hours",
    "crewops.rules.duty.window",
    "48.50h prior + 12.83h added by P-2291 = 61.33h against a 60.00h limit.",
  ),
  computed(
    "C-3305.flight_28d.projected",
    "Projected 28 day flight hours",
    101.6,
    "hours",
    "crewops.rules.flight.window",
    "96.40h to 15 Sep + 5.20h block on 16 Sep = 101.60h against a 100.00h limit.",
  ),
  dataset(
    "C-2091.ratings",
    "Type ratings held",
    "ATR72",
    "aircraft_type",
    "crew.json#C-2091",
  ),
  computed(
    "C-4188.rest.available",
    "Rest before sign on",
    3.17,
    "hours",
    "crewops.rules.rest.before",
    "02:30 to 05:40 on 2026-09-15 is 3h10m = 3.17h against a 12.00h minimum.",
  ),
];

export const RECOMMENDATION: Recommendation = {
  situation:
    "C-1042 is unavailable from 15 Sep. P-2291 needs a captain for both duty days, six legs in total.",
  impact: IMPACT,
  candidates_evaluated: 14,
  ranking_basis:
    "Legal options only. Ordered by whether the option covers every leg without opening a new gap, then by knock-on delay to the first departure, then by total cost. Cost is the last tie break, not the objective.",
  notification_draft:
    "C-3310, you are called from reserve for P-2291. Report BLR 05:40 on 15 Sep for DX412. The pairing runs two days and releases at BLR 13:35 on 16 Sep. Acknowledge to Crew Control.",
  facts: REC_FACTS,
  options: [
    {
      rank: 1,
      kind: "reserve",
      action: "Assign reserve C-3310",
      crew_id: "C-3310",
      crew_name: "R. Menon",
      crew_base: "BLR",
      crew_rank: "Captain",
      legal: true,
      legality: LEGALITY_C3310,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: {
        line_items: [
          {
            label: "Reserve callout",
            amount_inr: 12000,
            basis: "Flat callout, reserve grade A",
            rule_ref: "callout.reserve_grade_a",
          },
          {
            label: "Duty premium",
            amount_inr: 6500,
            basis: "6.5 premium duty hours x INR 1,000/h",
            rule_ref: "premium.duty_hourly",
          },
        ],
        total_inr: 18500,
        note: "No positioning and no delay compensation, because the callout is from base.",
      },
      coverage_summary: "all six legs",
      covered_flights: ["DX412", "DX413", "DX588", "DX589", "DX590", "DX591"],
      uncovered_flights: [],
      reachable: true,
      reachability_minutes: 45,
      delay_minutes: 0,
      reasoning:
        "BLR based and A320 rated, on call 06:00-18:00, reachable in 45 minutes against a 05:40 report. Clear on all seven rules on both duty days, with 25.08h of duty headroom to spare on the first day.",
      tradeoffs: [
        "Spends the strongest BLR reserve two days before the weekend peak.",
        "Leaves three A320 reserves at BLR for 16 Sep, one of them airport standby.",
      ],
      confidence: "high",
      facts: [F.c3310, REC_FACTS[25], REC_FACTS[26], REC_FACTS[27]],
    },
    {
      rank: 2,
      kind: "deadhead",
      action: "Deadhead C-2210 from DEL",
      crew_id: "C-2210",
      crew_name: "S. Iyer",
      crew_base: "DEL",
      crew_rank: "Captain",
      legal: true,
      legality: LEGALITY_C2210,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: {
        line_items: [
          {
            label: "Positioning, DEL to BLR",
            amount_inr: 22000,
            basis: "1 positioning sector at the DEL-BLR deadhead rate",
            rule_ref: "deadhead.DEL-BLR",
          },
          {
            label: "Callout",
            amount_inr: 12000,
            basis: "Flat callout, reserve grade A",
            rule_ref: "callout.reserve_grade_a",
          },
          {
            label: "Delay penalty, DX412",
            amount_inr: 7200,
            basis: "3 delay hours x INR 2,400/h",
            rule_ref: "penalty.delay_hourly",
          },
        ],
        total_inr: 41200,
        note: "Positioning is the bulk of it. The delay penalty assumes the departure moves once, not repeatedly.",
      },
      coverage_summary: "all six legs, with DX412 delayed",
      covered_flights: ["DX412", "DX413", "DX588", "DX589", "DX590", "DX591"],
      uncovered_flights: [],
      reachable: true,
      reachability_minutes: 195,
      delay_minutes: 180,
      reasoning:
        "Legal on both days, but out of base. RULE-BASE-07 is satisfied only with positioning applied, and the earliest DEL to BLR positioning sector puts DX412 back by 180 minutes. Flight duty period lands at 10.75h against an 11h limit, the thinnest margin of any legal option.",
      tradeoffs: [
        "Delays DX412 by 180 minutes, which cascades into the DEL turnaround.",
        "Costs INR 41,200, more than twice option 1.",
        "Leaves 15 minutes of flight duty period margin. A short delay on the positioning sector makes this illegal.",
      ],
      confidence: "medium",
      facts: [F.c2210, REC_FACTS[28], REC_FACTS[29], REC_FACTS[30]],
    },
    {
      rank: 3,
      kind: "swap",
      action: "Swap C-3312 across from P-2304",
      crew_id: "C-3312",
      crew_name: "K. Raghavan",
      crew_base: "BLR",
      crew_rank: "Captain",
      legal: true,
      legality: LEGALITY_C3312,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: {
        line_items: [
          {
            label: "Re-roster premium",
            amount_inr: 9400,
            basis: "Contractual change inside 24 hours, flat",
            rule_ref: "premium.reroster_short_notice",
          },
          {
            label: "Overtime on the displaced duty",
            amount_inr: 8500,
            basis: "4.25 overtime hours x INR 2,000/h",
            rule_ref: "overtime.hourly",
          },
          {
            label: "Backfill callout for P-2304",
            amount_inr: 9000,
            basis: "Flat callout, reserve grade B",
            rule_ref: "callout.reserve_grade_b",
          },
        ],
        total_inr: 26900,
        note: "The backfill line is the honest part of this option: it prices the gap the swap creates.",
      },
      coverage_summary: "all six legs, but opens a gap on P-2304",
      covered_flights: ["DX412", "DX413", "DX588", "DX589", "DX590", "DX591"],
      uncovered_flights: ["DX640", "DX641"],
      reachable: true,
      reachability_minutes: 60,
      delay_minutes: 0,
      reasoning:
        "Legal on both duty days with no delay, but the swap moves the problem rather than closing it: P-2304 then needs cover on 16 Sep, and the backfill has not been searched.",
      tradeoffs: [
        "Opens a new gap on P-2304 the following morning.",
        "Two crew are re-rostered inside 24 hours instead of one.",
        "The backfill cost is an estimate from the rate card, not a searched option.",
      ],
      confidence: "medium",
      facts: [F.c3312, REC_FACTS[31], REC_FACTS[32]],
    },
  ],
  rejected: [
    {
      rank: 0,
      kind: "reassign",
      action: "Reassign C-2087 from standby",
      crew_id: "C-2087",
      crew_name: "V. Krishnan",
      crew_base: "BLR",
      crew_rank: "Captain",
      legal: false,
      legality: LEGALITY_C2087,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: { line_items: [], total_inr: 0, note: "Not priced: the option is illegal." },
      coverage_summary: "would have covered all six legs",
      covered_flights: [],
      uncovered_flights: ["DX412", "DX413", "DX588", "DX589", "DX590", "DX591"],
      reachable: true,
      reachability_minutes: 40,
      delay_minutes: 0,
      reasoning:
        "Excluded on RULE-DUTY-02 on the second duty day. 48.5h of duty already sits in the seven days to 16 Sep, and P-2291 adds 12.83h, reaching 61.33h against a 60h limit.",
      tradeoffs: [],
      confidence: "high",
      facts: [F.c2087, REC_FACTS[33]],
    },
    {
      rank: 0,
      kind: "reassign",
      action: "Reassign C-3305",
      crew_id: "C-3305",
      crew_name: "M. Pillai",
      crew_base: "BLR",
      crew_rank: "Captain",
      legal: false,
      legality: LEGALITY_C3305,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: { line_items: [], total_inr: 0, note: "Not priced: the option is illegal." },
      coverage_summary: "legal for 15 Sep only",
      covered_flights: [],
      uncovered_flights: ["DX589", "DX590", "DX591"],
      reachable: true,
      reachability_minutes: 55,
      delay_minutes: 0,
      reasoning:
        "Clear on 15 Sep with 3.6h of flight hour headroom, then breaches RULE-FLT-03 on 16 Sep at 101.6h against a 100h limit. A candidate has to be legal on every day of the cover, so this is excluded rather than split.",
      tradeoffs: [],
      confidence: "high",
      facts: [F.c3305, REC_FACTS[34], F.fltLimit],
    },
    {
      rank: 0,
      kind: "reserve",
      action: "Assign reserve C-2091",
      crew_id: "C-2091",
      crew_name: "T. Fernandes",
      crew_base: "BLR",
      crew_rank: "Captain",
      legal: false,
      legality: LEGALITY_C2091,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: { line_items: [], total_inr: 0, note: "Not priced: the option is illegal." },
      coverage_summary: "no legs",
      covered_flights: [],
      uncovered_flights: ["DX412", "DX413", "DX588", "DX589", "DX590", "DX591"],
      reachable: true,
      reachability_minutes: 50,
      delay_minutes: 0,
      reasoning:
        "On call and reachable, but holds ATR72 only. P-2291 operates A320 on every leg, so RULE-QUAL-05 excludes them. A rating breach cannot be priced away.",
      tradeoffs: [],
      confidence: "high",
      facts: [F.c2091, REC_FACTS[35], F.a320],
    },
    {
      rank: 0,
      kind: "reassign",
      action: "Reassign C-4188",
      crew_id: "C-4188",
      crew_name: "G. Sundaram",
      crew_base: "BLR",
      crew_rank: "Captain",
      legal: false,
      legality: LEGALITY_C4188,
      rules_checked: [
        "RULE-FDP-01",
        "RULE-DUTY-02",
        "RULE-FLT-03",
        "RULE-REST-04",
        "RULE-QUAL-05",
        "RULE-CERT-06",
        "RULE-BASE-07",
      ],
      cost: { line_items: [], total_inr: 0, note: "Not priced: the option is illegal." },
      coverage_summary: "no legs",
      covered_flights: [],
      uncovered_flights: ["DX412", "DX413", "DX588", "DX589", "DX590", "DX591"],
      reachable: true,
      reachability_minutes: 35,
      delay_minutes: 0,
      reasoning:
        "Came off duty at 02:30 on 15 Sep. That leaves 3.17h before a 05:40 sign on, against a 12h minimum, so RULE-REST-04 excludes them. Their recurrent training record is also missing, which RULE-CERT-06 reports as insufficient data rather than as a pass.",
      tradeoffs: [],
      confidence: "high",
      facts: [F.c4188, REC_FACTS[36], F.restLimit],
    },
  ],
};

export const REPLY_RECOMMENDATION: Reply = {
  thread_id: "T-mock-4",
  turn_id: "U-mock-4",
  question: "Captain C-1042 is out, what should I do?",
  asked_at: SNAPSHOT,
  kind: "answer",
  mode: "agent",
  tier: 3,
  headline:
    "Call reserve C-3310. Legal on both days of P-2291, INR 18,500, no delay.",
  text:
    "C-1042 operates P-2291, a two day A320 pairing out of BLR: DX412, DX413 and DX588 on 15 Sep, then DX589, DX590 and DX591 on 16 Sep. All six legs need a captain.\n\n" +
    "14 candidates were checked against all seven rules on every duty date. Three are legal.\n\n" +
    "C-3310 is the cleanest. BLR based and A320 rated, on call 06:00-18:00, reachable in 45 minutes, and clear on every rule across both days. Total cost INR 18,500 and no delay to any departure.\n\n" +
    "C-2210 is also legal but sits at DEL. Positioning costs INR 22,000 on top of the callout and puts DX412 back by 180 minutes, for a total of INR 41,200. Their flight duty period then lands 15 minutes inside the limit, which is thin.\n\n" +
    "C-3312 can be swapped across from P-2304, but that opens a new gap on P-2304 the next morning, so it ranks last at INR 26,900.\n\n" +
    "Four candidates were excluded. C-2087 would reach 61.33h of duty in the seven days to 16 Sep against a 60h limit. C-3305 is legal on 15 Sep and breaches RULE-FLT-03 on 16 Sep at 101.6h, which is why the check runs per day. C-2091 holds ATR72 only. C-4188 would have 3.17h of rest against a 12h minimum.",
  facts: REC_FACTS,
  traces: [
    {
      label: "Enumerated candidates",
      detail:
        "Reserves and rostered crew at BLR and DEL who could reach a 05:40 sign on. 14 evaluated.",
      fact_keys: ["cover.candidates_evaluated"],
    },
    {
      label: "Checked every candidate on every duty day",
      detail:
        "Seven rules times two duty days per candidate. Overall verdict is the worst day.",
      fact_keys: ["C-2087.duty_7d.projected", "C-3305.flight_28d.projected"],
    },
    {
      label: "Priced the legal options",
      detail:
        "Callout, positioning, overtime and delay lines from costs.json, each carrying its basis.",
      fact_keys: ["cover.C-3310.total", "cover.C-2210.total", "cover.C-3312.total"],
    },
    {
      label: "Ranked on coverage, then delay, then cost",
      detail:
        "Options that open a new gap sort below options that do not, whatever they cost.",
      fact_keys: [],
    },
  ],
  rule_traces: [],
  tables: [],
  impact: IMPACT,
  recommendation: RECOMMENDATION,
  citations: [
    { file: "reserve_pool.json", pointer: "date=2026-09-15,base=BLR" },
    { file: "crew.json", pointer: "14 records", note: "Candidates evaluated" },
    { file: "duty_clocks.json", pointer: "14 records" },
    { file: "costs.json", pointer: "callout, deadhead, overtime, penalty" },
    { file: "rules.json", pointer: "all 7 rules" },
  ],
  tool_calls: [
    envelope(
      "get_crew_detail",
      { crew_id: "C-1042" },
      26,
      [F.c1042, F.p2291],
      [
        {
          label: "Loaded crew record and roster",
          detail: "C-1042 is assigned P-2291 on 15 and 16 Sep.",
          fact_keys: ["C-1042.identity"],
        },
      ],
      [{ file: "crew.json", pointer: "C-1042" }],
      "Crew record with roster and clocks.",
    ),
    envelope(
      "get_pairing",
      { pairing_id: "P-2291" },
      33,
      [F.p2291, F.dx412, F.dx413, F.dx588, F.dx589, F.dx590, F.dx591, F.a320],
      [
        {
          label: "Expanded the pairing",
          detail: "Two duty days, six legs, A320 throughout.",
          fact_keys: ["P-2291.identity"],
        },
      ],
      [{ file: "rosters.json", pointer: "P-2291" }],
      "Pairing with both duty days, every leg, and the crew assigned.",
    ),
    envelope(
      "simulate_absence",
      { crew_id: "C-1042", from_date: "2026-09-15" },
      171,
      IMPACT_FACTS,
      [
        {
          label: "Modelled the absence",
          detail: "Three legs uncrewed on day one, 486 passengers exposed.",
          fact_keys: ["impact.passengers_affected"],
        },
      ],
      [{ file: "flights.json", pointer: "DX412, DX413, DX588" }],
      "ImpactReport.",
    ),
    envelope(
      "find_cover_options",
      { pairing_id: "P-2291", include_rejected: true, max_options: 5 },
      612,
      REC_FACTS,
      [
        {
          label: "Enumerated and checked candidates",
          detail: "14 evaluated, 3 legal, 4 excluded with the rule that excluded them.",
          fact_keys: ["cover.candidates_evaluated"],
        },
        {
          label: "Priced and ranked",
          detail:
            "Coverage first, then delay, then cost. Ranking basis returned with the result.",
          fact_keys: ["cover.C-3310.total"],
        },
      ],
      [
        { file: "costs.json", pointer: "callout, deadhead, overtime, penalty" },
        { file: "reserve_pool.json", pointer: "date=2026-09-15" },
      ],
      "Recommendation with 3 options and 4 rejected candidates.",
    ),
  ],
  confidence: "high",
  verification: VERIFIED(41),
  timings: {
    total_ms: 7940,
    plan_ms: 910,
    tools_ms: 842,
    verify_ms: 168,
    model_calls: 4,
    tool_calls: 4,
  },
  caveats: [
    "The backfill cost on option 3 comes from the rate card. No search was run for who would actually cover P-2304.",
    "Delay on option 2 assumes the positioning sector departs on schedule.",
    "Ranking is heuristic, not an optimisation. The basis is stated so it can be argued with.",
  ],
  follow_ups: [
    "Draft the callout message for C-3310.",
    "What happens to P-2304 if I take option 3?",
    "Show me the rule traces for C-3305 on 16 Sep.",
  ],
};

/* ------------------------------------------------------- 5  Abstention */

const ABSTAIN_FACTS: Fact[] = [
  F.blr,
  F.day1,
  dataset(
    "BLR.departures.2026-09-15",
    "Departures from BLR on 15 Sep",
    24,
    "count",
    "flights.json#origin=BLR,date=2026-09-15",
  ),
];

export const REPLY_ABSTAIN: Reply = {
  thread_id: "T-mock-5",
  turn_id: "U-mock-5",
  question: "What is the weather at BLR tomorrow morning?",
  asked_at: SNAPSHOT,
  kind: "abstain",
  mode: "agent",
  tier: null,
  headline: "The dataset carries no weather. I cannot answer this one.",
  text: "",
  facts: ABSTAIN_FACTS,
  traces: [
    {
      label: "Checked what the dataset covers",
      detail:
        "Eleven files: flights, crew, rosters, duty clocks, reserves, certifications, rules, costs, risk signals, scenarios and questions. None carries meteorological data.",
      fact_keys: [],
    },
  ],
  rule_traces: [],
  tables: [],
  abstention: {
    reason: "out_of_scope",
    message:
      "There is no weather data in the provided dataset. I can tell you what is scheduled and who is legal to fly it, but not whether the weather will allow it. Guessing here would be worse than saying so.",
    missing: [
      "Meteorological observations or forecasts for BLR",
      "Any weather or disruption feed in the eleven provided files",
    ],
    did_establish: [
      "BLR has 24 departures scheduled on 15 Sep",
      "Six crew are on the reserve register at BLR that day",
      "No station closure is recorded against BLR in the dataset",
    ],
    suggestions: [
      "Which flights depart BLR on 15 Sep?",
      "What is the crew impact if BLR closes 14:00 to 20:00?",
      "Who is on reserve at BLR tomorrow?",
    ],
  },
  citations: [{ file: "flights.json", pointer: "origin=BLR,date=2026-09-15" }],
  tool_calls: [
    envelope(
      "get_world_summary",
      {},
      12,
      [F.blr],
      [
        {
          label: "Read the dataset shape",
          detail:
            "147 flights, 150 crew, 39 pairings, 8 stations. No weather source.",
          fact_keys: [],
        },
      ],
      [{ file: "flights.json", pointer: "summary" }],
      "Dataset shape and snapshot time.",
    ),
  ],
  confidence: "high",
  verification: {
    status: "skipped",
    checked_atoms: 0,
    attested_atoms: 0,
    unattested: [],
    repair_attempts: 0,
    note: "A refusal states no figures, so there is nothing to attest.",
  },
  timings: {
    total_ms: 1120,
    plan_ms: 480,
    tools_ms: 12,
    verify_ms: 0,
    model_calls: 2,
    tool_calls: 1,
  },
  caveats: [],
  follow_ups: [],
};

/* ---------------------------------------------- 6  Verification failure */

const FAILED_FACTS: Fact[] = [
  F.blr,
  F.p2291,
  F.c3310,
  computed(
    "cover.C-3310.total",
    "Total cost, cheapest option for P-2291",
    18500,
    "inr",
    "crewops.ops.cost.total",
    "Reserve callout INR 12,000 plus duty premium INR 6,500 = INR 18,500.",
  ),
  computed(
    "cover.candidates_evaluated",
    "Candidates evaluated for P-2291",
    14,
    "count",
    "crewops.ops.candidates.enumerate",
    "16 reserves and rostered crew at BLR and DEL, less 2 already assigned, = 14 evaluated.",
  ),
];

export const REPLY_VERIFICATION_FAILED: Reply = {
  thread_id: "T-mock-6",
  turn_id: "U-mock-6",
  question:
    "Roughly what would it cost to cover every open pairing at BLR for the rest of the week?",
  asked_at: SNAPSHOT,
  kind: "abstain",
  mode: "agent",
  tier: 3,
  headline: "The draft answer failed the grounding check, so it was not shown.",
  text: "",
  facts: FAILED_FACTS,
  traces: [
    {
      label: "Costed the one pairing that is open",
      detail:
        "P-2291 has three legal options, the cheapest at INR 18,500 after 14 candidates were evaluated.",
      fact_keys: ["cover.C-3310.total", "cover.candidates_evaluated"],
    },
    {
      label: "Looked for an aggregate across pairings",
      detail:
        "No tool aggregates cover cost across multiple pairings, and no tool enumerates open pairings for a date range.",
      fact_keys: [],
    },
    {
      label: "Rejected the draft",
      detail:
        "Two atoms in the draft answer matched no fact from this turn. One repair pass was attempted and produced the same unattested total.",
      fact_keys: [],
    },
  ],
  rule_traces: [],
  tables: [],
  abstention: {
    reason: "verification_failed",
    message:
      "A total was drafted and could not be attested. Two figures in the draft, an aggregate cost and a count of open pairings, were produced by no tool on this turn, so the answer was rejected rather than shown. The word 'roughly' in the question is exactly the case where an approximation would be indistinguishable from a fabrication.",
    missing: [
      "A tool that aggregates cover cost across more than one pairing",
      "An enumeration of open pairings at BLR for 17 Sep to 20 Sep",
    ],
    did_establish: [
      "P-2291 has three legal cover options",
      "The cheapest of them is INR 18,500",
      "14 candidates were evaluated for that pairing",
    ],
    suggestions: [
      "Captain C-1042 is out, what should I do?",
      "Find me cover for P-2291 that does not delay DX412.",
      "Which pairings at BLR have no captain assigned on 17 Sep?",
    ],
  },
  citations: [
    { file: "costs.json", pointer: "callout, deadhead" },
    { file: "rosters.json", pointer: "P-2291" },
  ],
  tool_calls: [
    envelope(
      "get_world_summary",
      {},
      11,
      [F.blr],
      [
        {
          label: "Read the dataset shape",
          detail: "39 pairings across the week, 8 stations.",
          fact_keys: [],
        },
      ],
      [{ file: "flights.json", pointer: "summary" }],
      "Dataset shape.",
    ),
    envelope(
      "find_cover_options",
      { pairing_id: "P-2291", include_rejected: false },
      588,
      FAILED_FACTS,
      [
        {
          label: "Costed P-2291",
          detail: "Three legal options, cheapest INR 18,500.",
          fact_keys: ["cover.C-3310.total"],
        },
      ],
      [{ file: "costs.json", pointer: "callout, deadhead" }],
      "Recommendation for a single pairing.",
    ),
  ],
  confidence: "low",
  verification: {
    status: "rejected",
    checked_atoms: 9,
    attested_atoms: 7,
    unattested: [
      {
        atom: "2,40,000",
        kind: "currency",
        context:
          "covering the remaining open pairings would come to roughly INR 2,40,000 in callout and positioning",
      },
      {
        atom: "11",
        kind: "number",
        context: "spread across 11 open pairings between 17 and 20 Sep",
      },
    ],
    repair_attempts: 1,
    note: "One repair pass was run. The model produced the same figure with a hedge attached, which is not a repair, so the turn was refused.",
  },
  timings: {
    total_ms: 9260,
    plan_ms: 840,
    tools_ms: 599,
    verify_ms: 214,
    model_calls: 5,
    tool_calls: 2,
  },
  caveats: [
    "This is a known limit, not a transient failure. The tool surface has no cross pairing aggregation.",
  ],
  follow_ups: [],
};

/* ------------------------------------------------------------- registry */

export const REPLIES: Reply[] = [
  REPLY_RESERVES,
  REPLY_CLOCKS,
  REPLY_IMPACT,
  REPLY_RECOMMENDATION,
  REPLY_ABSTAIN,
  REPLY_VERIFICATION_FAILED,
];

/**
 * Picks the fixture that best matches a question, so the demo launcher and
 * free typing both land somewhere sensible. Keyword matching only: this is a
 * fixture router, not an intent classifier.
 */
export function pickReply(question: string): Reply {
  const q = question.toLowerCase();
  if (/weather|rain|fog|wind|temperature/.test(q)) return REPLY_ABSTAIN;
  if (/roughly|every open pairing|rest of the week|approximate/.test(q)) {
    return REPLY_VERIFICATION_FAILED;
  }
  if (/what should i do|cover|option|recommend|swap|deadhead|draft/.test(q)) {
    return REPLY_RECOMMENDATION;
  }
  if (/sick|uncrewed|impact|closed|breach|reassign|move c-/.test(q)) {
    return REPLY_IMPACT;
  }
  if (/duty hour|headroom|clock|flight hour|left this week/.test(q)) {
    return REPLY_CLOCKS;
  }
  return REPLY_RESERVES;
}
