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

## Landed: weight, width and colour

- [x] Type up one notch across the scale, and body weight at 450. Cabinet
      Grotesk renders smaller and lighter than the face the scale was set
      against, so a page that had been merely dense became thin.
- [x] Resizable rails: a 9px drag handle with a 1px line, `col-resize`,
      clamped, persisted, double-click to reset, arrow keys to nudge. Both
      the conversations rail and the evidence panel.
- [x] Colour: a soft tint and a matching icon tile per suggestion card, a
      gradient over the second clause of the greeting only, and a question
      bubble in its own warm colour. Calmer than the reference: no
      photograph, no six-hue spectrum, chroma about a third of it.

## Landed: the landing page moves

- [x] The section heading now lives inside the pinned area rather than above
      it. It had scrolled off the top before the cards started walking, so a
      reader arrived at a screen of cards with no label and could not tell
      whether the sideways movement was the page working or a glitch.
- [x] A scroll progress hairline across the top of the document, on a
      `scroll()` timeline.
- [x] Section headings arrive word by word out of a mask, 40ms apart.
- [x] Cards settle as they enter: a little further away and a little turned,
      resolving square by the middle of the window, alternating direction.
- [x] Section padding up from py-24/32 to py-32/48, so the scroll has room to
      show what it is doing between blocks.
- [x] A proper footer: a reverse ticker, three link columns including four
      questions somebody can click straight into, the brand block, the
      snapshot line, and a cropped wordmark drifting sideways against the
      scroll.
- [x] Fix: `Words` was a deadlock. Each word watched itself with an
      IntersectionObserver from inside the mask that was hiding it, and the
      observer accounts for clipping by an ancestor's overflow, so it reported
      zero area and the word never revealed. It only appeared to work at
      desktop size, where the word was taller than the 40px of travel and a
      sliver stayed inside the clip box. One observer on the heading now.
- [x] Fix: word spaces are a margin. A trailing space inside an inline-block
      is trimmed, so the heading rendered as "Itgoesasfarasthe questiondoes".
- [x] Fix: the footer wordmark ran a third of a viewport past both edges,
      which reads as text that escaped rather than as a crop.

## Landed: a landing page

The advisor moved to `/ask` and `/` became a page that explains the product.
`/?q=...` and `/?thread=...` forward on the server, so every demo link, the
brief's suggested questions and anything already shared still land on the
console with the question intact.

- [x] Built it once as the template and threw that away. Centred eyebrow,
      centred headline with a gradient on two words, centred subtitle, two
      centred buttons, repeated five times down the page. Competent, and the
      exact page a generator produces.
- [x] Rebuilt asymmetric: the hero is set left with three cards stacked to the
      right of it at different depths and rotations, each drifting at its own
      rate. Section headings sit still on the left while their content scrolls
      past.
- [x] The three tiers are a horizontal track. The section pins to the window
      and the cards walk left as the reader scrolls down, on a CSS scroll
      timeline. No scroll listener anywhere, and where scroll timelines are
      unsupported the same markup is a row you swipe.
- [x] A ticker of dataset counts, a highlighter mark, a progress line tied to
      the same timeline as the track it measures, and a fourth card at the end
      of the three tiers for the question it refuses.
- [x] Copy rewritten with a voice. "The model plans and explains,
      deterministic code computes" is accurate and reads like a datasheet.
      "The model isn't allowed to do the maths" is the same claim, shorter,
      and how anybody would say it out loud.
- [x] shadcn primitives: `Button` and `ButtonLink` on `cva` with the trailing
      icon in its own disc, and an accordion on Radix for the seven rules so
      the panel height animates instead of snapping.
- [x] No scorecard on it, on purpose. `PROGRESS.md` records the same model
      scoring 16, 15 and 16 on three identical passes, and a landing page is
      the surface nobody returns to update. The dataset counts cannot drift;
      an accuracy figure would be quietly false within a week.
- [x] Fix: the landing page was making two API calls it had nowhere to put,
      which also made it depend on the API being up. It talks to nothing now.
- [x] Fix: `router.replace("/")` after a URL-seeded question sent the reader
      to the landing page instead of to their answer.

## Landed: the answer has no heading

- [x] `Reply.headline` stops being an `h2` at 24px in the display face. It is
      the answer's first sentence and it goes back into the prose stream as
      its own paragraph, same face, same size, same weight. Answer first is
      carried by position, which is how a chat does it, not by typography.
- [x] Fix: the figures in the headline were the only figures in the product
      not bound to the Fact that attests them. The `h2` rendered plain text,
      so `39.07h` in the lead was dead and the identical `39.07h` one line
      below opened its arithmetic. Routing the lead through `Markdown` links
      the whole answer.
- [x] Fix: a first line over the 200 character budget printed its lead
      sentence twice. `_body_after` only recognised the case where the
      headline was the WHOLE first line, and over the budget it is a slice of
      it, so the body kept the line entire.
- [x] Fix, at the root: a headline is a sentence or it is nothing.
      `_first_sentence` used to fall back to a cut on the nearest word
      boundary when no sentence end fitted, which produced "C-1042 has accrued
      20.93 duty hours ... (max 60 duty hours in" as the lead line, printed by
      the CLI in a bold panel and by the web immediately above the same
      sentence in full. There is no interface where a truncated clause is the
      right thing to lead with.
- [x] The turns already in the log were written by the version that cut mid
      sentence, so the web checks whether the body still opens with the lead
      before prepending it. A fresh reply never reaches that branch.

## Landed: colour, second pass

The first pass read the reference at about a third of its chroma and the
result was too quiet to see. This pass takes the reference at its word on the
chrome and leaves the answers alone, because colour on an answer already means
something and a decorative hue next to a verdict is worse than no colour.

- [x] Card tints up from 0.022 to 0.038, tiles from 0.045 to 0.085. Six cards
      now read as six colours rather than as six sheets of paper.
- [x] Each card carries a filled arrow button in its own hue, always visible,
      which is the reference's most distinctive element and the thing that
      makes a card read as a button rather than as a panel.
- [x] New conversation is a gradient button, the one strongest colour in the
      rail, instead of a text row that looked like a list item.
- [x] The primary gradient runs blue to violet rather than blue to blue. Two
      neighbouring hues still, not a spectrum.
- [x] The hero light is full bleed and three layers: an indigo top right, a
      warm rose top left, and the original wash under the greeting.
- [x] The greeting is bigger, and the gradient still covers one clause only.
- [x] The active conversation and the active section both carry the accent
      rather than a grey fill.
- [x] A gradient mark in the composer. It is decoration, and the composer's
      rule was against putting plumbing and unverifiable claims in front of a
      controller, not against the product having a face.

Deliberately not taken from the reference: the "All systems operational" pill
(the engine and the snapshot are on the section rail already, and a mode
indicator on the chat surface is the thing that was removed once), the "Try
asking" chips under the composer (the six cards are that, and they would
follow the composer into every conversation), and the handwritten script
accent (no script face is loaded and adding one for two words is a network
request for decoration).

## Landed: one sentence once, and a name that fits

- [x] Fix: an answer printed its opening sentence twice, once as the heading
      and once at the top of the body. `_body_after` only removed the headline
      when the answer had a line break in it, and most answers are one
      paragraph. It now removes a leading *sentence* and leaves a word
      boundary cut alone, because taking that out would open the body halfway
      through a clause.
- [x] Fix: a greeting rendered three times over. The heading, the paragraph
      under it and the card all carried the same words, and the three
      suggestions appeared once inside the card and again below it. When a
      turn abstains the card is the answer, so the heading and the body above
      it are gone and the follow ups are deduplicated against the card's own.
- [x] Fix: a greeting is no longer dressed as a failure. It was headed "No
      answer given" beside an empty status pill, because the web
      `AbstentionReason` union never learned the `greeting` case the API had
      started sending. It now reads "Crew Ops Advisor" and "Try asking",
      matching what the CLI already did.
- [x] Conversation names come from the question, not the answer's headline.
      Five words, identifier first, no model: `agent/titles.py`, checked
      against all 38 dataset questions. "hey" is "Greeting"; Q02 is "C-1042
      duty hours"; Q31 is "C-1042 on P-2291 ranked options". The identifier
      leads because the rail truncates from the right, and the id is the token
      somebody is scanning thirty rows for.
- [x] Suggested questions are rows at reading size in the tinted card family,
      not 11px grey chips. On an abstention they are the only actionable
      content on the card, and they were the smallest thing on it.
- [x] Pagination, one primitive in `ui/pagination.tsx`, applied to the brief's
      alerts (8), the rulebook (4), a Tier 1 table's rows (10), the evidence
      panel's facts (12) and tool calls (8), and the candidates a cover search
      ruled out (6). It renders nothing when the list fits on one page.
- [x] Pinning a fact turns the evidence panel to its page. Paging broke the
      link outright: clicking a figure in the prose opened the panel on page 1
      showing twelve rows that had nothing to do with what was clicked.

## Landed: the font finally applies

- [x] Fonts, verified by computed style rather than by network requests. The
      `--font-app-*` variables were on `<body>` and read on `:root`, its
      parent, so both tokens resolved to empty and every surface fell back to
      the UA stack. Four typefaces in a row "did not change anything" for this
      one reason.
- [x] Reasoning above the answer, folded, so an answer never arrives with no
      visible account of where it came from
- [x] A fact popover closes on click-away and on Escape
- [x] Bigger toggles on the threads rail and the evidence panel
- [x] The evidence panel no longer overflows: grid columns can shrink, long
      derivations wrap, and a long text Fact stopped pushing its row 155px
      past the panel
- [x] `fonts/.gitignore` fixed, so the extracted archives stop showing as 93
      untracked changes

## Landed: agent mode

- [x] Fix: the API and the CLI never read `.env.local`, so a configured key
      was ignored and every turn ran offline. `load_env` moved out of the eval
      harness into `crewops.env` and is called by both.
- [x] Agent mode verified end to end through the UI, 59/59 figures attested

## Landed: this pass

- [x] Fonts: Clash Grotesk display, Cabinet Grotesk text, the variable files
      from `fonts/`, self hosted, one request each
- [x] Landing cards: a short prompt on the button, the dataset's exact
      question sent and shown on hover
- [x] Landing subtitle cut from three lines to two
- [x] Delete asks in a real dialog, on Radix, with Keep it as the default
- [x] Delete every conversation at once, from the rail header
- [x] Conversations grouped by day: Today, Yesterday, the week, earlier
- [x] Ctrl-K opens search, and the hint now says Ctrl on a Linux keyboard
      rather than a Mac key that is not there
- [x] shadcn primitives for the dialog and the row menu, which also removed
      three hand-rolled bugs by deleting the code that had them
- [x] A pointer cursor on everything pressable, restored once in base rather
      than sprinkled through the markup
- [x] Gradients: the primary action, the rank-1 marker, one soft light behind
      the empty conversation, and the rail edge in place of a border
- [x] Cleared the 26 throwaway runs from the demo database

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

Everything below is coverage. The deterministic path currently answers 27 of 38
with no wrong answers, no partials and no verdict inversions; the 11 it
declines it declines honestly. Every one investigated so far has been a routing
gap, never a rules, tool or arithmetic gap.

- [ ] S4 partial at 70%: the delay answer does not name the delayed flight in
      prose. Fourth instance of the renderer summarising a collection the key
      wants the members of.
- [ ] S6 partial at 79%: the double sick call needs richer per-gap enumeration
      alongside the joint allocation.
- [ ] Five Tier 3 questions still abstain. Four of them name an aircraft by
      tail; the tool can now bridge a tail to a pairing but the offline path
      deliberately will not route on it (see DECISIONS 15), so this needs the
      agent, or a date-disambiguated intent.
- [ ] Q38 is a design question ("which three data points should a morning
      briefing surface and why"). It may not be answerable by this system at
      all, and saying so is a legitimate outcome.
- [ ] Agent-mode Tier 2 is 11 of 14 plus or minus 2. Quote a median of five
      runs, never a single run.

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
- [x] Model bake-off on Tier 1. `deepseek-v4-flash:cloud` is now the default:
      16/16 correct, zero wrong, 16/16 grounded, p95 12.1s. It is the first
      configuration to beat the deterministic path (16 against 15). gpt-oss
      13/16 with one wrong; glm-5.1 13/16 and a 27.4s p95, too close to the
      "45s is not a decision aid" line; qwen2.5:7b emits no tool calls at all.
- [ ] Agent results are not reproducible: deepseek scored 16, 15, 16 on three
      identical passes and under gpt-oss Q12 graded wrong, abstained and
      correct. Quote a range or run three times, never a single number.
- [ ] With a valid hosted key, re-run `scorecard --mode both` and compare
      against deepseek before deciding what the demo runs on.

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
