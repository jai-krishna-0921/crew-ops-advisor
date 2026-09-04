# rules

The legality kernel. Seven rules, `RuleTrace` per evaluation, no language model
reachable from here at any depth. `tests/test_boundary.py` walks the import
graph and fails the build if that stops being true.

Everything below is verified against the shipped answer keys and against the
dataset's own `generate.py`, which is the reference implementation that
produced them. **These are not style preferences. Each one changes an answer.**

## The comparison directions

| Rule | Breach test | The case that proves it |
|---|---|---|
| RULE-FDP-01 | `fdp > limit` (strict) | `DX454-2026-09-17` is rated "delay (crew legal)" at exactly 12.0h against a 12.0h limit |
| RULE-DUTY-02 | `total > 60` (strict) | a 60.00h projection is legal |
| RULE-FLT-03 | `total > 100` (strict) | never binds: the dataset peak is 79.28h |
| RULE-REST-04 | `rest < 12` (strict) | exactly 12.0h rest is legal |
| RULE-CERT-06 | `valid_to < duty_date` | C-5417's `recurrent_training` expires 2026-09-17 and their 09-17 duty would be **legal**; the 09-19 duty is not |
| RULE-QUAL-05 | `aircraft_type not in ratings` | C-2091 is ATR72 only |
| RULE-BASE-07 | different base and no positioning | only DEL to BLR positioning exists |

Float slack is `EPSILON = 1e-6`, applied as `observed > limit + EPSILON` and
`rest < limit - EPSILON`, so a value sitting exactly on a limit is legal in
both directions. That is the reference implementation's behaviour.

## The windows are calendar dates

RULE-DUTY-02 is `[end - 6, end]` and RULE-FLT-03 is `[end - 27, end]`, both
inclusive UTC calendar dates. A rolling 168 hour clock gives different and
wrong answers. `WorldOverlay.window_hours` is the single implementation.

## The 2026-09-14 overlap

`daily_history` runs to 2026-09-14 and the roster week starts 2026-09-14, so
that date contributes from **both** sources. Eleven crew are double counted.

This is the dataset's own convention, not a bug:

- Including the roster contribution reproduces `duty_hours_7d` for **150 of
  150** crew and `flight_hours_28d` for 150 of 150.
- Dropping it reproduces `duty_hours_7d` for only **118 of 150**, and
  `150 - 118 = 32` is exactly the number of crew rostered on 2026-09-14.
- The dataset's own `validate.py` asserts the double counted figure.

`tests/core/test_clocks.py` pins all three numbers. Do not "fix" it: doing so
moves 32 crew's duty totals and breaks every answer key downstream.

## The cumulative add across cover days

When simulating a multi-day cover, **day 2's 7 day window already contains day
1's cover duty**:

```
prior  = window_hours(candidate, day, 7, duty) - (their own duties on the pairing being replaced)
added  = sum(duty_hours of every cover day whose date <= day)      # cumulative
total  = round(prior + added, 2)
```

This is the whole reason:

- **C-2087** breaches on *both* days of P-2291: 51.83 + 9.50 = 61.33h, then
  40.83 + 9.50 + 10.75 = 61.08h.
- **C-3305** passes day 1 at 59.50h and fails day 2 at 68.25h (`8h15m` over).
  Counting only day 2's own duty gives 58.75h and wrongly passes.

A candidate must be legal on **every** day of the cover. `LegalityReport.overall`
is the worst day, never an average.

## The subtraction for a role swap

If the candidate already holds a seat on the pairing being covered, their own
duties on it come out of the base window before the cover goes in, or they are
counted twice. That is the `exclude_pairing` argument, and
`WorldOverlay.window_hours` deliberately still includes those duties so the
subtraction is explicit and visible rather than hidden in the window function.

## RULE-QUAL-05 short-circuits

A rating failure suppresses every other reason for that candidate. The shipped
`excluded_candidates` show `"RULE-QUAL-05: no ATR72 rating"` alone, with no
accompanying rest or duty reason, even where those also apply. Emitting every
reason produces text that does not match the keys even where the verdict does.

RULE-BASE-07 short-circuits ahead of it, on the same principle.

## Evaluation order

`assess_cover` mirrors `generate.py` exactly, because the order determines
which reason is reported when several apply:

1. RULE-BASE-07, short-circuits when no positioning exists.
2. RULE-QUAL-05, short-circuits everything below.
3. Per cover day: RULE-CERT-06, then RULE-FDP-01.
4. Own duties merged with the cover, sorted by report time: RULE-REST-04
   pairwise, then double bookings as a separate pass.
5. Per cover day: RULE-DUTY-02 with the cumulative add, then RULE-FLT-03.

## `valid_from` is unusable

Generated as `valid_to - 730 days` and never corrected after the engineered
expiries. One record (`C-2087` licence) has `valid_from > valid_to`, and
several show a future start date for a currently flying crew member. **Check
`valid_to` only.** There is a test asserting the string `.valid_from` does not
appear in `engine.py`.

## RULE-FLT-03 is inert but implemented

The peak 28 day block total across all 150 crew and all seven dates is 79.28h
against a 100h limit. It is one of the seven, so it is evaluated and reported
like the others. No shipped key exercises a breach, and its failure message
format is therefore unverified against the keys.

## `Verdict.NOT_APPLICABLE` versus `INSUFFICIENT_DATA`

- **NOT_APPLICABLE**: the rule was evaluated and had nothing to measure, for
  example RULE-REST-04 on a date with no adjacent duty. The reason is stated.
- **INSUFFICIENT_DATA**: the rule was not reached, or the inputs are missing.
  A short-circuited candidate's remaining rules are INSUFFICIENT_DATA, never
  NOT_APPLICABLE and never PASS.

Neither is PASS. A rule that does not appear in a day's traces would read as a
passing rule, so `_complete` guarantees all seven are present on every day.
