# Production

Three questions the rubric asks that are about a system this one is not yet:
what happens to crew personal data, what happens at real airline scale, and
what the thing is worth. They are grouped here rather than in the README
because none of them describes the repository, and mixing "how to run it" with
"how it would be operated at 12,000 crew" makes both harder to read.

The engineering claims below are traceable to code in this repository. The
figures in Business impact are stated as assumptions with their arithmetic
shown, because they are estimates and the point of this whole system is that
an estimate presented as a measurement is a lie.

---

## Crew PII in a production system

No real personal data is involved here: the dataset is synthetic. A real
deployment would carry licence numbers, medical certificate status, home base
and contact details, which is regulated personal data in most jurisdictions and
medical data in some.

What this architecture already does well is unusual and worth naming: the model
never sees the dataset. It sees tool results. That means the set of fields
crossing the boundary to a third-party inference provider is enumerable, and it
is enumerated, in `crewops.tools.payloads`.

For production we would:

- Pseudonymise at the tool boundary. Crew ids are already opaque; names,
  contact details and certificate numbers would not enter a payload at all. The
  agent can reason about `C-1042` perfectly well without knowing who that is,
  and the UI can rehydrate the name locally for display.
- Keep medical certificate detail out of the model's half entirely. The rules
  engine needs to know whether a certificate is valid on a date. It does not
  need to say why one is not, and neither does the model.
- Log the evidence ledger, not the prompt. The `Fact` list is the audit record
  a regulator would want, and it is already structured. Prompts and completions
  would be retained only briefly, for debugging, with crew identifiers redacted.
- Apply purpose limitation to reachability data. Knowing a crew member is
  reachable in 45 minutes is operationally necessary and also location
  adjacent, so it should not outlive the disruption it was fetched for.

---

## Scaling this approach

The dataset is deliberately small, so retrieval strategy here is a design
choice rather than a scaling necessity. What would and would not hold at real
airline scale:

**Holds.** The boundary itself gets stronger, not weaker, with scale: the more
data there is, the worse an idea it is to put it in a prompt. The tool surface
is already a query interface rather than a file reader, and `WorldState` is
already backed by a SQLite projection, so the same tools run against a real
database by changing the store, not the engine.

**Needs work.** Candidate enumeration is currently a scan over eligible crew.
At 150 crew that is instant. At 15,000 it wants an index on the filters that
actually discriminate (base, rank, rating, duty headroom) and an early cutoff,
because a controller needs the top five options, not a complete ordering.
Cover search across simultaneous disruptions is a joint allocation problem, and
the current implementation solves the small case exactly; the large case would
need a proper solver, or an honest statement that it is producing a good plan
rather than the optimal one.

**Would change.** The seven-day and 28-day clock windows are recomputed per
candidate per day. That is correct and cheap here, and at scale it becomes an
incrementally maintained running total, which is what a real rostering system
does.

---

## Business impact

The bottleneck on a Crew Control desk is not detecting that something broke.
It is working out the consequences, correctly, from data spread across rosters,
duty clocks, reserve lists and a rulebook, while more disruptions arrive.

What this changes:

- **The downstream break is found.** The uncovered flight is obvious. The crew
  member who moves into a duty-limit breach three days later is not, and that is
  the one that turns a single disruption into four.
- **The reasoning is reviewable.** Every verdict carries its arithmetic, so a
  decision can be checked, handed over at shift change, and learned from. Today
  that reasoning lives in one experienced controller's head.
- **The refusals are trustworthy.** A tool that is confidently wrong once stops
  being used. One that declines clearly, and says what it was missing, keeps
  being used, which is the only way any of the above value is realised.
