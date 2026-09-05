# Contracts

Three workstreams build against this document in parallel. It is the only
place where their boundaries are defined. If something here is wrong or
missing, raise it rather than working around it locally: a local workaround
becomes an integration failure two hours later.

The authoritative Python types live in `api/src/crewops/contracts/`. This
document explains them and adds the HTTP surface. Where the two disagree, the
Python wins and this document is the bug.

## Ownership map

| Workstream      | Owns (writes)                                                                                | Reads                                  | Never touches                                           |
| --------------- | -------------------------------------------------------------------------------------------- | -------------------------------------- | ------------------------------------------------------- |
| **Core**  | `api/src/crewops/{domain,rules,ops,store,tools}/`, `api/tests/core/`                     | `data/`, `contracts/`              | `agent/`, `verify/`, `server/`, `web/`          |
| **Agent** | `api/src/crewops/{agent,verify,server}/`, `api/src/crewops/cli.py`, `api/tests/agent/` | `contracts/`, `tools/` interface   | `domain/`, `rules/`, `ops/`, `store/`, `web/` |
| **UI**    | `web/`                                                                                     | `contracts/stream.py`, this document | everything under`api/src/`                            |
| **Root**  | `contracts/`, `Makefile`, `CLAUDE.md`, `docs/`                                       | everything                             |                                                         |

`data/` is read only for everyone, always.

## The boundary rule, stated precisely

The model may decide:

- which tools to call, with which arguments, in what order
- when it has enough to answer and when it must abstain
- how to phrase an answer for a controller under time pressure
- which of the returned facts are worth surfacing first

The model may not:

- state a number, identifier, date, station code, currency amount or rule id
  that no tool returned this turn
- perform arithmetic, including "roughly", "about" and unit conversion
- infer a rule verdict from context instead of calling `check_legality`
- soften a breach into a warning, or a `INSUFFICIENT_DATA` into a pass

The verifier enforces the second list mechanically. It is not a prompt
instruction, it is a graph node that can reject the turn.

## Evidence model

Every tool returns a `ToolEnvelope`:

```
ToolEnvelope
  tool        str            which tool ran
  args        dict           what it was called with
  ok          bool           false means the lookup failed, not "nothing found"
  payload     typed model    the structured result
  facts       list[Fact]     every citable atom in the payload
  trace       list[TraceStep] readable reasoning steps
  citations   list[Citation] dataset files and records touched
  latency_ms  int
```

A `Fact` is the unit the verifier checks against:

```
Fact
  key         str          "C-2087.duty_7d.projected"
  label       str          "Projected 7 day duty"
  value       scalar       61.33
  unit        FactUnit     "hours"
  provenance  dataset | computed | assumed
  source      str          "duty_clocks.json#C-2087" or "crewops.rules.duty.window"
  derivation  str | None   required when computed: the arithmetic, written out
```

**The rule that makes this work:** if a number can appear in an answer, a tool
must have emitted a `Fact` for it. When the verifier rejects an answer for an
unattested number, the fix is to add the missing `Fact` in the tool, never to
relax the verifier.

## Tool surface

Defined as a `Protocol` in `api/src/crewops/contracts/tools.py`. The Core
workstream implements it as `crewops.tools.registry.Tools`. The Agent
workstream binds it and never reaches past it.

Twenty four tools across three tiers:

| Tier              | Tools                                                                                                                                                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1, retrieval      | `find_crew`, `get_crew_detail`, `find_flights`, `find_pairings`, `get_duty_clocks`, `list_reserves`, `find_expiring_certifications`, `get_pairing`, `get_roster`, `find_crew_at_risk`, `aggregate`, `get_cost_rates` |
| 2, consequence    | `check_legality`, `simulate_absence`, `simulate_reassignment`, `simulate_station_closure`, `simulate_delay`, `scan_duty_headroom`                                                                                                |
| 3, recommendation | `find_cover_options`, `plan_joint_cover`, `draft_notification`                                                                                                                                                                         |
| cross cutting     | `get_watchlist`, `get_world_summary`, `explain_rule`                                                                                                                                                                                   |

`RETRIEVAL_ONLY` names the tools that cannot, on their own, support a Tier 2 or
Tier 3 answer. Retrieval establishes what is; it does not establish what
follows. The agent graph checks this before it lets an answer through.

## HTTP surface

Base URL `http://localhost:8000`. The web app talks to nothing else.

### `POST /api/chat` : text/event-stream

Request body is `ChatRequest`:

```json
{ "question": "Captain C-1042 is out, what should I do?",
  "thread_id": "optional, omit to start a new thread",
  "as_of": "optional ISO datetime, defaults to the dataset snapshot",
  "force_mode": "optional: agent | deterministic" }
```

Response is a sequence of SSE events. Every event is one JSON object with a
`type` discriminator, a `turn_id`, a monotonic `seq` and an `at` timestamp.

| `type`         | Carries                                                     | UI should                                         |
| ---------------- | ----------------------------------------------------------- | ------------------------------------------------- |
| `run_started`  | `thread_id`, `question`, `mode`                       | open the turn, show the mode badge                |
| `plan`         | `intent`, `tier`, `steps[]`                           | show what the system intends to do                |
| `tool_call`    | `tool`, `args`, `label`                               | append a live step chip                           |
| `tool_result`  | `tool`, `ok`, `latency_ms`, `summary`, `envelope` | settle the chip, stock the evidence drawer        |
| `trace`        | `step`                                                    | append to the reasoning trail                     |
| `token`        | `text`                                                    | stream provisional prose, visibly provisional     |
| `verifying`    | `atom_count`                                              | show the grounding check running                  |
| `verification` | `report`                                                  | show verified, repaired or rejected               |
| `abstain`      | `abstention`                                              | render the refusal card, not an error             |
| `reply`        | full`Reply`                                               | replace provisional prose with the settled answer |
| `error`        | `message`, `recoverable`                                | error state                                       |
| `done`         | `total_ms`                                                | close the turn                                    |

**Ordering guarantee:** `reply` always arrives before `done`, and `verification`
always arrives before `reply`. Tokens are provisional until `reply` lands. The
UI must not present streamed tokens as final: that is the difference between a
system that looks honest and one that is.

### Other routes

| Method   | Path                           | Returns                                                      |
| -------- | ------------------------------ | ------------------------------------------------------------ |
| `GET`  | `/api/health`                | `{status, dataset_loaded, snapshot, llm_configured, mode}` |
| `GET`  | `/api/world/summary`         | counts, snapshot time, base, date range                      |
| `GET`  | `/api/brief?date=YYYY-MM-DD` | `Watchlist`                                                |
| `POST` | `/api/simulate`              | `ImpactReport`, deterministic, no model                    |
| `POST` | `/api/legality`              | `LegalityReport`, deterministic, no model                  |
| `POST` | `/api/cover`                 | `Recommendation`, deterministic, no model                  |
| `GET`  | `/api/threads`               | thread list from checkpoint memory                           |
| `GET`  | `/api/threads/{id}`          | full turn history for a thread                               |
| `GET`  | `/api/rules`                 | the seven rules as shipped                                   |
| `GET`  | `/api/questions`             | the 38 sample questions, for the demo launcher               |

**Response envelopes, stated exactly.** Naming a type here without pinning its
JSON is how the console ended up crashing against the live server: both sides
implemented something reasonable and they disagreed. So, precisely:

| Path                                                                 | Body                                                                                                          |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `/api/health`                                                      | the object itself, unwrapped                                                                                  |
| `/api/world/summary`                                               | `{summary, facts, snapshot}`, the world under `summary`                                                   |
| `/api/rules`                                                       | `{rules, count}`, and each entry is itself an envelope with the rule under `payload`                      |
| `/api/questions`                                                   | `{questions, count}`, records in the dataset's own vocabulary: `question_id`, `tier`, `prompt`        |
| `/api/threads`                                                     | `{threads, count}`, records in the memory layer's vocabulary: `first_question`, `turns`, `started_at` |
| `/api/brief`, `/api/simulate`, `/api/legality`, `/api/cover` | a full`ToolEnvelope`, result under `payload`, with `facts` alongside                                    |

The envelope is deliberate on the tool-backed routes: its `facts` are what let
the console trace a figure on screen back to the arithmetic that produced it.
Clients unwrap; they do not ask the server to flatten.

The dataset's field names and the memory layer's field names are not ours to
rename. A client that wants different names adapts them at its own boundary,
in one place.

The deterministic routes exist so the UI can build panels that never invoke the
model. A judge should be able to see the rules engine working with the API key
unset.

### CORS

Allow `http://localhost:3000` in development. No auth: the problem statement
explicitly excludes authentication from scope.

## TypeScript mirror

`web/src/lib/contracts.ts` mirrors every type in this document. It is written
by hand, not generated, and kept in sync by review. The UI workstream owns it.

## Rules of engagement between workstreams

1. **Do not stub another workstream's code.** If the Core tools do not exist
   yet, the Agent workstream builds against the `ToolSurface` protocol with a
   fake that returns fixtures, in its own test tree.
2. **Do not edit `contracts/`.** Raise a change request instead.
3. **Do not add a dependency to the other side's manifest.**
4. **Commit small and often on your own paths.** Never `git add -A` from the
   repository root: you will commit another workstream's half finished work.
5. **No em dashes, no attribution trailers in commit messages.** See the root
   `CLAUDE.md`.
