"""The grounding check.

Deterministic. No model call, no network, no clock. Given a drafted answer and
the envelopes the tools returned during the same turn, it decides whether every
checkable atom in the prose traces back to something the deterministic layer
computed.

The algorithm is four steps:

1. Extract every atom from the prose (`extract.py`).
2. Build the attested set from the envelopes (`attest.py`).
3. Drop atoms the allowlist exempts (`allowlist.py`).
4. Anything left over that is not in the attested set is an `UnattestedAtom`.

When it fires, the fix is to make the tool emit the missing `Fact`, never to
loosen the check. That rule is in `docs/CONTRACTS.md` and it is the reason this
module has no configuration knob that makes rejections go away.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from crewops.contracts import (
    ToolEnvelope,
    UnattestedAtom,
    VerificationReport,
    VerificationStatus,
)
from crewops.verify.allowlist import is_allowlisted
from crewops.verify.attest import AttestedSet, build_attested_set
from crewops.verify.extract import Atom, extract_atoms

__all__ = ["Verifier", "VerifierPolicy", "verify_answer"]

#: How many unattested atoms to name in the report. Beyond this the repair
#: prompt stops being readable and the model starts ignoring it.
_DEFAULT_REPORT_CAP: Final = 12


@dataclass(frozen=True, slots=True)
class VerifierPolicy:
    """Knobs that change how strict the check is, not whether it runs."""

    #: When true, only the `Fact` channel attests. Payload scalars, trace prose
    #: and call arguments stop counting. This is the mode that proves the
    #: tool layer is emitting a Fact for every number it lets into an answer.
    require_fact_attestation: bool = False

    #: Cap on named atoms in the report.
    report_cap: int = _DEFAULT_REPORT_CAP


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """The report plus the working, so callers can explain a rejection."""

    report: VerificationReport
    atoms: tuple[Atom, ...]
    attested: AttestedSet

    @property
    def ok(self) -> bool:
        return self.report.status in (
            VerificationStatus.VERIFIED,
            VerificationStatus.REPAIRED,
            VerificationStatus.SKIPPED,
        )


class Verifier:
    """Checks a drafted answer against what the tools returned."""

    def __init__(self, policy: VerifierPolicy | None = None) -> None:
        self.policy = policy or VerifierPolicy()

    def check(
        self,
        text: str,
        envelopes: Sequence[ToolEnvelope],
        *,
        repair_attempts: int = 0,
    ) -> VerificationOutcome:
        """Run the check and return the report together with its working."""
        atoms = tuple(extract_atoms(text))
        attested = build_attested_set(
            envelopes,
            include_payload_channel=not self.policy.require_fact_attestation,
        )

        checkable = [atom for atom in atoms if not is_allowlisted(atom)]
        if not checkable:
            return VerificationOutcome(
                report=VerificationReport(
                    status=VerificationStatus.SKIPPED,
                    checked_atoms=0,
                    attested_atoms=0,
                    repair_attempts=repair_attempts,
                    note=(
                        "No checkable figure, identifier or date in the answer. "
                        "Nothing to ground."
                    ),
                ),
                atoms=atoms,
                attested=attested,
            )

        unattested: list[UnattestedAtom] = []
        attested_count = 0
        payload_only = 0
        seen: set[tuple[str, str]] = set()

        for atom in checkable:
            if attested.contains(atom):
                attested_count += 1
                if not attested.is_fact_backed(atom):
                    payload_only += 1
                continue
            if atom.key in seen:
                continue
            seen.add(atom.key)
            unattested.append(
                UnattestedAtom(
                    atom=atom.text.strip(),
                    kind=atom.contract_kind,  # type: ignore[arg-type]
                    context=_trim(atom.sentence),
                )
            )

        status = (
            VerificationStatus.VERIFIED
            if not unattested
            else VerificationStatus.REJECTED
        )
        report = VerificationReport(
            status=status,
            checked_atoms=len(checkable),
            attested_atoms=attested_count,
            unattested=unattested[: self.policy.report_cap],
            repair_attempts=repair_attempts,
            note=self._note(
                checked=len(checkable),
                attested=attested_count,
                payload_only=payload_only,
                unattested=len(unattested),
            ),
        )
        return VerificationOutcome(report=report, atoms=atoms, attested=attested)

    def verify(
        self,
        text: str,
        envelopes: Sequence[ToolEnvelope],
        *,
        repair_attempts: int = 0,
    ) -> VerificationReport:
        """The report only. Convenience wrapper over `check`."""
        return self.check(text, envelopes, repair_attempts=repair_attempts).report

    def _note(
        self, *, checked: int, attested: int, payload_only: int, unattested: int
    ) -> str:
        parts = [f"{attested}/{checked} atoms attested"]
        if payload_only:
            parts.append(
                f"{payload_only} attested by tool payload only, with no Fact behind them"
            )
        if unattested:
            parts.append(f"{unattested} unattested")
        if self.policy.require_fact_attestation:
            parts.append("strict mode: Fact channel only")
        return "; ".join(parts) + "."


def verify_answer(
    text: str,
    envelopes: Sequence[ToolEnvelope],
    *,
    policy: VerifierPolicy | None = None,
) -> VerificationReport:
    """One shot check, for callers that do not need to keep a Verifier."""
    return Verifier(policy).verify(text, envelopes)


_WHITESPACE: Final = re.compile(r"\s+")


def _trim(sentence: str, limit: int = 220) -> str:
    collapsed = _WHITESPACE.sub(" ", sentence).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"
