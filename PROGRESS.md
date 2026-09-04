# Progress

Status as of 2026-09-04. Written to be read by someone deciding what to do
next, so it leads with what is not working. Every number here came from
`make test` and `python -m crewops.eval.scorecard` on this commit, not from
memory.

## The short version

The architecture is built and the boundary it claims is real and enforced. The
deterministic path answers Tier 1 at 100% accuracy in single digit
milliseconds. What is not done is Tier 2 and Tier 3 parity, and the agent path
is currently **worse than no agent at all** on the one tier that is mandatory.

## Where each tier actually stands

Scored against the shipped answer keys, all 38 questions.

### Deterministic mode (no model, `--offline`)

| Tier | n | correct | partial | abstained | wrong | accuracy | grounded | avg/p95 |
|---|---|---|---|---|---|---|---|---|
| 1 | 16 | 15 | 0 | 1 | 0 | 100% | 15/16 | 4ms / 5ms |
| 2 | 14 | 6 | 1 | 6 | 1 | 75% | 8/14 | 8ms / 14ms |
| 3 | 8 | 2 | 0 | 6 | 0 | 100% | 2/8 | 32ms / 91ms |
| **All** | **38** | **23** | **1** | **13** | **1** | **92%** | **25/38** | 9ms / 23ms |

"Accuracy" excludes abstentions. It is the share of questions the system chose
to answer that it got right, which is the number the rubric's scoring principle
actually rewards. Coverage is the weak column, not correctness: 13 of 38
questions are declined.

### Agent mode (LangGraph, Ollama `gpt-oss:120b-cloud`), Tier 1 only

| Tier | n | correct | partial | abstained | wrong | accuracy | grounded | avg/p95 |
|---|---|---|---|---|---|---|---|---|
| 1 | 16 | 10 | 1 | 4 | 1 | 83% | 10/16 | 7.3s / 13.9s |

**This is a regression and it is the most important fact in this document.**
Routing Tier 1 through the agent turns 15 correct into 10 correct, introduces
one outright wrong answer, and costs three orders of magnitude of latency.

Two things are worth separating:

- The guardrails worked. Four of the six losses are abstentions, not wrong
  answers, and the scorer reported no verdict inversions. The system declined
  rather than inventing. That is the design doing its job under a weak model.
- The model is the bottleneck, not the architecture. `gpt-oss:120b-cloud` was
  the only locally reachable model that emits tool calls at all (`qwen2.5:7b`
  returns an empty `tool_calls` list for a bound schema, which strands the
  agent loop). It is not good enough for this task.

Agent mode has **never been run against Claude or GPT**, because no key for
either has been configured. Every agent-mode number here is a statement about
`gpt-oss:120b-cloud`, not about the design.

## Test suite

`make test`: **338 passed, 7 failed, 15 xfailed, 2 deselected.**

The 7 failures are all pre-existing golden parity failures and were failing
before this session's work:

- `test_questions.py::test_parity[Q19-T2]`, `[Q29-T2]`
- `test_scenarios.py::test_scenario_parity[S1]`, `[S2]`, `[S3]`, `[S6]`
- `test_scenarios.py::test_flagship_scenario_holds`

The last one matters most. **S2 is the demo scenario** and it currently grades
`wrong` at 14% recall. If the presentation is built around "Captain C-1042 is
out, what do I do", that path does not hold up right now.

The 2 deselected are the new live-provider tests, excluded by default.

## What is already built, contrary to assumption

These came up as open questions and are all present. Listed because it is
cheaper to read this than to rediscover it.

- **Chat history and thread memory.** `agent/memory.py`. Two stores in one
  SQLite file: LangGraph's `AsyncSqliteSaver` checkpointer for message state,
  and a `turns` table holding every settled `Reply` as JSON for audit. Wired
  into the CLI (`crewops chat`, `crewops ask`) and the server
  (`/api/threads`, `/api/threads/{id}`).
- **The database file exists.** `api/.crewops/memory.db`, holding 27 logged
  turns across 26 threads. It is not visible in the repo because `*.db` is
  gitignored and it lives in a dot directory.
- **Database lookup tools.** `store/projection.py` builds an indexed SQLite
  projection of `WorldState` (crew, crew_rating, flight, and more, with
  indices). `tools/registry.py` imports `DatasetStore` and queries it, falling
  back to Python where a column is not indexed. 24 tools total, 14 of them
  classified retrieval-only so the tier guard can refuse a Tier 2 answer built
  on retrieval alone.

### But the memory is less proven than it looks

All 27 recorded turns ran in `deterministic` mode, and the `checkpoints` table
has **0 rows**. The LangGraph checkpointer has therefore never persisted a
single checkpoint, because the deterministic path bypasses the graph entirely.
26 threads for 27 turns means multi-turn conversation is essentially
unexercised. Follow-up resolution ("and what about the first officer?") is
written but not demonstrated.

## What changed this session

The gap was that the model layer was Anthropic-only, so the agent path had
never once executed. It is now provider-agnostic and Tier 1 has been run end to
end through the LangGraph agent.

### Added

| File | Purpose |
|---|---|
| `api/src/crewops/agent/providers.py` | The only module that knows which vendor is behind the model. Provider detection, per-vendor defaults, and the three quirks below. |
| `api/tests/agent/test_providers.py` | 16 tests over detection, precedence, and construction. |
| `api/tests/golden/test_agent_tier1.py` | Two live-provider evals, marked `llm`. |

### Modified

| File | Change |
|---|---|
| `api/pyproject.toml` | Added `langchain-openai`, `langchain-ollama`. Banned all model clients from the core via `banned-api`. Excluded `llm` tests by default. |
| `api/src/crewops/agent/config.py` | `llm_configured()` is provider-aware; `AgentConfig` carries `provider`; `from_env()` takes the default model from the selected provider. |
| `api/src/crewops/agent/factory.py` | `build_model` dispatches through `providers.build` instead of constructing `ChatAnthropic` directly. |
| `api/src/crewops/agent/graph.py` | The no-model abstention names whichever env vars would fix it, not `ANTHROPIC_API_KEY` specifically. Two lines. |
| `api/src/crewops/cli.py` | `crewops health` reports the provider rather than one hardcoded key name. |
| `api/src/crewops/eval/runner.py` | `has_api_key()` is provider-aware; added `provider_name()`. |
| `api/src/crewops/eval/scorecard.py` | Skip message names all three providers. |
| `api/tests/test_boundary.py` | `langchain_ollama` added to the banned client list. |

Nothing in `domain/`, `rules/`, `ops/` or `store/` was touched. The boundary
test still passes.

### Three provider quirks found by measurement

1. The default model id has to follow the provider. `claude-sonnet-5` sent to
   Ollama is a 404 on the first turn.
2. Sampling has to be pinned per vendor. Anthropic's current models reject
   sampling parameters outright; Ollama defaults to temperature 0.8, which
   would make the same question answer differently on consecutive asks.
3. `with_structured_output` has no portable method. Ollama's default
   (`json_schema`) made `gpt-oss:120b-cloud` ignore the schema and return
   prose, failing the parse. `function_calling` binds correctly. The quirk is
   handled inside `providers.py` so the planner node stays vendor-neutral.

Provider precedence is `anthropic -> openai -> ollama`. Dropping in
`ANTHROPIC_API_KEY` switches everything over with no config edit.

## Known defects

- **S2, the flagship demo scenario, grades `wrong`.** 14% recall. Highest
  priority. All 7 golden failures are traced to intent matching in `resolve/`,
  not to the tools or the ops engine, so this is likely one fix rather than
  seven. The six Tier 3 abstentions look like the same cause.
- **Agent mode regresses Tier 1** (10/16 vs 15/16 offline), with one wrong
  answer.
- **Q12 is non-deterministic under the agent.** It graded `wrong` in the scored
  run and `abstained` on re-run of the identical prompt. The hosted model does
  not honour temperature 0 strictly, so single agent-mode results are not
  reproducible and should not be quoted as if they were.
- **Q12's deterministic answer has a duplication bug.** It renders
  "DX401, DX589, DX402, DX401, DX402, DX588, ..." repeating four flight numbers
  21 times. The expected answer is four flights. It grades `correct` only
  because matching is containment-based, so the grader is hiding a real
  presentation bug.
- **`make lint` is red, and was before this session.** `ruff format --check`
  wants 41 files reformatted. Left alone rather than sweeping unrelated files
  into this change.
- **Tier 3 answers 2 of 8.** Six abstain on one shared cause:
  `find_cover_options` cannot resolve a pairing from a question that names a
  person and a date. Same `resolve/` intent matching as the golden failures.

Open work is tracked in `TODO.md`.

## Honest read on the rubric

The 20% "AI utilisation / deliberate boundary" criterion is in good shape and
is provable: there is a boundary test that walks the import graph, a verifier
that attests every atom, four structural guards, and a measured result showing
the guardrails catching a weak model rather than shipping its drift.

"Functionality" is the exposed criterion. Tier 1 is solid offline and shaky
through the agent, Tier 2 is half, Tier 3 is a quarter, and the flagship
scenario does not currently hold.
