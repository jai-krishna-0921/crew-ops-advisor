"""Loading the shipped answer keys.

Read only. This module opens files under `data/` and never writes there. The
dataset is the answer key every golden test asserts against; regenerating or
mutating it would silently move the target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

#: `api/src/crewops/eval/cases.py` -> repository root.
REPO_ROOT: Path = Path(__file__).resolve().parents[4]
DATA_DIR: Path = REPO_ROOT / "data" / "crew-ops-advisor-dataset" / "data"
INTERNAL_DIR: Path = REPO_ROOT / "data" / "crew-ops-advisor-dataset" / "internal"
HELD_OUT: Path = INTERNAL_DIR / "held_out_scenarios.json"

#: Questions whose shipped answer key is deliberately not an exact match, by the
#: key's own words. Grading these on fact containment marks correct answers
#: wrong and understates the submission, so they are scored as rubric items.
#:
#: Q30: "any A320 leg (162 seats)" against "ATR72 legs (72 seats)".
#: Q36: "judged on completeness, correctness of times and clarity, not template
#:       wording".
#: Q38: "Open-ended; judged on operational reasoning, not exact match."
RUBRIC_QUESTIONS: frozenset[str] = frozenset({"Q30", "Q36", "Q38"})


@dataclass(frozen=True)
class Case:
    """One question from `questions.json`."""

    case_id: str
    tier: int
    prompt: str
    expected: Any
    explanation: str
    rules_ref: tuple[str, ...]

    @property
    def is_rubric(self) -> bool:
        return self.case_id in RUBRIC_QUESTIONS


@dataclass(frozen=True)
class ScenarioCase:
    """One worked scenario from `scenarios.json`."""

    scenario_id: str
    difficulty: str
    title: str
    event: dict[str, Any]
    answer_key: dict[str, Any]

    @property
    def narrative(self) -> str:
        """The scenario as a controller would say it out loud.

        Scenarios ship as structured events, not prompts. `narrative` is the
        field written for a human, so it is the fairest thing to ask the system.
        """
        text = str(self.event.get("narrative", "")).strip()
        return text or f"{self.title}: {json.dumps(self.event)}"


def dataset_available() -> bool:
    return (DATA_DIR / "questions.json").is_file()


def _read(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_questions() -> tuple[Case, ...]:
    """All 38 questions, in file order."""
    return tuple(
        Case(
            case_id=str(row["question_id"]),
            tier=int(row["tier"]),
            prompt=str(row["prompt"]),
            expected=row["expected_answer"],
            explanation=str(row.get("explanation", "")),
            rules_ref=tuple(row.get("rules_ref") or ()),
        )
        for row in _read("questions.json")
    )


@lru_cache(maxsize=1)
def load_scenarios() -> tuple[ScenarioCase, ...]:
    """All 6 worked scenarios, in file order."""
    return tuple(
        ScenarioCase(
            scenario_id=str(row["scenario_id"]),
            difficulty=str(row.get("difficulty", "")),
            title=str(row.get("title", "")),
            event=dict(row.get("event") or {}),
            answer_key=dict(row.get("answer_key") or {}),
        )
        for row in _read("scenarios.json")
    )


def load_held_out() -> tuple[ScenarioCase, ...] | None:
    """The gitignored judging set, or None when it is absent.

    This is a generalisation check and never a target. Nothing is tuned against
    it and its contents are never quoted into a committed file.
    """
    if not HELD_OUT.is_file():
        return None
    rows = json.loads(HELD_OUT.read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = rows.get("scenarios") or []
    return tuple(
        ScenarioCase(
            scenario_id=str(row.get("scenario_id", f"H{index + 1}")),
            difficulty=str(row.get("difficulty", "")),
            title=str(row.get("title", "")),
            event=dict(row.get("event") or {}),
            answer_key=dict(row.get("answer_key") or {}),
        )
        for index, row in enumerate(rows)
    )


def as_case(scenario: ScenarioCase) -> Case:
    """Grade a scenario with the same machinery as a question.

    Scenarios carry no tier of their own. They are the Tier 3 worked set, so
    they are tallied as tier 3 and keep their scenario id. The prompt is the
    scenario's `narrative`, which is the text the dataset wrote for a human:
    asking the structured event instead would test JSON parsing rather than the
    conversational interface the problem statement requires.
    """
    return Case(
        case_id=scenario.scenario_id,
        tier=3,
        prompt=scenario.narrative,
        expected=scenario.answer_key,
        explanation=scenario.title,
        rules_ref=(),
    )


def question_cases() -> list[Case]:
    """The 38 questions, or an empty list when the dataset is absent."""
    return list(load_questions()) if dataset_available() else []


def scenario_cases() -> list[Case]:
    """The 6 worked scenarios as gradeable cases."""
    return [as_case(s) for s in load_scenarios()] if dataset_available() else []


def held_out_cases() -> list[Case]:
    """The held-out scenarios as gradeable cases, empty when the file is absent."""
    scenarios = load_held_out()
    return [as_case(s) for s in scenarios] if scenarios else []


@lru_cache(maxsize=1)
def stations() -> frozenset[str]:
    """The station codes actually present in the schedule."""
    if not dataset_available():
        from crewops.eval.atoms import DEFAULT_STATIONS

        return DEFAULT_STATIONS
    flights = _read("flights.json")
    return frozenset(str(leg[field]) for leg in flights for field in ("dep_station", "arr_station"))


__all__ = [
    "DATA_DIR",
    "HELD_OUT",
    "REPO_ROOT",
    "RUBRIC_QUESTIONS",
    "Case",
    "ScenarioCase",
    "as_case",
    "dataset_available",
    "held_out_cases",
    "load_held_out",
    "load_questions",
    "load_scenarios",
    "question_cases",
    "scenario_cases",
    "stations",
]
