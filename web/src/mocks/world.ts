/**
 * Static reference data for the mock API: world summary, the seven rules as
 * shipped, the sample question bank and the thread list.
 *
 * Every value here mirrors the shipped dataset described in the root
 * CLAUDE.md: dCortex Air, hub BLR, week 2026-09-14 to 2026-09-20, snapshot
 * 2026-09-14T18:00:00, all times UTC, currency INR.
 */

import type {
  HealthResponse,
  RuleDefinition,
  SampleQuestion,
  ThreadSummary,
  WorldSummary,
} from "@/lib/contracts";

export const SNAPSHOT = "2026-09-14T18:00:00";

export const WORLD: WorldSummary = {
  snapshot: SNAPSHOT,
  base: "BLR",
  date_from: "2026-09-14",
  date_to: "2026-09-20",
  operator: "dCortex Air",
  currency: "INR",
  counts: {
    flights: 147,
    crew: 150,
    pairings: 39,
    reserves: 16,
    rules: 7,
    stations: 8,
    scenarios: 6,
    questions: 38,
  },
};

export const HEALTH: HealthResponse = {
  status: "ok",
  dataset_loaded: true,
  snapshot: SNAPSHOT,
  llm_configured: true,
  mode: "agent",
};

export const RULES: RuleDefinition[] = [
  {
    rule_id: "RULE-FDP-01",
    title: "Flight duty period",
    constraint: "Maximum flight duty period of 13 hours, reduced by sectors flown",
    limit: 13,
    unit: "hours",
    detail:
      "The 13 hour ceiling is cut by 30 minutes for every sector beyond the first. A four sector day is capped at 11 hours 30 minutes. The period runs from report time to on blocks at the final destination.",
  },
  {
    rule_id: "RULE-DUTY-02",
    title: "Rolling duty hours",
    constraint: "Maximum 60 duty hours in any 7 consecutive days",
    limit: 60,
    unit: "hours",
    detail:
      "Evaluated over the seven day window ending on the duty date, inclusive. The window sums the recorded daily history and the rostered duty length for each day it covers.",
  },
  {
    rule_id: "RULE-FLT-03",
    title: "Rolling flight hours",
    constraint: "Maximum 100 flight hours in any 28 consecutive days",
    limit: 100,
    unit: "hours",
    detail:
      "Block hours only. Positioning and deadhead sectors do not count toward this limit, though they do count toward RULE-DUTY-02.",
  },
  {
    rule_id: "RULE-REST-04",
    title: "Minimum rest",
    constraint: "Minimum 12 hours rest before commencing duty",
    limit: 12,
    unit: "hours",
    detail:
      "Measured from the end of the previous duty period to report time for the next. There is no reduced rest provision in this ruleset.",
  },
  {
    rule_id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    constraint: "Crew must hold a valid rating for the assigned aircraft type",
    limit: null,
    unit: "boolean",
    detail:
      "Checked against every leg of the assignment, not only the first. A crew member rated on one type in a mixed pairing fails the rule for the whole pairing.",
  },
  {
    rule_id: "RULE-CERT-06",
    title: "Certification validity",
    constraint: "All certifications must be valid on the duty date",
    limit: null,
    unit: "date",
    detail:
      "Licence, medical and recurrent training. Validity is checked against each duty date in the assignment, so a certificate lapsing mid pairing fails the later days only.",
  },
  {
    rule_id: "RULE-BASE-07",
    title: "Reserve callout base",
    constraint: "Reserve callout from base only, unless a deadhead cost is applied",
    limit: null,
    unit: "boolean",
    detail:
      "An out of base reserve is not illegal. It is legal with a positioning cost attached, which is why a deadhead option can rank second rather than being excluded.",
  },
];

/**
 * The sample question bank. The shipped dataset carries 38; this mock carries
 * a representative subset across the three tiers so the demo launcher has
 * something to fire without pretending to be the full file.
 */
export const QUESTIONS: SampleQuestion[] = [
  // Tier 1, lookup and retrieval
  {
    id: "Q-101",
    tier: 1,
    topic: "Reserves",
    question: "Who is on reserve at BLR tomorrow?",
  },
  {
    id: "Q-102",
    tier: 1,
    topic: "Duty clocks",
    question: "How many duty hours does C-1042 have left this week?",
  },
  {
    id: "Q-103",
    tier: 1,
    topic: "Schedule",
    question: "Which flights depart DEL this afternoon?",
  },
  {
    id: "Q-104",
    tier: 1,
    topic: "Certifications",
    question: "List crew whose licence expires in the next 30 days.",
  },
  {
    id: "Q-105",
    tier: 1,
    topic: "Pairings",
    question: "What does pairing P-2291 cover?",
  },
  {
    id: "Q-106",
    tier: 1,
    topic: "Crew",
    question: "Which A320 rated captains are based at BLR?",
  },
  {
    id: "Q-107",
    tier: 1,
    topic: "Rulebook",
    question: "What does RULE-DUTY-02 actually say?",
  },
  // Tier 2, consequence and simulation
  {
    id: "Q-201",
    tier: 2,
    topic: "Sick call",
    question:
      "Captain C-1042 just called in sick for tomorrow, which flights are now uncrewed?",
  },
  {
    id: "Q-202",
    tier: 2,
    topic: "Reassignment",
    question: "If I move C-2087 onto DX412, does anyone breach a duty limit?",
  },
  {
    id: "Q-203",
    tier: 2,
    topic: "Station closure",
    question: "Station BLR is closed 14:00 to 20:00, what is the crew impact?",
  },
  {
    id: "Q-204",
    tier: 2,
    topic: "Legality",
    question: "Is C-3305 legal to operate the whole of P-2291?",
  },
  {
    id: "Q-205",
    tier: 2,
    topic: "Legality",
    question: "Can C-2091 cover DX412 on 15 Sep?",
  },
  // Tier 3, recommendation and action
  {
    id: "Q-301",
    tier: 3,
    topic: "Cover options",
    question: "Captain C-1042 is out, what should I do?",
  },
  {
    id: "Q-302",
    tier: 3,
    topic: "Cover options",
    question: "Find me cover for P-2291 that does not delay DX412.",
  },
  {
    id: "Q-303",
    tier: 3,
    topic: "Notification",
    question: "Draft the callout message for the reserve you recommended.",
  },
  // Deliberate limits, kept in the bank because a refusal is a result
  {
    id: "Q-401",
    tier: 1,
    topic: "Known limit",
    question: "What is the weather at BLR tomorrow morning?",
  },
  {
    id: "Q-402",
    tier: 3,
    topic: "Known limit",
    question:
      "Roughly what would it cost to cover every open pairing at BLR for the rest of the week?",
  },
];

export const THREADS: ThreadSummary[] = [
  {
    thread_id: "T-9f21",
    title: "C-1042 sick call, 15 Sep",
    titled_by: "auto",
    created_at: "2026-09-14T18:12:00",
    updated_at: "2026-09-14T18:19:00",
    turn_count: 4,
    tier: 3,
  },
  {
    thread_id: "T-7c04",
    title: "BLR reserve availability",
    titled_by: "auto",
    created_at: "2026-09-14T17:40:00",
    updated_at: "2026-09-14T17:44:00",
    turn_count: 2,
    tier: 1,
  },
  {
    thread_id: "T-5b88",
    title: "C-5417 recurrent training lapse",
    titled_by: "user",
    created_at: "2026-09-14T09:02:00",
    updated_at: "2026-09-14T09:11:00",
    turn_count: 3,
    tier: 2,
  },
];
