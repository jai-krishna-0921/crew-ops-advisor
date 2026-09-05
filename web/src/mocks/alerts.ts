/**
 * The proactive alert scan fixture.
 *
 * Deterministic on the API side: no model decides what appears here, which is
 * why the alert card renders with the API key unset.
 *
 * Copied from a real `scan_proactive_alerts` run against the shipped dataset,
 * not invented. Two things in it are easy to mistake for a broken fixture and
 * are neither:
 *
 * 1. `alerts` contains no duty or flight hour breach. The shipped roster does
 *    not have one in any 48 hour horizon. Breaches come from a change to the
 *    roster, and those are simulated elsewhere.
 * 2. `closest_approaches` is therefore the only place the limit rules appear.
 *    It is not padding. It is what makes "no breaches" a checked statement
 *    rather than an empty list, and the card must keep rendering it.
 */

import type { AlertScan } from "@/lib/contracts";
import { computed, dataset } from "@/mocks/facts";
import { SNAPSHOT } from "@/mocks/world";

export const ALERT_SCAN: AlertScan = {
  as_of: SNAPSHOT,
  horizon_hours: 48,
  horizon_end: "2026-09-16T18:00:00",
  cert_horizon_days: 30,
  headline:
    "6 to raise in the next 48 hours, 1 critical, across RULE-CERT-06. No limit breaches in the next 48 hours; the tightest margin is C-1694 at 19h02m under RULE-DUTY-02.",
  counts: { critical: 1, high: 0, medium: 5, low: 0 },
  scanned: {
    crew: 150,
    crew_in_horizon: 58,
    duties_in_horizon: 64,
    certifications: 600,
  },
  alerts: [
    {
      alert_id: "rule-cert-06:C-5417:recurrent_training",
      kind: "certification",
      severity: "critical",
      rule_id: "RULE-CERT-06",
      crew_id: "C-5417",
      crew_name: "S. Krishnan",
      rank: "Cabin Crew",
      base: "BLR",
      effective_date: "2026-09-17",
      title:
        "C-5417 is rostered on 2026-09-19 with recurrent_training expired since 2026-09-17",
      detail:
        "recurrent_training is valid to 2026-09-17, which is 3 days away. C-5417 is rostered on P-2213 on 2026-09-19. Every one of those duties breaches RULE-CERT-06, because the test is that the certificate is valid on the duty date.",
      projection: null,
      certification: {
        cert_type: "recurrent_training",
        valid_to: "2026-09-17",
        days_to_expiry: 3,
        first_invalid_duty: "2026-09-19",
        invalid_pairings: ["P-2213"],
      },
      downstream_flights: [
        {
          flight_no: "DX421",
          departure: "2026-09-19T03:00:00",
          origin: "BLR",
          destination: "CCU",
          seats: 162,
          duty_date: "2026-09-19",
          pairing_id: "P-2213",
        },
        {
          flight_no: "DX422",
          departure: "2026-09-19T06:15:00",
          origin: "CCU",
          destination: "BLR",
          seats: 162,
          duty_date: "2026-09-19",
          pairing_id: "P-2213",
        },
        {
          flight_no: "DX423",
          departure: "2026-09-19T09:30:00",
          origin: "BLR",
          destination: "HYD",
          seats: 162,
          duty_date: "2026-09-19",
          pairing_id: "P-2213",
        },
        {
          flight_no: "DX424",
          departure: "2026-09-19T12:15:00",
          origin: "HYD",
          destination: "BLR",
          seats: 162,
          duty_date: "2026-09-19",
          pairing_id: "P-2213",
        },
      ],
      seats_at_risk: 648,
      disruption_risk_score: null,
      risk_drivers: [],
      recommended_action:
        "Renew recurrent_training before 2026-09-17 or re-crew P-2213. This is a breach already on the roster, not a forecast.",
      suggested_question:
        "Can recurrent_training for C-5417 be renewed before 2026-09-17?",
      facts: [
        dataset(
          "rule-cert-06:C-5417:recurrent_training.valid_to",
          "recurrent_training expiry",
          "2026-09-17",
          "date",
          "certifications.json#C-5417/recurrent_training",
        ),
        computed(
          "rule-cert-06:C-5417:recurrent_training.days_to_expiry",
          "Days until expiry",
          3,
          "days",
          "crewops.ops.alerting",
          "2026-09-17 - 2026-09-14 = 3 days",
        ),
        computed(
          "rule-cert-06:C-5417:recurrent_training.seats_at_risk",
          "Seats exposed",
          648,
          "count",
          "crewops.ops.alerting",
          "162 + 162 + 162 + 162 = 648 seats",
        ),
      ],
      trace: [
        {
          label: "Read the expiry",
          detail:
            "certifications.json gives recurrent_training for C-5417 as valid to 2026-09-17",
          fact_keys: ["rule-cert-06:C-5417:recurrent_training.valid_to"],
        },
      ],
    },
    {
      alert_id: "rule-cert-06:C-2087:licence",
      kind: "certification",
      severity: "medium",
      rule_id: "RULE-CERT-06",
      crew_id: "C-2087",
      crew_name: "R. Iyer",
      rank: "Captain",
      base: "BLR",
      effective_date: "2026-09-18",
      title: "licence lapses for C-2087 on 2026-09-18",
      detail:
        "licence is valid to 2026-09-18, which is 4 days away. No duty in the schedule week falls after the expiry, so nothing on the current roster breaches RULE-CERT-06 yet.",
      projection: null,
      certification: {
        cert_type: "licence",
        valid_to: "2026-09-18",
        days_to_expiry: 4,
        first_invalid_duty: null,
        invalid_pairings: [],
      },
      downstream_flights: [],
      seats_at_risk: 0,
      disruption_risk_score: null,
      risk_drivers: [],
      recommended_action:
        "Book the renewal. C-2087 cannot be rostered after 2026-09-18 until it is done, which removes a Captain from the BLR pool.",
      suggested_question:
        "Can licence for C-2087 be renewed before 2026-09-18?",
      facts: [
        dataset(
          "rule-cert-06:C-2087:licence.valid_to",
          "licence expiry",
          "2026-09-18",
          "date",
          "certifications.json#C-2087/licence",
        ),
        computed(
          "rule-cert-06:C-2087:licence.days_to_expiry",
          "Days until expiry",
          4,
          "days",
          "crewops.ops.alerting",
          "2026-09-18 - 2026-09-14 = 4 days",
        ),
      ],
      trace: [],
    },
  ],
  closest_approaches: [
    {
      alert_id: "rule-duty-02:C-1694:2026-09-16",
      kind: "duty_limit",
      severity: "low",
      rule_id: "RULE-DUTY-02",
      crew_id: "C-1694",
      crew_name: "S. Menon",
      rank: "First Officer",
      base: "BLR",
      effective_date: "2026-09-16",
      title: "C-1694 projects to 40.96h of 60h duty hours on 2026-09-16",
      detail:
        "20.71h prior + 20.25h from duties in the next 48 hours = 40.96h against a 60.00h limit over 2026-09-10 to 2026-09-16, 19.04h spare.",
      projection: {
        rule_id: "RULE-DUTY-02",
        window_days: 7,
        window_start: "2026-09-10",
        window_end: "2026-09-16",
        limit_hours: 60,
        banked_hours: 20.71,
        committed_hours: 20.25,
        projected_hours: 40.96,
        margin_hours: 19.04,
        breaches: false,
        verdict: "pass",
        arithmetic:
          "20.71h prior + 20.25h from duties in the next 48 hours = 40.96h against a 60.00h limit over 2026-09-10 to 2026-09-16, 19.04h spare",
      },
      certification: null,
      downstream_flights: [],
      seats_at_risk: 0,
      disruption_risk_score: null,
      risk_drivers: [],
      recommended_action:
        "No breach on the roster as it stands. Treat 19h02m as the room available before any extension or reassignment is offered.",
      suggested_question:
        "How much duty headroom does C-1694 have on 2026-09-16?",
      facts: [
        computed(
          "rule-duty-02:C-1694:2026-09-16.projected",
          "Projected 7 day duty hours",
          40.96,
          "hours",
          "crewops.ops.alerting",
          "20.71 + 20.25 = 40.96h",
        ),
        computed(
          "rule-duty-02:C-1694:2026-09-16.margin",
          "Margin under RULE-DUTY-02",
          19.04,
          "hours",
          "crewops.ops.alerting",
          "60.00 - 40.96 = 19.04h",
        ),
      ],
      trace: [],
    },
    {
      alert_id: "rule-flt-03:C-1042:2026-09-16",
      kind: "flight_limit",
      severity: "low",
      rule_id: "RULE-FLT-03",
      crew_id: "C-1042",
      crew_name: "A. Nair",
      rank: "Captain",
      base: "BLR",
      effective_date: "2026-09-16",
      title: "C-1042 projects to 71.31h of 100h block hours on 2026-09-16",
      detail:
        "57.31h prior block + 14.00h from duties in the next 48 hours = 71.31h against a 100.00h limit over 2026-08-20 to 2026-09-16, 28.69h spare.",
      projection: {
        rule_id: "RULE-FLT-03",
        window_days: 28,
        window_start: "2026-08-20",
        window_end: "2026-09-16",
        limit_hours: 100,
        banked_hours: 57.31,
        committed_hours: 14,
        projected_hours: 71.31,
        margin_hours: 28.69,
        breaches: false,
        verdict: "pass",
        arithmetic:
          "57.31h prior block + 14.00h from duties in the next 48 hours = 71.31h against a 100.00h limit over 2026-08-20 to 2026-09-16, 28.69h spare",
      },
      certification: null,
      downstream_flights: [],
      seats_at_risk: 0,
      disruption_risk_score: null,
      risk_drivers: [],
      recommended_action:
        "No breach on the roster as it stands. Treat 28h41m as the room available before any extension or reassignment is offered.",
      suggested_question:
        "How much block headroom does C-1042 have on 2026-09-16?",
      facts: [
        computed(
          "rule-flt-03:C-1042:2026-09-16.projected",
          "Projected 28 day block hours",
          71.31,
          "hours",
          "crewops.ops.alerting",
          "57.31 + 14.00 = 71.31h",
        ),
        computed(
          "rule-flt-03:C-1042:2026-09-16.margin",
          "Margin under RULE-FLT-03",
          28.69,
          "hours",
          "crewops.ops.alerting",
          "100.00 - 71.31 = 28.69h",
        ),
      ],
      trace: [],
    },
  ],
};
