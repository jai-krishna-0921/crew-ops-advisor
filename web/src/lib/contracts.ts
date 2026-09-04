/**
 * TypeScript mirror of `api/src/crewops/contracts/`.
 *
 * Hand written, not generated. Kept in sync by review. If a shape here
 * disagrees with the Python, the Python wins and this file is the bug.
 *
 * Sources mirrored:
 *   evidence.py  -> Fact, TraceStep, Citation, ToolEnvelope, Table, Abstention,
 *                   VerificationReport, Timings
 *   rules.py     -> RuleId, Verdict, RuleTrace, DayLegality, LegalityReport
 *   ops.py       -> FlightRef, DownstreamRisk, ImpactReport, CostLine,
 *                   CostBreakdown, CoverOption, Recommendation, Alert, Watchlist
 *   reply.py     -> Reply, ReplyKind, AnswerMode, Tier
 *   stream.py    -> EventType and the twelve stream events, ChatRequest
 *   tools.py     -> TOOL_NAMES, RETRIEVAL_ONLY
 *
 * Datetimes arrive as ISO 8601 strings over the wire. Dates arrive as
 * YYYY-MM-DD. Neither is parsed into a Date anywhere in the data layer:
 * formatting happens at the edge, in `lib/format.ts`.
 */

// ---------------------------------------------------------------- evidence

export type FactUnit =
  | "hours"
  | "minutes"
  | "days"
  | "inr"
  | "count"
  | "date"
  | "datetime"
  | "crew_id"
  | "flight_no"
  | "pairing_id"
  | "rule_id"
  | "station"
  | "aircraft_type"
  | "rank"
  | "text"
  | "boolean"
  | "percent";

export type FactValue = string | number | boolean | null;

export type Provenance = "dataset" | "computed" | "assumed";

export interface Fact {
  key: string;
  label: string;
  value: FactValue;
  unit: FactUnit;
  provenance: Provenance;
  source: string;
  /** Mandatory when provenance is "computed": the arithmetic, written out. */
  derivation?: string | null;
}

export interface TraceStep {
  label: string;
  detail: string;
  fact_keys: string[];
}

export interface Citation {
  file: string;
  pointer: string;
  note?: string | null;
}

export interface ToolEnvelope {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  payload: unknown;
  facts: Fact[];
  trace: TraceStep[];
  citations: Citation[];
  latency_ms: number;
  error?: string | null;
  truncated: boolean;
}

export interface Table {
  title: string;
  columns: string[];
  rows: FactValue[][];
  row_ids: string[];
  caption?: string | null;
}

export type Confidence = "high" | "medium" | "low";

export type AbstentionReason =
  | "out_of_scope"
  // Not a question at all: "hey", "thanks". Separate from out_of_scope
  // because the right response is a capability statement, not a refusal.
  | "greeting"
  | "not_in_dataset"
  | "ambiguous_referent"
  | "underspecified"
  | "requires_unmodelled_rule"
  | "conflicting_data"
  | "verification_failed"
  | "tool_error";

export interface Abstention {
  reason: AbstentionReason;
  message: string;
  missing: string[];
  did_establish: string[];
  suggestions: string[];
}

export type UnattestedKind =
  | "number"
  | "identifier"
  | "date"
  | "currency"
  | "rule_id"
  | "station";

export interface UnattestedAtom {
  atom: string;
  kind: UnattestedKind;
  context: string;
}

export type VerificationStatus = "verified" | "repaired" | "rejected" | "skipped";

export interface VerificationReport {
  status: VerificationStatus;
  checked_atoms: number;
  attested_atoms: number;
  unattested: UnattestedAtom[];
  repair_attempts: number;
  note?: string | null;
}

export interface Timings {
  total_ms: number;
  plan_ms: number;
  tools_ms: number;
  verify_ms: number;
  model_calls: number;
  tool_calls: number;
}

// ------------------------------------------------------------------- rules

export type RuleId =
  | "RULE-FDP-01"
  | "RULE-DUTY-02"
  | "RULE-FLT-03"
  | "RULE-REST-04"
  | "RULE-QUAL-05"
  | "RULE-CERT-06"
  | "RULE-BASE-07";

export const ALL_RULE_IDS: readonly RuleId[] = [
  "RULE-FDP-01",
  "RULE-DUTY-02",
  "RULE-FLT-03",
  "RULE-REST-04",
  "RULE-QUAL-05",
  "RULE-CERT-06",
  "RULE-BASE-07",
];

export type Verdict = "pass" | "breach" | "not_applicable" | "insufficient_data";

export type RuleUnit = "hours" | "minutes" | "count" | "boolean" | "date";

export interface RuleTrace {
  rule_id: RuleId;
  title: string;
  verdict: Verdict;
  duty_date?: string | null;
  limit?: number | null;
  observed?: number | null;
  unit?: RuleUnit | null;
  /** Signed headroom. Positive is room to spare, negative is a breach. */
  margin?: number | null;
  margin_human?: string | null;
  arithmetic: string;
  inputs: Fact[];
  note?: string | null;
}

export interface DayLegality {
  duty_date: string;
  verdict: Verdict;
  traces: RuleTrace[];
}

export type AssignmentKind = "pairing" | "flight" | "flight_set" | "duty_day";

export interface LegalityReport {
  crew_id: string;
  assignment_ref: string;
  assignment_kind: AssignmentKind;
  /** The worst day, never an average. */
  overall: Verdict;
  per_day: DayLegality[];
  rules_checked: RuleId[];
}

// --------------------------------------------------------------------- ops

export interface FlightRef {
  flight_no: string;
  origin: string;
  destination: string;
  departure: string;
  arrival: string;
  aircraft_type?: string | null;
  passengers?: number | null;
  pairing_id?: string | null;
}

export type RiskSeverity = "critical" | "high" | "medium" | "low";

export interface DownstreamRisk {
  crew_id?: string | null;
  flight_no?: string | null;
  pairing_id?: string | null;
  rule_id?: RuleId | null;
  severity: RiskSeverity;
  detail: string;
  duty_date?: string | null;
}

export type TriggerKind =
  | "crew_absence"
  | "station_closure"
  | "reassignment"
  | "flight_delay"
  | "custom";

export interface ImpactReport {
  trigger: string;
  trigger_kind: TriggerKind;
  as_of: string;
  uncrewed_flights: FlightRef[];
  pairings_broken: string[];
  crew_affected: string[];
  stations_affected: string[];
  passengers_affected: number;
  downstream_risks: DownstreamRisk[];
  explanation: string;
  facts: Fact[];
}

export interface CostLine {
  label: string;
  amount_inr: number;
  /** Shows the multiplication, not just the total. */
  basis: string;
  rule_ref?: string | null;
}

export interface CostBreakdown {
  line_items: CostLine[];
  total_inr: number;
  note?: string | null;
}

export type CoverKind = "reserve" | "reassign" | "deadhead" | "swap" | "cancel";

export interface CoverOption {
  rank: number;
  kind: CoverKind;
  action: string;
  crew_id: string;
  crew_name: string;
  crew_base: string;
  crew_rank: string;
  legal: boolean;
  legality: LegalityReport;
  rules_checked: RuleId[];
  cost: CostBreakdown;
  coverage_summary: string;
  covered_flights: string[];
  uncovered_flights: string[];
  reachable: boolean;
  reachability_minutes?: number | null;
  delay_minutes: number;
  reasoning: string;
  tradeoffs: string[];
  confidence: Confidence;
  facts: Fact[];
}

export interface Recommendation {
  situation: string;
  impact?: ImpactReport | null;
  options: CoverOption[];
  /** Candidates found and excluded, each with the breaching RuleTrace. */
  rejected: CoverOption[];
  candidates_evaluated: number;
  ranking_basis: string;
  notification_draft?: string | null;
  facts: Fact[];
}

export interface Alert {
  severity: RiskSeverity;
  title: string;
  detail: string;
  crew_id?: string | null;
  flight_no?: string | null;
  pairing_id?: string | null;
  rule_id?: RuleId | null;
  due_date?: string | null;
  suggested_question?: string | null;
  facts: Fact[];
}

export interface Watchlist {
  as_of: string;
  for_date: string;
  alerts: Alert[];
  headline: string;
  scanned: Record<string, number>;
}

// ------------------------------------------------------------------- reply

export type Tier = 1 | 2 | 3;

export type ReplyKind = "answer" | "abstain" | "error";

export type AnswerMode = "agent" | "deterministic";

export interface Reply {
  thread_id: string;
  turn_id: string;
  question: string;
  asked_at: string;

  kind: ReplyKind;
  mode: AnswerMode;
  tier?: Tier | null;

  headline?: string | null;
  text: string;

  facts: Fact[];
  traces: TraceStep[];
  rule_traces: RuleTrace[];
  tables: Table[];

  impact?: ImpactReport | null;
  recommendation?: Recommendation | null;

  citations: Citation[];
  tool_calls: ToolEnvelope[];

  abstention?: Abstention | null;
  confidence: Confidence;
  verification: VerificationReport;
  timings: Timings;

  caveats: string[];
  follow_ups: string[];
}

// ------------------------------------------------------------------ stream

export type EventType =
  | "run_started"
  | "plan"
  | "tool_call"
  | "tool_result"
  | "trace"
  | "token"
  | "verifying"
  | "verification"
  | "abstain"
  | "reply"
  | "error"
  | "done";

interface BaseEvent {
  turn_id: string;
  /** Monotonic within a turn, so the UI can order and dedupe. */
  seq: number;
  at: string;
}

export interface RunStartedEvent extends BaseEvent {
  type: "run_started";
  thread_id: string;
  question: string;
  mode: AnswerMode;
}

export interface PlanEvent extends BaseEvent {
  type: "plan";
  intent: string;
  tier?: Tier | null;
  steps: string[];
}

export interface ToolCallEvent extends BaseEvent {
  type: "tool_call";
  tool: string;
  args: Record<string, unknown>;
  label: string;
}

export interface ToolResultEvent extends BaseEvent {
  type: "tool_result";
  tool: string;
  ok: boolean;
  latency_ms: number;
  summary: string;
  envelope?: ToolEnvelope | null;
}

export interface TraceEvent extends BaseEvent {
  type: "trace";
  step: TraceStep;
}

export interface TokenEvent extends BaseEvent {
  type: "token";
  text: string;
}

export interface VerifyingEvent extends BaseEvent {
  type: "verifying";
  atom_count: number;
}

export interface VerificationEvent extends BaseEvent {
  type: "verification";
  report: VerificationReport;
}

export interface AbstainEvent extends BaseEvent {
  type: "abstain";
  abstention: Abstention;
}

export interface ReplyEvent extends BaseEvent {
  type: "reply";
  reply: Reply;
}

export interface ErrorEvent extends BaseEvent {
  type: "error";
  message: string;
  recoverable: boolean;
}

export interface DoneEvent extends BaseEvent {
  type: "done";
  total_ms: number;
}

export type StreamEvent =
  | RunStartedEvent
  | PlanEvent
  | ToolCallEvent
  | ToolResultEvent
  | TraceEvent
  | TokenEvent
  | VerifyingEvent
  | VerificationEvent
  | AbstainEvent
  | ReplyEvent
  | ErrorEvent
  | DoneEvent;

export interface ChatRequest {
  question: string;
  thread_id?: string | null;
  as_of?: string | null;
  force_mode?: AnswerMode | null;
}

// ------------------------------------------------------------------- tools

export const TOOL_NAMES = [
  "find_crew",
  "get_crew_detail",
  "find_flights",
  "get_duty_clocks",
  "list_reserves",
  "find_expiring_certifications",
  "get_pairing",
  "get_roster",
  "check_legality",
  "simulate_absence",
  "simulate_reassignment",
  "simulate_station_closure",
  "find_cover_options",
  "draft_notification",
  "get_watchlist",
  "get_world_summary",
  "explain_rule",
] as const;

export type ToolName = (typeof TOOL_NAMES)[number];

/** Tools that cannot, on their own, support a Tier 2 or Tier 3 answer. */
export const RETRIEVAL_ONLY: ReadonlySet<string> = new Set([
  "find_crew",
  "get_crew_detail",
  "find_flights",
  "get_duty_clocks",
  "list_reserves",
  "find_expiring_certifications",
  "get_pairing",
  "get_roster",
  "get_world_summary",
  "explain_rule",
]);

/** Which tier a tool belongs to, for chip colouring in the trace. */
export const TOOL_TIER: Record<string, 1 | 2 | 3 | 0> = {
  find_crew: 1,
  get_crew_detail: 1,
  find_flights: 1,
  get_duty_clocks: 1,
  list_reserves: 1,
  find_expiring_certifications: 1,
  get_pairing: 1,
  get_roster: 1,
  check_legality: 2,
  simulate_absence: 2,
  simulate_reassignment: 2,
  simulate_station_closure: 2,
  find_cover_options: 3,
  draft_notification: 3,
  get_watchlist: 0,
  get_world_summary: 0,
  explain_rule: 0,
};

// ---------------------------------------------------- non-streaming routes
//
// These shapes are not in `contracts/`; they are the HTTP envelopes described
// in `docs/CONTRACTS.md`. Anything marked MOCKED below is a field the UI needs
// that the contract does not yet name. See web/README.md, "Contract gaps".

export interface HealthResponse {
  status: string;
  dataset_loaded: boolean;
  snapshot: string;
  llm_configured: boolean;
  mode: AnswerMode;
}

export interface WorldSummary {
  snapshot: string;
  base: string;
  date_from: string;
  date_to: string;
  counts: Record<string, number>;
  /** MOCKED: not named in docs/CONTRACTS.md, useful for the ops header. */
  currency?: string;
  /** MOCKED: airline display name for the shell header. */
  operator?: string;
}

export interface RuleDefinition {
  rule_id: RuleId;
  title: string;
  constraint: string;
  /** MOCKED: the machine readable limit as shipped in rules.json. */
  limit?: number | null;
  unit?: RuleUnit | null;
  /** MOCKED: prose a controller reads when they challenge a verdict. */
  detail?: string | null;
}

export type QuestionTier = 1 | 2 | 3;

export interface SampleQuestion {
  id: string;
  tier: QuestionTier;
  question: string;
  /** MOCKED: short label for the demo launcher list. */
  topic?: string | null;
}

export interface ThreadSummary {
  thread_id: string;
  /** Named from the first answer's headline, or by a person who renamed it. */
  title: string;
  /** "user" once somebody has typed a name, so a later turn cannot overwrite it. */
  titled_by: "auto" | "user";
  created_at: string;
  updated_at: string;
  turn_count: number;
  /** MOCKED: highest tier reached in the thread, for the rail badge. */
  tier?: Tier | null;
}

export interface ThreadDetail {
  thread_id: string;
  title: string;
  created_at: string;
  turns: Reply[];
}

export interface SimulateRequest {
  kind: TriggerKind;
  crew_id?: string;
  from_date?: string;
  to_date?: string;
  station?: string;
  from_time?: string;
  to_time?: string;
  reason?: string;
}

export interface LegalityRequest {
  crew_id: string;
  pairing_id?: string;
  flight_numbers?: string[];
  on_date?: string;
  as_replacement_for?: string;
}

export interface CoverRequest {
  pairing_id?: string;
  flight_numbers?: string[];
  exclude_crew_ids?: string[];
  max_options?: number;
  include_rejected?: boolean;
}
