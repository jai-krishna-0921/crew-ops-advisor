/**
 * Semantic tone to class name.
 *
 * Written as full literal class strings rather than composed at runtime, so
 * Tailwind sees every one of them. Colour is never the only signal: every
 * place that uses a tone also renders a word and, where it matters, a glyph.
 *
 * THE RINGS ARE GONE. Every chip used to carry `ring-1 ring-X-line` on top of
 * its tint, which put a coloured outline around a coloured fill: two edges
 * describing the same shape. On a page with a dozen chips on it that reads as
 * a wireframe of chips rather than as chips. The tint alone separates them
 * from the surface, and dropping the ring is most of what makes a row of
 * pills settle down.
 */

import type { Tone } from "@/lib/format";

export interface ToneClasses {
  /** Tinted fill. For pills and badges. */
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
    chip: "bg-pass-tint text-pass",
    text: "text-pass",
    edge: "border-l-2 border-l-pass",
    fill: "bg-pass",
  },
  breach: {
    chip: "bg-breach-tint text-breach",
    text: "text-breach",
    edge: "border-l-2 border-l-breach",
    fill: "bg-breach",
  },
  caution: {
    chip: "bg-caution-tint text-caution",
    text: "text-caution",
    edge: "border-l-2 border-l-caution",
    fill: "bg-caution",
  },
  unknown: {
    chip: "bg-unknown-tint text-unknown",
    text: "text-unknown",
    edge: "border-l-2 border-l-unknown",
    fill: "bg-unknown",
  },
  na: {
    chip: "bg-na-tint text-ink-2",
    text: "text-na",
    edge: "border-l-2 border-l-na",
    fill: "bg-na",
  },
  accent: {
    chip: "bg-accent-tint text-accent-ink",
    text: "text-accent-ink",
    edge: "border-l-2 border-l-accent",
    fill: "bg-accent",
  },
};

/** Tier badge colours. Tier is a scope marker, not a verdict, so it stays neutral. */
export const TIER_CHIP: Record<number, string> = {
  1: "bg-na-tint text-ink-2",
  2: "bg-na-tint text-ink-2",
  3: "bg-accent-tint text-accent-ink",
};

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
