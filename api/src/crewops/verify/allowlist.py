"""The allowlist: atoms that are safe without attestation.

Every entry here weakens the guarantee the whole system rests on, so the list
is short, explicit, and each entry carries the reason it is safe. The test
`test_allowlist_stays_small` fails if it grows past the documented size, which
is a deliberate speed bump: a permissive allowlist is how a grounding check
quietly stops working.

There are exactly three entries.
"""

from __future__ import annotations

import re
from typing import Final

from crewops.verify.extract import Atom

__all__ = ["ALLOWLIST_SIZE", "SAFE_UPPERCASE_TOKENS", "is_allowlisted"]

# ---------------------------------------------------------------------------
# Entry 1: three-letter uppercase tokens that are not station codes.
#
# The scanner treats any bare three-letter uppercase token as a candidate
# station, because that is the only way to catch an invented station code. The
# cost is that ordinary aviation acronyms in an answer look like stations. The
# tokens below are vocabulary, not data: none of them can be wrong, because
# none of them asserts anything about the dataset.
#
# Note what is deliberately absent: every real station code (BLR, BOM, CCU,
# COK, DEL, GOI, HYD, MAA). Those must be attested, because "flights depart
# HYD" is a claim about the data even when HYD exists.
# ---------------------------------------------------------------------------
SAFE_UPPERCASE_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "UTC",  # the dataset's single timezone, stated in rules.json
        "FDP",  # flight duty period, the RULE-FDP-01 term of art
        "ETA",  # estimated time of arrival
        "ETD",  # estimated time of departure
        "PIC",  # pilot in command
        "SIC",  # second in command
        "ATC",  # air traffic control
        "SOP",  # standard operating procedure
        "EOD",  # end of day
        "TBD",  # to be determined
        "SMS",  # a draft_notification channel value
        "APP",  # a draft_notification channel value
        "AND",  # survives in a shouted heading
        "NOT",  # survives in a shouted heading
        "ALL",  # survives in a shouted heading
        "INR",  # the currency, when it appears with no amount beside it
    }
)

# ---------------------------------------------------------------------------
# Entry 2: the rule count.
#
# `len(ALL_RULE_IDS) == 7` is a compile-time constant of `contracts/rules.py`
# and a fixed property of the problem statement, not a value read out of a
# tool result. An answer that says "all seven rules were checked" is stating a
# property of the system, not of the dataset.
# ---------------------------------------------------------------------------
_RULE_COUNT_CONTEXT: Final = re.compile(r"\brule", re.IGNORECASE)
_RULE_COUNT_CANON: Final = "7"

# ---------------------------------------------------------------------------
# Entry 3: a small positional ordinal after a structure word.
#
# "day 1 of P-2291", "option 2", "leg 3", "step 1". The number is a position
# inside a structure a tool returned, not a measurement of anything. Requiring
# attestation here produces constant false rejections on correct answers,
# because a two day pairing has a day 1 whether or not any tool emitted the
# integer 1 as a Fact.
#
# Bounded three ways, because this is the loosest of the four entries:
#   - the preceding word must be one of a fixed, short list;
#   - the number must be 1 to 9, so it cannot launder a duty figure or a cost;
#   - it must be a bare integer, so "day 1.33" is still checked.
#
# The residual risk is a wrong ordinal ("option 4" when three were returned).
# That is a low consequence error next to a wrong duty hour, and the ranking
# guard in agent/guards.py already refuses a ranked answer that no cover search
# stands behind.
# ---------------------------------------------------------------------------
_ORDINAL_CONTEXT: Final = re.compile(
    r"\b(?:day|option|leg|step|rank|phase|choice|sector|part)\s*$", re.IGNORECASE
)
_ORDINAL_VALUES: Final[frozenset[str]] = frozenset("123456789")

# ---------------------------------------------------------------------------
# Entry 4: years that sit inside an attested date.
#
# This one is not implemented here. It is implemented in `attest.py` by
# registering the year component of every attested date as an attested number,
# which is strictly safer than an allowlist: the year 2026 is only safe
# because some tool returned a 2026 date this turn, and if none did, the year
# is not safe and must be flagged. Recorded here so the list of exemptions is
# in one place even though one of them lives elsewhere.
# ---------------------------------------------------------------------------

#: Asserted by a test. Bump it only alongside a written justification above.
ALLOWLIST_SIZE: Final[int] = 4


def is_allowlisted(atom: Atom) -> bool:
    """True when this atom is safe without attestation.

    Keep this function boring. Anything that needs to look at tool results
    belongs in `attest.py`, not here.
    """
    if atom.kind == "station" and atom.canon in SAFE_UPPERCASE_TOKENS:
        return True
    if atom.kind != "number":
        return False
    if (
        atom.canon == _RULE_COUNT_CANON
        and _RULE_COUNT_CONTEXT.search(atom.sentence) is not None
    ):
        return True
    return atom.canon in _ORDINAL_VALUES and _is_positional(atom)


def _is_positional(atom: Atom) -> bool:
    """True when the atom is preceded by a structure word in its own sentence."""
    prefix = atom.sentence[: atom.sentence.find(atom.text.strip())]
    return bool(prefix) and _ORDINAL_CONTEXT.search(prefix) is not None
