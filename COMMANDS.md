# Commands

Every command below was run on this machine and its output checked. Written for
someone standing in front of a judge with a terminal, so each entry says what to
type, what comes back, and what it proves.

Measured numbers live in `PROGRESS.md`. Open work lives in `TODO.md`.

---

## Read this first: the one gotcha

`.env.local` contains an **invalid `ANTHROPIC_API_KEY`** that returns HTTP 401.
Provider precedence is anthropic, then openai, then ollama, so its mere presence
takes agent mode down: the turn dies in under a second with an authentication
error and zero tool calls.

Until that key is fixed or deleted, prefix any agent-mode command with:

```fish
CREWOPS_LLM_PROVIDER=ollama
```

Check which way it is currently pointing before you demo anything:

```fish
cd api
uv run crewops health
```

```
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Check    ┃ Value                   ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Provider │ ollama                  │
│ Mode     │ agent                   │
│ Model    │ deepseek-v4-flash:cloud │
│ Dataset  │ loaded                  │
└──────────┴─────────────────────────┘
```

If `Provider` says `anthropic`, every agent answer will 401. That is the single
most likely way the demo breaks.

---

## Setup

```fish
make install          # uv sync for the API, pnpm install for the web
make dev              # API on :8000 and web on :3000 together
```

Individually:

```fish
make serve            # API only
make web              # web only
```

---

## The demo, in the order to run it

### 1. It works with no API key at all

The strongest opening, because it answers the "is this just a wrapper on a
model" question before anyone asks it.

```fish
cd api
uv run crewops ask "Who is on reserve at BLR on 2026-09-15?" --offline
```

```
╭──────────── tier 1 | deterministic, no model ────────────╮
│ 12 reserve(s) on call for 2026-09-15.                    │
╰──────────────────────────────────────────────────────────╯
Grounding: verified  4/4 figures traced to a tool result
1 tool calls, 0 model calls, 3 ms
```

**Zero model calls, 3 milliseconds, and the grounding line still says 4 of 4
figures traced to a tool result.** The deterministic core answers Tier 1 on its
own; the model adds language, not truth.

### 2. The same question through the LangGraph agent

```fish
CREWOPS_LLM_PROVIDER=ollama uv run crewops ask "Who is on reserve at BLR on 2026-09-15?"
```

Same answer, now with a plan and a visible tool trace. Slower, because a model
is in the loop.

### 3. The proactive watchlist

Not asked for by the rubric, listed under optional enhancements.

```fish
uv run crewops brief 2026-09-15
```

Returns 14 items for that date, 2 critical. The first is `C-5417`, rostered
illegally on 2026-09-19 because a recurrent training certificate expires on
2026-09-17. Deterministic: no model call on this path.

### 4. Multi-turn, with memory that survives a restart

```fish
CREWOPS_LLM_PROVIDER=ollama uv run crewops chat
```

Be honest about this one if asked: it is wired but lightly exercised. See
"Known weak spots" below.

---

## Evaluation: the numbers

This is the repo's own harness, `api/src/crewops/eval/scorecard.py`. It grades
every answer against the shipped answer keys in `questions.json` and
`scenarios.json`. It is not something written for the demo.

### The headline comparison

```fish
cd api
CREWOPS_LLM_PROVIDER=ollama uv run python -m crewops.eval.scorecard --mode both
```

`--mode both` runs the deterministic path and the agent path over all 38
questions and prints **only the rows where the two disagree**, which is the
interesting output.

### Tier 1 only, agent path

The command behind every agent-mode number quoted anywhere:

```fish
CREWOPS_LLM_PROVIDER=ollama uv run python -m crewops.eval.scorecard \
  --mode agent --tier 1 --quiet
```

```
│ Tier 1  │ 16 │ 16 │    0 │    0 │     0 │ 100% │ 16/16 │ 7117/12282 │
   scope    n   ok  part  abst  wrong   acc    grnd    ms avg/p95
```

### Deterministic, everything

```fish
uv run python -m crewops.eval.scorecard --mode deterministic
```

### Useful flags

| Flag | Does |
|---|---|
| `--mode {auto,deterministic,agent,both}` | `auto` picks agent when a provider is configured |
| `--tier 1` | repeatable, so `--tier 1 --tier 2` works |
| `--only Q06,Q12` | single cases, for chasing one failure |
| `--scenarios` | adds the six worked scenarios |
| `--scenarios-only` | just the scenarios |
| `--json path.json` | write the artefact, default `.eval/scorecard-<mode>.json` |
| `--quiet` | drop per-question progress |
| `--no-detail` | summary tables only |
| `--fail-on-unsafe` | exit non-zero if any answer inverts a verdict, for CI |

### Reading the scorecard honestly

`acc` is correct as a share of the questions the system **chose to answer**.
Abstentions are excluded and never counted as failures.

That column misleads on its own, and `kimi-k2.6` is the proof: it scored
**100% accuracy** by declining 11 of 16 questions and getting the other 5
right. Always quote accuracy next to coverage.

---

## The model bake-off

How `deepseek-v4-flash` was chosen. Four models, same 16 Tier 1 questions, same
answer keys.

```fish
cd api
for M in deepseek-v4-flash:cloud gpt-oss:120b-cloud glm-5.1:cloud kimi-k2.6:cloud
    echo "##### $M"
    CREWOPS_LLM_PROVIDER=ollama CREWOPS_MODEL=$M \
      uv run python -m crewops.eval.scorecard --mode agent --tier 1 --quiet \
      | sed -n '/Scorecard, mode=agent/,/^└/p'
end
```

| Model | correct | abst | wrong | grounded | avg | p95 |
|---|---|---|---|---|---|---|
| **deepseek-v4-flash** | **16/16** | 0 | **0** | **16/16** | 6.5s | 12.1s |
| deterministic (no LLM) | 15/16 | 1 | 0 | 15/16 | 4ms | 5ms |
| gpt-oss:120b | 13/16 | 1 | 1 | 15/16 | 7.2s | 10.0s |
| glm-5.1 | 13/16 | 3 | 0 | 13/16 | 16.9s | 27.4s |
| kimi-k2.6 | 5/16 | 11 | 0 | 5/16 | 37.3s | 63.2s |
| qwen2.5:7b | unusable, emits no tool calls | | | | | |

deepseek is the only configuration that beats the deterministic path (16 against
15) and has never produced a wrong answer in 48 graded questions.

`glm-5.1` and `kimi-k2.6` are ruled out on latency: the problem statement says
"a 45 second response is not a decision aid", and their p95 figures are 27.4s
and 63.2s.

**These models do not honour temperature 0 strictly.** deepseek scored 16, 15,
16 on three identical passes. Never quote a single run as if it were stable.

### Switching model or provider

```fish
CREWOPS_MODEL=glm-5.1:cloud ...              # one run, different model
CREWOPS_LLM_PROVIDER=anthropic ...           # once a valid key exists
CREWOPS_LLM_PROVIDER=none ...                # force the offline path
```

---

## Tests and checks

```fish
make test        # full Python suite
make golden      # parity against the shipped answer keys
make check       # ruff, mypy, boundary test, tests. Everything CI runs
make boundary    # just the boundary test
```

Current state: **358 passed, 7 failed, 15 xfailed, 2 deselected.**

The 7 failures are pre-existing and known: Q19, Q29, S1, S2, S3, S6 and the
flagship scenario. All traced to intent matching in `resolve/`. Do not be
surprised by them on stage.

`make lint` is **red**, and was before any of this work: `ruff format --check`
wants 41 files reformatted. `ruff check` itself passes.

### The boundary test, which is the whole submission

```fish
cd api
uv run pytest tests/test_boundary.py -v
```

It walks the **import graph** of `contracts/`, `domain/`, `rules/`, `ops/`,
`store/`, `tools/` and `verify/` and fails if any model client is reachable from
any of them, at any depth. It also asserts the mirror: that `agent/` *does*
import one, so the boundary is not decorative. And it asserts the shipped
dataset is unmodified on disk.

This is how "the model never produces a fact" is enforced structurally rather
than promised in a prompt. It is the 20% AI-utilisation criterion, made
falsifiable.

### The live-provider evals

Excluded from `make test` by default, because they cost time and money and are
not reproducible run to run.

```fish
cd api
CREWOPS_LLM_PROVIDER=ollama uv run pytest -m llm -v
```

Two tests, asserting the rubric's own scoring principle rather than an accuracy
target: an abstention **passes**, only a wrong answer fails, and the agent may
not turn a question the offline path gets right into one it gets wrong.

---

## If a judge asks

**"How do I know the model isn't doing the arithmetic?"**
`uv run pytest tests/test_boundary.py -v`. It walks the import graph.

**"How do I know it isn't making the numbers up?"**
Every answer prints a grounding line: `4/4 figures traced to a tool result`.
The verifier extracts every number, duration, currency amount, date, time,
identifier, station code and rule id from the drafted prose and attests each
one against what the tools actually returned. Unattested atoms get one repair
pass, then the turn abstains.

**"Show me it failing safely."**
`--mode agent --tier 1` on `gpt-oss:120b-cloud` abstains rather than inventing.
Every scorecard prints "No verdict inversions. Every failure failed safely."

**"Does it work without the internet?"**
`uv run crewops ask "..." --offline`. Zero model calls. That is the whole
deterministic path, and it answers Tier 1 at 15 of 16.

**"What does it do badly?"**
Tier 3 answers 2 of 8, the flagship scenario S2 fails, and thread memory is
written but barely exercised. All in `PROGRESS.md`, which is deliberately blunt.

---

## Known weak spots, so nothing is a surprise

- **Tier 2 and Tier 3 are the gap.** Tier 2 is 6 of 14, Tier 3 is 2 of 8. Six
  Tier 3 questions abstain on one shared cause in `resolve/`.
- **S2, the flagship scenario, grades wrong** at 14% recall. If the demo is
  built around "Captain C-1042 is out, what do I do", rehearse it first.
- **Thread memory is unproven.** The `checkpoints` table has 0 rows: every
  logged turn so far ran deterministic, which bypasses the graph, so the
  LangGraph checkpointer has never persisted anything. Multi-turn follow-up is
  implemented and not demonstrated.
- **Agent runs are not reproducible.** Run three times, quote a range.
- **The invalid `ANTHROPIC_API_KEY`.** See the top of this file.

---

## Repository map

| Path | What | Model allowed |
|---|---|---|
| `data/` | Provided dataset. Read only, never regenerate. | no |
| `api/src/crewops/contracts/` | Shared types. The seam. | no |
| `api/src/crewops/domain/` | Typed records, loader, immutable `WorldState` | no |
| `api/src/crewops/rules/` | Clock arithmetic, the seven rules, `RuleTrace` | never |
| `api/src/crewops/ops/` | Cover search, positioning, costing, ranking | never |
| `api/src/crewops/store/` | Indexed SQLite projection of the world | no |
| `api/src/crewops/tools/` | The 24 tools the agent calls | no |
| `api/src/crewops/agent/` | LangGraph graph, prompts, memory, providers | yes |
| `api/src/crewops/verify/` | The grounding verifier | no |
| `api/src/crewops/eval/` | The scorecard harness | no |
| `web/` | Next.js front end. No answering logic. | no |

`agent/providers.py` is the only module in the repository that names a model
vendor.
