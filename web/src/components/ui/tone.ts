/**
 * Semantic tone to class name.
 *
 * Written as full literal class strings rather than composed at runtime, so
 * Tailwind sees every one of them. Colour is never the only signal: every
 * place that uses a tone also renders a word and, where it matters, a glyph.
 */

import type { Tone } from "@/lib/format";

export interface ToneClasses {
  /** Tinted fill plus a matching hairline. For pills and badges. */
  chip: string;
  /** Text only. For inline emphasis inside prose or a table cell. */
  text: string;
  /** A left rule, for a card that must be unmissable. */
  edge: string;
  /** Solid fill for a dot or a meter segment. */
  fill: string;
}

export const TONE: Record<Tone, ToneClasses> = {
  pass: {
    chip: "bg-pass-tint text-pass ring-1 ring-pass-line",
    text: "text-pass",
    edge: "border-l-2 border-l-pass",
    fill: "bg-pass",
  },
  breach: {
    chip: "bg-breach-tint text-breach ring-1 ring-breach-line",
    text: "text-breach",
    edge: "border-l-2 border-l-breach",
    fill: "bg-breach",
  },
  caution: {
    chip: "bg-caution-tint text-caution ring-1 ring-caution-line",
    text: "text-caution",
    edge: "border-l-2 border-l-caution",
    fill: "bg-caution",
  },
  unknown: {
    chip: "bg-unknown-tint text-unknown ring-1 ring-unknown-line",
    text: "text-unknown",
    edge: "border-l-2 border-l-unknown",
    fill: "bg-unknown",
  },
  na: {
    chip: "bg-na-tint text-na ring-1 ring-na-line",
    text: "text-na",
    edge: "border-l-2 border-l-na",
    fill: "bg-na",
  },
  accent: {
    chip: "bg-accent-tint text-accent ring-1 ring-accent-line",
    text: "text-accent",
    edge: "border-l-2 border-l-accent",
    fill: "bg-accent",
  },
};

/** Tier badge colours. Tier is a scope marker, not a verdict, so it stays neutral. */
export const TIER_CHIP: Record<number, string> = {
  1: "bg-inset text-ink-2 ring-1 ring-line",
  2: "bg-inset text-ink-2 ring-1 ring-line-strong",
  3: "bg-accent-tint text-accent ring-1 ring-accent-line",
};

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
