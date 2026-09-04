# Agent design

How the language model is wired in, what it is allowed to decide, and what
stops it deciding anything else.

The short version: the model chooses which computations to run and how to say
the result. Every fact, every number and every verdict comes from deterministic
code, and three independent mechanisms enforce that rather than requesting it.

---

## The graph

```
START
  |
  v
route ----------------- out of scope --------------> abstain --> END
  |
  v
plan            the model states its intent before any tool runs
  |
  v
agent <----------------------+
  |  |                       |
  |  +--- tool calls ---> tools
  |                           (executes against ToolSurface, accumulates
  |                            envelopes into turn state)
  v
verify
  |
  +-- verified ------------------------------------> END
  |
  +-- unattested atoms ------> repair --------> agent
  |
  +-- guard failure ---------> policy_repair -> agent
  |
  +-- second failure --------> abstain --------> END
```

Implemented in `api/src/crewops/agent/graph.py` as a LangGraph `StateGraph`
over a typed `TurnState`.

### Node responsibilities

| Node | Does | Model involved |
|---|---|---|
| `route` | Triage. In scope at all? Which tier? An out of scope question short circuits before any tool planning is paid for. | yes, cheaply |
| `plan` | States the intent and the steps, emitted as a `PlanEvent` before any tool runs | yes |
| `agent` | The tool calling loop. Chooses tools and arguments. | yes |
| `tools` | Executes against the injected `ToolSurface`, accumulates every `ToolEnvelope` into turn state | no |
| `verify` | Grounding check and structural guards | no |
| `repair` | One correction pass, told exactly which atoms were unattested | yes |
| `policy_repair` | One correction pass, told exactly which guard failed and which tool would fix it | yes |
| `abstain` | Builds a specific, actionable `Abstention` | no |

The agent is constructed with a `ToolSurface` injected. It never imports the
concrete registry, which is why the whole graph is testable against a
`FakeTools` with no dataset and no key.

---

## Two different kinds of wrong, and two different guards

This is the part of the design worth arguing about, so it is worth stating
precisely.

**The verifier checks values.** Given the drafted prose and every envelope from
this turn, it asks: does every number, duration, currency amount, date, time,
identifier, station code, rule id and aircraft type in this sentence trace back
to a `Fact` the deterministic layer produced?

**The guards check entitlement.** They ask a different question: was this answer
allowed to exist at all?

The distinction matters because of a case the verifier cannot catch. Take:

> C-3310 is legal for P-2291.

Every atom in that sentence can be attested. `C-3310` is a real crew id the
tools returned. `P-2291` is a real pairing the tools returned. And the sentence
can still be false, because **a verdict is a relation between values, not a
value.** No amount of token matching catches a wrong relation.

What catches it is refusing to accept a verdict that no rules engine produced.
That is `verdict_guard`, and it is why the guards exist as a separate layer
rather than as more regex in the verifier.

### The guards, in `agent/guards.py`

| Guard | Refuses | Because |
|---|---|---|
| `tier_guard` | A Tier 2 or 3 answer whose tool calls were all in `RETRIEVAL_ONLY` | Retrieval establishes what is. It does not establish what follows. This is the guard that stops the system degrading into a fluent lookup with a confident tone. |
| `verdict_guard` | Any legality claim with no `check_legality` (or cover search) envelope this turn | A verdict is computed, never inferred |
| `ranking_guard` | Any ranked recommendation with no cover search envelope | Ranking needs every candidate enumerated, rule checked and priced, including the rejected ones |
| `substance_guard` | An empty answer, or a bare refusal with no reason | A refusal has to name what was missing and what the system can answer instead |

Each failure names the tools that would fix it, so the repair pass is specific
rather than scolding. "Call `check_legality` for C-3310 on P-2291" is
actionable. "Be more careful" is not.

---

## The verifier

`api/src/crewops/verify/`. Deterministic: no model call, no network, no clock.

Four steps:

1. **Extract** (`extract.py`) every checkable atom from the prose. The scanner
   runs every pattern over the whole string, then resolves overlaps by earliest
   match and, at equal start, longest. That ordering is what stops `INR 18,500`
   from also yielding the bare numbers `18` and `500`, and what stops the
   aircraft tail `VT-DXB` from yielding the station code `DXB`.

2. **Attest** (`attest.py`) from the envelopes. Two channels, and the report
   says which one carried each atom so the gap between them stays visible. The
   primary channel is every `Fact` on every successful envelope. Because facts
   are typed, `unit="hours"` registers the duration equivalence as well as the
   bare number, and the `derivation` string is re-scanned so the operands inside
   `51.83h prior + 9.50h added = 61.33h against a 60.00h limit` are attested too.

3. **Normalise** (`normalise.py`) both sides to a canonical form. This is the
   part that is easy to get wrong and it is the single source of truth for "are
   these two renderings the same fact". `61.33`, `61.33h`, `61h20m` and
   `61 hours 20 minutes` are one fact, and the shipped answer keys render
   durations in the `h/m` form while the arithmetic is decimal. The module has no
   dependency on the rest of the system precisely so the eval scorecard's
   fact-containment grader imports the same rules. There is one normaliser, so
   the verifier and the grader cannot disagree.

4. **Decide.** Any atom with no attestation becomes an `UnattestedAtom`
   carrying its surrounding sentence. The turn gets exactly one repair pass,
   naming the offending atoms. A second failure abstains. Never a third pass,
   never a silent pass-through.

### The allowlist

`allowlist.py` holds exactly four entries, each with a written justification,
and `test_allowlist_stays_small` fails if it grows past the documented size.

That test is a deliberate speed bump. A permissive allowlist is how a grounding
check quietly stops working: nothing fails, the guarantee just evaporates. Any
growth should be an argued decision, not a convenience.

---

## Prompts are the last line, not the first

`agent/prompts.py`, versioned, in one module, each constraint commented with
why it is there.

The system prompt states the boundary plainly: you plan and explain, you never
compute, you never state a figure a tool did not return, and when you cannot
answer reliably you say so and say what was missing. It also reinforces that
abstention is a correct outcome rather than a failure, because a model that
believes refusing is failing will guess.

None of that is relied upon. Every guarantee above is enforced by a graph edge
or a deterministic check. The prompt makes the model likely to comply; the graph
makes compliance the only path to an answer.

---

## Running without a key

Everything works with no `ANTHROPIC_API_KEY`. `api/src/crewops/resolve/` matches
the question against a fixed set of shapes, calls the same tools, and renders
through the same verifier and the same guards. Replies are marked
`mode=DETERMINISTIC` and the UI shows the badge, because hiding which path
answered would overstate the system.

It is demo insurance, and it is also the cleanest available proof of the central
claim: the deterministic path has no model in it at all and still answers, with
the same facts and the same arithmetic. If the model were producing the facts,
this path could not exist.

When it cannot match a shape it abstains and says exactly that, rather than
guessing. It is deliberately kept small: it is a fallback, not a second product.

---

## Latency

The rubric says a 45 second response is not a decision aid. The tool loop is
capped at roughly 8 iterations and the turn is capped on wall clock. Progress
events stream throughout, so the wait is legible rather than blank: the plan
appears first, then tool chips resolve one by one with their latencies, then
provisional text, then the grounding check, then the settled answer.

Streamed tokens render visibly provisional until the `reply` event lands.
Presenting streaming text as final would overstate what the system knows at that
moment, which is the failure this whole design exists to avoid.

---

## What this design does not handle

Stated plainly, because overstating capability scores badly and, more
importantly, because a controller needs to know where the tool stops.

- **Compound questions.** "Who is on reserve and which flights are at risk" is
  two questions. The agent path usually handles it; the deterministic path
  matches one shape and answers that one.
- **Rules outside the seven.** Seven rules is the full regulatory scope. A
  question needing an eighth is refused rather than approximated. Double booking
  is carried as a `FeasibilityIssue`, deliberately not as a fake `RULE-` id.
- **Ambiguous referents.** Two crew with similar names, or a flight number
  without a date, abstain and ask rather than picking one.
- **Simultaneous disruptions.** Joint allocation is solved exactly for the small
  case. Independent searches can return the same candidate as rank 1 for two
  gaps, and composing them would put one person on two aircraft. That is the
  single most dangerous output the system could produce, so the joint planner
  refuses rather than composing.
- **The repair pass can fail twice.** When it does, a correct answer is
  sometimes thrown away. We prefer that to shipping an unverified one, but it is
  a real cost and it shows up in the scorecard as an abstention.

Failures graded safe against unsafe are in `docs/FAILURE-ANALYSIS.md`.
