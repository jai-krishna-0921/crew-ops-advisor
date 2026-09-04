"""Fact containment for the scorecard, built on the verifier's normaliser.

Grading a natural language answer against an answer key is the hard part of
this harness. String equality is useless: the key says
`"RULE-DUTY-02: would exceed 60h/7d by 1h20m on 2026-09-15 (total 61.33h)"` and
a good answer says "C-2087 would be 1.33 hours over the 60 hour limit on 15
September". Those are the same answer.

**There is one normaliser in this repository and it lives in
`crewops.verify`.** This module does not define a second one. It imports
`crewops.verify.extract.extract_atoms` and the `crewops.verify.normalise`
canonical forms, and adds exactly two things the verifier must not have:

1. `flatten`, which renders an arbitrary answer-key JSON value as text the
   extractor can walk. The verifier only ever scans prose.
2. **Grading tolerance.** The verifier is strict on purpose: a flight number is
   not a flight id, and a bare number is not a duration, because letting those
   through would let a wrong figure into an answer. A grader needs the opposite
   bias: marking a correct answer wrong understates the system and pushes the
   team to optimise the wrong thing. So each verified atom is expanded into a
   set of equivalence keys, and two atoms match when their key sets intersect.

The expansions, and why each one is safe here and would not be safe in the
verifier:

- **duration to number**, so `1h20m` in a key is satisfied by `1.33 hours` in
  prose, and the other way round.
- **currency to number**, because a key carries `cost_inr: 18500` as a bare
  integer and a good answer writes `INR 18,500`.
- **flight id to flight number**, because the keys mix `DX412-2026-09-15` and
  `DX412` for the same leg, and prose usually states the date in a separate
  clause.

Nothing here imports a model client. Grading is deterministic: a harness that
used a model to judge a model would be measuring the wrong thing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

try:
    from crewops.verify.extract import Atom as VerifiedAtom
    from crewops.verify.extract import extract_atoms
    from crewops.verify.normalise import canonical_number, hours_to_minutes
except ImportError as exc:  # pragma: no cover - verify is a declared dependency
    raise ImportError(
        "crewops.eval depends on crewops.verify for atom extraction and "
        "normalisation. There is deliberately only one normaliser in this "
        "repository: see the module docstring. Do not add a second one here."
    ) from exc

#: Bare integers at or below this are list indices, ranks and sector counts
#: rather than facts worth requiring of an answer.
TRIVIAL_INTEGER_CEILING = 3

#: Above this many hours a value is not plausibly a duration, so it is not
#: cross-matched against one. Keeps a 162 seat count away from a 2h42m span.
MAX_PLAUSIBLE_DURATION_HOURS = 200

_FLIGHT_ID_RE = re.compile(r"^(DX\d{2,4})-\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Atom:
    """One verified atom plus every form a correct answer might state it in."""

    kind: str
    canon: str
    text: str
    keys: frozenset[str]

    def matches(self, other: Atom) -> bool:
        return bool(self.keys & other.keys)

    def __str__(self) -> str:
        return f"{self.kind}:{self.text}"


def _keys_for(kind: str, canon: str) -> frozenset[str]:
    """The equivalence keys one canonical atom is satisfied by.

    Keys are namespaced, so kinds that should never unify (a station and a
    rule id) cannot collide even though matching is a plain set intersection.
    """
    if kind == "rule_id":
        return frozenset({f"rule:{canon}"})
    if kind == "station":
        return frozenset({f"station:{canon}"})
    if kind == "aircraft":
        return frozenset({f"actype:{canon}"})
    if kind == "date":
        return frozenset({f"date:{canon}"})
    if kind == "time":
        return frozenset({f"time:{canon}"})

    if kind == "identifier":
        keys = {f"id:{canon}"}
        leg = _FLIGHT_ID_RE.match(canon)
        if leg:
            keys.add(f"id:{leg.group(1)}")
        return frozenset(keys)

    if kind == "duration":
        keys = {f"qty:{canon}"}
        try:
            total_minutes = int(canon)
        except ValueError:
            return frozenset(keys)
        as_hours = canonical_number(total_minutes / 60)
        if as_hours is not None:
            keys.add(f"num:{as_hours}")
        return frozenset(keys)

    # number and currency both reduce to a decimal string, so they unify.
    keys = {f"num:{canon}"}
    try:
        value = float(canon)
    except ValueError:
        return frozenset(keys)
    if 0 < value < MAX_PLAUSIBLE_DURATION_HOURS:
        minutes = hours_to_minutes(value)
        if minutes is not None:
            keys.add(f"qty:{minutes}")
    return frozenset(keys)


def _adapt(verified: VerifiedAtom) -> Atom:
    return Atom(
        kind=verified.kind,
        canon=verified.canon,
        text=verified.text,
        keys=_keys_for(verified.kind, verified.canon),
    )


def extract(text: str) -> list[Atom]:
    """Every gradeable atom in a block of text, in first-appearance order."""
    return [_adapt(atom) for atom in extract_atoms(text)]


def flatten(value: Any) -> str:
    """Render an arbitrary JSON value as text the extractor can walk.

    Dict keys are kept. `passengers_day1` carries no atom of its own, but
    dropping keys would silently discard `"legal": false`, which is the field
    the verdict check reads.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    if isinstance(value, list):
        return " ; ".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return " ; ".join(f"{key} = {flatten(item)}" for key, item in value.items())
    return str(value)


def extract_from(value: Any) -> list[Atom]:
    """Atoms from any JSON-shaped value."""
    return extract(flatten(value))


def dedupe(atoms: list[Atom]) -> list[Atom]:
    """Collapse repeats, keeping first-appearance order.

    A key that lists `RULE-FDP-01` in six `rules_checked` arrays should require
    it once, not six times, or recall becomes a measure of how much boilerplate
    the answer repeated.
    """
    seen: set[frozenset[str]] = set()
    unique: list[Atom] = []
    for atom in atoms:
        if atom.keys in seen:
            continue
        seen.add(atom.keys)
        unique.append(atom)
    return unique


def containment(required: list[Atom], produced: list[Atom]) -> tuple[list[Atom], list[Atom]]:
    """Split `required` into the atoms `produced` asserts and the ones it misses."""
    available: set[str] = set()
    for atom in produced:
        available |= atom.keys

    hit: list[Atom] = []
    missed: list[Atom] = []
    for atom in required:
        (hit if atom.keys & available else missed).append(atom)
    return hit, missed


def is_trivial(atom: Atom) -> bool:
    """True for atoms too weak to require of an answer.

    Three exclusions, all of them to stop the grader marking good answers wrong:

    - **Stations.** A three letter code appears incidentally in almost any
      answer, so requiring one adds noise without signal.
    - **Zero.** `"delay_hours": 0.0` asserts that there is no delay, and a good
      answer says "no delay" rather than "0.0 hours".
    - **Small bare integers.** Ranks, sector counts and list positions.
    """
    if atom.kind == "station":
        return True
    if atom.kind not in {"number", "currency", "duration"}:
        return False
    try:
        value = float(atom.canon)
    except ValueError:
        return False
    if value == 0:
        return True
    return atom.kind != "duration" and value.is_integer() and abs(value) <= TRIVIAL_INTEGER_CEILING


__all__ = [
    "MAX_PLAUSIBLE_DURATION_HOURS",
    "TRIVIAL_INTEGER_CEILING",
    "Atom",
    "containment",
    "dedupe",
    "extract",
    "extract_from",
    "flatten",
    "is_trivial",
]
