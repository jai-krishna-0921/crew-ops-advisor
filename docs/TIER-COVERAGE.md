# Tier coverage and tool gap analysis

Every question in `data/crew-ops-advisor-dataset/data/questions.json` (38: 16
Tier 1, 14 Tier 2, 8 Tier 3) and every scenario in `scenarios.json` (6), mapped
onto the tool surface in `api/src/crewops/contracts/tools.py`.

The point of this document is the gap analysis in section 4. The tables exist
to justify it. Read section 4 first if you are short of time.

`docs/DATA-MODEL.md` is the authoritative reference for record shapes, the rule
decodings and the numbered traps. This document cites its trap numbers rather
than restating them. Where the problem statement PDF and the shipped data
disagree, the data wins; the drift table lives in `DATA-MODEL.md` section 8 and
is carried into `docs/REQUIREMENTS.md`.

Tool names are the entries of `TOOL_NAMES`. Where a question is answerable only
by a capability that does not exist, the cell reads **GAP-n**.

---

## 1. Tier 1: lookup and retrieval (16 questions, mandatory)

| Q | Question | Expected answer, in brief | Tools | What makes it hard |
|---|---|---|---|---|
| Q01 | Reserves at BLR on 2026-09-15 with on-call windows | 12 reserves, C-3305 through C-4809, each with rank and window | `list_reserves` | Answer is in `reserve_pool.json` file order. All 16 reserves are on call all 7 days (trap 18), so the `dates` array never discriminates and a date filter that appears to work proves nothing. |
| Q02 | C-1042 duty hours in the 7 days ending 2026-09-14, and RULE-DUTY-02 headroom | 20.93h accrued, 39.07h headroom | `get_duty_clocks`, `explain_rule` | The window ends on the snapshot date, so it is `daily_history` only. Returning 48.5h means you read the stale PDF sample instead of the data. |
| Q03 | Flights departing DEL on 2026-09-15 | `["DX402"]`, flight **numbers** | `find_flights` | DX589 runs only on VT-DXC's DEL-start days (14/16/18/20 Sep). Off-by-one on the date returns two. |
| Q04 | Certifications expiring within 30 days of 2026-09-15 | 6 rows, C-2087 licence through C-2993 medical | `find_expiring_certifications` | Anchored on 2026-09-15, not the snapshot. Check `valid_to` only: `valid_from` is corrupt in the data (trap 11). |
| Q05 | Aircraft operating DX412 on 2026-09-15 and its seat count | VT-DXC, A320, 162 seats | `find_flights` + **GAP-6**, **GAP-9** | `FlightRef` carries neither the tail registration nor `seats`. It has `aircraft_type` and `passengers`, which are different fields from the two the answer wants. |
| Q06 | C-3310's on-call window and reachability | 06:00 to 18:00, 45 minutes | `get_crew_detail` or `list_reserves` | `reachability_minutes` is never used in any computation (trap 21). Surface it, do not gate on it. |
| Q07 | C-2210's base and rating | DEL, A320 | `get_crew_detail` | Nothing. |
| Q08 | Crew on pairing P-2291 and their roles | 6 crew, C-1042 Captain through C-1873 Cabin Crew | `get_pairing` | Nothing. |
| Q09 | Flights BLR to BOM on 2026-09-17 | `["DX431", "DX412"]`, flight numbers, DX431 first | `find_flights` | Ordering is not schedule order. |
| Q10 | Total flights operating on 2026-09-16 | 21 | `find_flights` + **GAP-4** | The answer is a count and the model may not count. `find_flights` must emit a `count` Fact or the guard rejects the number. |
| Q11 | Captains based at DEL | `["C-2210"]` | `find_crew` + **GAP-4** | Same count problem. |
| Q12 | Longest block time in the schedule and which flights have it | 2.75h: DX401, DX402, DX588, DX589 | **GAP-4** | Max plus argmax over all 147 flights, and `find_flights(limit=100)` truncates before the max can be taken. |
| Q13 | C-2087's rank and 28-day flight hours to 2026-09-14 | Captain, 23.5h | `get_crew_detail`, `get_duty_clocks` | C-2087 is a Captain. The PDF calls them an FO and is wrong. Anything sourced from the PDF rather than the data is a bug. |
| Q14 | Stations served nonstop from BLR | BOM, CCU, COK, DEL, GOI, HYD, MAA | **GAP-4** | Distinct destinations over the whole week, plus the same truncation. |
| Q15 | Senior Cabin Crew on VT-DXB's pairing on 2026-09-16 | C-3171 | **GAP-6** | Requires resolving a tail registration and a date to a pairing. There is no `find_pairings` tool and no registration filter on `find_flights`, so `get_pairing` can never be handed an id. |
| Q16 | Disruption-risk score for C-1042 and its drivers | 0.78, short-rest pattern and two fatigue reports | **GAP-3** | `risk_signals.json` is reachable by no tool. A mandatory-tier question with a two-field answer that we currently cannot produce. |

## 2. Tier 2: consequence and simulation (14 questions, strongly expected)

| Q | Question | Expected answer, in brief | Tools | What makes it hard |
|---|---|---|---|---|
| Q17 | C-1042 sick at 05:00Z 15 Sep on P-2291, which flights uncrewed | Day 1 DX412/413/588 uncrewed, day 2 DX589/590/591 also at risk, 486 passengers | `simulate_absence` | Two distinct lists, and `passengers_day1` counts day 1 only even though six legs are at risk (trap 23). `ImpactReport.uncrewed_flights` is one flat list with no such split. |
| Q18 | Does C-2087 covering P-2291 breach anything | No: RULE-DUTY-02 by 1h20m on 15 Sep (61.33h) and by 1h05m on 16 Sep (61.08h) | `check_legality` | Two breach lines, one per day, because the day-1 cover duty is inside the day-2 window (trap 7). A collapsed verdict loses the second line. |
| Q19 | BLR closed 08:00 to 14:00Z on 17 Sep, flights affected | 13 flight **ids** | `simulate_station_closure` | Half-open window `[start, end)` (trap 24), and "affected" means departing **or arriving** BLR inside it. Departure-only logic returns roughly half. |
| Q20 | VT-DXA delayed 90 min before DX401 on 16 Sep, does the rostered crew breach | Yes, FDP 12.75h against a 12.0h limit | **GAP-1**, **GAP-6** | No delay simulation tool exists. The limit is 12.0h not 13.0h because four sectors costs 2 x 0.5h. This is the whole-duty delay model where report and release both slide (trap 26). |
| Q21 | Can C-2210 cover P-2291 positioned from DEL, and what does it cost operationally | Legal; deadhead on DX402 arriving 08:45Z delays first departure by ~3h | `find_cover_options` then filter to C-2210 | `check_legality` has no positioning argument, so a question about one named person has to run the whole cover search. The 75-minute positioning constant (trap 20) sets the delay and therefore the cost. |
| Q22 | Can C-5417 operate their rostered VT-DXB duty on 19 Sep | No, RULE-CERT-06, recurrent_training expired 2026-09-17 | `check_legality`, `get_crew_detail` | Cert validity is `valid_to >= duty_date`, so their 16 Sep duty is legal and only 19 Sep is not (trap 5). |
| Q23 | Crew released 15:30Z on 16 Sep, earliest next report | 2026-09-17T03:30:00Z | **GAP-7** | No crew is named. Pure rule arithmetic on a hypothetical. `explain_rule` returns `min_rest_hours: 12` but nothing adds 12 hours to a timestamp and the model is forbidden from doing it. |
| Q24 | Can reserve C-3305 cover the FULL pairing P-2291 | No: RULE-DUTY-02 exceeded by 8h15m on 16 Sep (68.25h) | `check_legality` | The multi-day trap (trap 6). Day 1 gives 59.50h and passes. Anything that checks the first day and stops answers this wrongly and confidently. |
| Q25 | DX404 cancelled on 16 Sep, passengers and direct cost | 162 passengers, INR 250,000 | `find_flights` + **GAP-8** | Nothing exposes `costs.json` outside a `CostBreakdown` on a `CoverOption`. A cancellation with no crew gap has no entry point. |
| Q26 | Crew with 45h or more duty in the 7 days ending 2026-09-15 including planned duty | C-2087 at 51.83h, C-3305 at 50.0h | **GAP-5** | `get_duty_clocks` takes one `crew_id`. This needs the window recomputed for all 150. |
| Q27 | VT-DXE captain sick 16 Sep called 01:30Z, which reserve captains' windows cover it and are they qualified | Eligible: C-3315. Excluded: C-3305 no ATR72, C-3310 window misses the 03:00Z report | `list_reserves`, `check_legality` + **GAP-6** | Eligibility tests the required **report** time (03:00Z), not the call time (01:30Z) (trap 14). Using the call time makes C-3310 look eligible. |
| Q28 | Is C-5837 legal to cover P-2291 | No: RULE-REST-04, only 10.75h rest before P-2204 on 2026-09-17 | `check_legality` | The conflict is two days after the cover. RULE-REST-04 must be checked forward against the crew member's own next rostered duty, not only backward from `last_rest_ended`. |
| Q29 | HYD closed 05:00 to 09:00Z on 19 Sep, flights affected | DX461, DX462 as flight ids | `simulate_station_closure` | Nothing beyond Q19. |
| Q30 | Flight leg with the most seats at risk if cancelled | Any A320 leg at 162 seats, against ATR72 at 72 | **GAP-4** | Deliberately qualitative. An exact-match grader marks a correct answer wrong; the scorecard must treat this as a rubric question. |

## 3. Tier 3: recommendation and action (8 questions, stretch)

| Q | Question | Expected answer, in brief | Tools | What makes it hard |
|---|---|---|---|---|
| Q31 | C-1042 out for P-2291, ranked resolution options | C-3310 reserve at INR 18,500 rank 1, day-off callouts at 24,000, C-2210 deadhead at 41,200, cancel at 1,500,000 last | `find_cover_options`, `simulate_absence` + **GAP-11** | The flagship. Cancellation is priced per leg, so 6 legs is 1,500,000, and it is appended after sorting rather than sorted into place (traps 28, 29). C-2087 and C-3305 must appear in `rejected` with their traces. |
| Q32 | Both A320 captains sick at 00:30Z 18 Sep, optimal joint plan | Total INR 42,500: C-3305 to one line, C-1017 to the other | **GAP-2**, **GAP-6** | `find_cover_options` takes one pairing. Called twice it returns C-3305 as rank 1 for both, and naive composition puts one captain on two aircraft at the same time. Equal-cost mirror assignments are both correct (trap 30). |
| Q33 | What to do about the FDP breach after the VT-DXA delay | Rank 1: original crew flies DX401-403, full reserve set takes DX404, INR 75,000. Rank 2: cancel DX404, INR 250,000 | **GAP-1**, **GAP-11** | Blocked on delay simulation. Dropping a leg changes the sector count and therefore the FDP limit, 12.0 to 12.5 (trap 27). Re-crewing one leg needs a full six-person reserve set, not one substitution. |
| Q34 | Resolve C-5417's 19 Sep assignment after the training lapse | C-4809 cabin reserve at INR 9,500, then day-off callouts at 12,500 | `find_cover_options`, `check_legality` + **GAP-11** | Cabin ranks and cabin callout rates. Rank equals role exactly, so Senior Cabin Crew cannot cover Cabin Crew (trap 12). |
| Q35 | Recovery plan across pairings for the BLR closure | 13 rows of min delay, crew FDP after delay, FDP limit, action | `simulate_station_closure` + **GAP-10** | This is the mid-duty delay model where release extends but report does not, the opposite of Q20 (trap 26). `ImpactReport` has no structured per-flight delay or post-delay FDP field. |
| Q36 | Draft the callout notification to C-3310 for P-2291 | Crew and pairing ids, report 06:00Z 15 Sep BLR crew room, day 1 legs, DEL overnight with hotel, day 2 legs with 04:00Z DEL report, acknowledgement deadline, contact | `draft_notification`, `get_pairing` | Graded on completeness, not wording. The day-2 report time and station come from the second `days[]` entry, which a single-day template drops. |
| Q37 | Cheapest legal cover for the VT-DXF First Officer sick at 03:30Z on 20 Sep | C-3316 reserve callout, INR 18,500 | `find_cover_options` + **GAP-6**, **GAP-11** | Tail resolution, ATR rating, and an FO-rank search. |
| Q38 | Three data points a standing morning briefing should surface per aircraft line | Duty headroom, reserve availability by window and rating, risk signals. Explicitly open-ended | `get_watchlist`, `get_world_summary` + **GAP-3** | The one question where the model should genuinely reason. The key says "judged on operational reasoning, not exact match", so the grader must special-case it. It also names risk signals, which we cannot retrieve. |

## 4. Scenarios (6)

| S | Title | Trigger | Answer key demands | Tools | Verdict |
|---|---|---|---|---|---|
| S1 | ATR captain sick call | C-3231 sick 01:30Z 16 Sep, P-2224, 4 legs | 4 uncovered flights, 7 ranked options (C-3315 reserve at 18,500 first, cancel-all at 1,000,000 last), ~20 excluded candidates dominated by RULE-QUAL-05 | `simulate_absence`, `find_cover_options` + **GAP-6**, **GAP-11** | Reachable. The excluded list is the hard part: each name needs the specific rule that removed it, and RULE-QUAL-05 short-circuits every other reason (trap 9). |
| S2 | Flagship: C-1042 sick, 2-day pairing | C-1042 sick 05:00Z 15 Sep, P-2291 | Day 1 and day 2 uncovered lists, 486 passengers, 6 ranked options, C-2087 and C-3305 excluded with per-day arithmetic | `simulate_absence`, `find_cover_options`, `check_legality` + **GAP-11** | Reachable, and it is the demo. Every anchor fact in the root `CLAUDE.md` comes from here. |
| S3 | BLR station closure | 08:00 to 14:00Z 17 Sep | 13 affected flights plus a per-flight assessment carrying min delay, post-delay crew FDP, FDP limit and an action | `simulate_station_closure` + **GAP-10** | Partially reachable. The flight list is easy. The per-flight FDP consequence has nowhere structured to live, and the delay anchors on the BLR event rather than the flight's own departure (trap 25). |
| S4 | Tech delay cascades into an FDP breach | VT-DXA, 90 min, 16 Sep | FDP 12.75h against 12.0h, breach true, two options at 75,000 and 250,000 | **GAP-1**, **GAP-6**, **GAP-11** | **Not reachable.** No delay tool exists. |
| S5 | Certification lapse found pre-flight | C-5417 flagged 10:00Z 18 Sep, duty 19 Sep | Illegal assignment identified, ranked cabin cover options, excluded candidates | `check_legality`, `find_cover_options` + **GAP-11** | Reachable. The trigger is an ineligibility rather than an absence, so it needs a cert-driven entry point or `simulate_absence(reason=...)` used loosely. |
| S6 | Two simultaneous captain sick calls | C-3940 and C-1938 at 00:30Z 18 Sep | Options and exclusions per pairing, plus a joint plan at INR 42,500 with no double-assignment | **GAP-2**, **GAP-6**, **GAP-11** | **Not reachable as a joint plan.** Per-pairing options are reachable; the allocation across both is not. |

---

## 5. The gap table

Eleven gaps, ordered by how much of the answer key they block.

| Gap | What is missing | Blocks | Severity | Cheapest fix |
|---|---|---|---|---|
| **GAP-1** | **No delay simulation.** The three simulation tools cover absence, reassignment and station closure. A delay is the fourth disruption type in the dataset and has no tool. `ImpactReport.trigger_kind` already contains `"flight_delay"`, so the contract anticipated it and the tool surface did not follow. The dataset carries **two** delay models: a pre-departure delay slides report and release together (S4, Q20), a mid-duty delay extends release only (S3, Q35). | Q20, Q33, S4 fully. Q35 and S3 partially, because the closure answer key is expressed as delays. | **Critical.** Two of eight Tier 3 questions and one of six scenarios. | `simulate_delay(aircraft=None, flight_no=None, on_date, delay_minutes, mode: Literal["pre_departure", "mid_duty"])` returning an `ImpactReport` with `trigger_kind="flight_delay"`. The FDP recomputation it needs already exists for RULE-FDP-01. Do not let it default to one mode: the two produce different numbers and both appear in the keys. |
| **GAP-2** | **No joint allocation across simultaneous gaps.** `find_cover_options` takes exactly one `pairing_id`. Two calls return the same scarce reserve as rank 1 for both gaps. | Q32, S6 | **Critical, and uniquely dangerous.** Every other gap causes an abstention. This one causes a fluent, confident, wrong answer: one captain assigned to two aircraft at the same time. Under a rubric that scores a refusal above an error, this is the most expensive single failure in the set. | `plan_joint_cover(gaps: list[CoverGap], objective="min_total_cost")`, or widen `find_cover_options` to `pairing_ids: list[str]` with a mutual-exclusion constraint. The root `CLAUDE.md` already assigns joint allocation to `ops/`; the surface simply has no way to call it. Accept equal-cost mirror plans. |
| **GAP-11** | **`find_cover_options` cannot tell which role it is covering.** Its parameters are `pairing_id`, `flight_numbers`, `exclude_crew_ids`, `max_options`, `include_rejected`. None of them names the crew member being replaced or the required rank. The enumeration algorithm in `DATA-MODEL.md` 6.2 filters on `c.rank == required role` as its second step, and the callout rate differs by role (18,500 pilot against 9,500 cabin). | Q31, Q34, Q37, and the cover path in all six scenarios | **Critical.** Without it, cover search either returns the wrong candidate population or has to guess the role from the pairing, which is ambiguous: every pairing has six crew across four ranks. | Add `for_crew_id: str \| None` and `role: str \| None` to `find_cover_options`. `for_crew_id` is the natural one: it gives the role, and it is the pairing to subtract under trap 8. |
| **GAP-3** | **`risk_signals.json` is unreachable.** No tool returns a disruption-risk score. | Q16 (Tier 1), Q38 | **High**, and the cheapest thing on this list to fix. Q16 is a mandatory-tier question with a two-field answer. | Fold `disruption_risk_score` and `drivers` into `get_crew_detail`, and surface them on `get_watchlist` rows. That costs nothing and puts the number where a controller would look. |
| **GAP-6** | **Aircraft registration is invisible.** `flights.json` and `rosters.json` both key on `aircraft` (VT-DXA through VT-DXF). `find_flights` filters on `aircraft_type` only. `FlightRef` has no registration field. There is no `find_pairings` tool, only `get_pairing(pairing_id)`, so a question naming a tail and a date can never obtain the pairing id. | Q05, Q15, Q20, Q27, Q32, Q33, Q37, and S1, S3, S4, S6 | **Critical by blast radius.** Seven questions and four scenarios identify an aircraft by registration and by nothing else. | Three small changes: `aircraft_registration` filter on `find_flights`; `aircraft: str \| None` and `seats: int \| None` on `FlightRef`; and `find_pairings(aircraft=None, on_date=None, crew_id=None, station=None)`. |
| **GAP-4** | **No aggregation over a result set.** No count, max, argmax or distinct. The model is forbidden from computing them, so nothing can. Compounded by `find_flights(limit=100)` against a 147-flight schedule: whole-network questions silently truncate before the aggregate is taken. | Q12, Q14, Q30 fully. Count facts also needed for Q10, Q11. | **High.** Five questions, four of them Tier 1, all trivially easy for a human. | Have `find_flights` and `find_crew` emit aggregate `Fact`s over the whole matched set (`count`, `max(block_hours)` plus the argmax ids, `distinct(arr_station)`), computed **before** truncation, with `truncated=True` set on the envelope. Smaller than a new tool and it fixes the truncation bug in the same change. |
| **GAP-5** | **No fleet-wide duty scan.** `get_duty_clocks(crew_id: str)` is single crew. There is no threshold query over the population. | Q26 | **High.** The workaround is 150 sequential tool calls, which breaks the performance criterion and the context budget before it breaks correctness. | Accept `crew_ids: list[str] \| None` plus `min_duty_hours_7d: float \| None` on `get_duty_clocks`, or add `scan_duty_headroom(on_date, threshold_hours, rule_id)`. |
| **GAP-10** | **`ImpactReport` cannot express a per-flight delay consequence.** S3 and Q35 want `min_delay_hours`, `crew_fdp_after_delay`, `fdp_limit` and an action per flight. Only `DownstreamRisk.detail`, a free-text string, is available. | Q35, S3 | **Medium.** Producible as prose but not checkable as data, which weakens both the grounding guard and the scorecard. | Typed optional fields on `DownstreamRisk`: `delay_minutes`, `observed`, `limit`, `recommended_action`. |
| **GAP-7** | **No rule arithmetic on a hypothetical.** Every legality path is anchored to a `crew_id`. Q23 names no crew: it is "release plus 12h". | Q23 | **Medium.** One question, but the answer is a single addition and abstaining on it looks worse than it is. | Let `explain_rule` accept optional `inputs: dict` and return the applied result as a computed `Fact`, or add `apply_rule(rule_id, inputs)`. |
| **GAP-8** | **No cost rate lookup.** `costs.json` reaches the outside world only inside a `CostBreakdown` attached to a `CoverOption`. A costing question with no crew gap has no entry point. | Q25 | **Medium.** Reachable by abusing `find_cover_options` on a single flight and reading the CANCEL option, which is fragile. | `get_cost_rates()` returning `costs.json` as facts. |
| **GAP-9** | **`FlightRef` carries `passengers` but not `seats`.** They coincide in this dataset, which hides the confusion until a judge asks about load factor. Q05 asks for seats explicitly. | Q05, Q30 | **Low.** Naming, not capability. | Add `seats` alongside `passengers`, or document in the contract that they are the same field in this pack. |

### Signature notes that are not gaps but will cause mismatches

1. **`simulate_absence(from_date: date)` cannot express a callout time.** Every
   scenario carries a `reported_utc` (01:30Z, 05:00Z, 00:30Z). It is narrative
   only for eligibility (trap 14), but dropping it means the system cannot
   restate the disruption it was asked about. Accept a `reported_at: datetime`.
2. **`find_cover_options` has no `as_of`.** It cannot be run against a
   hypothetical world clock. If `as_of` is threaded globally through the tool
   implementation, say so in the contract; if not, add it.
3. **Flight identifier inconsistency in the answer keys.** Q03, Q09, Q12 and
   Q14 expect flight **numbers** (`DX402`). Q17, Q19, Q29 and every scenario
   expect flight **ids** (`DX402-2026-09-17`). Payloads should carry both, and
   the grader must accept either.

### Two findings for the Core workstream

Neither is a tool gap, but both will cause answer-key mismatches if missed.

1. **The answer keys use an eighth constraint that is not in `rules.json`.**
   Exclusion reasons across S1, S2, S5 and S6 include lines such as
   `double-booked: P-2203 overlaps COVER on 2026-09-16`. That is an assignment
   overlap check, not a regulation. The problem statement says the seven rules
   are the full regulatory scope, and they are, but the keys will not reproduce
   without a separate feasibility check for a crew member already being on duty
   elsewhere. Label it a feasibility constraint, never an eighth rule, or we
   contradict our own scope statement in front of a judge.
2. **RULE-REST-04 must be checked forward as well as backward.** Q28 and the S2
   exclusions turn on rest before the candidate's own next rostered duty, up to
   two days after the cover. A rest check that only looks back at
   `last_rest_ended` passes C-5837, C-2143 and C-3187 and produces a wrong
   ranked list on the flagship scenario.

## 6. Rule exercise coverage

Which of the seven rules any question or scenario actually drives to a breach.
This matters because `rules_checked` in every answer key lists all seven, which
makes coverage look complete when it is not.

| Rule | Breach exercised by | Status |
|---|---|---|
| RULE-FDP-01 | Q20 (12.75h vs 12.0h), Q33, Q35, S3, S4 | Exercised |
| RULE-DUTY-02 | Q18, Q24, Q26, S2 exclusions | Exercised, and it is the flagship |
| RULE-FLT-03 | nothing | **Never exercised.** The maximum 28-day block total in the dataset is 79.28h against a 100h limit (`DATA-MODEL.md` trap 10). It appears in every `rules_checked` array and no question can breach it. We must implement it and must not claim it is tested. Say so in the README and the failure analysis rather than letting a judge find it. |
| RULE-REST-04 | Q23 (arithmetic only), Q28, S1/S2/S5/S6 exclusions | Exercised |
| RULE-QUAL-05 | Q27, S1/S2/S6 exclusions | Exercised, and it short-circuits other reasons |
| RULE-CERT-06 | Q22, Q34, S5 | Exercised |
| RULE-BASE-07 | Q21, S2 (C-2210 deadhead), cross-base exclusions | Exercised |

Six of seven rules are exercised by a breach somewhere in the shipped material.
RULE-FLT-03 is inert by construction.

## 7. What the gaps cost us

Assuming the deterministic core lands as specified and nothing above is fixed:

| Tier | Answerable | Blocked or degraded | Note |
|---|---|---|---|
| Tier 1 | 11 of 16 | Q05, Q10, Q11 degraded; Q12, Q14, Q15, Q16 blocked | Tier 1 is mandatory and the scoring principles rank a polished Tier 1 above a broken Tier 3. Failures here cost more than the same count anywhere else. |
| Tier 2 | 10 of 14 | Q20, Q23, Q25, Q26 | Q20 is cleanly blocked. The others have ugly workarounds. |
| Tier 3 | 4 of 8 | Q32, Q33, Q35 blocked; Q31/Q34/Q37 degraded by GAP-11 | Q32 is the dangerous one: it fails unsafely unless we deliberately abstain. |
| Scenarios | 3 of 6 | S4 and S6 blocked; S3 degraded | Both blocked scenarios sit at the hard end of the worked set, which is exactly where judges look. |

GAP-1, GAP-2, GAP-3, GAP-6 and GAP-11 account for every hard block. They are
five small additions to the tool surface: one new simulation tool, one joint
planner, two new parameters on `find_cover_options`, a registration filter plus
`find_pairings`, and two fields on `get_crew_detail`. All of them are cheap now
and expensive once the agent has been wired to seventeen fixed names and the
prompts have been tuned against them.

## 8. A note on grading these answers

Two formatting facts shape the scorecard, recorded here because they follow
from the answer keys rather than from the design:

- Durations appear as `1h20m` and `8h15m`, not as decimals. 1.33 hours and
  `1h20m` are the same fact. The fact-containment grader must normalise them to
  one representation or it will mark correct answers wrong. The `verify`
  workstream is building this normaliser; the scorecard reuses it rather than
  writing a second one.
- Q30, Q36 and Q38 have deliberately non-exact answer keys ("any A320 leg",
  "judged on completeness, not wording", "judged on operational reasoning, not
  exact match"). They must be graded as rubric questions. A containment grader
  applied to them scores three correct answers as wrong and understates the
  submission.
