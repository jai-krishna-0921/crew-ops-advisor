# ops

Candidate search, costing, ranking, simulation and the watchlist. No language
model is reachable from here at any depth, and `tests/test_boundary.py` proves
it by walking the import graph.

Every simulation runs on a `WorldOverlay`, never on the base `WorldState`, so
two simulations cannot contaminate each other and the shipped data is always
recoverable.

Everything below is verified against `scenarios.json` and `questions.json`.
**These are not preferences. Each one changes a headline answer.**

## Candidate enumeration order

`CandidateSearcher.search` reproduces the reference implementation's order,
because the order decides which reason a candidate is excluded for when several
apply:

1. Skip the crew member being replaced, anyone the caller forbids, anyone whose
   **rank does not exactly match** the role, and anyone not `active`.
2. Plan a deadhead if they are not based at the departure station. No
   positioning available is a RULE-BASE-07 exclusion and it stops there.
3. If they are a reserve, test the on-call window against the **required report
   time**, which is the pairing's report plus any positioning delay.
4. Run the full seven rule assessment. RULE-QUAL-05 short-circuits.
5. Price, sort by `(cost, crew_id)`, append cancellation **last**, number
   from 1.

### Non-active crew are dropped silently

`leave` and `training` crew are filtered before any rule runs and never appear
in the exclusion list. They are not rule failures. Reporting them would put
eight names in every exclusion list that the shipped keys do not have.

### Rank equals role, exactly

`Senior Cabin Crew` is not substitutable for `Cabin Crew`, in either direction.

## Reserve on-call windows

- Tested against the **required report time**, never the scenario's narrative
  `reported_utc`. S1's callout is 01:30Z but the required report is 03:00Z, and
  the shipped exclusion string quotes 03:00Z.
- **Inclusive at both ends.** C-3310's window opens at 06:00 and P-2291 reports
  at 06:00Z, which is why C-3310 is the S2 expected choice rather than an
  exclusion.
- After a deadhead, tested against the **delayed** report. C-2210 is tested at
  09:00Z, not 06:00Z, and that changes who is eligible.
- **Only day 1 is window-tested.** Once activated a reserve operates as line
  crew, so day 2 of a multi-day cover has no window test.
- All 16 reserves are on call all 7 days, so the `dates` array never
  discriminates. The window is the only filter.

## Positioning

The rule implemented is **"the earliest arrival into the required station, from
the crew member's base, on the cover date"**, then:

```
new first departure = positioning arrival + 75 min   (15 min transit + 60 min report lead)
new report          = positioning arrival + 15 min
delay_hours         = max(0, new first departure - original first departure)
```

That reproduces every positioning in the shipped keys without hard coding a
station pair: on even dates it selects DX589 (arrives BLR 07:45Z) and on odd
dates DX402 (08:45Z), which is exactly the reference's date parity.

**One deliberate divergence.** The reference hard codes `base == "DEL" and
required == "BLR"` and refuses every other cross-base request outright. This
implementation derives the answer from the schedule instead, so a BLR based
crew member asked to cover a DEL origin duty gets a real positioning plan
rather than a blanket refusal. No shipped answer key exercises that branch:
every scenario's day 1 departs BLR, and the only DEL origin pairing day is
P-2289 day 1 plus the day 2 halves of the two day pairings, which are never
covered from day 2. The generalisation is safer against the held-out set than
the special case would be.

The 75 minute constant is load-bearing. Getting it wrong shifts the delay hours
and therefore the cost.

## Costing

| Fact | Consequence |
|---|---|
| Callout is charged **once per assignment**, not per duty day | two day P-2291 by reserve C-3310 costs 18,500, not 37,000 |
| `hotel_overnight` (4,200) is **never charged in any shipped key** | not applied, including for the DEL overnight |
| There is **no overtime rate** | despite the problem-statement PDF describing one |
| Cancellation is priced **per leg** | 6 legs of P-2291 is 1,500,000, not 250,000 |

Worked deadhead: `18,500 + 6,500 + round(3.0 x 5,400) = 41,200` for C-2210 on
P-2291, with `delay_hours` 3.0.

Every `CostLine` carries a `basis` showing the multiplication, not just a total.

## Ranking

Sort legal options by `(cost_inr, crew_id)`, then **append cancellation last
regardless of its cost**, then number from 1. Cancellation is a last resort,
not a cheap one, and the reference appends it after sorting.

Every `CoverOption` states its trade-offs. An option with no stated downside is
under-analysed, not perfect, and there is a test asserting the list is never
empty.

## The one thing that cannot be matched positionally

The shipped `excluded_candidates` lists are ordered by the generator's internal
crew creation order, which puts the ten engineered crew first. `crew.json` is
written **sorted by `crew_id`**, so that order is not recoverable from the
shipped data.

Every excluded crew member and every reason string reproduces exactly, for all
five cover searches in the scenarios (18, 19, 21, 12 and 12 exclusions). Only
the sequence differs. This engine emits them sorted by `crew_id`, which is
deterministic and explainable. `tests/core/test_cover.py` asserts the mapping
rather than the list, and documents why.

## The two delay models

Both appear in the shipped keys and they answer different questions. Using the
wrong one produces a plausible number and the wrong verdict.

| Model | Where | Arithmetic |
|---|---|---|
| **Release slides, report does not** | S3, a closure part way through a duty | `fdp_after = original duty length + delay` |
| **The whole duty slides** | S4, a tech delay before the first departure | report and release both move, so the length grows by the delay too |

## Station closure

- The window is **half-open, `[start, end)`**. A movement exactly at the reopen
  time is not affected.
- The delay **anchors on the event at the closed station**: the departure when
  the flight departs there inside the window, and the arrival otherwise.
- The target is **reopen plus 30 minutes**, one turnaround.

That reproduces S3's 13 flight set and all 13 delay, FDP, limit and action rows
exactly, including `DX454-2026-09-17` at 12.0h against a 12.0h limit, which is
legal only because the FDP comparison is strict.

The infeasible `action` string separates its clauses with U+2014. It is built
from an escape in `disruption.py` so the output matches the key byte for byte
without an em dash appearing in source we author.

## Partial re-crew changes the FDP limit

Dropping a leg lowers the sector count and therefore **raises** the limit: four
sectors at 12.0h becomes three sectors at 12.5h, and the S4 duty falls from
12.75h to 9.5h. Recompute it; never inherit the original.

## Absence cascades through the whole pairing

Losing a crew member breaks **every day of every pairing they hold**, not just
today's. P-2291 loses its captain on day 1 and day 2 is equally exposed,
because the aircraft overnights at DEL and the cover has to take the pairing
whole.

`ImpactReport.passengers_affected` is the **day of the absence** figure (486 for
S2, three legs at 162 seats), matching the shipped `passengers_at_risk_day1`.
The whole pairing figure (972) is carried as a separate fact, clearly labelled.
Do not sum both days into the headline field.

## Joint allocation

Enumerate the option lists for every gap, forbid the same person covering two,
minimise the total. Cancellation is always available, so a plan always exists.

Ties are real: S6's own note says equal cost mirror assignments are equally
correct, so `JointPlan.alternatives` carries the other optimal plans rather
than pretending one arbitrary pick is the answer. The S6 optimum is 42,500,
which is C-3305 at 18,500 plus any one of ten day-off captains at 24,000.

## Risk scores are a provided input

`risk_signals.json` scores are read, never computed. There is a clean gap
between 0.41 and 0.64 in the shipped data, so any threshold in that range
selects exactly the four engineered scenario crew. `reachability_minutes` is
surfaced but never gates a legality or cost decision: it appears in no shipped
computation.

## Proactive alerting

`alerting.py` projects the running accruals forward over a horizon and reports
which limit gets crossed. It is a different question from `watchlist.py`, which
asks what is worth looking at on one date, and the two are deliberately allowed
to surface the same crew member.

### The roster as shipped contains no limit breach

Across every 48 hour horizon from the snapshot, the peak projected 7 day duty
total is **40.96h against a 60h limit** (C-1694 on 2026-09-16) and the peak
projected 28 day block total is **71.81h against a 100h limit** (C-2907). The
global weekly peaks are 56.4h duty and 79.28h block, both legal.

So a scan of the roster **as it stands** correctly finds nothing under
RULE-DUTY-02 or RULE-FLT-03. Breaches in this dataset come from a *change*:
a sick call, a cover assignment, a delay. Those go through `candidates.py` and
`rules.assess_cover`, not here.

Do not retune `MARGIN_THRESHOLDS` to manufacture alerts on the shipped data.
The thresholds are set against the limits, not against what happens to be in
the file, and a threshold chosen to make a demo look busy is the exact failure
mode this system claims to prevent.

### A clean scan still has to show its working

`AlertScan.closest_approaches` carries the tightest margins found on each limit
rule whether or not anything crossed a threshold, with the same arithmetic a
real breach would carry. This is not padding. A screen that says "no alerts"
and shows nothing is indistinguishable from a scan that failed to run, and a
controller who cannot tell those apart stops trusting the brief.

The headline states the limit position even when every raised alert is
certification work, for the same reason: reading "6 to raise" and assuming duty
hours are among them is reading the wrong crisis.

### The horizon filters on report time, not date

A duty reporting at 17:00Z tomorrow is inside a 48 hour horizon and one
reporting at 19:00Z the day after is not. Rounding either to a calendar date
puts the wrong duties in the window and inflates every projection built on it.

The **window** the limit is measured over is still inclusive calendar dates,
`[end - 6, end]` and `[end - 27, end]`, and comes from
`WorldOverlay.window_hours`. Two different notions of time, both load-bearing.

### banked plus committed

`projected_hours` is `window_hours`, split into what is already accrued
(`banked_hours`) and what the duties inside the horizon add (`committed_hours`).
The split is the actionable part: "you will be at 61.33h" tells a controller
nothing, "48.50h is banked and the next 48 hours add 12.83h" tells them which
duty to move. The verdict and the `arithmetic` string come from
`LegalityEngine.check_duty_window` and `check_flight_window`, never from a
second comparison written here.

### Certifications are swept over 30 days, not 48 hours

A renewal is a booking, not a swap. `DEFAULT_CERT_HORIZON_DAYS` matches
`watchlist.CERT_HORIZON_DAYS` on purpose: two modules disagreeing about when a
certificate becomes urgent is a bug a controller finds before we do.

An expiry with a rostered duty after it is CRITICAL and already illegal today.
An expiry with nothing behind it is a renewal to book, and is never CRITICAL.
Collapsing the two is how a desk learns to ignore the brief. C-5417 is the
critical case and the dataset flags it itself, so an alerting module that
misses it is demonstrably not working.
