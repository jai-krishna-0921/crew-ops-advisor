# contracts

**Do not edit this package without saying so.**

These types are the seam three parallel workstreams build against:

- `crewops.domain`, `crewops.rules`, `crewops.ops`, `crewops.store` and
  `crewops.tools` **produce** them.
- `crewops.agent` and `crewops.verify` **consume** them.
- `crewops.server` **serialises** them, and `web/src/lib/contracts.ts`
  **mirrors** them.

A signature change here breaks work in flight somewhere else. If you need a
field that is not here, raise it rather than adding it locally, and update
`docs/CONTRACTS.md` and the TypeScript mirror in the same change.

## Invariants

1. **No model client import in this package, ever.** These are data types.
2. **No behaviour.** Validators and derived properties are fine. Business logic
   is not. If you are writing an `if` that encodes a rule, it belongs in
   `crewops.rules`.
3. **Every numeric payload field has a matching `Fact`.** The verifier only
   knows what the facts tell it. A number that reaches the UI without a `Fact`
   is a number nobody checked.
4. **`Verdict.INSUFFICIENT_DATA` is not `Verdict.PASS`.** Never collapse the
   two. Silence about a rule is not compliance with it.
5. **`LegalityReport.overall` is the worst day, never an average.** A candidate
   legal on day one and breaching on day two is not a legal candidate.
6. Keep `TOOL_NAMES` in sync with the `ToolSurface` protocol methods. There is
   a test that asserts they match.
