# Requirements

Every requirement in `problem-statement/problem_explanation_k66g3nx88t.pdf`,
extracted, given an id, and tracked. Requirement text is quoted verbatim from
the PDF with its page number. Nothing here is aspirational: the status column
says what is true today, and "not yet" appears wherever it is true.

Status values:

| Status | Meaning |
|---|---|
| **done** | built and verified by the named test or command |
| **partial** | built, but not to the standard the requirement asks for |
| **planned** | designed, owner assigned, not yet built |
| **not yet** | nothing exists |
| **n/a** | out of scope by the problem statement's own instruction |

Class values follow the PDF's own language: **mandatory** where it says
mandatory or uses "must", **expected** where it says "strongly expected" or
"should", **stretch** for the tier it labels stretch, **optional** for the
enhancements list, **non-goal** for the "You are NOT expected to build" list.

---

## 1. Expected output (PDF section 5, page 5)

| Id | Requirement, verbatim | Class | How we satisfy it | Where | Verified by |
|---|---|---|---|---|---|
| REQ-01 | "Conversational interface — web chat, voice, or a well-designed CLI" | mandatory | Both: a Typer/Rich CLI (`crewops chat`, `crewops ask`) and a Next.js web console streaming over SSE | `api/src/crewops/cli.py`, `web/` | manual demo; `GET /api/health` |
| REQ-02 | "Reasoning layer answering questions across as many tiers as you reach" | mandatory | LangGraph agent selecting deterministic tools, with a deterministic offline resolver behind the same `Reply` type | `api/src/crewops/agent/`, `api/src/crewops/resolve/` | `make eval`, per-tier scorecard |
| REQ-03 | "Visible explanations on all non-trivial answers" | mandatory | Every tool returns a `ToolEnvelope` carrying `trace` and `facts`; every rule verdict carries a `RuleTrace.arithmetic` string with both operands, the operator, the result and the limit | `contracts/evidence.py`, `contracts/rules.py` | `make golden`; UI evidence drawer |
| REQ-04 | "Architecture diagram — showing the boundary you drew between LLM reasoning and deterministic logic" | mandatory | Not yet drawn. Owner: presentation. The boundary itself is enforced by `tests/test_boundary.py`, which is the stronger claim and should be shown next to the diagram | `docs/` (pending) | n/a, it is a document |
| REQ-05 | "README — setup, approach, key trade-offs, known limitations" | mandatory | Not yet written | `README.md` (pending) | n/a |
| REQ-06 | "Sample inputs and outputs, including at least one case your system handles poorly, with your analysis" | mandatory | `docs/FAILURE-ANALYSIS.md` plus a generated transcript set from the scorecard | `docs/FAILURE-ANALYSIS.md`, `make eval` artefact | `make eval` writes the transcripts |
| REQ-07 | "Presentation deck and live demo" | mandatory | Not yet built | pending | n/a |

**REQ-04 note.** The PDF asks for a diagram of the boundary. We have something
better available and should present both: an executable test that fails if any
module in `contracts`, `domain`, `rules`, `ops`, `store`, `tools` or `verify`
can reach a model client at any import depth, and that also fails if
`crewops.agent` imports *no* model client, on the grounds that a boundary with
nothing on the other side of it is decorative. A diagram asserts the boundary.
`make boundary` proves it.

## 2. The tiers (PDF section 2, page 2)

| Id | Requirement, verbatim | Class | Status | Where | Verified by |
|---|---|---|---|---|---|
| REQ-08 | "Tier 1 — Lookup & Retrieval (mandatory). Answerable directly from the data. No domain modelling required." | mandatory | planned | `tools/` tier 1 group | `make eval`, Tier 1 rows; `docs/TIER-COVERAGE.md` section 1 |
| REQ-09 | "Tier 2 — Consequence & Simulation (strongly expected). Requires reasoning about impact, not just retrieval." | expected | planned | `ops/`, `rules/`, `tools/` tier 2 group | `make eval`, Tier 2 rows |
| REQ-10 | "Tier 3 — Recommendation & Action (stretch). Requires ranking legal options against real trade-offs. Expected: ranked, rule-compliant options with cost, legality status, reachability and reasoning." | stretch | planned | `ops/rank`, `find_cover_options` | `make golden` against S1, S2, S5; `make eval` Tier 3 rows |
| REQ-11 | "Bonus: draft the notification message to the affected crew." | optional | planned | `draft_notification` | Q36 golden test |
| REQ-12 | "Explainability is mandatory. Every non-trivial answer must carry reasoning a controller can read and challenge. A correct answer with no visible reasoning scores poorly." | mandatory | planned | `narrate/`, `RuleTrace`, `TraceStep`, `Citation` | grounding guard; UI reasoning trail |
| REQ-13 | "What should the language model do, what should deterministic code do, and how do you compose them into a system that is both conversational and correct?" | mandatory | The submission's entire thesis: the model plans and explains, deterministic code computes, and a guard node rejects any sentence containing a number, identifier, date or rule id that no tool emitted this turn | `docs/CONTRACTS.md` "The boundary rule, stated precisely"; `agent/graph.py`; `verify/` | `make boundary`; verification status on every `Reply` |

REQ-10 has a caveat that belongs here rather than buried. The PDF's Tier 3
expected-output sample shows `coverage` and `reasoning` fields on each option.
The shipped answer keys carry `action`, `crew_id`, `legal`, `rules_checked`,
`cost_inr`, `delay_hours` and `rank`, and only S4's two options carry
`reasoning`. We produce both shapes: the shipped fields because the golden
tests assert them, and `coverage_summary`, `reasoning` and `tradeoffs` because
the PDF asks for them and because a controller needs them.

## 3. Assumptions and constraints, mandatory (PDF section 6, page 5)

| Id | Requirement, verbatim | Class | How we satisfy it | Verified by |
|---|---|---|---|---|
| REQ-14 | "Use the provided synthetic dataset — no external or real airline data" | mandatory | `data/` is read only for every workstream. A test walks the whole source tree and fails on any write call in a module that also references the dataset path | `tests/test_boundary.py::test_nothing_writes_to_the_dataset` |
| REQ-15 | "Natural language must be the primary interface" | mandatory | `crewops chat` and the web console are the primary entry points. The deterministic HTTP routes (`/api/simulate`, `/api/legality`, `/api/cover`) exist so a judge can watch the rules engine run with no API key, not as the main path | manual demo |
| REQ-16 | "Non-trivial answers must be explainable" | mandatory | Same mechanism as REQ-03 and REQ-12 | grounding guard |
| REQ-17 | "Answers must be grounded in the data — invented facts are treated as failures, not rounding errors" | mandatory | The `Fact` contract: if a number can appear in an answer, a tool must have emitted a `Fact` for it. The guard extracts every number, identifier, date, currency amount, station and rule id from the drafted reply and rejects any that no tool attested. When the guard fires, the fix is to add the missing `Fact`, never to relax the guard | `verify/`; `VerificationReport` on every `Reply`; scorecard grounding column |

REQ-17 is the requirement most likely to be tested adversarially by a judge,
and it is the one this architecture is built around. The phrase "not rounding
errors" is deliberate: an approximated duty-hour figure is an invented fact,
not a near miss.

## 4. Optional enhancements (PDF section 6, page 5)

The PDF lists these as enhancements, not requirements. We take four and decline
two, deliberately.

| Id | Requirement, verbatim | Class | Decision | Where |
|---|---|---|---|---|
| REQ-18 | "Voice interface" | optional | **Declined.** It adds a failure surface on stage and buys nothing under any weighted criterion. REQ-01 is already satisfied twice over | n/a |
| REQ-19 | "Multi-turn conversation with context retention" | optional | **Taken.** LangGraph SQLite checkpointing, so a thread survives a restart and replays as an audit trail | `agent/memory`, `GET /api/threads/{id}` |
| REQ-20 | "Proactive alerting ('three crew approach duty limits tomorrow')" | optional | **Taken.** `get_watchlist` and `crewops brief <date>`, entirely deterministic | `tools/`, `cli.py` |
| REQ-21 | "Drafting crew notifications" | optional | **Taken.** `draft_notification`, deterministic template filled from computed facts. The model may adjust tone and may not introduce a time, flight number or report location the template did not supply | `draft_notification` |
| REQ-22 | "Chained or simultaneous disruptions" | optional | **Taken, and it is not really optional.** Q32 and S6 are simultaneous disruptions in the shipped answer keys, so declining this loses a Tier 3 question and a scenario. See GAP-2 in `docs/TIER-COVERAGE.md` | `ops/` joint allocation, pending a tool to call it |
| REQ-23 | "Confidence / uncertainty signalling" | optional | **Taken.** `Reply.confidence`, `Abstention` with a typed reason, and `Provenance.ASSUMED` rendered differently in the UI so the system is visibly not claiming a modelling assumption as observed fact | `contracts/evidence.py` |
| REQ-24 | "The dataset is clean; real operational data is not. Handling malformed input is a bonus, not a requirement." | optional | **Partially taken.** We do not harden against malformed dataset records. We do harden against malformed *questions*, which is the input a controller actually supplies: ambiguous referents and underspecified questions return a typed `Abstention` rather than a guess | `AbstentionReason.AMBIGUOUS_REFERENT`, `UNDERSPECIFIED` |

## 5. Performance and security (PDF section 6, page 6)

| Id | Requirement, verbatim | Class | Target | Verified by |
|---|---|---|---|---|
| REQ-25 | "Answers should arrive fast enough to feel usable on a live shift. No formal benchmark, but a 45-second response is not a decision aid." | expected | Tier 1 under 2s, Tier 2 under 8s, Tier 3 under 20s, all end to end in agent mode. Deterministic mode should be under 500ms at every tier. The scorecard reports mean and p95 latency per tier so the claim is measured, not asserted | `make eval` latency columns |
| REQ-26 | "Commentary in your README on how such a system would handle crew PII in production earns credit under Technical Excellence." | optional, credited | Not yet written. It is a paragraph of README for explicit marks under a 15% criterion, so it is worth writing well: field-level classification, redaction at the tool boundary rather than in the prompt, no crew identifiers in model context where a pseudonymous handle would do, and retention limits on the checkpoint database | `README.md` (pending) |

REQ-25 has a design consequence worth stating: GAP-5 in
`docs/TIER-COVERAGE.md` (no fleet-wide duty scan) forces 150 sequential tool
calls to answer Q26. That is a latency failure before it is a correctness
failure, which is why it is filed as high severity rather than medium.

## 6. Deliverables checklist (PDF section 8, page 7)

| Id | Item | Status |
|---|---|---|
| REQ-27 | "Source code repository (GitHub / GitLab)" | done |
| REQ-04 | "Architecture diagram — including the LLM vs deterministic boundary" | not yet |
| REQ-05 | "README with setup instructions, approach and trade-offs" | not yet |
| REQ-06 | "Sample inputs and outputs, including one failure case with analysis" | partial, `docs/FAILURE-ANALYSIS.md` started |
| REQ-07a | "Presentation deck" | not yet |
| REQ-07b | "Live demo" | not yet |

## 7. Generalisation (PDF section 7, page 7)

| Id | Requirement, verbatim | Class | How we satisfy it |
|---|---|---|---|
| REQ-28 | "Submissions may additionally be run against a small set of held-out scenarios not in the starter pack, to test generalisation." | mandatory in effect | Nothing in `rules/` or `ops/` may special-case a question id, a crew id or a scenario id. The rules engine computes from `rules.json` params; the cover search enumerates candidates. `api/tests/golden/test_heldout.py` runs `internal/held_out_scenarios.json` when present and skips cleanly when it is not. That file is gitignored judging material: it is a generalisation check, never a target, and nothing is tuned against it |

If any golden test ever has to name a specific answer to pass, the fix is in
the engine, not the test.

---

## 8. Non-goals

The PDF's "You are NOT expected to build" list, as explicit non-goals. Scope
discipline is worth marks under Technical Excellence and Innovation; scope
creep costs them and costs hours we do not have.

| Id | "You are NOT expected to build", verbatim | Page | Our position |
|---|---|---|---|
| NG-01 | "A prediction model. Disruption-risk signals are provided pre-computed. Treat them like a weather forecast; your job is what the controller does about it." | 5 | We build no model of any kind that predicts anything. `risk_signals.json` is read and surfaced as a `DATASET` provenance fact and never recomputed, adjusted or blended. Note that we currently cannot surface it at all: GAP-3 |
| NG-02 | "Authentication, user management or multi-tenancy" | 6 | None. The HTTP surface has no auth and `docs/CONTRACTS.md` says so explicitly, citing this line, so a judge reads it as a decision rather than an omission |
| NG-03 | "Production infrastructure, CI/CD or deployment pipelines" | 6 | **We have partially crossed this line and it is defensible.** `.github/workflows/ci.yml` exists. It is not a deployment pipeline: it runs lint, types, the boundary test and the golden tests. Its purpose is to fail if the dataset moves or the boundary leaks, which is a correctness guarantee for REQ-14 and REQ-13, not infrastructure. We add nothing further: no containers, no deploy step, no environments |
| NG-04 | "Integrations with real airline systems" | 6 | None. The only data source is `data/`, which REQ-14 also requires |
| NG-05 | "A mobile application" | 6 | None. The web console is responsive because that is free, not because we are targeting mobile |
| NG-06 | "A full mathematical optimisation solver — heuristic ranking with clear reasoning is sufficient" | 6 | We rank by cost then crew id, exactly as the answer keys do, and state the ranking basis in `Recommendation.ranking_basis` so it can be argued with. The joint allocation in GAP-2 is a two-gap exhaustive enumeration over a candidate list of tens, not a solver. If that ever needs an LP, we have misread the problem |
| NG-07 | "Coverage of all real regulations — the seven provided rules are the full scope" | 6 | Seven rules, loaded from `rules.json` params, no eighth. `RuleId` is a closed `Literal` of exactly seven values, so an eighth rule is a type error rather than a judgement call. When a question needs a rule we do not model, the system abstains with `AbstentionReason.REQUIRES_UNMODELLED_RULE` and names what it would need. See the caveat below |

### The NG-07 caveat, stated plainly

The shipped answer keys exclude candidates with reasons like `double-booked:
P-2203 overlaps COVER on 2026-09-16`. That is not one of the seven rules. It is
an assignment feasibility check: a person cannot be in two places at once. We
implement it, and we label it a feasibility constraint rather than a rule, so
that NG-07 stays true and our own scope statement stays honest. It never
appears in a `rules_checked` list and it never gets a `RULE-` id.

Related, and worth saying in the README before a judge finds it: RULE-FLT-03
appears in every `rules_checked` array in the answer keys and **never binds
anywhere in the dataset**. The maximum 28-day block total is 79.28h against a
100h limit. We implement it. We do not claim it is tested, because no shipped
question can breach it.

---

## 9. Documentation drift: where the PDF and the data disagree

The PDF is stale in several places. **The shipped data wins every time**, and
we chose it deliberately rather than by accident. This table exists so that a
judge who checks one of our figures against the PDF sees that we noticed.

| PDF says | Page | Shipped data | What we do |
|---|---|---|---|
| "FO C-2087" in the Tier 2 example question | 2 | C-2087 is a **Captain**. The dataset README flags this as a doc bug to be fixed before release | We say Captain. Q13's own answer key says Captain, so following the PDF fails a shipped test |
| `crew.json` sample: C-1042 `seniority: 14`, no `status` field | 4 | `seniority: 22`, and `status: "active"` is present and load bearing: `leave` and `training` crew are filtered out before any rule runs | We use 22 and we filter on `status` |
| `duty_clocks.json` sample: C-1042 `duty_hours_7d: 48.5`, `flight_hours_28d: 82.0`, `last_rest_ended: 2026-09-14T22:00:00Z`, no `daily_history` | 4 | `20.93`, `64.27`, `2026-09-13T02:00:00Z`, plus `as_of_utc` and a 28-entry `daily_history` array | We use the data. Q02's answer key is 20.93 with 39.07 headroom, so the PDF sample would fail a Tier 1 question |
| `reserve_pool.json` holds "on-call windows and **standby status**" | 3 | There is no standby-status field anywhere in the pack | We do not invent one. Reserve usability is decided by the on-call window against the required report time, which is what `rules.json` actually says |
| `costs.json` holds "Callout, **overtime**, deadhead and penalty rates" | 3 | There is no overtime rate. The file holds reserve and day-off callout rates split by pilot and cabin, deadhead positioning, delay per duty hour, cancellation per leg and a hotel rate | No overtime line ever appears in a `CostBreakdown` |
| Tier 3 option shape includes `coverage` and `reasoning` per option | 4 | Shipped options carry `action`, `crew_id`, `legal`, `rules_checked`, `cost_inr`, `delay_hours`, `rank`. Only S4's two options carry `reasoning`; nothing carries `coverage` | We emit both, as set out under REQ-10 |
| "~140 flights", "~40 questions", "~8 stations", "~150 crew" | 3 | Exactly 147 flights, 38 questions, 8 stations, 150 crew | We quote exact counts and never the approximations |
| RULE-BASE-07: "Reserve callout from base only, unless deadhead cost is applied" | 4 | "Reserve callout from own base only; covering from another base requires deadhead positioning (cost applies)" | We implement the `rules.json` text. Positioning exists only DEL to BLR in this pack; any other cross-base request is excluded |

Two consequences of this table are worth carrying into the deck, because they
are the kind of detail that separates a submission that read the data from one
that read the brief:

1. Anyone who builds from the PDF's `duty_clocks` sample gets 48.5h for C-1042
   and fails Q02, a mandatory Tier 1 question, on the first try.
2. Anyone who trusts "FO C-2087" builds a First Officer cover search for a
   Captain vacancy and returns an empty candidate list on the flagship
   scenario.

## 10. Constraints that shape the build

Not requirements, but instructions we are following.

| Id | Text, verbatim | Page | Effect |
|---|---|---|---|
| C-01 | "The dataset runs on a laptop. Do not spend hackathon hours on infrastructure — a local SQLite file plus a clean interface scores better than an unfinished distributed deployment." | 3 | SQLite projection for retrieval, SQLite for agent memory, everything runs locally with `make dev`. No container, no cloud |
| C-02 | "Volume is small by design — retrieval strategy is a design choice, not a scaling necessity." | 6 | We are not required to justify retrieval on performance grounds, and should not pretend to. The Scalability criterion asks for reasoned commentary, which is a README paragraph, not an engineering effort |
| C-03 | "Base rates are synthetic and not statistically calibrated." | 6 | No claim anywhere in the deck or README about realistic sick-call rates, expected annual savings, or anything else derived from base rates |
| C-04 | "It targets relational and constraint realism, not statistical realism. What is guaranteed is: every roster is legal or explicitly flagged, every duty clock sums correctly, every pairing obeys the ruleset. Your reasoning is therefore objectively checkable against the rules and answer keys." | 5 | This is the licence for the golden tests. Exact parity against the keys is a legitimate bar because the data was built to make it one |
