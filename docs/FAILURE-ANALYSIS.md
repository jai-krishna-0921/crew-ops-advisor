# Failure analysis

The problem statement asks for "at least one case your system handles poorly,
with your analysis" (page 5), and then says plainly: "Honest failure analysis
scores well; overstating capability scores badly."

So this document is written to be useful rather than flattering. Every entry
says what happens, why, whether the failure is safe or unsafe, and what we
would do with more time.

**The distinction that matters.** A **safe** failure is one where the system
declines and says why. A controller loses time and goes to the screens they
were using before. An **unsafe** failure is one where the system produces a
fluent, confident, wrong operational instruction. A controller acts on it. The
second is worse than having no system at all, and it is the failure the rubric
punishes hardest: "answering ten questions correctly and saying 'I can't answer
that reliably' on the eleventh scores higher than answering all eleven with
three wrong" (page 6).

Everything below is graded on that axis first and on severity second.

> **Status.** This is a first pass, written from the dataset and the design
> before the full system runs end to end. Entries marked **predicted** are
> derived from the data and the architecture. Entries marked **observed** have
> been reproduced. It is refreshed from `make eval` output as the system lands,
> and predicted entries that turn out to be wrong will be deleted rather than
> quietly softened.

---

## Summary

| # | Failure | Safe or unsafe | Severity | Status |
|---|---|---|---|---|
| F1 | Simultaneous disruptions: the same reserve assigned to two aircraft | **unsafe by default** | critical | predicted |
| F2 | Compound and multi-part questions answered in half | safe | high | predicted |
| F3 | Ambiguous crew referent, seven names are shared by two crew each | **unsafe if unguarded** | high | observed in the data |
| F4 | A question needing a rule outside the seven | safe | medium | predicted |
| F5 | Data the pack does not contain | safe | medium | predicted |
| F6 | The multi-day pairing trap | safe, and we handle it | high if got wrong | handled |
| F7 | The 2026-09-14 duty clock overlap | **unsafe if "fixed"** | high | handled |
| F8 | Aggregation over the schedule, no tool computes a maximum | safe | medium | predicted |
| F9 | The deterministic offline path is narrower than the agent path | safe | medium | predicted |
| F10 | RULE-FLT-03 is implemented and never exercised | latent | low | observed |
| F11 | Model API failure or timeout during a live demo | safe if handled | medium | predicted |
| F12 | The grader itself is wrong | meta | medium | partly observed |

---

## F1. Simultaneous disruptions: one captain, two aircraft

**The headline failure case.** If we ship only one, this is the one to present.

**What happens.** Ask "both A320 captains are sick at 00:30Z on 18 Sep, what do
I do" (Q32, scenario S6). The natural implementation calls
`find_cover_options` once per broken pairing. Both calls return Captain C-3305
as rank 1, because C-3305 is genuinely the cheapest legal cover for each gap
considered on its own. Composing the two answers assigns one person to two
aircraft departing within thirty minutes of each other, and reports a total
cost of INR 37,000. The shipped answer is INR 42,500 with C-3305 on one line
and C-1017 on the other.

**Why.** `find_cover_options` in `contracts/tools.py` takes exactly one
`pairing_id`. There is no way to express "these two gaps, and no crew member
may fill both". The constraint is not a rule in `rules.json`, so no per
candidate legality check catches it either: each assignment really is legal in
isolation. It is a joint feasibility constraint and it only exists between the
two answers, which is exactly where nothing is looking. This is GAP-2 in
`docs/TIER-COVERAGE.md`.

**Safe or unsafe: unsafe.** This is the only failure in the whole question set
that produces a confident wrong operational instruction rather than a refusal.
Every other gap causes an abstention. A controller acting on this answer sends
two callouts to the same person and discovers the problem when one aircraft has
no captain at the gate.

**What we do about it now.** Until a joint planner exists, the correct
behaviour is an explicit abstention: detect that two or more gaps overlap in
time, decline to produce a combined plan, and say so with
`AbstentionReason.UNDERSPECIFIED`, naming the missing capability and offering
the per pairing option lists separately with a warning that they share
candidates. Under the second scoring principle that costs almost nothing.
Answering it wrongly costs us the argument we are making.

**What we would do with more time.** `plan_joint_cover(gaps, objective)` over an
exhaustive enumeration with a mutual exclusion constraint. Two gaps against a
candidate list of tens is a few hundred combinations, which is a loop and not
an optimisation problem, so it stays inside NG-06 ("a full mathematical
optimisation solver" is out of scope). Equal cost mirror assignments are both
correct, per the dataset's own note, so the planner must not pretend there is a
unique answer.

## F2. Compound and multi-part questions

**What happens.** "C-1042 is sick and BLR closes at 08:00, what do I do about
DX412" contains three questions: an absence, a station closure, and a specific
leg. The agent plans against whichever intent it recognises first, answers that
one well, and does not mention the other two. The controller reads a confident
answer and assumes it covered everything they asked.

**Why.** The tool surface models one disruption per call.
`simulate_absence`, `simulate_reassignment` and `simulate_station_closure` each
take one event. There is no composition operator, and the dataset itself says
scenarios are independent alternate timelines that do not chain. So a genuinely
compound question has no representation.

**Safe or unsafe: safe, but only just.** The answer given is correct about the
part it addressed. The failure is one of omission, and an omission a controller
cannot see is close to the unsafe end of safe: they asked three things and got
one, with no signal that two were dropped.

**What we do about it.** The answer must state its own scope. When more than one
disruption is detected in a question, the reply carries a `caveat` naming what
was and was not modelled, and a `follow_up` for each unaddressed part. That
turns an invisible omission into a visible one, which is the whole difference.

**What we would do with more time.** A planning step that decomposes a compound
question into sub-questions, answers each, and reports them as a list rather
than merging them into one narrative. Merging is where the dishonesty creeps
in: two impacts described as one read as a single analysis.

## F3. Ambiguous crew referents

**What happens.** Ask "is A. Nair legal for P-2291 tomorrow" and there are two
A. Nairs. Seven names in `crew.json` are shared by two crew members each: A.
Nair, R. Iyer, H. Naidu, S. Kapoor, K. Rao, P. Sharma and N. Verma. An
implementation that resolves a name to the first match returns a legality
verdict about the wrong person, with correct arithmetic, full rule traces and a
grounding check that passes, because every figure in it is genuinely attested.
It is simply about someone else.

**Why.** `find_crew(name_contains=...)` exists in the tool surface and names are
not unique. The grounding guard cannot catch this: the guard checks that every
number came from a tool, and every number did.

**Safe or unsafe: unsafe if unguarded, and it is invisible to our main
defence.** This is the sharpest lesson in the whole exercise. Our central
mechanism, verifying that every atom is attested, defends against invented
facts and is completely blind to correctly computed facts about the wrong
entity. Naming that limitation is worth more than pretending the guard is
comprehensive.

**What we do about it.** Name resolution must return all matches and abstain
when there is more than one, with `AbstentionReason.AMBIGUOUS_REFERENT`, listing
the candidates with enough context (base, rank, aircraft type) for the
controller to disambiguate in one word. Never resolve a name to one person
silently. The dataset made this trap deliberately, and it is the one place
where the right answer is a question.

**What we would do with more time.** Carry the referent resolution into the
reply as an explicit `TraceStep` ("A. Nair resolved to C-1042, Captain, BLR;
one other crew member shares this name"), so that even a successful resolution
is visible and challengeable.

## F4. A question that needs a rule we do not model

**What happens.** "Can C-1042 fly a fourth sector if we swap to the ATR" invokes
type conversion currency, which is not one of the seven rules. Or "does this
breach minimum cabin crew complement" invokes a rule that does not exist here.
The system declines.

**Why.** By design. The problem statement says the seven provided rules are the
full scope (NG-07), so `RuleId` is a closed `Literal` of seven values and an
eighth rule is a type error rather than a judgement call.

**Safe or unsafe: safe.** `AbstentionReason.REQUIRES_UNMODELLED_RULE`, naming
the rule it would need and listing the seven it does check.

**Worth stating out loud:** the answer keys themselves use a constraint that is
not one of the seven. Exclusion strings across S1, S2, S5 and S6 include
`double-booked: P-2203 overlaps COVER on 2026-09-16`. We implement that, and we
label it a feasibility constraint rather than a rule: it never gets a `RULE-`
id and never appears in a `rules_checked` list. If we called it an eighth rule
we would be contradicting our own scope statement in front of a judge.

## F5. Data the pack does not contain

**What happens.** "What is the weather at BLR", "how many passengers have
connections", "what is this crew member's hotel booking". The pack has eight
files and none of them carry any of that.

**Safe or unsafe: safe.** `AbstentionReason.NOT_IN_DATASET`, with
`get_world_summary` used to say what the system does hold: 147 flights, 150
crew, 39 pairings, 16 reserves, 7 rules, one week from 2026-09-14, hub BLR.

**The failure mode we are actually guarding against here** is not the refusal,
it is the near miss. `costs.json` has a `hotel_overnight` rate of INR 4,200 and
no hotel bookings, so "what will the hotel cost" is answerable and "is the
hotel booked" is not. A system that answers the second because it recognised
the word "hotel" is the dangerous version. The tool must return `ok=False` with
a specific error rather than an empty result that reads like a negative
finding: "no booking found" and "we do not model bookings" are different
answers.

## F6. The multi-day pairing trap

**What happens now: we handle it.** This is in the failure analysis because it
is the failure a plausible implementation makes, and because it is the best
thirty seconds of the demo.

Reserve C-3305 covering P-2291 is legal on day 1: the seven day duty window
reaches 59.50 hours against a 60 hour limit. On day 2 it reaches 68.25 hours,
over by 8h15m, because day 1's cover duty is itself inside the day 2 window.
An implementation that checks the first day of a multi-day pairing and stops
returns "yes, C-3305 can cover it" with correct arithmetic for the day it
checked.

**Why it is easy to get wrong.** The cumulative add is not obvious, and the day
1 answer is genuinely correct. Nothing about it looks like a partial check.

**Our defence is structural rather than careful.** `LegalityReport.overall` is
defined as the worst day and never an average, `per_day` is a list rather than
a scalar, and the contract package carries the invariant in writing. A
single day verdict is not representable in the type.

**Safe or unsafe if we got it wrong: unsafe.** It is a legality verdict, which
is the class of answer a controller acts on directly.

## F7. The 2026-09-14 duty clock overlap

**What happens.** `daily_history` in `duty_clocks.json` runs to 2026-09-14 and
the roster week starts on 2026-09-14, so eleven crew have that date counted
twice in the shipped seven day summaries. It looks exactly like a bug.

**Why it is not a bug.** The shipped `duty_hours_7d` values include the double
count and the dataset's own validator asserts it. It is the dataset's
convention, verified numerically against all 150 crew.

**Safe or unsafe: unsafe if "fixed".** Removing the overlap changes
`C-2087`'s day 1 figure away from 61.33 hours, which turns the flagship breach
into a pass. That is a legality verdict inverting because someone tidied up an
apparent inconsistency, and it would sail through code review as a correction.

**What we do about it.** It is recorded in the root `CLAUDE.md`, in
`docs/DATA-MODEL.md` and in a test in `tests/core` that asserts the formula
against all 150 crew. The defence against this failure is documentation plus a
test, because it is a failure of understanding rather than of code.

## F8. Aggregation over the schedule

**What happens.** "What is the longest block time in the schedule" (Q12) and
"which stations does BLR serve nonstop" (Q14). These are trivial for a human
with the file open, and there is no tool that computes a maximum or a distinct
set. Worse, `find_flights` defaults to `limit=100` against a 147 flight
schedule, so a whole network question truncates before the aggregate could be
taken even by hand.

**Safe or unsafe: safe**, because the model is forbidden from computing the
maximum itself and will abstain rather than guess. But it is a Tier 1
abstention, and the first scoring principle says a polished Tier 1 matters more
than a working Tier 3. Declining "what is the longest flight" in front of a
judge reads as fragility even though it is the architecture behaving correctly.

**What we would do about it.** GAP-4: have `find_flights` and `find_crew` emit
aggregate facts (`count`, `max` with the argmax ids, `distinct`) computed over
the whole matched set before truncation, with `truncated=True` on the envelope.
That is smaller than a new tool and fixes the silent truncation in the same
change.

## F9. The deterministic offline path is narrower than the agent path

**What happens.** With no API key, questions are answered by an intent resolver
rather than by a planner. It handles the question shapes it was written for and
abstains on the rest. Rephrase a question it knows and it may stop recognising
it. Ask something that needs three tools composed in an order nobody anticipated
and it has no rule for that composition.

**Safe or unsafe: safe.** It abstains rather than guessing, and both paths run
through the same tools and the same grounding guard, so both are equally
grounded when they do answer.

**Why we keep it anyway.** Every command must run with no API key. It is demo
insurance, and it is also the control group: the scorecard's agent versus
deterministic comparison is the artefact that shows whether the agent is
solving a real reasoning problem or decorating a lookup, which is the question
the largest evaluation criterion asks.

**The uncomfortable version of this entry.** If the two modes score the same,
the honest conclusion is not that the fallback is impressive. It is that the
agent is not earning its place, and we should say so rather than let the deck
imply otherwise. `make eval --mode both` prints that comparison, and it prints
a warning when the two modes disagree on nothing at all.

## F10. RULE-FLT-03 is implemented and never exercised

**What happens.** Nothing, which is the problem. RULE-FLT-03 (100 block hours
in 28 days) appears in every `rules_checked` array in every answer key, so a
reader of our output would reasonably assume it is tested. The maximum 28 day
block total anywhere in the dataset is 79.28 hours against a 100 hour limit. No
shipped question can breach it.

**Safe or unsafe: latent.** The code path exists and is unexercised. It could be
wrong and nothing would tell us.

**What we do about it.** Say so, in the README and here, rather than letting a
judge discover that our "all seven rules checked" claim includes one that no
test drives to a breach. And add a unit test with a synthetic crew record that
does breach it, so the arithmetic is at least covered even though no scenario
reaches it. A synthetic test record is not a dataset mutation and does not
touch `data/`.

## F11. Model API failure during a live demo

**What happens.** Rate limit, timeout, or venue network. The turn dies.

**Safe or unsafe: safe if handled, unsafe as an experience.** An error state on
stage reads as a broken system regardless of the architecture behind it.

**What we do about it.** A hard timeout on the agent path that falls back to the
deterministic resolver rather than failing the turn. That machinery already
exists for the no key case, so reusing it as a timeout path costs almost
nothing, and it converts the most likely live failure into a visible mode
switch. The mode badge stays on screen, so the audience sees the system
degrade honestly rather than pretend.

## F12. The grader itself is wrong

Included because a failure analysis that only examines the system and not the
instrument measuring it is incomplete.

**What happened, observed.** The scorecard's own tests caught two bugs in it
before the system it grades even ran.

1. `reduce_expected` treated any `rank` field as a ranking position. Q01's
   reserve list carries `"rank": "Captain"`, a job title, so twelve required
   reserves collapsed to whichever name sorted first alphabetically. Every
   answer naming one reserve would have scored correct on a question requiring
   twelve.
2. Requiring `rules_checked` verbatim turned Tier 3 recall into a measure of how
   much boilerplate an answer repeated, because that array lists all seven rule
   ids on every option in every key.

**The bias we deliberately built in.** The grader is generous where it is
uncertain: a flight number satisfies a flight id, a duration satisfies a
decimal, three questions with self declared open ended keys are scored on a
rubric rather than on containment. The reason is that marking a correct answer
wrong pushes the team to optimise the wrong thing, and there is no symmetric
harm from a slightly lenient score we report ourselves.

**The exception, and it is not generous at all.** A verdict inversion fails
regardless of recall and is flagged `unsafe` on its own line. An answer can
recite every correct figure and still be wrong if it concludes "legal" where
the key says "breach", and no amount of surrounding accuracy redeems that.

**Known remaining weakness in the grader.** It reads legality from rule traces
first and falls back to a regular expression over the prose. The regex is a
heuristic. An answer phrased unusually ("C-2087 has 1h20m less headroom than
required") may register as neither positive nor negative, in which case the
verdict check is skipped and grading falls back to containment alone. That
makes the scorecard slightly optimistic on verdict questions phrased in an
unusual way. The fix is for the reply to always carry structured
`rule_traces` on a legality answer, which the contract already supports, so
this is a prompt and rendering issue rather than a grader one.

---

## What we would fix first, given one more day

In order, and the ordering is the argument.

1. **F1.** It is the only unsafe failure in the shipped question set. Even
   without a joint planner, making it abstain converts our worst outcome into
   our best kind of outcome.
2. **F3.** The second unsafe one, and the one that shows our main defence has a
   blind spot. Cheap to fix: return all matches, abstain on more than one.
3. **F8.** Five Tier 1 questions, weighted highest by the scoring principles,
   and the fix is a few aggregate facts rather than new tools.
4. **F2.** Not because compound questions are common, but because the caveat
   mechanism that fixes it is the same mechanism that makes every other
   partial answer honest about its own scope.
