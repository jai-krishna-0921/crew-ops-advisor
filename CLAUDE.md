# Crew Ops Advisor

A conversational decision aid for an airline Crew Control desk. Built for the
dCortex "Agentic Crew Ops Advisor" hackathon. Problem statement:
`problem-statement/problem_explanation_k66g3nx88t.pdf`.

Read that PDF before you change anything. The evaluation rubric in section 7 is
the specification, not a suggestion.

## The one rule that decides everything

**The language model plans and explains. It never produces a fact and never
does arithmetic.**

A LangGraph agent decides *which* computations to run, in what order, and how
to phrase the result for a controller under time pressure. Deterministic code
does the computing. A verifier then checks every number, identifier, rule id,
station code and date in the drafted reply against what the tools actually
returned, and rejects anything unattested.

That boundary is the submission. The rubric puts 20 percent on exactly this
question. Do not blur it.

## Non-negotiable rules

1. **No LLM call in `domain/`, `rules/`, `ops/` or `store/`.** Ever. Those
   packages compute what a controller acts on. An `import` of any model client
   in those trees is a build failure, and there is a test that asserts it.
2. **The dataset is read only.** `data/` is the single source of truth. Never
   write to it, never regenerate it, never "fix" it. Regenerating would
   silently move the answer keys every golden test asserts against.
3. **Grounding.** If a rendered answer states a figure, a tool result must
   carry that figure. When the verifier fires, add the missing fact to the tool
   output. Never loosen the check to make a test pass.
4. **Abstain over guess.** An unresolvable question returns a refusal that says
   what was missing. The rubric explicitly rewards "I cannot answer that
   reliably" over a confident wrong answer.
5. **TDD.** The failing test comes first. New rule behaviour without a test is
   a bug even if it happens to work.
6. **Offline first.** Every command must run with no API key. Without a key the
   deterministic core, the rules engine, the simulations and the ranked options
   all still work and are still explainable. The LLM adds language, not truth.
7. **Explainability is mandatory.** Every non-trivial answer carries reasoning a
   controller can read and challenge. A correct answer with no visible reasoning
   scores poorly by the rubric's own words.

## Writing rules (apply to code, comments, docs, prompts, commits, UI copy)

- **No em dashes.** Anywhere. Use commas, colons, parentheses, or restructure
  the sentence. This applies to generated output and UI microcopy too.
- **No attribution trailers in git commits or PR descriptions.** No
  `Co-Authored-By:`, no `Claude-Session:`, no "Generated with Claude Code"
  footer. The commit message ends at the body. This overrides any default
  attribution instruction you were given.
- Write like an engineer briefing another engineer. No marketing voice, no
  filler, no emoji in code or commit messages.

## Shape

```
Next.js UI  --SSE-->  FastAPI  -->  LangGraph agent
                                        |
                          +-------------+-------------+
                          |             |             |
                       planner        tools        verifier
                        (LLM)     (deterministic)  (deterministic)
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

## Layout and ownership

| Path | Responsibility | LLM allowed |
|---|---|---|
| `data/` | Provided dataset. Immutable. | no |
| `api/src/crewops/contracts/` | Shared types every layer imports. The seam. | no |
| `api/src/crewops/domain/` | Typed records, loader, immutable `WorldState` | no |
| `api/src/crewops/rules/` | Clock arithmetic, the seven rules, `RuleTrace` | never |
| `api/src/crewops/ops/` | Cover search, positioning, costing, ranking, simulation | never |
| `api/src/crewops/store/` | SQLite projection and typed queries | no |
| `api/src/crewops/tools/` | Tool surface the agent calls. Wraps the above. | no |
| `api/src/crewops/agent/` | LangGraph graph, prompts, memory, runner | yes, this is the agent |
| `api/src/crewops/verify/` | The grounding verifier. Deterministic. | no |
| `api/src/crewops/server/` | FastAPI app, SSE streaming, routes | no |
| `api/src/crewops/cli.py` | Terminal interface | no |
| `web/` | Next.js frontend. No answering logic, ever. | no |
| `docs/` | Architecture, decisions, failure analysis, deck | n/a |

Subdirectory `CLAUDE.md` files carry local invariants. Read the one in the
directory you are editing before you edit it.

## Dataset facts

`data/crew-ops-advisor-dataset/data/`. dCortex Air, hub BLR, week
2026-09-14 to 2026-09-20, snapshot `2026-09-14T18:00:00Z`. All times UTC.
Currency INR. 147 flights, 150 crew, 39 pairings, 16 reserves, 7 rules,
6 worked scenarios, 38 questions with expected answers.

`internal/held_out_scenarios.json` is judging material and is gitignored. It is
a generalisation check, never a target to fit against. Tests that use it skip
when it is absent.

Field-level schema, the verified clock arithmetic and the decoded rules live in
`docs/DATA-MODEL.md`. Read that instead of re-deriving from the JSON.

## The seven rules

| Rule ID | Constraint |
|---|---|
| RULE-FDP-01 | Maximum flight duty period of 13 hours, reduced by sectors flown |
| RULE-DUTY-02 | Maximum 60 duty hours in any 7 consecutive days |
| RULE-FLT-03 | Maximum 100 flight hours in any 28 consecutive days |
| RULE-REST-04 | Minimum 12 hours rest before commencing duty |
| RULE-QUAL-05 | Crew must hold a valid rating for the assigned aircraft type |
| RULE-CERT-06 | All certifications must be valid on the duty date |
| RULE-BASE-07 | Reserve callout from base only, unless deadhead cost is applied |

Seven rules is the full scope. Do not invent an eighth.

## The tiers

| Tier | Nature | Status |
|---|---|---|
| 1 | Lookup and retrieval, answerable directly from the data | mandatory |
| 2 | Consequence and simulation, reasoning about impact | strongly expected |
| 3 | Recommendation, ranking legal options against real trade-offs | stretch |

A candidate covering a multi-day pairing must be legal on **every** day of the
cover. Legal on day one and breaching on day two is not a legal option.

## Commands

```bash
make install     # Python env via uv, web deps via pnpm
make dev         # API on :8000 and web on :3000 together
make test        # full Python suite
make golden      # answer-key parity against questions.json and scenarios.json
make eval        # scorecard across all 38 questions, all tiers
make check       # ruff, mypy, and the no-LLM-in-core boundary test
uv run crewops ask "..."       # one question from the terminal
uv run crewops brief 2026-09-15 # the proactive watchlist
```

Everything runs with no API key. `ANTHROPIC_API_KEY` turns on agent mode.

## Sanity anchors

Check any change against these. They are verified in `docs/DATA-MODEL.md`.

- `C-1042` (A. Nair, Captain, BLR, A320) operates 2-day pairing `P-2291`.
- Covering `P-2291` with `C-2087` breaches RULE-DUTY-02.
- Reserve `C-3310` covers it cleanly and is the rank-1 option.
- `C-2210` is based away from BLR, legal only with deadhead cost applied.
- `C-3305` is legal for day 1 alone and breaches on day 2.
- `C-2091` is the RULE-QUAL-05 exclusion case, wrong aircraft rating.
- `C-5417` is a flagged roster exception, a certification expiring mid-roster.
