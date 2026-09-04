/**
 * The 6 a.m. watchlist fixture.
 *
 * Deterministic on the API side: no model is involved in producing this, which
 * is why the brief page can run with the API key unset.
 */

import type { Watchlist } from "@/lib/contracts";
import { computed, dataset } from "@/mocks/facts";
import { SNAPSHOT } from "@/mocks/world";

export const WATCHLIST: Watchlist = {
  as_of: SNAPSHOT,
  for_date: "2026-09-15",
  headline:
    "One certification lapse inside the roster week, two crew within five hours of the duty limit, and one pairing with no captain.",
  scanned: {
    crew: 150,
    rosters: 150,
    pairings: 39,
    certifications: 450,
    flights: 147,
  },
  alerts: [
    {
      severity: "critical",
      title: "C-5417 rostered after recurrent training expires",
      detail:
        "Recurrent training expires 2026-09-17. C-5417 is rostered to operate on 2026-09-19, two days past validity. This is the one flagged roster exception in the dataset.",
      crew_id: "C-5417",
      rule_id: "RULE-CERT-06",
      due_date: "2026-09-17",
      suggested_question: "Is C-5417 legal to operate on 19 Sep?",
      facts: [
        dataset(
          "C-5417.recurrent_training.expires",
          "Recurrent training expires",
          "2026-09-17",
          "date",
          "certifications.json#C-5417",
        ),
        dataset(
          "C-5417.rostered",
          "Next rostered duty",
          "2026-09-19",
          "date",
          "rosters.json#C-5417",
        ),
      ],
    },
    {
      severity: "high",
      title: "P-2291 has no captain assigned",
      detail:
        "C-1042 is marked unavailable from 15 Sep. Six legs across two duty days are uncovered, and 486 passengers sit on the first day alone.",
      crew_id: "C-1042",
      pairing_id: "P-2291",
      due_date: "2026-09-15",
      suggested_question: "Captain C-1042 is out, what should I do?",
      facts: [
        dataset(
          "P-2291.identity",
          "Pairing",
          "P-2291",
          "pairing_id",
          "rosters.json#P-2291",
        ),
        computed(
          "impact.passengers_affected",
          "Passengers on the uncrewed legs",
          486,
          "count",
          "crewops.ops.impact.passengers",
          "180 on DX412 plus 174 on DX413 plus 132 on DX588 = 486.",
        ),
      ],
    },
    {
      severity: "high",
      title: "C-2087 within 5.08h of the 7 day duty limit",
      detail:
        "48.5h recorded in the seven days to 16 Sep. Any two day pairing added from here breaches RULE-DUTY-02.",
      crew_id: "C-2087",
      rule_id: "RULE-DUTY-02",
      due_date: "2026-09-16",
      suggested_question: "How many duty hours does C-2087 have left this week?",
      facts: [
        dataset(
          "C-2087.duty_7d.prior",
          "Duty in the 7 days to 16 Sep",
          48.5,
          "hours",
          "duty_clocks.json#C-2087",
        ),
        dataset(
          "RULE-DUTY-02.limit",
          "Rolling duty limit",
          60,
          "hours",
          "rules.json#RULE-DUTY-02",
        ),
      ],
    },
    {
      severity: "medium",
      title: "C-3305 within 3.6h of the 28 day flight hour limit",
      detail:
        "96.4h against a 100h limit after 15 Sep. Legal today, illegal tomorrow, which is the pattern a single day check misses.",
      crew_id: "C-3305",
      rule_id: "RULE-FLT-03",
      due_date: "2026-09-16",
      suggested_question: "Is C-3305 legal to operate the whole of P-2291?",
      facts: [
        computed(
          "C-3305.flight_28d.day1",
          "Projected 28 day flight hours, 15 Sep",
          96.4,
          "hours",
          "crewops.rules.flight.window",
          "91.20h prior + 5.20h block = 96.40h against a 100.00h limit.",
        ),
      ],
    },
    {
      severity: "medium",
      title: "Two medicals expire inside 30 days",
      detail:
        "C-3310 on 2026-12-14 and C-4402 on 2026-10-02. Neither affects this week, but C-4402 is inside the next roster publication.",
      rule_id: "RULE-CERT-06",
      due_date: "2026-10-02",
      suggested_question: "List crew whose licence expires in the next 30 days.",
      facts: [
        dataset(
          "C-4402.medical.expires",
          "Medical expires",
          "2026-10-02",
          "date",
          "certifications.json#C-4402",
        ),
      ],
    },
    {
      severity: "low",
      title: "Reserve cover at BLR thins after 16 Sep",
      detail:
        "Six reserves on 15 Sep, four on 16 Sep, two on 17 Sep. Using two captains this week leaves a single A320 captain on standby for the weekend.",
      due_date: "2026-09-17",
      suggested_question: "Who is on reserve at BLR on 17 Sep?",
      facts: [
        dataset(
          "reserves.BLR.2026-09-17",
          "Reserves at BLR on 17 Sep",
          2,
          "count",
          "reserve_pool.json#date=2026-09-17,base=BLR",
        ),
      ],
    },
  ],
};
