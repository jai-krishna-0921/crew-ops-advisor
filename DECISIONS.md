# Decisions

The choices that shaped this system, why each was made, and what it cost. A
decision with no cost written down is a decision nobody actually made.

Ordered roughly by how much of the design each one determines. Measured numbers
live in `PROGRESS.md`, commands in `COMMANDS.md`, open work in `TODO.md`.

---

## 1. The model plans and explains. It never produces a fact.

**Decision.** A LangGraph agent decides *which* computations to run, in what
order, and how to phrase the result. Deterministic code does the computing. A
verifier then checks every number, identifier, rule id, station code and date in
the drafted reply against what the tools actually returned.

**Why.** The problem statement puts 20% on exactly this question and says the
obvious approach, put the data in the prompt and let the model answer, fails at
Tier 2 and 3. Legality is exact arithmetic against a rulebook. A model that
approximates a duty-hour calculation produces answers that are fluent,
confident and wrong, which is operationally worse than no answer.

**Cost.** Far more code than prompting would need. Every tool has to emit typed
facts rather than prose, and a question the tools cannot express is a question
the system declines rather than improvises.

**How it is enforced, rather than promised.** `tests/test_boundary.py` walks the
import graph of `contracts/`, `domain/`, `rules/`, `ops/`, `store/`, `tools/`
and `verify/` and fails if any model client is reachable from any of them at
any depth. It also asserts the mirror, that `agent/` *does* import one, so the
boundary is not decorative.

---

## 2. Abstain over guess

**Decision.** An unresolvable question returns a refusal naming what was
missing. Abstentions are excluded from the accuracy figure and are never
counted as failures.

**Why.** The rubric is explicit: answering ten questions correctly and saying
"I cannot answer that reliably" on the eleventh scores higher than answering all
eleven with three wrong.

**Cost.** Coverage. 13 of 38 questions are declined on the deterministic path.
That is the single weakest column in the scorecard and it is a deliberate
trade, not an accident.

**The trap this creates.** Accuracy alone becomes meaningless. `kimi-k2.6`
scored **100% accuracy** on Tier 1 by declining 11 of 16 questions and getting
the other 5 right. Always read accuracy next to coverage.

---

## 3. The deterministic path is a first-class product, not a fallback

**Decision.** Every command runs with no API key. Without one, the rules
engine, the simulations and the ranked options all still work and are still
explainable.

**Why.** Offline-first is a hedge against the demo failing, but it is also the
proof of decision 1. If the system answers Tier 1 at 100% accuracy in 4ms with
no model in the loop, then the model demonstrably is not the thing computing
the answer.

**Cost.** Two answer paths to maintain, and they can diverge. They did: the
offline resolver matches fixed question shapes, so a typo ("reserv**er**") that
the agent handles without noticing makes the offline path decline.

**Unexpected benefit.** It became the measuring instrument. Every agent result
is scored against the offline result on the same question, which is how the
verdict inversion in decision 8 was caught.

---

## 4. One provider module, and the vendor is a config choice

**Decision.** `agent/providers.py` is the only module in the repository that
names a model vendor. The graph is written against `BaseChatModel`. Precedence
is anthropic, then openai, then ollama.

**Why.** The system had to run on a local model now and switch to a hosted one
later without a rewrite. Ordering hosted providers first means dropping in
`ANTHROPIC_API_KEY` switches everything over with no config edit and nothing to
remember to unset.

**Cost, and it bit immediately.** Precedence by presence means an *invalid* key
takes the system down. An unusable `ANTHROPIC_API_KEY` appeared in `.env.local`
and every agent turn started failing with a 401 in under a second.
`CREWOPS_LLM_PROVIDER` overrides it, but the failure mode is real and is
documented at the top of `COMMANDS.md`.

**Three vendor quirks live here so the graph stays neutral.** The default model
id must follow the provider (`claude-sonnet-5` sent to Ollama is a 404).
Sampling must be pinned per vendor (Anthropic rejects the parameters; Ollama
defaults to temperature 0.8). And `with_structured_output` has no portable
method: Ollama's default `json_schema` made the tool-capable models answer in
prose, `function_calling` binds.

---

## 5. The model was chosen by measurement, not preference

**Decision.** `deepseek-v4-flash:cloud` is the default, chosen by scoring four
candidates on Tier 1 against the shipped answer keys.

**Why.** The first agent-mode run scored 10 of 16 and the tempting conclusion
was "the model is too weak". That conclusion was wrong (decision 7), and it
would have sent hours into prompt tuning. Scoring the alternatives took twenty
minutes and produced a better answer.

deepseek is the only configuration that beats the deterministic path on Tier 1,
16 against 15, and has never produced a wrong answer in 48 graded questions.
`glm-5.1` and `kimi-k2.6` were ruled out on latency: p95 27.4s and 63.2s
against the problem statement's "a 45 second response is not a decision aid".
`qwen2.5:7b` returns an empty `tool_calls` list for a bound schema and cannot
drive the loop at all.

**Cost.** None of these honour temperature 0 strictly. deepseek scored 16, 15,
16 on three identical passes. **No single agent-mode number is stable enough to
quote on its own**, which makes every measurement here a range rather than a
figure.

---

## 6. Guards check entitlement. The verifier checks values.

**Decision.** Two independent mechanisms, deliberately not merged.

The **verifier** asks: does every number, duration, currency amount, date,
time, identifier, station code and rule id in this sentence trace back to a
`Fact` the deterministic layer produced?

The **guards** ask a different question: was this answer allowed to exist at
all?

**Why.** There is a failure the verifier structurally cannot catch. Take
"C-3310 is legal for P-2291". Every atom is attestable: `C-3310` is a real crew
id the tools returned, `P-2291` is a real pairing. The sentence can still be
false, because **a verdict is a relation between values, not a value**. No
amount of token matching catches a wrong relation.

**Cost.** Two places to look when an answer is rejected, and a repair budget
they share.

---

## 7. A guard that rejects good answers is as useless as one that passes bad ones

**Decision.** Fold typographic characters to ASCII before extracting atoms.

**Why.** This is the most instructive failure in the project. Language models
write typographically: `gpt-oss` renders a crew id as `C‑3310` with U+2011
NON-BREAKING HYPHEN so it will not wrap. The extractor scanned for an ASCII
hyphen, did not find one, and fell through to the bare integer `3310`. A number
in no tool output cannot be attested, so the grounding check **rejected answers
that were correct**, whose figures were all genuinely in the tool results.

It cost four of sixteen Tier 1 questions and it read exactly like the model
being stupid. It was us.

**Why this is not a loosening.** Identifiers still compare exactly, `C-3310` is
still not `C-3301`, and a test pins the other direction: the fold may only
recover an identifier that was genuinely written, never manufacture one from
prose. The fold is one character to one character, so every span offset the
scanner reports stays valid.

**The lesson.** An over-strict guard fails in the direction that *looks*
responsible, which makes it easy to misattribute. `verify/CLAUDE.md` warned
about this failure mode in as many words and it still took a skeptical question
to go and look.

---

## 8. When the guard fires, add the missing fact. Never loosen the check.

**Decision.** A repository rule, and the verdict inversion is what it is for.

**The case.** Q20 asks whether a 90 minute delay pushes the rostered crew over
a limit. `simulate_delay` computed it correctly, `breach=True`, 12.75h against
a 12.0h FDP limit, and emitted it as a `Fact`. What it did not emit was a
`RuleTrace`. Six `check_legality` calls on the pairing *as scheduled* did emit
traces, all PASS, because as scheduled it does pass. The question was about the
delay.

So the assembled `Reply` carried 31 PASS traces and zero BREACH, for a question
whose answer is a breach. Everything reading the structured verdict rather than
the prose concluded the assignment was legal. **That is the worst output this
system can produce**: a controller acting on it dispatches a crew into an FDP
breach.

**The fix was to the tool, not the check.** `simulate_delay` now emits its FDP
evaluation as a rule trace. A pass is emitted as well as a breach, because a
rule that was checked and cleared is evidence, and silence leaves a controller
unable to tell "checked, fine" from "never checked".

Alongside it, `breach_agreement_guard`: if the tools computed a breach, the
answer may not reach an all-clear before mentioning it. Ordering rather than
presence, so the correct answer, which opens with the breach and then notes
what passes, still gets through.

---

## 9. Batch the call, do not add a tool

**Decision.** `check_legality` gained a `crew_ids` argument. It delegates to
the single-crew path once per person rather than reimplementing anything.

**Why.** Six of eight Tier 2 abstentions were the turn budget alone, and the
computations were never the slow part: the agent asked the same question once
per crew member, paying a model round trip each time. A second tool name would
have been a second thing for the model to get wrong, and a second
implementation that could drift.

Delegating means the batch cannot disagree with the individual answer. There is
one legality engine and this is deliberately not a second one. The test that
matters asserts exactly that equality, per crew and per rule.

**Cost.** The contract, the registry and the agent's argument model have to
move together. `tests/test_boundary.py` makes drift between them a build
failure, because Pydantic drops unknown fields **silently**: an argument
missing from the ToolSpec is not rejected, it evaporates.

---

## 10. The turn budget is 30 seconds, and no higher

**Decision.** Raised from 25s once Tier 2 was measured. Not raised further.

**Why.** The problem statement says a 45 second response is not a decision aid.
A budget set just under the line it is trying to respect is not a budget.

**Cost, stated plainly.** p95 is currently **38.6s**, above the budget, because
the budget is checked *before* each model call rather than interrupting one in
flight. A turn that starts a call at 29s runs well past. Four Tier 2 questions
still abstain on time.

---

## 11. A greeting is answered. Trivia is refused.

**Decision.** "Hey" gets a capability statement. "What is the capital of
France" gets a refusal at 2ms, before any model call.

**Why.** They look similar and are not. Refusing trivia is the system working:
an advisor that answers general knowledge is one that will also confidently
answer a duty-hour question it should decline. Refusing a greeting is the
system looking broken, and it is the first thing anyone types.

**Cost.** A classification that can be wrong. Matching is therefore strict:
every token must be a pleasantry and the whole thing at most four tokens, which
is what keeps "hey, who is on reserve at BLR" a real question.

---

## 12. The dataset is read only

**Decision.** `data/` is never written to, never regenerated, never "fixed".

**Why.** Regenerating would silently move the answer keys every golden test
asserts against, and every figure quoted in the README and the deck.

**How it is enforced.** `test_nothing_writes_to_the_dataset` walks the AST for
write calls whose target looks like the dataset, and
`test_the_dataset_on_disk_is_unmodified` re-parses every shipped JSON file so a
run that corrupted them fails loudly rather than rewriting the keys quietly.

---

## 13. Chat memory is a separate database from operational data

**Decision.** `agent/memory.py` keeps LangGraph checkpoints and a turn log in
`.crewops/memory.db`. The operational projection built from `WorldState` is a
different store entirely.

**Why.** The reasoning rule is that Tier 2 and 3 computations come from current
tables plus deterministic code, never from conversation history. Separate files
make that structural rather than a convention someone has to remember.

**Cost, and it is unpaid.** The `checkpoints` table has **0 rows**. Every turn
logged so far ran on the deterministic path, which bypasses the graph, so the
checkpointer has never persisted anything. Multi-turn follow-up is implemented
and undemonstrated. This is written down here rather than left to be discovered
on stage.

---

## What was deliberately not done

- **An eighth rule.** Seven is the full scope the problem statement defines.
- **A prediction model.** Disruption-risk signals are provided pre-computed.
  The job is what the controller does *about* them.
- **A full optimisation solver.** The statement says heuristic ranking with
  clear reasoning is sufficient.
- **Prompt tuning as a first response.** Every problem investigated so far,
  the typographic hyphen, the verdict inversion, the round trips, the headline
  truncation, turned out to be code. Prompt changes are the least testable
  lever and the one most likely to regress a measured result.
