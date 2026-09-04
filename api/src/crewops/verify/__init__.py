"""The grounding guard: deterministic, model free, and the reason the system's
central claim is true rather than merely asserted.

Public surface:

    from crewops.verify import Verifier, VerifierPolicy, verify_answer

The equivalence normaliser is importable on its own, without pulling in the
rest of the package, for anyone who needs the same "are these the same fact"
rules elsewhere (the eval scorecard's fact-containment grader, for instance):

    from crewops.verify.normalise import canonical_duration_minutes
"""

from crewops.verify.allowlist import SAFE_UPPERCASE_TOKENS, is_allowlisted
from crewops.verify.attest import AttestedSet, build_attested_set
from crewops.verify.extract import Atom, AtomKind, extract_atoms, sentences_of
from crewops.verify.normalise import (
    canonical_currency,
    canonical_date,
    canonical_datetime,
    canonical_duration_minutes,
    canonical_identifier,
    canonical_number,
    canonical_time,
    hours_to_minutes,
    render_duration,
)
from crewops.verify.verifier import (
    VerificationOutcome,
    Verifier,
    VerifierPolicy,
    verify_answer,
)

__all__ = [
    "SAFE_UPPERCASE_TOKENS",
    "Atom",
    "AtomKind",
    "AttestedSet",
    "VerificationOutcome",
    "Verifier",
    "VerifierPolicy",
    "build_attested_set",
    "canonical_currency",
    "canonical_date",
    "canonical_datetime",
    "canonical_duration_minutes",
    "canonical_identifier",
    "canonical_number",
    "canonical_time",
    "extract_atoms",
    "hours_to_minutes",
    "is_allowlisted",
    "render_duration",
    "sentences_of",
    "verify_answer",
]
