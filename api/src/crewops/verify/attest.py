"""Build the set of atoms the tools actually established this turn.

There are exactly two attestation channels, and the report says which one
carried each atom so the gap between them stays visible.

**Fact channel (primary).** Every `Fact` on every successful envelope. Facts
are typed, so `unit="hours"` registers the duration equivalence as well as the
bare number, and a `derivation` string is re-scanned so the operands inside
"51.83h prior + 9.50h added = 61.33h against a 60.00h limit" are attested too.
Facts also carry a key and a provenance, which is what lets the UI link prose
to evidence.

**Payload channel (fallback).** Every scalar reachable in the payload, the
trace, the citations and the call arguments of a successful envelope. These
are still deterministic output, so nothing the model invented can enter this
way. What is lost is citation quality, not safety, which is why the report
counts payload-only attestations separately: that count is a punch list of
`Fact` objects the tool layer should be emitting.

Set `VerifierPolicy.require_fact_attestation` to turn the payload channel off
entirely. The strict-mode tests run with it on.

Two registration rules deserve their own note.

1. **Arguments of a successful call are attested.** `find_crew(base="BLR")`
   returning `ok=True` makes `BLR` attested, because the deterministic layer
   accepted that filter and computed against it. Arguments of a *failed* call
   are not attested, because a lookup for `C-9999` failing is exactly the case
   where the model made the identifier up.
2. **A unit rendering of an attested value is attested.** If `61.33` is an
   attested number then `61.33h` and `61h20m` are attested durations. The
   verifier's job is to catch a wrong *value*; asserting the wrong unit on a
   right value is a different and much rarer failure, and chasing it produces
   false rejections on correct answers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime as datetime_cls
from typing import Any, Final

from crewops.contracts import Fact, ToolEnvelope
from crewops.verify.extract import Atom, AtomKind, extract_atoms
from crewops.verify.normalise import (
    canonical_currency,
    canonical_date,
    canonical_datetime,
    canonical_duration_minutes,
    canonical_identifier,
    canonical_number,
    canonical_time,
)

__all__ = ["AttestedSet", "build_attested_set"]

#: How deep the payload walk goes. The deepest shipped payload is a
#: Recommendation holding CoverOptions holding LegalityReports holding
#: DayLegality holding RuleTrace holding Fact, which is six.
_MAX_DEPTH: Final = 10

#: Ceiling on scalars harvested from one turn. A runaway payload should slow
#: nothing down; it should just stop contributing.
_MAX_SCALARS: Final = 50_000

#: Payload and argument keys whose values are plumbing, not findings. Left out
#: of the attested set so a latency figure can never launder a wrong number.
_IGNORED_KEYS: Final[frozenset[str]] = frozenset(
    {"latency_ms", "seq", "turn_id", "thread_id", "limit", "max_options"}
)


@dataclass(slots=True)
class AttestedSet:
    """Everything the tools established, indexed by kind and canonical form."""

    numbers: set[str] = field(default_factory=set)
    durations: set[str] = field(default_factory=set)
    currencies: set[str] = field(default_factory=set)
    dates: set[str] = field(default_factory=set)
    times: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)
    stations: set[str] = field(default_factory=set)
    rule_ids: set[str] = field(default_factory=set)
    aircraft: set[str] = field(default_factory=set)

    #: `(kind, canon)` pairs that arrived through the Fact channel.
    fact_backed: set[tuple[str, str]] = field(default_factory=set)

    _scalars_seen: int = 0

    # -------------------------------------------------------------- lookup

    def _bucket(self, kind: AtomKind) -> set[str]:
        return {
            "number": self.numbers,
            "duration": self.durations,
            "currency": self.currencies,
            "date": self.dates,
            "time": self.times,
            "identifier": self.identifiers,
            "station": self.stations,
            "rule_id": self.rule_ids,
            "aircraft": self.aircraft,
        }[kind]

    def contains(self, atom: Atom) -> bool:
        """True when some tool established this atom this turn."""
        if atom.canon in self._bucket(atom.kind):
            return True
        # An identifier that the scanner classified as a station (or the other
        # way round) is still attested if the other bucket holds it. The two
        # patterns overlap on shapes like a three letter aircraft code.
        if atom.kind == "station" and atom.canon in self.identifiers:
            return True
        if atom.kind == "identifier" and atom.canon in self.stations:
            return True
        if atom.kind == "date" and atom.canon.startswith("--"):
            # A partial date matches any attested date with that month and day.
            suffix = atom.canon[1:]
            return any(day.endswith(suffix) for day in self.dates)
        return False

    def is_fact_backed(self, atom: Atom) -> bool:
        return atom.key in self.fact_backed

    def size(self) -> int:
        return sum(
            len(bucket)
            for bucket in (
                self.numbers,
                self.durations,
                self.currencies,
                self.dates,
                self.times,
                self.identifiers,
                self.stations,
                self.rule_ids,
                self.aircraft,
            )
        )

    # --------------------------------------------------------- registration

    def _add(self, kind: AtomKind, canon: str | None, *, fact_backed: bool) -> None:
        if not canon:
            return
        self._bucket(kind).add(canon)
        if fact_backed:
            self.fact_backed.add((kind, canon))

    def register_scalar(
        self,
        value: object,
        *,
        unit: str | None = None,
        fact_backed: bool = False,
    ) -> None:
        """Register one deterministic value under every form it can take."""
        if value is None or isinstance(value, bool):
            return
        if self._scalars_seen >= _MAX_SCALARS:
            return
        self._scalars_seen += 1

        if isinstance(value, datetime_cls):
            self._add("date", value.date().isoformat(), fact_backed=fact_backed)
            self._add("date", _partial(value.date().isoformat()), fact_backed=fact_backed)
            self._add("time", canonical_time(value), fact_backed=fact_backed)
            self._add("number", str(value.year), fact_backed=fact_backed)
            return
        if isinstance(value, date_cls):
            iso = value.isoformat()
            self._add("date", iso, fact_backed=fact_backed)
            self._add("date", _partial(iso), fact_backed=fact_backed)
            self._add("number", str(value.year), fact_backed=fact_backed)
            return

        if isinstance(value, int | float):
            self._register_number(value, unit=unit, fact_backed=fact_backed)
            return

        if not isinstance(value, str):
            return

        text = value.strip()
        if not text:
            return

        # A timestamp string is a date and a clock time.
        split = canonical_datetime(text)
        if split is not None:
            day, clock = split
            self._add("date", day, fact_backed=fact_backed)
            self._add("date", _partial(day), fact_backed=fact_backed)
            self._add("time", clock, fact_backed=fact_backed)
            self._add("number", day[:4], fact_backed=fact_backed)
            return

        iso_day = canonical_date(text)
        if iso_day is not None:
            day = iso_day
            self._add("date", day, fact_backed=fact_backed)
            self._add("date", _partial(day), fact_backed=fact_backed)
            if not day.startswith("--"):
                self._add("number", day[:4], fact_backed=fact_backed)
            return

        if _looks_like_clock(text):
            self._add("time", canonical_time(text), fact_backed=fact_backed)
            return

        number = canonical_number(text)
        if number is not None:
            self._register_number(text, unit=unit, fact_backed=fact_backed)
            return

        ident = canonical_identifier(text)
        if ident and _looks_like_identifier(ident):
            kind: AtomKind = (
                "rule_id"
                if ident.startswith("RULE-")
                else "station"
                if len(ident) == 3
                else "aircraft"
                if _looks_like_aircraft(ident)
                else "identifier"
            )
            self._add(kind, ident, fact_backed=fact_backed)
            # Register under `identifier` as well so the cross-bucket lookup in
            # `contains` never depends on the scanner and the registrar having
            # classified the same string identically.
            self._add("identifier", ident, fact_backed=fact_backed)
            return

        # Anything longer is prose written by deterministic code: a derivation,
        # an explanation, a rule trace's arithmetic. Every atom inside it was
        # produced by the rules engine, so re-scan and register.
        if len(text) > 3:
            self.register_prose(text, fact_backed=fact_backed)

    def _register_number(
        self, value: object, *, unit: str | None, fact_backed: bool
    ) -> None:
        canon = canonical_number(value)
        if canon is None:
            return
        self._add("number", canon, fact_backed=fact_backed)
        self._add("currency", canonical_currency(value), fact_backed=fact_backed)

        # Unit renderings. A value known to be in hours registers its minute
        # equivalent explicitly (this is what makes 61.33h == 61h20m); a value
        # with no declared unit registers both readings, because the unit is
        # the model's assertion and the value is the fact.
        if unit == "hours":
            self._add(
                "duration",
                _as_str(canonical_duration_minutes(hours=value)),
                fact_backed=fact_backed,
            )
        elif unit == "minutes":
            self._add(
                "duration",
                _as_str(canonical_duration_minutes(minutes=value)),
                fact_backed=fact_backed,
            )
        elif unit in (None, "count", "percent", "days", "inr"):
            self._add(
                "duration",
                _as_str(canonical_duration_minutes(hours=value)),
                fact_backed=fact_backed,
            )
            self._add(
                "duration",
                _as_str(canonical_duration_minutes(minutes=value)),
                fact_backed=fact_backed,
            )

    def register_prose(self, text: str, *, fact_backed: bool) -> None:
        """Register every atom inside a string authored by deterministic code."""
        for atom in extract_atoms(text):
            self._add(atom.kind, atom.canon, fact_backed=fact_backed)
            if atom.kind == "duration":
                # A duration in a derivation also attests its numeric reading,
                # so "over by 1.33h" covers a later bare "1.33".
                minutes = int(atom.canon)
                self._add("number", canonical_number(minutes / 60), fact_backed=fact_backed)
            if atom.kind == "date" and not atom.canon.startswith("--"):
                self._add("date", _partial(atom.canon), fact_backed=fact_backed)
                self._add("number", atom.canon[:4], fact_backed=fact_backed)

    def register_fact(self, fact: Fact) -> None:
        """The primary channel. Typed, so the unit equivalences are exact."""
        self.register_scalar(fact.value, unit=fact.unit, fact_backed=True)
        rendered = fact.rendered()
        if rendered:
            self.register_scalar(rendered, unit=fact.unit, fact_backed=True)
        if fact.derivation:
            self.register_prose(fact.derivation, fact_backed=True)

    def register_container(self, node: object, *, depth: int = 0) -> None:
        """Walk a payload, registering every scalar it reaches."""
        if depth > _MAX_DEPTH or self._scalars_seen >= _MAX_SCALARS:
            return
        if isinstance(node, Fact):
            self.register_fact(node)
            return
        if hasattr(node, "model_dump"):
            dumped: Any = node.model_dump(mode="python")
            self.register_container(dumped, depth=depth + 1)
            return
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and key in _IGNORED_KEYS:
                    continue
                self.register_container(value, depth=depth + 1)
            return
        if isinstance(node, str | bytes):
            self.register_scalar(node)
            return
        if isinstance(node, Sequence):
            # The length of a returned list is a deterministic property of the
            # tool result, so "all three legs" is attested by a three item list
            # even when no tool emitted a count Fact.
            self._add("number", str(len(node)), fact_backed=False)
            for item in node:
                self.register_container(item, depth=depth + 1)
            return
        self.register_scalar(node)


def build_attested_set(
    envelopes: Sequence[ToolEnvelope],
    *,
    include_payload_channel: bool = True,
) -> AttestedSet:
    """Assemble the attested set for one turn."""
    attested = AttestedSet()
    for envelope in envelopes:
        if not envelope.ok:
            # A failed lookup attests nothing, including its own arguments.
            # `get_crew_detail(crew_id="C-9999")` failing is precisely the case
            # where the identifier was invented.
            continue
        for fact in envelope.facts:
            attested.register_fact(fact)
        if not include_payload_channel:
            continue
        for key, value in envelope.args.items():
            if key in _IGNORED_KEYS:
                continue
            attested.register_container(value)
        attested.register_container(envelope.payload)
        for step in envelope.trace:
            attested.register_prose(step.detail, fact_backed=False)
            attested.register_prose(step.label, fact_backed=False)
        for citation in envelope.citations:
            attested.register_scalar(citation.pointer)
            if citation.note:
                attested.register_prose(citation.note, fact_backed=False)
    return attested


def _partial(iso_date: str) -> str | None:
    if len(iso_date) == 10 and iso_date[4] == "-":
        return f"--{iso_date[5:]}"
    return None


def _as_str(value: int | None) -> str | None:
    return None if value is None else str(value)


def _looks_like_clock(text: str) -> bool:
    stripped = text.strip().rstrip("Z")
    parts = stripped.split(":")
    return len(parts) in (2, 3) and all(part.isdigit() for part in parts)


def _looks_like_identifier(text: str) -> bool:
    if len(text) > 40:
        return False
    return any(character.isalnum() for character in text) and " " not in text


def _looks_like_aircraft(text: str) -> bool:
    return bool(text) and text[0] in "AB" and text[1:].isdigit()
