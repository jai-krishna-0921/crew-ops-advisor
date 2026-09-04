/**
 * Links figures in prose back to the `Fact` that attests them.
 *
 * This is the visual proof of the architecture: if a number is in the answer,
 * a tool emitted a Fact for it, and the reader can reach that Fact in one
 * gesture. Anything the guard verified is reachable; anything not linked is
 * plain language rather than a claim.
 *
 * IMPORTANT, and the reason this file is careful:
 *
 *   This does string matching only. It never parses a figure out of prose and
 *   never produces a value. Every surface form it looks for is generated from
 *   a `Fact.value` the API already supplied, through the formatters in
 *   `lib/format.ts`. If a number appears in the text and no Fact carries it,
 *   this code leaves it alone. It does not guess, and it must never be made
 *   to guess.
 *
 * Contract gap: the API does not send character spans. Matching by surface
 * form is a second-best. A `spans: [{start, length, fact_key}]` field on
 * `Reply` computed by the verifier (which already locates every atom) would
 * remove the ambiguity entirely. Raised in web/README.md.
 */

import type { Fact } from "@/lib/contracts";
import { decimal, grouped, inr, longDate, shortDate, withUnit } from "@/lib/format";

export interface ProseSegment {
  text: string;
  /** Present when this segment is attested by a Fact. */
  factKey?: string;
}

/** Characters that, if adjacent, mean we matched the middle of a token. */
const WORDISH = /[A-Za-z0-9_-]/;

/**
 * Every way a fact's value could legitimately be written in prose. Order does
 * not matter here; the caller sorts by length so the most specific form wins.
 */
export function surfaceForms(fact: Fact): string[] {
  const v = fact.value;
  if (v === null || v === undefined) return [];

  if (typeof v === "boolean") return [];

  if (typeof v === "number") {
    const forms = new Set<string>();
    forms.add(decimal(v));
    forms.add(String(v));
    if (Number.isInteger(v)) {
      forms.add(grouped(v));
    }
    if (fact.unit === "inr") {
      forms.add(inr(v));
      forms.add(grouped(Math.round(v)));
    } else if (fact.unit && fact.unit !== "count") {
      forms.add(withUnit(v, fact.unit));
    }
    return [...forms].filter((f) => f.length >= 2);
  }

  // Strings: identifiers, stations, rule ids and dates.
  const forms = new Set<string>([v]);
  if (fact.unit === "date" && /^\d{4}-\d{2}-\d{2}$/.test(v)) {
    forms.add(longDate(v));
    forms.add(shortDate(v));
  }
  return [...forms].filter((f) => f.length >= 2);
}

interface Candidate {
  form: string;
  key: string;
}

function buildCandidates(facts: Fact[]): Candidate[] {
  const seen = new Map<string, string>();
  for (const fact of facts) {
    for (const form of surfaceForms(fact)) {
      if (!seen.has(form)) seen.set(form, fact.key);
    }
  }
  return [...seen.entries()]
    .map(([form, key]) => ({ form, key }))
    // Longest first: "INR 18,500" must win over "18,500", and "61.33h" over
    // "61.33".
    .sort((a, b) => b.form.length - a.form.length || a.form.localeCompare(b.form));
}

/**
 * Splits prose into segments, marking the ones a Fact attests.
 *
 * The scan is greedy and left to right. A position already consumed is never
 * re-matched, so overlapping forms cannot double-link.
 */
export function linkFacts(text: string, facts: Fact[]): ProseSegment[] {
  if (!text) return [];
  const candidates = buildCandidates(facts);
  if (candidates.length === 0) return [{ text }];

  const segments: ProseSegment[] = [];
  let cursor = 0;
  let plainStart = 0;

  outer: while (cursor < text.length) {
    for (const { form, key } of candidates) {
      if (!text.startsWith(form, cursor)) continue;

      const before = cursor > 0 ? text[cursor - 1] : "";
      const afterIndex = cursor + form.length;
      const after = afterIndex < text.length ? text[afterIndex] : "";

      // Reject a hit inside a larger token: "413" inside "DX413", or "18,5"
      // inside "18,500". A trailing full stop is allowed unless a digit
      // follows it, so "cost INR 18,500." links but "18.50" does not match
      // on "18".
      if (before && WORDISH.test(before)) continue;
      if (after && WORDISH.test(after)) continue;
      if (after === "." && /\d/.test(text[afterIndex + 1] ?? "")) continue;
      if (after === "," && /\d/.test(text[afterIndex + 1] ?? "")) continue;

      if (cursor > plainStart) {
        segments.push({ text: text.slice(plainStart, cursor) });
      }
      segments.push({ text: form, factKey: key });
      cursor = afterIndex;
      plainStart = cursor;
      continue outer;
    }
    cursor += 1;
  }

  if (plainStart < text.length) {
    segments.push({ text: text.slice(plainStart) });
  }
  return segments;
}

/** Convenience for components that hold a fact list keyed by `Fact.key`. */
export function indexFacts(facts: Fact[]): Map<string, Fact> {
  const index = new Map<string, Fact>();
  for (const fact of facts) index.set(fact.key, fact);
  return index;
}

/**
 * Every fact a reply can cite, in one list: the reply's own facts plus the
 * facts each tool envelope carried, deduplicated by key. The reply's copy
 * wins, because it is the one the guard checked against.
 */
export function collectFacts(...groups: (Fact[] | undefined | null)[]): Fact[] {
  const out: Fact[] = [];
  const seen = new Set<string>();
  for (const group of groups) {
    for (const fact of group ?? []) {
      if (seen.has(fact.key)) continue;
      seen.add(fact.key);
      out.push(fact);
    }
  }
  return out;
}
