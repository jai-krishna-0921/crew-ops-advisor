# UI rebuild: from console to chat

Tracking checklist. Ticked as each lands.

## Research
- [x] Scrape beautifului.dev fully: component inventory, design language, motion
- [x] Locate the Comarketer / serviceworker font stack in the local Cashfree repos

## Correctness before polish
- [x] Thread state machine: one source of truth for the active thread
- [x] Fix the edge case: new chat, type, then jump to an existing thread
- [x] Load a thread's history when you open it, do not just switch the id
- [x] Abort in-flight streams on thread switch, never let a late event land in the wrong thread
- [x] Graceful errors everywhere: API down, stream drop, 422, empty result
- [x] Session persistence so a reload does not lose the conversation
- [x] Contextual memory stubs, wired to the thread

## The chat itself
- [x] Fonts from the reference stack
- [ ] Centred assistant response, not the traditional left-aligned bubble
- [x] react-markdown rendering with a hardened component map
- [ ] AI elements from beautifului.dev: prompt bar, task rows, tool chips,
      reasoning, recommendation card, context cards, streaming text
- [ ] Floating sliding top bar for the non-chat pages
- [x] Minimalist pass: one accent, one radius scale, one type scale

## Verify
- [ ] Screenshots of every state via Playwright
- [ ] Walk the edge cases by hand in the browser
- [ ] No em dashes anywhere
- [ ] Build, lint and typecheck clean
