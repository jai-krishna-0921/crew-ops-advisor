/**
 * Fact builders for the fixtures.
 *
 * Keeping these tiny and explicit matters: every figure a mock reply states in
 * prose has to exist here as a Fact, or the grounding link in the UI will not
 * find it and the fixture will have quietly reproduced the exact failure the
 * real system is built to prevent.
 */

import type { Fact, FactUnit, FactValue } from "@/lib/contracts";

export function dataset(
  key: string,
  label: string,
  value: FactValue,
  unit: FactUnit,
  source: string,
): Fact {
  return { key, label, value, unit, provenance: "dataset", source };
}

export function computed(
  key: string,
  label: string,
  value: FactValue,
  unit: FactUnit,
  source: string,
  derivation: string,
): Fact {
  return {
    key,
    label,
    value,
    unit,
    provenance: "computed",
    source,
    derivation,
  };
}

export function assumed(
  key: string,
  label: string,
  value: FactValue,
  unit: FactUnit,
  source: string,
  derivation: string,
): Fact {
  return {
    key,
    label,
    value,
    unit,
    provenance: "assumed",
    source,
    derivation,
  };
}
