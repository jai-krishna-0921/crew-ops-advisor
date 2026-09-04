# Rubric map

The nine weighted criteria from PDF section 7 (page 6), what the judges said
they look for, what in our submission addresses each, and where we are weak.

The self assessment column is deliberately unflattering. A rubric map that
scores itself well is a marketing document and is worth nothing to the people
building this.

Quotations from the PDF are exact in wording. Punctuation is normalised: this
repository uses no em dashes, so a clause the PDF sets off with one is set off
here with a colon or a comma instead.

| Criterion | Weight |
|---|---|
| AI Utilization | 20% |
| Innovation and Problem Solving | 15% |
| Technical Excellence | 15% |
| Functionality | 15% |
| User Experience | 10% |
| Presentation | 10% |
| Business Impact | 5% |
| Scalability | 5% |
| Performance | 5% |

---

## The three scoring principles

Stated on page 6, and they should drive sequencing more than the weights do.

**1. "A polished, reliable Tier 1 with a credible Tier 2 attempt beats a broken
Tier 3."**

Consequence: five soft or hard failures in Tier 1 (Q05, Q10/Q11 count facts,
Q12, Q14, Q15, Q16) cost more than the two blocked Tier 3 questions. We are
currently investing the tool surface as though the reverse were true.
`find_cover_options` is the most elaborate tool in the contract and there is no
way to count flights.

**2. "Correctness outweighs coverage, answering ten questions correctly and
saying 'I can't answer that reliably' on the eleventh scores higher than
answering all eleven with three wrong."**

Consequence: an abstention is not a failure and must never be scored as one.
The scorecard tracks four outcomes (correct, partial, abstained, wrong) and
reports abstentions separately from wrong answers, because a grader that
punishes abstention would push this project in exactly the wrong direction. It
also means GAP-2 in `docs/TIER-COVERAGE.md` is the most expensive defect in the
build: it is the only gap that produces a confident wrong answer rather than a
refusal.

**3. "Explainability is weighted throughout, not scored in isolation."**

Consequence: there is no "explainability" row below to optimise. Every row is
partly an explainability row. A ranked cover list with no visible rejects
scores worse under Functionality *and* AI Utilization *and* User Experience,
not just under some explanation heading.

---

## 1. AI Utilization, 20%

> "Is AI solving a real reasoning problem, or decorating a lookup? How
> deliberately is the LLM / deterministic boundary drawn?"

**What addresses it.** The boundary is the submission. The model chooses which
tools to call, in what order, when it has enough to answer, when to abstain,
and how to phrase the result for someone under time pressure. It may not state
a number, identifier, date, station, currency amount or rule id that no tool
emitted this turn, may not do arithmetic including "roughly" and "about", and
may not infer a rule verdict instead of calling `check_legality`. That second
list is enforced by a graph node that can reject the turn, not by a prompt.

**Evidence.** `docs/CONTRACTS.md` "The boundary rule, stated precisely";
`api/tests/test_boundary.py`, which walks the import graph and fails if any core
package can reach a model client at any depth, and also fails if
`crewops.agent` imports no model client at all; `VerificationReport` attached to
every `Reply` and rendered rather than hidden.

**Where we are weak.** We have built an extremely strong answer to the second
half of the question and put the first half at risk. The criterion asks whether
AI is solving a real reasoning problem *or decorating a lookup*. Our
architecture forbids the model from producing facts. If the deterministic
offline resolver turns out to answer all 38 questions about as well as the
agent does, then we have built the mirror image of the failure the criterion
names: not AI decorating a lookup, but a chat interface decorating a rules
engine. A judge who spots that will say so, and it costs the largest single
criterion on the sheet.

**Recommendation.** Treat the scorecard's agent-versus-deterministic comparison
as a primary artefact rather than a diagnostic. It must show a concrete set of
questions where the agent answers and the deterministic path abstains, and it
must show at least one where the agent recovers from a tool returning
`ok=False` by planning a different route. Compound questions, ambiguous
referents, and anything needing three tools composed in an order the fallback
does not have a rule for are the natural candidates. If that set turns out to be
empty, we have a real architectural problem and we need to know in hours, not on
stage. Build the comparison first and look at it honestly.

## 2. Innovation and Problem Solving, 15%

> "Thoughtfulness of approach; non-obvious insight into the problem"

**What addresses it.** Three things. The grounding guard as a graph node with a
single correction pass, so an unattested figure gets one chance to be repaired
and is otherwise rejected. `Recommendation.rejected`, which carries the
candidates that were found and excluded each with the `RuleTrace` that excluded
them, because showing the rejects is what proves the search was real. And the
`Fact` contract's rule that when the guard fires, the fix is to add the missing
fact in the tool and never to relax the guard.

**Evidence.** `contracts/evidence.py`; `contracts/ops.py` `Recommendation`;
`agent/graph.py`.

**Where we are weak.** None of that is non-obvious to anyone who has built an
agent before. It is good engineering, which is criterion 3, not insight, which
is this one. The genuinely non-obvious insight in this problem is sitting in the
data unused: **a candidate can be legal on day one of a multi-day pairing and
breach on day two**, because the day-one cover duty is itself inside the
day-two seven-day window. C-3305 covers P-2291 at 59.50h on 15 Sep and 68.25h
on 16 Sep. That is precisely the class of error a fluent language model makes,
it is invisible to anyone who checks the first day and stops, and it takes
thirty seconds to demonstrate.

**Recommendation.** Build the demo around C-3305, not C-1042. C-1042 is the
flagship the PDF hands to every team, so every team will demo it and it
demonstrates competence. C-3305 demonstrates that we understood why this
problem is hard. Show the day-one check passing, then show day two, then show
the system refusing the candidate that a plausible implementation would have
accepted. Second candidate for the same slot: C-5837, whose rest conflict is
two days after the cover and is invisible to any same-day check.

## 3. Technical Excellence, 15%

> "Architecture, code quality, engineering judgement, sound trade-offs"

**What addresses it.** Contracts-first development with three workstreams
building against one typed seam. Strict mypy, ruff with a banned-api rule that
makes importing a model client into the core a lint error as well as a test
failure. TDD, with the failing test before the rule. A closed `Literal` of seven
rule ids, so an eighth rule is a type error rather than a judgement call. And
`docs/REQUIREMENTS.md` section 9, which documents where the problem statement
PDF is stale and records that we chose the shipped data deliberately.

**Evidence.** `api/pyproject.toml` (`banned-api`, strict mypy);
`docs/CONTRACTS.md`; `docs/DATA-MODEL.md`; `.github/workflows/ci.yml`.

**Where we are weak.** Two things. First, none of the core exists yet, so all of
the above is currently a promise. Second, the PII commentary is unwritten and
the problem statement says in terms that it "earns credit under Technical
Excellence" (page 6). That is an explicitly advertised mark on a 15% criterion
and it costs one paragraph.

**Recommendation.** Write the PII paragraph and make it specific rather than
generic: field-level classification of `crew.json`, redaction at the tool
boundary rather than in the prompt so the model never receives a name it does
not need, pseudonymous handles in model context with resolution at render time,
and a retention limit on the checkpoint database given that it is an audit
trail of operational decisions about named individuals. Generic GDPR prose
scores nothing here; the specific version is credible because it follows from
our own architecture.

## 4. Functionality, 15%

> "Does it work? How high up the tiers does it reliably reach?"

**What addresses it.** Three tiers of tools, golden tests asserting parity
against the shipped answer keys, and a scorecard across all 38 questions
reporting per tier.

**Evidence.** `make golden`, `make eval`, `docs/TIER-COVERAGE.md`.

**Where we are weak.** This is our weakest criterion by a clear margin, and the
reason is in `docs/TIER-COVERAGE.md` section 7. As the tool surface stands:
11 of 16 Tier 1, 10 of 14 Tier 2, 4 of 8 Tier 3, and 3 of 6 scenarios. Both
blocked scenarios (S4, the delay cascade, and S6, the double sick call) sit at
the hard end of the worked set, which is exactly where a judge looks to test the
"how high up the tiers" half of the question.

**Recommendation.** Close GAP-1, GAP-2, GAP-3, GAP-6 and GAP-11 before the
agent is wired to seventeen fixed tool names. Together they are one new
simulation tool, one joint planner, two parameters on `find_cover_options`, a
registration filter plus a `find_pairings` tool, and two extra fields on
`get_crew_detail`. They account for every hard block in the set. Every hour
this waits gets more expensive, because the prompts and the tool bindings are
tuned against whatever surface exists at the time.

## 5. User Experience, 10%

> "Would a controller under pressure find this usable and trustworthy?"

**What addresses it.** A streaming console that shows the plan before the
answer, live tool chips, an evidence drawer, and an explicit mode badge so a
judge can see whether the model or the fallback produced this turn. The
ordering guarantee that `verification` precedes `reply` and `reply` precedes
`done`, with streamed tokens presented as visibly provisional until the settled
`Reply` lands.

**Evidence.** `docs/CONTRACTS.md` HTTP surface; `web/`.

**Where we are weak.** `web/src/app/page.tsx` is three lines. The SSE contract
defines twelve event types and there is nothing yet to render any of them.
There is a real risk of an elaborate stream protocol against an under-built
interface, which reads worse than a plain interface would.

**Recommendation.** The single highest-value UX element is the abstention card.
"Would a controller find this trustworthy" is answered by what the system does
when it cannot answer, not by what it does when it can. Render `Abstention` as
a first-class answer with its typed reason, what was established before the
system ran out of ground, what was missing, and the questions it *can* answer
instead. Never as an error state. Second: keep the mode badge visible at all
times, because showing that the fallback ran is the difference between a system
that looks honest and one that is.

## 6. Presentation, 10%

> "Clear articulation of problem, approach, trade-offs and limitations"

**What addresses it.** Nothing yet.

**Evidence.** None.

**Where we are weak.** This is 10% of the total sitting at zero, and it has the
highest ratio of marks to effort of anything on this sheet. It is also the
criterion where our existing documents are already most of the work:
`docs/CONTRACTS.md` is the trade-offs slide, `docs/TIER-COVERAGE.md` is the
limitations slide, and `docs/FAILURE-ANALYSIS.md` is the honesty slide the PDF
explicitly rewards ("Honest failure analysis scores well; overstating
capability scores badly", page 5).

**Recommendation.** Build the deck from the documents that already exist rather
than writing new content, and put the failure analysis in the deck rather than
leaving it in the repository. Most teams will present capability. Presenting a
known limitation, with the arithmetic showing exactly why it fails and what we
would do about it, is worth more here and costs nothing we have not already
written.

## 7. Business Impact, 5%

> "Credible link to operational value, time saved, disruptions avoided, cost
> reduced"

**What addresses it.** The cost model is real and comes from `costs.json`:
reserve callout at 18,500 against a day-off callout at 24,000 against a
cancellation at 250,000 per leg. Ranking by cost with a stated `ranking_basis`
makes the value claim concrete and arguable. S4 is the cleanest single example
in the pack: re-crewing one leg costs 75,000 against 250,000 to cancel it, a
3.3x difference on one decision.

**Evidence.** `CostBreakdown.basis` showing the multiplication rather than the
total; `Recommendation.ranking_basis`.

**Where we are weak.** The temptation to quantify annual savings, and page 6
forbids it: "Base rates are synthetic and not statistically calibrated." A
system whose entire thesis is that it never invents a figure cannot open its
business case with an invented figure. That would be the single most damaging
inconsistency available to us.

**Recommendation.** Make the impact claim about time and about consequence
blindness, not about money at scale. The defensible claims are: the per
decision cost delta, which is computed and citable; the number of downstream
consequences surfaced that a controller cross-referencing screens would have to
find by hand; and the fact that the reasoning trail makes a decision reviewable
after the shift. Say explicitly that we are not extrapolating to annual savings
because the base rates are synthetic. That sentence costs nothing and it
protects the thesis.

## 8. Scalability, 5%

> "Would the approach hold at real airline scale? Reasoned commentary counts."

**What addresses it.** The honest answer, which is that the architecture scales
along the axis that matters and the current implementation does not, and that
we know which is which. The tool surface is a query interface, so the
substitution is SQLite for a real operational store without touching `rules/`,
`ops/` or the agent. The rules engine is per crew per day and parallelises
trivially. The part that does not scale is candidate enumeration, which is
linear over the crew table today: at 150 crew that is correct and instant, at
15,000 it needs a pre-filter on base, rank and rating before any rule runs.

**Evidence.** `docs/CONTRACTS.md` tool surface; README section, pending.

**Where we are weak.** The commentary is unwritten, and page 6 says explicitly
that volume is small by design and retrieval strategy is a design choice rather
than a scaling necessity. So we get no credit for engineering effort here, only
for reasoning.

**Recommendation.** One README section, three paragraphs: what scales unchanged,
what needs a pre-filter and why, and what breaks outright (the joint allocation
enumeration, which is fine for two simultaneous gaps and is not fine for twenty,
and at that point genuinely does become the optimisation problem NG-06 tells us
not to build).

## 9. Performance, 5%

> "Responsiveness and reliability"

**What addresses it.** Targets set in `docs/REQUIREMENTS.md` REQ-25, measured
by the scorecard: mean and p95 latency per tier, in both modes. The
deterministic HTTP routes answer without a model call at all, so a judge can
see the rules engine respond in milliseconds.

**Evidence.** `make eval` latency columns.

**Where we are weak.** GAP-5. With no fleet-wide duty scan, Q26 needs 150
sequential `get_duty_clocks` calls. That is a latency failure long before it is
a correctness failure, and it is the kind of thing a judge notices live because
they are watching a spinner. The reliability half is also untested: nothing
currently handles a model API timeout or a rate limit on stage.

**Recommendation.** Fix GAP-5, and add a hard timeout on the agent path that
falls back to the deterministic resolver rather than failing the turn. The
fallback already exists for the no-API-key case; reusing it as a timeout path
costs almost nothing and converts the most likely live-demo failure into a
visible mode switch, which under principle 2 reads as honesty rather than as a
crash.

---

## Where the submission is weakest, in one place

Ordered by expected marks lost, not by how uncomfortable each is to say.

| Rank | Weakness | Criteria hit | Weight exposed |
|---|---|---|---|
| 1 | **Nothing is built yet.** Contracts, docs and a boundary test exist. No `domain`, `rules`, `ops`, `tools`, `agent`, `verify` or `server`, and a three-line web page. Every claim below assumes the core lands | Functionality, Technical Excellence, UX, Performance | 45% |
| 2 | **Five tool gaps hard-block 3 of 6 scenarios and half of Tier 3**, and degrade five Tier 1 questions, which the first scoring principle says cost the most | Functionality | 15% |
| 3 | **The agent may be provably decorative.** If the deterministic fallback matches it on the scorecard, the largest criterion on the sheet is answered badly | AI Utilization | 20% |
| 4 | **Presentation is at zero** and is the cheapest 10% available | Presentation | 10% |
| 5 | **GAP-2 produces the only unsafe failure in the set**: one captain on two aircraft at once, delivered confidently. Every other gap abstains | Functionality, and it contradicts principle 2 | 15% |
| 6 | **Three explicitly advertised free marks unwritten**: the PII paragraph, the scalability commentary, the business-impact framing | Technical Excellence, Scalability, Business Impact | 25% combined, small slice of each |

## The single change that would improve the score most

**Build the agent-versus-deterministic comparison into the scorecard first, and
look at the result honestly before anything else is tuned.**

It is the only artefact that answers the largest criterion on the sheet, at 20%,
and it is the only one that can tell us early whether our central architectural
claim survives contact with the question set. If the agent beats the fallback on
a nameable set of questions, that table is the strongest slide in the deck and
the answer to "is AI solving a real reasoning problem". If it does not, we have
until the deadline to make the agent earn its place instead of discovering on
stage that it has not.

Everything else on this page is a known quantity: the gaps have known fixes, the
deck has known content, the paragraphs are known paragraphs. This is the only
open question whose answer we cannot currently predict, and it is attached to
the biggest number.

**Separately, and it is a different question:** the single most dangerous defect
is GAP-2. It is the only place in the whole question set where we would produce
a fluent, confident, wrong operational instruction rather than a refusal. Until
the joint planner exists, the correct behaviour for Q32 and S6 is an explicit
abstention naming the missing capability. Under the second scoring principle
that costs us almost nothing. Answering it wrongly costs us the argument.
