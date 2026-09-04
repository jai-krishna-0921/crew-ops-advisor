# verify

The grounding guard. **Deterministic. No model call, no network, no clock, no
randomness.** Same input, same report, forever.

This package is why the submission's central claim ("the model plans and
explains, it never produces a fact") is true rather than merely asserted. Treat
every change here as a change to the system's guarantee.

## The one rule

**When the guard fires, add the missing `Fact` in the tool. Never loosen the
check.**

There is no configuration that makes a rejection go away. `VerifierPolicy` has
exactly two fields and neither of them weakens the check:
`require_fact_attestation` makes it *stricter*, and `report_cap` only bounds how
many atoms get named in the report.

## Shape

| Module | Responsibility |
|---|---|
| `normalise.py` | Canonical form per kind. The equivalence rules live here and nowhere else. |
| `extract.py` | Scan prose for checkable atoms. Overlap resolved by span, not by pattern order. |
| `attest.py` | Build the attested set from the turn's envelopes. |
| `allowlist.py` | Exactly three exemptions, each with its written justification. |
| `verifier.py` | Compose the four steps into a `VerificationReport`. |

`normalise.py` has no dependency on the rest of the package on purpose: other
workstreams import it directly so there is one definition of "same fact" in the
repository, not two that disagree.

## Invariants

1. **Duration equivalence is whole minutes, rounded half up.** `61.33h`,
   `61h20m`, `61 hours 20 minutes` and the bare number `61.33` are the same
   fact; `61.3h` is not. That two-minute window is the entire tolerance budget.
   The shipped answer keys render 1.33h as `1h20m` and 8.25h as `8h15m`, which
   is the same rule.
2. **Non-duration numbers quantise to two decimal places.** `61.33` and
   `61.330` agree. `61.33` and `61.3` do not.
3. **Identifiers, stations, rule ids and dates compare exactly.** `C-3310` is
   not `C-3301`. `2026-09-15` is not `2026-09-16`. There is no fuzzy match, no
   edit distance, no "close enough".
4. **A failed envelope attests nothing, including its own arguments.** A lookup
   for `C-9999` returning `ok=False` is exactly the case where the model made
   the identifier up.
5. **Arguments of a *successful* call are attested.** The deterministic layer
   accepted that filter and computed against it.
6. **Two channels, counted separately.** The `Fact` channel is primary and
   typed. The payload channel is a fallback over the same deterministic output,
   so it cannot launder anything the model invented; what it loses is citation
   quality. The report's `note` names the payload-only count, and that count is
   a punch list of Facts the tool layer should be emitting.
7. **The allowlist has three entries and a test that fails if it grows.** Adding
   a fourth requires a written justification in `allowlist.py`, in the same
   change.

## What it does not catch

Recorded here so nobody assumes more than it delivers. The long form is in
`docs/AGENT-DESIGN.md`.

- **Spelled-out numbers above twelve.** "sixty one point three three hours"
  is not extracted. The prompt tells the model to use digits; the guard does
  not enforce that.
- **Relations between attested atoms.** Every atom in "C-3310 breaches
  RULE-DUTY-02" can be attested while the sentence is false, because the guard
  checks values, not predicates. This is what the graph's verdict guardrails in
  `agent/guards.py` exist to cover.
- **Unit swaps on an attested value.** If `61.33` is attested, `61.33 minutes`
  passes. Catching this produces false rejections on correct answers, which is
  a worse failure.
- **Coincidental collision.** A wrong number that happens to equal an unrelated
  number elsewhere in a large payload passes. Running with
  `require_fact_attestation=True` removes this class entirely, at the cost of
  requiring complete `Fact` coverage from the tool layer.

## Tests

`api/tests/verify/`. Two halves, and both matter:

- **It fires.** One digit changed, one rupee changed, one crew id transposed,
  one date shifted by a day. Each must be caught.
- **It does not fire.** A correct answer, rendered every legitimate way, must
  pass. A guard that rejects good answers is exactly as useless as one that
  passes bad ones, and it is the failure mode that kills a live demo.
