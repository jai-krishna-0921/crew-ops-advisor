# TODO

Working tracker for the Crew Ops Advisor submission. Ticked as each lands.

## Landed: the chat surface

- [x] Fonts: Figtree across five weights, one family, display is the same face
      at 800 with the tracking pulled in
- [x] Mono is only for strings a machine reads (tool names, payloads, a rule's
      arithmetic), not for every crew id and clock time
- [x] Composer: field and button only, no "Enter to send", no grounding line,
      no Auto / Agent / Offline switch
- [x] Conversations rail: resident, collapsible, remembered between visits
- [x] Conversations rail: one line per thread, title only, count and time on
      hover
- [x] Section rail down the right edge, no full-width header
- [x] Motion: turn entry, staggered questions and threads, rail collapse,
      streaming caret, route change, send button
- [x] Markdown: per-element rhythm, hanging list markers, tables with room
- [x] Remove the borders: elevation and gap grids instead of hairlines
- [x] Warm ground, one theme, no dark mode and no toggle
- [x] Drop the tier vocabulary from the chat surface
- [x] beautifului.dev primitives: task rows, tool chips, thinking, streaming
      text, confidence meter, context cards, insight cards, elapsed loader

## Landed: correctness

- [x] Thread state machine, one source of truth for the active thread
- [x] Fix: new chat, type, then jump to an existing thread
- [x] Load a thread's history when you open it, not just its id
- [x] Abort in-flight streams on thread switch
- [x] Fix: session restore no longer clobbers a question asked from the URL
- [x] Fix: timestamps leave the API with their zone on them, so a reader
      outside UTC is not shown "5h ago" about something one second old
- [x] Fix: the impact renderer stated "Pairings broken" twice
- [x] Tier 1 result sets render as tables, not run-on prose
- [x] Recommendation above its own working, not under two hundred rule rows
- [x] Fix: "Opens a gap" no longer runs six flight ids off the card edge
- [x] Graceful errors: API down, stream drop, 422, empty result
- [x] Session persistence across a reload
- [x] Contextual memory stubs, wired per thread

## Landed: this pass

- [x] Fonts: Cabinet Grotesk for display, Satoshi for text, both self hosted
      so the product still runs with no network
- [x] Composer: the send button sits in the field, so the empty row is gone
- [x] Fact hover opens one popover, the one under the cursor
- [x] Tool calls and the trace stream on a live turn, not only in history
- [x] Reference elements wired: elapsed loader, task rows, tool chips,
      thinking, source chips under every answer, insight cards on the brief
- [x] Rename and delete a conversation
- [x] The assistant names the conversation from the first answer's headline
- [x] Fix: CORS refused PATCH and DELETE, so rename and delete failed in the
      browser while working under curl
- [x] Fix: the rename field was focused during the click that opened it, so
      the click's own focus handling took the caret straight back out
- [x] Fix: the row menu was trapped in the stacking context its entry
      animation created, and the rows below painted over it
- [x] Fix: an invisible full-viewport backdrop swallowed every click meant
      for the menu it was supposed to dismiss

## Open

- [ ] 7 golden failures (Q19, Q29, S1, S2, S3, S6, flagship), all traced to
      intent matching in `resolve/`, not to the tools or the ops engine
- [ ] Six of the eight Tier 3 questions abstain on one shared cause:
      `find_cover_options` wants a pairing and the question names a person and
      a date. Same `resolve/` intent matching, so likely one fix for both.
- [ ] `docs/SAMPLES.md`, a required deliverable
- [ ] Presentation deck, a required deliverable
- [ ] Architecture diagram of the LLM vs deterministic boundary. It is the 20%
      criterion and the strongest part of the build.

## The model layer

Measured numbers and the full write-up are in `PROGRESS.md`.

- [x] Provider agnostic: `agent/providers.py` is the only module naming a
      vendor. Precedence anthropic, then openai, then ollama.
- [x] Ollama wired, Tier 1 proven end to end through the LangGraph agent
- [x] Fixed: the verifier rejected correct answers when the model wrote
      `C‑3310` with a non-breaking hyphen. Recovered 3 answers, grounding went
      10/16 to 15/16.
- [ ] The `ANTHROPIC_API_KEY` in `.env.local` is invalid and returns 401.
      Anthropic sorts first, so its presence alone takes agent mode down. Fix
      it or remove it. `CREWOPS_LLM_PROVIDER=ollama` overrides meanwhile.
- [ ] With a valid key, re-run `scorecard --mode both`, then decide whether the
      agent path earns its latency: offline is 15/16 at 4ms, the agent is 13/16
      at 7.2s.
- [ ] Q06: `gpt-oss` answers "the window is recorded in the system" instead of
      stating 06:00 to 18:00. The one remaining genuine model shortcoming.
- [ ] Agent results are not reproducible: Q12 has graded wrong, abstained and
      correct on the identical prompt. Do not quote a single run.

## Thread memory, written but unproven

- [ ] The `checkpoints` table has 0 rows: all 27 logged turns ran
      deterministic, which bypasses the graph, so the LangGraph checkpointer
      has never persisted anything
- [ ] 26 threads for 27 turns, so multi-turn follow-up is never exercised
- [ ] The eval harness builds `Advisor` with no memory, so nothing it runs is
      logged. Decide whether that should change.

## Housekeeping

- [ ] Q12's deterministic answer repeats four flight numbers 21 times. It
      grades correct only because matching is containment based, so the grader
      is hiding it.
- [ ] `make lint` format half is red and was before any of this:
      `ruff format --check` wants 41 files. One isolated commit, coordinated,
      since two tools are editing this tree.

## Scorecard, deterministic path

| Tier | Total | Correct | Abstained | Wrong |
|---|---|---|---|---|
| 1 | 16 | 15 | 1 | 0 |
| 2 | 14 | 6 | 6 | 1 (plus 1 partial) |
| 3 | 8 | 2 | 6 | 0 |

Tier 1 answers at 100 percent accuracy when it answers, and nothing in any
tier fails unsafely: every failure is an abstention, not a confident wrong
answer.
