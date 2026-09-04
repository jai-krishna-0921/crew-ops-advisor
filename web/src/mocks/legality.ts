/**
 * Legality fixtures for pairing P-2291.
 *
 * P-2291 is a two day A320 pairing out of BLR:
 *   15 Sep  DX412 BLR-DEL, DX413 DEL-BLR, DX588 BLR-HYD
 *   16 Sep  DX589 HYD-BLR, DX590 BLR-COK, DX591 COK-BLR
 *
 * Five candidates are modelled, chosen because between them they exercise
 * every verdict the UI has to render:
 *
 *   C-3310  clean on both days, the recommended reserve
 *   C-2210  clean on both days but out of base, so BASE-07 costs a deadhead
 *   C-2087  DUTY-02 breach on day 2, 61.33h against a 60h limit
 *   C-3305  legal on day 1, FLT-03 breach on day 2, the "every day" trap
 *   C-2091  QUAL-05 breach, ATR rated only
 *   C-4188  REST-04 breach, 3h10m rest against a 12h minimum
 */

import type { DayLegality, LegalityReport, RuleTrace } from "@/lib/contracts";
import { computed, dataset } from "@/mocks/facts";

const DAY_1 = "2026-09-15";
const DAY_2 = "2026-09-16";

const ALL_SEVEN = [
  "RULE-FDP-01",
  "RULE-DUTY-02",
  "RULE-FLT-03",
  "RULE-REST-04",
  "RULE-QUAL-05",
  "RULE-CERT-06",
  "RULE-BASE-07",
] as const;

/* ------------------------------------------------------------- C-3310 --- */

const C3310_DAY_1: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 11.5,
    observed: 8.92,
    unit: "hours",
    margin: 2.58,
    margin_human: "2h35m spare",
    arithmetic:
      "13.00h base less 1.50h for 3 sectors = 11.50h limit. Duty 05:40 to 14:35 = 8.92h, 2.58h spare.",
    inputs: [
      dataset(
        "P-2291.day1.sectors",
        "Sectors on 15 Sep",
        3,
        "count",
        "rosters.json#P-2291/day1",
      ),
      computed(
        "C-3310.fdp.2026-09-15",
        "Flight duty period, 15 Sep",
        8.92,
        "hours",
        "crewops.rules.fdp.period",
        "Report 05:40, on blocks 14:35, 8h55m = 8.92h.",
      ),
    ],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 60,
    observed: 34.92,
    unit: "hours",
    margin: 25.08,
    margin_human: "25h05m spare",
    arithmetic:
      "26.00h prior in the 7 days to 15 Sep plus 8.92h from P-2291 day 1 = 34.92h against a 60.00h limit, 25.08h spare.",
    inputs: [
      dataset(
        "C-3310.duty_7d.prior",
        "Duty in the 7 days to 15 Sep",
        26.0,
        "hours",
        "duty_clocks.json#C-3310",
      ),
      computed(
        "C-3310.duty_7d.projected",
        "Projected 7 day duty",
        34.92,
        "hours",
        "crewops.rules.duty.window",
        "26.00h prior + 8.92h added = 34.92h against a 60.00h limit.",
      ),
    ],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 100,
    observed: 61.4,
    unit: "hours",
    margin: 38.6,
    margin_human: "38h36m spare",
    arithmetic:
      "56.20h prior in the 28 days to 15 Sep plus 5.20h block on P-2291 day 1 = 61.40h against a 100.00h limit, 38.60h spare.",
    inputs: [
      dataset(
        "C-3310.flight_28d.prior",
        "Flight hours in the 28 days to 15 Sep",
        56.2,
        "hours",
        "duty_clocks.json#C-3310",
      ),
    ],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 12,
    observed: 38.67,
    unit: "hours",
    margin: 26.67,
    margin_human: "26h40m spare",
    arithmetic:
      "Last duty ended 2026-09-13T15:00. Duty commences 2026-09-15T05:40. 38.67h rest against a 12.00h minimum, 26.67h spare.",
    inputs: [
      dataset(
        "C-3310.last_duty_end",
        "Last duty ended",
        "2026-09-13T15:00:00",
        "datetime",
        "duty_clocks.json#C-3310",
      ),
    ],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic:
      "C-3310 holds A320. Every leg of P-2291 operates A320. Rating held on all 6 legs.",
    inputs: [
      dataset(
        "C-3310.ratings",
        "Type ratings held",
        "A320",
        "aircraft_type",
        "crew.json#C-3310",
      ),
    ],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "date",
    arithmetic:
      "Licence valid to 2027-03-31, medical to 2026-12-14, recurrent training to 2027-01-22. All valid on 2026-09-15.",
    inputs: [
      dataset(
        "C-3310.medical.expires",
        "Medical expires",
        "2026-12-14",
        "date",
        "certifications.json#C-3310",
      ),
    ],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic:
      "C-3310 is based at BLR. P-2291 signs on at BLR. Callout is from base, so no deadhead cost applies.",
    inputs: [
      dataset("C-3310.base", "Base", "BLR", "station", "crew.json#C-3310"),
    ],
  },
];

const C3310_DAY_2: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 11.5,
    observed: 7.42,
    unit: "hours",
    margin: 4.08,
    margin_human: "4h05m spare",
    arithmetic:
      "13.00h base less 1.50h for 3 sectors = 11.50h limit. Duty 06:10 to 13:35 = 7.42h, 4.08h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 60,
    observed: 42.34,
    unit: "hours",
    margin: 17.66,
    margin_human: "17h40m spare",
    arithmetic:
      "34.92h in the 7 days to 15 Sep plus 7.42h from P-2291 day 2 = 42.34h against a 60.00h limit, 17.66h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 100,
    observed: 66.3,
    unit: "hours",
    margin: 33.7,
    margin_human: "33h42m spare",
    arithmetic:
      "61.40h to 15 Sep plus 4.90h block on P-2291 day 2 = 66.30h against a 100.00h limit, 33.70h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 12,
    observed: 15.58,
    unit: "hours",
    margin: 3.58,
    margin_human: "3h35m spare",
    arithmetic:
      "Day 1 duty ended 2026-09-15T14:35. Day 2 duty commences 2026-09-16T06:10. 15.58h rest against a 12.00h minimum, 3.58h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_2,
    unit: "boolean",
    arithmetic: "C-3310 holds A320. All 3 legs on 16 Sep operate A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_2,
    unit: "date",
    arithmetic:
      "Licence, medical and recurrent training all valid on 2026-09-16.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "not_applicable",
    duty_date: DAY_2,
    unit: "boolean",
    arithmetic:
      "Callout base is evaluated at sign on. Day 2 continues an existing duty pattern, so the rule does not apply.",
    inputs: [],
    note: "Not applicable is not a pass. It means the rule had nothing to bite on.",
  },
];

/* ------------------------------------------------------------- C-2210 --- */

const C2210_DAY_1: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 11.0,
    observed: 10.75,
    unit: "hours",
    margin: 0.25,
    margin_human: "15m spare",
    arithmetic:
      "13.00h base less 2.00h for 4 sectors, including the positioning sector = 11.00h limit. Duty 05:55 to 16:40 = 10.75h, 0.25h spare.",
    inputs: [
      computed(
        "C-2210.fdp.2026-09-15",
        "Flight duty period, 15 Sep",
        10.75,
        "hours",
        "crewops.rules.fdp.period",
        "Report 05:55 at DEL, on blocks 16:40 at HYD, 10h45m = 10.75h.",
      ),
    ],
    note: "The thinnest margin of any legal option. A 20 minute slip puts this over.",
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 60,
    observed: 41.25,
    unit: "hours",
    margin: 18.75,
    margin_human: "18h45m spare",
    arithmetic:
      "30.50h prior in the 7 days to 15 Sep plus 10.75h including positioning = 41.25h against a 60.00h limit, 18.75h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 100,
    observed: 58.9,
    unit: "hours",
    margin: 41.1,
    margin_human: "41h06m spare",
    arithmetic:
      "53.70h prior in the 28 days to 15 Sep plus 5.20h block = 58.90h against a 100.00h limit. The positioning sector is duty, not block, so it does not count here.",
    inputs: [],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 12,
    observed: 19.42,
    unit: "hours",
    margin: 7.42,
    margin_human: "7h25m spare",
    arithmetic:
      "Last duty ended 2026-09-14T10:30. Duty commences 2026-09-15T05:55. 19.42h rest against a 12.00h minimum, 7.42h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-2210 holds A320. Every leg of P-2291 operates A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "date",
    arithmetic: "All certifications valid on 2026-09-15.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic:
      "C-2210 is based at DEL, P-2291 signs on at BLR. Out of base, so the rule is satisfied only with a deadhead cost applied. INR 22,000 positioning is included in the costing.",
    inputs: [
      dataset("C-2210.base", "Base", "DEL", "station", "crew.json#C-2210"),
    ],
    note: "Legal with a cost attached, which is why this ranks rather than being excluded.",
  },
];

const C2210_DAY_2: RuleTrace[] = C3310_DAY_2.map((t) => ({
  ...t,
  arithmetic: t.arithmetic.replace("C-3310", "C-2210"),
  inputs: [],
}));

/* ------------------------------------------------------------- C-2087 --- */

const C2087_DAY_1: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 11.5,
    observed: 8.92,
    unit: "hours",
    margin: 2.58,
    margin_human: "2h35m spare",
    arithmetic:
      "13.00h base less 1.50h for 3 sectors = 11.50h limit. Duty 05:40 to 14:35 = 8.92h, 2.58h spare.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 60,
    observed: 54.92,
    unit: "hours",
    margin: 5.08,
    margin_human: "5h05m spare",
    arithmetic:
      "46.00h prior in the 7 days to 15 Sep plus 8.92h from P-2291 day 1 = 54.92h against a 60.00h limit, 5.08h spare.",
    inputs: [],
    note: "Legal today. The window moves with the date, and day 2 is where it fails.",
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 100,
    observed: 74.6,
    unit: "hours",
    margin: 25.4,
    margin_human: "25h24m spare",
    arithmetic:
      "69.40h prior in the 28 days to 15 Sep plus 5.20h block = 74.60h against a 100.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 12,
    observed: 14.17,
    unit: "hours",
    margin: 2.17,
    margin_human: "2h10m spare",
    arithmetic:
      "Last duty ended 2026-09-14T15:30. Duty commences 2026-09-15T05:40. 14.17h rest against a 12.00h minimum.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-2087 holds A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "date",
    arithmetic: "All certifications valid on 2026-09-15.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-2087 is based at BLR. P-2291 signs on at BLR.",
    inputs: [],
  },
];

const C2087_DAY_2: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 11.5,
    observed: 7.42,
    unit: "hours",
    margin: 4.08,
    margin_human: "4h05m spare",
    arithmetic:
      "13.00h base less 1.50h for 3 sectors = 11.50h limit. Duty 06:10 to 13:35 = 7.42h.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "breach",
    duty_date: DAY_2,
    limit: 60,
    observed: 61.33,
    unit: "hours",
    margin: -1.33,
    margin_human: "1h20m over the limit",
    arithmetic:
      "48.50h prior in the 7 days to 16 Sep plus 12.83h from P-2291 = 61.33h against a 60.00h limit, over by 1.33h.",
    inputs: [
      dataset(
        "C-2087.duty_7d.prior",
        "Duty in the 7 days to 16 Sep",
        48.5,
        "hours",
        "duty_clocks.json#C-2087",
      ),
      computed(
        "C-2087.duty_7d.added",
        "Duty added by P-2291",
        12.83,
        "hours",
        "crewops.rules.duty.assignment",
        "8.92h on 15 Sep plus 7.42h on 16 Sep, less 3.51h already inside the window = 12.83h.",
      ),
      computed(
        "C-2087.duty_7d.projected",
        "Projected 7 day duty",
        61.33,
        "hours",
        "crewops.rules.duty.window",
        "48.50h prior + 12.83h added = 61.33h against a 60.00h limit.",
      ),
      dataset(
        "RULE-DUTY-02.limit",
        "Rolling duty limit",
        60.0,
        "hours",
        "rules.json#RULE-DUTY-02",
      ),
    ],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 100,
    observed: 79.5,
    unit: "hours",
    margin: 20.5,
    margin_human: "20h30m spare",
    arithmetic:
      "74.60h to 15 Sep plus 4.90h block on day 2 = 79.50h against a 100.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 12,
    observed: 15.58,
    unit: "hours",
    margin: 3.58,
    margin_human: "3h35m spare",
    arithmetic:
      "Day 1 duty ended 2026-09-15T14:35. Day 2 commences 2026-09-16T06:10. 15.58h rest.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_2,
    unit: "boolean",
    arithmetic: "C-2087 holds A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_2,
    unit: "date",
    arithmetic: "All certifications valid on 2026-09-16.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "not_applicable",
    duty_date: DAY_2,
    unit: "boolean",
    arithmetic: "Sign on was on day 1. The rule does not apply to day 2.",
    inputs: [],
  },
];

/* ------------------------------------------------------------- C-3305 --- */

const C3305_DAY_1: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 11.5,
    observed: 8.92,
    unit: "hours",
    margin: 2.58,
    margin_human: "2h35m spare",
    arithmetic:
      "13.00h base less 1.50h for 3 sectors = 11.50h limit. Duty 05:40 to 14:35 = 8.92h.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 60,
    observed: 47.42,
    unit: "hours",
    margin: 12.58,
    margin_human: "12h35m spare",
    arithmetic:
      "38.50h prior in the 7 days to 15 Sep plus 8.92h = 47.42h against a 60.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 100,
    observed: 96.4,
    unit: "hours",
    margin: 3.6,
    margin_human: "3h36m spare",
    arithmetic:
      "91.20h prior in the 28 days to 15 Sep plus 5.20h block on day 1 = 96.40h against a 100.00h limit, 3.60h spare.",
    inputs: [
      computed(
        "C-3305.flight_28d.day1",
        "Projected 28 day flight hours, 15 Sep",
        96.4,
        "hours",
        "crewops.rules.flight.window",
        "91.20h prior + 5.20h block = 96.40h against a 100.00h limit.",
      ),
    ],
    note: "Legal, but with under four hours of headroom going into day 2.",
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 12,
    observed: 20.83,
    unit: "hours",
    margin: 8.83,
    margin_human: "8h50m spare",
    arithmetic:
      "Last duty ended 2026-09-14T08:50. Duty commences 2026-09-15T05:40. 20.83h rest.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-3305 holds A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "date",
    arithmetic: "All certifications valid on 2026-09-15.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-3305 is based at BLR. P-2291 signs on at BLR.",
    inputs: [],
  },
];

const C3305_DAY_2: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 11.5,
    observed: 7.42,
    unit: "hours",
    margin: 4.08,
    margin_human: "4h05m spare",
    arithmetic: "11.50h limit. Duty 06:10 to 13:35 = 7.42h.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 60,
    observed: 54.84,
    unit: "hours",
    margin: 5.16,
    margin_human: "5h10m spare",
    arithmetic:
      "47.42h to 15 Sep plus 7.42h on 16 Sep = 54.84h against a 60.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "breach",
    duty_date: DAY_2,
    limit: 100,
    observed: 101.6,
    unit: "hours",
    margin: -1.6,
    margin_human: "1h36m over the limit",
    arithmetic:
      "96.40h in the 28 days to 15 Sep plus 5.20h block on P-2291 day 2 = 101.60h against a 100.00h limit, over by 1.60h.",
    inputs: [
      computed(
        "C-3305.flight_28d.projected",
        "Projected 28 day flight hours, 16 Sep",
        101.6,
        "hours",
        "crewops.rules.flight.window",
        "96.40h to 15 Sep + 5.20h block on 16 Sep = 101.60h against a 100.00h limit.",
      ),
      dataset(
        "RULE-FLT-03.limit",
        "Rolling flight hour limit",
        100.0,
        "hours",
        "rules.json#RULE-FLT-03",
      ),
    ],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_2,
    limit: 12,
    observed: 15.58,
    unit: "hours",
    margin: 3.58,
    margin_human: "3h35m spare",
    arithmetic: "15.58h rest against a 12.00h minimum.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_2,
    unit: "boolean",
    arithmetic: "C-3305 holds A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_2,
    unit: "date",
    arithmetic: "All certifications valid on 2026-09-16.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "not_applicable",
    duty_date: DAY_2,
    unit: "boolean",
    arithmetic: "Sign on was on day 1. The rule does not apply to day 2.",
    inputs: [],
  },
];

/* ------------------------------------------------------------- C-2091 --- */

const C2091_DAY_1: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 11.5,
    observed: 8.92,
    unit: "hours",
    margin: 2.58,
    margin_human: "2h35m spare",
    arithmetic: "11.50h limit. Duty 05:40 to 14:35 = 8.92h.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 60,
    observed: 31.42,
    unit: "hours",
    margin: 28.58,
    margin_human: "28h35m spare",
    arithmetic:
      "22.50h prior in the 7 days to 15 Sep plus 8.92h = 31.42h against a 60.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 100,
    observed: 48.3,
    unit: "hours",
    margin: 51.7,
    margin_human: "51h42m spare",
    arithmetic: "43.10h prior plus 5.20h block = 48.30h against a 100.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 12,
    observed: 44.5,
    unit: "hours",
    margin: 32.5,
    margin_human: "32h30m spare",
    arithmetic: "44.50h rest against a 12.00h minimum.",
    inputs: [],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "breach",
    duty_date: DAY_1,
    unit: "boolean",
    margin: null,
    margin_human: "no valid rating",
    arithmetic:
      "C-2091 holds ATR72 only. P-2291 operates A320 on all 6 legs. No valid rating for the assigned aircraft type.",
    inputs: [
      dataset(
        "C-2091.ratings",
        "Type ratings held",
        "ATR72",
        "aircraft_type",
        "crew.json#C-2091",
      ),
      dataset(
        "P-2291.aircraft_type",
        "Aircraft type on P-2291",
        "A320",
        "aircraft_type",
        "rosters.json#P-2291",
      ),
    ],
    note: "A rating breach cannot be priced away. There is no cost that makes this legal.",
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "date",
    arithmetic: "All certifications valid on 2026-09-15.",
    inputs: [],
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-2091 is based at BLR.",
    inputs: [],
  },
];

/* ------------------------------------------------------------- C-4188 --- */

const C4188_DAY_1: RuleTrace[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 11.5,
    observed: 8.92,
    unit: "hours",
    margin: 2.58,
    margin_human: "2h35m spare",
    arithmetic: "11.50h limit. Duty 05:40 to 14:35 = 8.92h.",
    inputs: [],
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 60,
    observed: 44.92,
    unit: "hours",
    margin: 15.08,
    margin_human: "15h05m spare",
    arithmetic: "36.00h prior plus 8.92h = 44.92h against a 60.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    verdict: "pass",
    duty_date: DAY_1,
    limit: 100,
    observed: 71.8,
    unit: "hours",
    margin: 28.2,
    margin_human: "28h12m spare",
    arithmetic: "66.60h prior plus 5.20h block = 71.80h against a 100.00h limit.",
    inputs: [],
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    verdict: "breach",
    duty_date: DAY_1,
    limit: 12,
    observed: 3.17,
    unit: "hours",
    margin: -8.83,
    margin_human: "8h50m short of the minimum",
    arithmetic:
      "Last duty ended 2026-09-15T02:30. Duty would commence 2026-09-15T05:40. 3.17h rest against a 12.00h minimum, short by 8.83h.",
    inputs: [
      dataset(
        "C-4188.last_duty_end",
        "Last duty ended",
        "2026-09-15T02:30:00",
        "datetime",
        "duty_clocks.json#C-4188",
      ),
      computed(
        "C-4188.rest.available",
        "Rest before P-2291 sign on",
        3.17,
        "hours",
        "crewops.rules.rest.before",
        "02:30 to 05:40 on 2026-09-15 is 3h10m = 3.17h against a 12.00h minimum.",
      ),
    ],
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-4188 holds A320.",
    inputs: [],
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    verdict: "insufficient_data",
    duty_date: DAY_1,
    unit: "date",
    arithmetic:
      "Licence valid to 2027-06-30 and medical to 2026-11-08. No recurrent training record is present for C-4188, so validity on 2026-09-15 cannot be established.",
    inputs: [
      dataset(
        "C-4188.recurrent_training",
        "Recurrent training record",
        null,
        "date",
        "certifications.json#C-4188",
      ),
    ],
    note: "Insufficient data is not a pass. The candidate is excluded on RULE-REST-04 regardless, but this gap would have to be closed before anyone could clear them.",
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    verdict: "pass",
    duty_date: DAY_1,
    unit: "boolean",
    arithmetic: "C-4188 is based at BLR.",
    inputs: [],
  },
];

/* ------------------------------------------------------------- reports --- */

function report(
  crew_id: string,
  overall: LegalityReport["overall"],
  days: DayLegality[],
): LegalityReport {
  return {
    crew_id,
    assignment_ref: "P-2291",
    assignment_kind: "pairing",
    overall,
    per_day: days,
    rules_checked: [...ALL_SEVEN],
  };
}

function day(duty_date: string, traces: RuleTrace[]): DayLegality {
  const verdict = traces.some((t) => t.verdict === "breach")
    ? "breach"
    : traces.some((t) => t.verdict === "insufficient_data")
      ? "insufficient_data"
      : "pass";
  return { duty_date, verdict, traces };
}

export const LEGALITY_C3310 = report("C-3310", "pass", [
  day(DAY_1, C3310_DAY_1),
  day(DAY_2, C3310_DAY_2),
]);

export const LEGALITY_C2210 = report("C-2210", "pass", [
  day(DAY_1, C2210_DAY_1),
  day(DAY_2, C2210_DAY_2),
]);

export const LEGALITY_C2087 = report("C-2087", "breach", [
  day(DAY_1, C2087_DAY_1),
  day(DAY_2, C2087_DAY_2),
]);

export const LEGALITY_C3305 = report("C-3305", "breach", [
  day(DAY_1, C3305_DAY_1),
  day(DAY_2, C3305_DAY_2),
]);

export const LEGALITY_C2091 = report("C-2091", "breach", [
  day(DAY_1, C2091_DAY_1),
]);

export const LEGALITY_C4188 = report("C-4188", "breach", [
  day(DAY_1, C4188_DAY_1),
]);

/** A swap candidate: legal, but it opens a gap somewhere else. */
export const LEGALITY_C3312 = report("C-3312", "pass", [
  day(
    DAY_1,
    C3310_DAY_1.map((t) => ({
      ...t,
      arithmetic: t.arithmetic.replace("C-3310", "C-3312"),
      inputs: [],
    })),
  ),
  day(
    DAY_2,
    C3310_DAY_2.map((t) => ({
      ...t,
      arithmetic: t.arithmetic.replace("C-3310", "C-3312"),
      inputs: [],
    })),
  ),
]);

export const LEGALITY_BY_CREW: Record<string, LegalityReport> = {
  "C-3310": LEGALITY_C3310,
  "C-2210": LEGALITY_C2210,
  "C-3312": LEGALITY_C3312,
  "C-2087": LEGALITY_C2087,
  "C-3305": LEGALITY_C3305,
  "C-2091": LEGALITY_C2091,
  "C-4188": LEGALITY_C4188,
};
