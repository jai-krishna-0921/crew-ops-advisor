/**
 * Presentation formatting.
 *
 * Every function here is a pure string transform of a value the API already
 * computed. Nothing in this file derives a new figure: no addition, no unit
 * conversion, no rounding that changes meaning, no percentage of anything.
 * If you find yourself needing a number that is not already in the payload,
 * it belongs in a tool on the API side, not here.
 *
 * The one apparent exception is `minutesToClock`, which splits a minute count
 * into hours and minutes for display. That is a radix change on a single
 * value the API supplied, in the same way `1,250` is a radix change on
 * `1250`. It never combines two values.
 */

import { TOOL_TIER } from "@/lib/contracts";
import type {
  AbstentionReason,
  AnswerMode,
  FactValue,
  Provenance,
  RiskSeverity,
  Verdict,
  VerificationStatus,
} from "@/lib/contracts";

/* ------------------------------------------------------------------ time */

/** "2026-09-15T06:40:00" -> "15 Sep 06:40" (all dataset times are UTC). */
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, , mo, d, hh, mm] = m;
  return `${stripLeadingZero(d)} ${MONTHS[Number(mo) - 1]} ${hh}:${mm}`;
}

/** "2026-09-15T06:40:00" -> "06:40". */
export function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /[T ](\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : "";
}

/** "2026-09-15" -> "15 Sep 2026". */
export function longDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${stripLeadingZero(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

/** "2026-09-15" -> "15 Sep". */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${stripLeadingZero(m[3])} ${MONTHS[Number(m[2]) - 1]}`;
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function stripLeadingZero(v: string): string {
  return v.replace(/^0/, "");
}

/** 200 -> "3h20m". A radix change on one supplied value, not arithmetic. */
export function minutesToClock(mins: number | null | undefined): string {
  if (mins === null || mins === undefined) return "";
  const sign = mins < 0 ? "-" : "";
  const abs = Math.abs(mins);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  if (h === 0) return `${sign}${m}m`;
  if (m === 0) return `${sign}${h}h`;
  return `${sign}${h}h${String(m).padStart(2, "0")}m`;
}

/** 1234 -> "1.2s", 640 -> "640ms". */
export function latency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
}

/* --------------------------------------------------------------- numbers */

const GROUPED = new Intl.NumberFormat("en-IN");

/** 18500 -> "18,500" in the Indian grouping the dataset's currency implies. */
export function grouped(n: number): string {
  return GROUPED.format(n);
}

/** 18500 -> "INR 18,500". Never rounds, never converts. */
export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  const whole = Number.isInteger(n) ? n : Number(n.toFixed(2));
  return `INR ${GROUPED.format(whole)}`;
}

/**
 * 61.333 -> "61.33", 60 -> "60", 5.20 -> "5.2".
 *
 * Mirrors the Python `Fact.rendered()` exactly, including the trailing zero
 * trim. The UI and the verifier have to agree on how a figure is written or
 * the grounding link finds nothing.
 */
export function decimal(n: number): string {
  const s = n.toFixed(2);
  if (!s.includes(".")) return s;
  return s.replace(/0+$/, "").replace(/\.$/, "");
}

/** 61.33, "hours" -> "61.33h". Unit suffix only, no conversion. */
export function withUnit(value: number, unit?: string | null): string {
  const v = decimal(value);
  switch (unit) {
    case "hours":
      return `${v}h`;
    case "minutes":
      return `${v}m`;
    case "days":
      return `${v}d`;
    case "percent":
      return `${v}%`;
    case "inr":
      return inr(value);
    default:
      return v;
  }
}

/** Renders any `FactValue` for display, matching the Python `rendered()`. */
export function factValue(
  value: FactValue,
  unit?: string | null,
): string {
  if (value === null || value === undefined) return "not supplied";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    if (unit === "inr") return inr(value);
    if (unit === "count") return grouped(value);
    return withUnit(value, unit);
  }
  if (unit === "datetime") return dateTime(value);
  if (unit === "date") return longDate(value);
  return value;
}

/* ----------------------------------------------------------- vocabularies */

export const VERDICT_LABEL: Record<Verdict, string> = {
  pass: "Pass",
  breach: "Breach",
  not_applicable: "Not applicable",
  insufficient_data: "Insufficient data",
};

/** The token family a verdict paints with. Colour is never the only signal. */
export const VERDICT_TONE: Record<Verdict, Tone> = {
  pass: "pass",
  breach: "breach",
  not_applicable: "na",
  insufficient_data: "unknown",
};

export type Tone = "pass" | "breach" | "caution" | "unknown" | "na" | "accent";

export const SEVERITY_LABEL: Record<RiskSeverity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const SEVERITY_TONE: Record<RiskSeverity, Tone> = {
  critical: "breach",
  high: "breach",
  medium: "caution",
  low: "na",
};

export const SEVERITY_ORDER: Record<RiskSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  dataset: "Dataset",
  computed: "Computed",
  assumed: "Assumed",
};

export const PROVENANCE_NOTE: Record<Provenance, string> = {
  dataset: "Read straight from a provided file. True by definition.",
  computed: "Output of deterministic arithmetic. Carries its working.",
  assumed: "A stated modelling assumption, not an observed fact.",
};

export const VERIFICATION_LABEL: Record<VerificationStatus, string> = {
  verified: "Verified",
  repaired: "Repaired",
  rejected: "Rejected",
  skipped: "Not checked",
};

export const VERIFICATION_TONE: Record<VerificationStatus, Tone> = {
  verified: "pass",
  repaired: "caution",
  rejected: "breach",
  skipped: "na",
};

export const ABSTENTION_LABEL: Record<AbstentionReason, string> = {
  out_of_scope: "Outside the dataset's scope",
  greeting: "Not a question yet",
  not_in_dataset: "Not present in the dataset",
  ambiguous_referent: "Ambiguous referent",
  underspecified: "Question underspecified",
  requires_unmodelled_rule: "Requires a rule that is not modelled",
  conflicting_data: "Conflicting data",
  verification_failed: "Grounding check failed",
  tool_error: "A tool call failed",
};

export const MODE_LABEL: Record<AnswerMode, string> = {
  agent: "Agent",
  deterministic: "Deterministic",
};

export const MODE_NOTE: Record<AnswerMode, string> = {
  agent: "A LangGraph planner chose the tools for this turn.",
  deterministic:
    "No API key configured, so the offline resolver ran. Same tools, same guard.",
};

/** Readable tool name for a chip: "get_duty_clocks" -> "Get duty clocks". */
export function toolLabel(tool: string): string {
  const words = tool.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Which tier a tool serves. Retrieval alone cannot establish a consequence,
 * so the tier a call belongs to is worth showing next to it in the timeline.
 */
export function TOOL_TIER_LABEL(tool: string): string {
  const tier = TOOL_TIER[tool];
  if (!tier) return "support";
  return `Tier ${tier}`;
}

/** "C-1042 · P-2291" style joins that stay readable when a part is missing. */
export function joinParts(parts: (string | null | undefined)[]): string {
  return parts.filter((p): p is string => Boolean(p)).join(" · ");
}

/** "3 flights" / "1 flight". Pluralisation, not counting. */
/**
 * A timestamp as an unambiguous instant.
 *
 * ECMAScript parses a date-time with no offset on it as LOCAL time. The API
 * now always sends the offset, and this is the belt to that braces: a value
 * that predates the fix, or one that reaches here from storage, still resolves
 * as the UTC it has always been rather than as whatever zone the reader
 * happens to be in.
 */
function asInstant(iso: string): string {
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return zoned ? iso : `${iso}Z`;
}

/**
 * Coarse relative time, for a thread list.
 *
 * Deliberately coarse. "15h ago" is the resolution somebody scanning their own
 * conversations needs, and a live-updating minute counter on a list of twenty
 * rows is twenty re-renders a minute for information nobody reads.
 */
export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = Date.parse(asInstant(iso));
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, (Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return shortDate(iso);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${grouped(n)} ${n === 1 ? one : many}`;
}
