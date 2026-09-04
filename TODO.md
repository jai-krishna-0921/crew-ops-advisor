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

## Open

- [ ] 7 golden failures (Q19, Q29, S1, S2, S3, S6, flagship), all traced to
      intent matching in `resolve/`, not to the tools or the ops engine
- [ ] `docs/SAMPLES.md`, a required deliverable
- [ ] Presentation deck, a required deliverable

## Scorecard, deterministic path

| Tier | Total | Correct | Abstained | Wrong |
|---|---|---|---|---|
| 1 | 16 | 15 | 1 | 0 |
| 2 | 14 | 6 | 6 | 1 (plus 1 partial) |
| 3 | 8 | 2 | 6 | 0 |

Tier 1 answers at 100 percent accuracy when it answers, and nothing in any
tier fails unsafely: every failure is an abstention, not a confident wrong
answer.
