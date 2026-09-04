"""The evaluation harness: does the system answer the shipped questions.

`make eval` runs `python -m crewops.eval.scorecard` across all 38 questions in
`questions.json` and grades every answer against the shipped key.

Four modules:

| Module | Responsibility |
|---|---|
| `cases` | loading the answer keys, read only |
| `atoms` | extracting and normalising citable atoms from either side |
| `grading` | turning one reply plus one key into an `Outcome` |
| `scorecard` | running the set, tallying, reporting, writing the artefact |

No module here imports a model client. Grading is deterministic: a harness that
used a model to judge a model would be measuring the wrong thing.
"""

from __future__ import annotations

__all__: list[str] = []
