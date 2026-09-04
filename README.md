# Crew Ops Advisor

A conversational decision aid for an airline Crew Control desk, built for the
dCortex "Agentic Crew Ops Advisor" hackathon.

A controller asks a question in plain language. The system answers with a
figure, the arithmetic behind it, the rules it checked, and the options it
ranked. When it cannot answer reliably it says so, and says what was missing.

---

## The one design decision

The problem statement asks one question directly:

> What should the language model do, what should deterministic code do, and how
> do you compose them into a system that is both conversational and correct?

Our answer:

**The language model plans and explains. It never produces a fact and never
does arithmetic.**

A LangGraph agent decides which computations to run, in what order, and how to
phrase the result for someone under time pressure. Deterministic Python does
the computing. A verifier then checks every number, identifier, date, station
code and rule id in the drafted reply against what the tools actually returned,
and rejects anything unattested.

That boundary is not a convention we tried to follow. It is enforced three ways:

| Mechanism | What it stops |
|---|---|
| `api/tests/test_boundary.py` walks the import graph of `domain`, `rules`, `ops`, `store`, `tools` and `verify` and fails the build if a model client is reachable | Arithmetic drifting into the model's half |
| The verifier rejects any atom in the prose that no tool emitted as a `Fact` this turn | The model stating a plausible number nobody computed |
| Graph edges, not prompt text, require a `check_legality` result before any legality claim and a `find_cover_options` result before any recommendation | The model inferring a verdict from context |

The third one matters most. A guarantee written into a prompt is a request. A
guarantee written as a graph edge is a guarantee.

---

## Architecture

```
Next.js console  --SSE-->  FastAPI  -->  LangGraph agent
                                             |
                          +------------------+------------------+
                          |                  |                  |
                       planner             tools             verifier
                        (LLM)          (deterministic)    (deterministic)
                                             |
                                    +--------+--------+
                                rules engine     ops engine
                               (the 7 rules)   (cover search,
                                               costing, ranking)
                                             |
                                        WorldState
                                 (typed, immutable, loaded once)
                                             |
                                      SQLite projection
```

The interactive version of this diagram, including which side of the line each
component sits on, is at `/architecture` in the running app.

### What each layer may do

| Path | Responsibility | Model allowed |
|---|---|---|
| `api/src/crewops/contracts/` | Shared types. The seam three workstreams built against. | no |
| `api/src/crewops/domain/` | Typed records, loader, immutable `WorldState`, copy-on-write overlay | no |
| `api/src/crewops/rules/` | Clock arithmetic, the seven rules, `RuleTrace` | never |
| `api/src/crewops/ops/` | Cover search, positioning, costing, ranking, simulation | never |
| `api/src/crewops/store/` | SQLite projection and typed queries | no |
| `api/src/crewops/tools/` | The tool surface the agent calls | no |
| `api/src/crewops/agent/` | LangGraph graph, prompts, memory, guards | yes, this is the agent |
| `api/src/crewops/verify/` | The grounding verifier | no |
| `api/src/crewops/resolve/` | Offline resolver, used when no API key is set | no |
| `api/src/crewops/server/` | FastAPI, SSE streaming | no |
| `web/` | Next.js console. No answering logic, ever. | no |

---

## Evidence, and why every number carries its working

Every tool returns a `ToolEnvelope`. Inside it, every figure is a `Fact`:

```python
Fact(
    key="C-2087.duty_7d.projected",
    label="Projected 7 day duty",
    value=61.33,
    unit="hours",
    provenance=Provenance.COMPUTED,
    source="crewops.rules.duty.window",
    derivation="51.83h prior + 9.50h from P-2291 = 61.33h against a 60.00h limit, over by 1.33h",
)
```

`derivation` is the point. A controller who is about to move a crew member and
sign their name to it does not want to be told the answer, they want to be able
to check it and argue with it. In the console, hovering any figure in the prose
highlights the fact that attests it and shows this derivation.

It is also what makes the verifier possible. If a number can appear in an
answer, a tool must have emitted a `Fact` for it. When verification fails, the
fix is to add the missing fact to the tool. It is never to relax the check.

---

## Setup

Requires Python 3.12 or 3.13, Node 20+, [uv](https://docs.astral.sh/uv/) and
pnpm.

```bash
make install     # Python env via uv, web deps via pnpm
make dev         # API on :8000 and web on :3000
```

Then open http://localhost:3000.

**Everything runs with no API key.** Without one the deterministic core, the
rules engine, the simulations and the ranked options all still work and are
still explainable. Set `ANTHROPIC_API_KEY` to turn on the agent, which adds
language and planning, not truth.

```bash
make test          # full Python suite
make golden        # parity against the shipped answer keys
make eval          # scorecard across all 38 questions, every tier
make check         # ruff, mypy, and the boundary test
make validate-data # the dataset's own validator, read only

cd api && uv run crewops ask "Who is on reserve at BLR tomorrow?"
cd api && uv run crewops brief 2026-09-15
```

---

## The dataset is read only

`data/` is the provided pack and the single source of truth. It is never
written to and never regenerated. Regenerating it would silently move the
answer keys every golden test asserts against, and every figure quoted in this
README and the deck comes from the shipped files.

This is enforced by a deny rule in `.claude/settings.json`, a test that fails if
any module writes to that path, and a CI job that fails on any diff under
`data/`.

`data/crew-ops-advisor-dataset/internal/held_out_scenarios.json` is judging
material and is gitignored. Tests that use it assert safety only, never parity,
so it cannot become something to fit against.

The dataset was decoded once, numerically, into `docs/DATA-MODEL.md`: every
field, the seven rules as shipped, the verified clock arithmetic, the cost
model, and 33 traps. Read that rather than re-deriving from the JSON.

**Where the problem statement PDF and the shipped data disagree, the data
wins.** Confirmed drift: C-2087's rank, C-1042's seniority, a reserve standby
field that does not exist, and an overtime rate that does not exist.

---

## Key trade-offs

**Abstention is a feature, and it is scored as one.** The evaluation harness
counts abstentions separately from wrong answers and never treats one as a
failure. A grader that scored refusal as failure would push the system toward
confident guessing, which is the exact failure mode the problem statement warns
about. "I cannot answer that reliably, and here is what was missing" is a
correct outcome.

**Two answering paths, one set of tools.** With no API key an intent resolver
matches question shapes and calls the same tools through the same verifier.
This is demo insurance, and it is also the cleanest possible proof that the
facts come from code rather than from the model: the deterministic path has no
model at all and still answers.

**Seven rules is the full scope.** The answer keys exclude candidates for
reasons the rulebook does not cover, most importantly double booking. Modelling
that as an eighth `RULE-` id would misrepresent the rulebook to someone who has
to defend the decision, so it is carried as a `FeasibilityIssue` instead:
blocking, but honestly labelled as operational rather than regulatory.

**A candidate must be legal on every day of a multi-day cover.** Day two's
seven-day window already contains day one's cover duty. Legal on day one and
breaching on day two is not a legal option, and the report never rounds that
away.

**Rejected candidates are part of the answer.** Every recommendation carries
the candidates that were found and excluded, each with the rule trace that
excluded them. Showing the rejects is what proves the search was real.

---

## Sample inputs and outputs

Worked examples, including at least one case the system handles poorly, are in
`docs/SAMPLES.md`. The honest analysis of what breaks and why is in
`docs/FAILURE-ANALYSIS.md`, which grades each failure as safe (the system
declines) or unsafe (the system answers wrongly). Unsafe failures are treated as
much more serious than safe ones, and are listed first.

---

## Crew PII in a production system

No real personal data is involved here: the dataset is synthetic. A real
deployment would carry licence numbers, medical certificate status, home base
and contact details, which is regulated personal data in most jurisdictions and
medical data in some.

What this architecture already does well is unusual and worth naming: the model
never sees the dataset. It sees tool results. That means the set of fields
crossing the boundary to a third-party inference provider is enumerable, and it
is enumerated, in `crewops.tools.payloads`.

For production we would:

- Pseudonymise at the tool boundary. Crew ids are already opaque; names,
  contact details and certificate numbers would not enter a payload at all. The
  agent can reason about `C-1042` perfectly well without knowing who that is,
  and the UI can rehydrate the name locally for display.
- Keep medical certificate detail out of the model's half entirely. The rules
  engine needs to know whether a certificate is valid on a date. It does not
  need to say why one is not, and neither does the model.
- Log the evidence ledger, not the prompt. The `Fact` list is the audit record
  a regulator would want, and it is already structured. Prompts and completions
  would be retained only briefly, for debugging, with crew identifiers redacted.
- Apply purpose limitation to reachability data. Knowing a crew member is
  reachable in 45 minutes is operationally necessary and also location
  adjacent, so it should not outlive the disruption it was fetched for.

---

## Scaling this approach

The dataset is deliberately small, so retrieval strategy here is a design
choice rather than a scaling necessity. What would and would not hold at real
airline scale:

**Holds.** The boundary itself gets stronger, not weaker, with scale: the more
data there is, the worse an idea it is to put it in a prompt. The tool surface
is already a query interface rather than a file reader, and `WorldState` is
already backed by a SQLite projection, so the same tools run against a real
database by changing the store, not the engine.

**Needs work.** Candidate enumeration is currently a scan over eligible crew.
At 150 crew that is instant. At 15,000 it wants an index on the filters that
actually discriminate (base, rank, rating, duty headroom) and an early cutoff,
because a controller needs the top five options, not a complete ordering.
Cover search across simultaneous disruptions is a joint allocation problem, and
the current implementation solves the small case exactly; the large case would
need a proper solver, or an honest statement that it is producing a good plan
rather than the optimal one.

**Would change.** The seven-day and 28-day clock windows are recomputed per
candidate per day. That is correct and cheap here, and at scale it becomes an
incrementally maintained running total, which is what a real rostering system
does.

---

## Business impact

The bottleneck on a Crew Control desk is not detecting that something broke.
It is working out the consequences, correctly, from data spread across rosters,
duty clocks, reserve lists and a rulebook, while more disruptions arrive.

What this changes:

- **The downstream break is found.** The uncovered flight is obvious. The crew
  member who moves into a duty-limit breach three days later is not, and that is
  the one that turns a single disruption into four.
- **The reasoning is reviewable.** Every verdict carries its arithmetic, so a
  decision can be checked, handed over at shift change, and learned from. Today
  that reasoning lives in one experienced controller's head.
- **The refusals are trustworthy.** A tool that is confidently wrong once stops
  being used. One that declines clearly, and says what it was missing, keeps
  being used, which is the only way any of the above value is realised.

---

## Repository

| Path | What is in it |
|---|---|
| `docs/CONTRACTS.md` | The seam: tool surface, HTTP and SSE contracts |
| `docs/DATA-MODEL.md` | The dataset decoded and verified, and 33 traps |
| `docs/REQUIREMENTS.md` | Every requirement, with where it is satisfied and how it is verified |
| `docs/TIER-COVERAGE.md` | All 38 questions and 6 scenarios mapped to tools, with the gap analysis |
| `docs/RUBRIC-MAP.md` | The nine criteria, what addresses each, and where we are weak |
| `docs/FAILURE-ANALYSIS.md` | What breaks, graded safe against unsafe |
| `docs/AGENT-DESIGN.md` | The graph, the guards, and how the verifier works |

Licensed MIT. The dataset under `data/` is provided by dCortex and is not ours
to relicense.
