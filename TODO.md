# TODO

Working tracker for the Crew Ops Advisor submission. Ticked as each lands.
Anything struck through was dropped on purpose, with the reason.

## In flight: the chat surface

- [ ] Fonts: move to Figtree, drop the leftover display face
- [ ] Composer: remove the "Enter to send" hint and the grounding status line
- [ ] Conversations rail: a toggle that collapses it
- [ ] Conversations rail: one line per thread, title only
- [ ] Motion: entry, stagger, rail collapse, streaming, route change
- [ ] Markdown: paragraphs, lists, tables and code render with real rhythm

## Landed

- [x] Thread state machine, one source of truth for the active thread
- [x] Fix: new chat, type, then jump to an existing thread
- [x] Load a thread's history when you open it, not just its id
- [x] Abort in-flight streams on thread switch
- [x] Fix: session restore no longer clobbers a question asked from the URL
- [x] Graceful errors: API down, stream drop, 422, empty result
- [x] Session persistence across a reload
- [x] Contextual memory stubs, wired per thread
- [x] Remove the borders: elevation and gap grids instead of hairlines
- [x] Warm ground, one theme
- [x] Drop the dark theme, the toggle and the pre-paint script
- [x] Drop the Auto / Agent / Offline mode switch from the composer
- [x] Drop the tier vocabulary from the chat surface
- [x] Section rail down the right edge, no full-width header
- [x] Resident conversations rail
- [x] beautifului.dev primitives: task rows, tool chips, thinking, streaming
      text, confidence meter, context cards, insight cards, elapsed loader
- [x] Tier 1 result sets render as tables, not run-on prose
- [x] Fix: timestamps leave the API with their zone on them
- [x] Recommendation above its own working, not under two hundred rule rows

## Still open, wider than the UI

- [ ] 7 golden failures (Q19, Q29, S1, S2, S3, S6, flagship), all traced to
      intent matching in `resolve/`, not to the tools or the ops engine
- [ ] `docs/SAMPLES.md`, a required deliverable
- [ ] Presentation deck, a required deliverable

## The model layer

Measured numbers behind these are in `PROGRESS.md`.

- [x] Provider-agnostic model layer. `agent/providers.py` is the only module
      that names a vendor; precedence is anthropic, then openai, then ollama
- [x] Ollama wired and Tier 1 proven end to end through the LangGraph agent
- [ ] Add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` and re-run
      `scorecard --mode both`. One env var, nothing to code.
- [ ] Then decide whether the agent path earns its latency. Offline is 15/16
      on Tier 1 at 4ms; the agent on `gpt-oss:120b-cloud` is 10/16 at 7.3s and
      introduces one wrong answer. Demoing the deterministic path with the
      agent as the conversational front end is a legitimate call.
- [ ] Do not prompt-tune for `gpt-oss:120b-cloud`. It is the wrong variable:
      it is simply the only locally reachable model that emits tool calls at
      all (`qwen2.5:7b` returns an empty `tool_calls` list for a bound schema).

## Correctness, beyond the golden failures

- [ ] Six of the eight Tier 3 questions abstain on one shared cause:
      `find_cover_options` reports "Name a pairing_id, a set of flight_numbers,
      or a for_crew_id to cover". The question names a person and a date and
      nothing bridges that to a pairing. Same `resolve/` intent matching as the
      golden failures above, so likely one fix for both.
- [ ] Q12's deterministic answer repeats four flight numbers 21 times
      ("DX401, DX589, DX402, DX401, ..."). It grades `correct` only because
      matching is containment-based, so the grader is hiding it. Dedup in the
      renderer, and consider what else containment matching is masking.

## Thread memory, written but unproven

- [ ] The `checkpoints` table has 0 rows and all 27 logged turns ran
      deterministic, which bypasses the graph. The LangGraph checkpointer has
      never persisted anything.
- [ ] 26 threads for 27 turns: multi-turn follow-up ("and what about the first
      officer?") is implemented but never exercised
- [ ] Confirm a thread survives a process restart, which is the claim in
      `agent/memory.py`
- [ ] The eval harness builds `Advisor` with no memory, so nothing it runs is
      logged. Decide whether that should change.

## Housekeeping

- [ ] `make lint` is red and was before any of this: `ruff format --check`
      wants 41 files. Do it as one isolated commit touching nothing else, and
      coordinate first, since two tools are editing this tree.
- [ ] Architecture diagram of the LLM vs deterministic boundary. It is the 20%
      criterion and the strongest part of the build; it should not be the part
      with no picture.
- [ ] README commentary on crew PII in production, which the problem statement
      says earns credit under Technical Excellence.
- [ ] The failure case for `docs/SAMPLES.md` is already sitting here: the agent
      regressing Tier 1 under a weak model while the guardrails held and
      abstained rather than inventing. Better than anything invented.

## Deliberately not doing

- An eighth rule. Seven is the full scope.
- Regenerating or "fixing" `data/`. Read only; regenerating moves every key.
- Loosening the verifier or a guard to make a test pass. If a figure is
  unattested, add the fact to the tool output instead.
- Chasing all six Tier 3 scenarios. One excellent path beats six shaky ones.
