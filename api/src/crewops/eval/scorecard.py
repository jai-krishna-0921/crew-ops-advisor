"""The scorecard. `make eval`, or `python -m crewops.eval.scorecard`.

Runs every question in `questions.json` (and optionally every scenario) through
the advisor, grades the result on fact containment, and reports per tier and
overall: correct, partial, abstained, wrong, latency, and how many answers
passed grounding verification.

Two rules this report is built around, both from the problem statement:

1. **Abstentions are counted separately and never as failures.** Page 6:
   answering ten correctly and declining the eleventh scores higher than
   answering all eleven with three wrong.
2. **A verdict inversion is called out on its own line.** Saying a candidate is
   legal when the key says they breach is the one failure mode that is worse
   than not answering, so it gets its own section rather than being averaged
   into a percentage.

It runs with no API key, exercising the deterministic path, and with a key,
exercising the agent. `--mode both` runs both and prints the comparison, which
is the artefact that answers "is AI solving a real reasoning problem, or
decorating a lookup".

It also runs before the core exists: with no advisor to call it prints a skip
message naming the entry points it looked for, and exits 0.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from crewops.eval import runner
from crewops.eval.cases import (
    Case,
    dataset_available,
    question_cases,
    scenario_cases,
)
from crewops.eval.grading import Grade, Outcome, grade

DEFAULT_ARTEFACT_DIR = Path(__file__).resolve().parents[3] / ".eval"

_OUTCOME_STYLE: dict[Outcome, str] = {
    Outcome.CORRECT: "green",
    Outcome.PARTIAL: "yellow",
    Outcome.ABSTAINED: "cyan",
    Outcome.WRONG: "red",
    Outcome.ERROR: "red",
    Outcome.SKIPPED: "dim",
}


@dataclass
class Tally:
    """Counts for one tier, or for everything."""

    label: str
    grades: list[Grade] = field(default_factory=list)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for g in self.grades if g.outcome is outcome)

    @property
    def total(self) -> int:
        return len(self.grades)

    @property
    def answered(self) -> int:
        """Questions the system chose to answer. Abstentions are excluded."""
        return self.total - self.count(Outcome.ABSTAINED) - self.count(Outcome.SKIPPED)

    @property
    def accuracy_when_answered(self) -> float:
        """Correct as a share of answered.

        This is the number the second scoring principle actually rewards: it
        rises when the system declines a question it would have got wrong.
        """
        if not self.answered:
            return 0.0
        return self.count(Outcome.CORRECT) / self.answered

    @property
    def unsafe(self) -> list[Grade]:
        return [g for g in self.grades if g.unsafe]

    @property
    def grounded(self) -> int:
        return sum(1 for g in self.grades if g.grounded)

    @property
    def latencies(self) -> list[int]:
        return [g.latency_ms for g in self.grades if g.latency_ms]

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def p95_ms(self) -> float:
        values = sorted(self.latencies)
        if not values:
            return 0.0
        index = min(len(values) - 1, round(0.95 * (len(values) - 1)))
        return float(values[index])

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total": self.total,
            "correct": self.count(Outcome.CORRECT),
            "partial": self.count(Outcome.PARTIAL),
            "abstained": self.count(Outcome.ABSTAINED),
            "wrong": self.count(Outcome.WRONG),
            "error": self.count(Outcome.ERROR),
            "skipped": self.count(Outcome.SKIPPED),
            "unsafe": len(self.unsafe),
            "grounded": self.grounded,
            "accuracy_when_answered": round(self.accuracy_when_answered, 4),
            "mean_ms": round(self.mean_ms, 1),
            "p95_ms": round(self.p95_ms, 1),
        }


@dataclass
class Run:
    """One full pass over the question set in one mode."""

    mode: str
    entry_point: str
    grades: list[Grade] = field(default_factory=list)
    started_at: str = ""

    def tally(self, label: str, grades: Iterable[Grade]) -> Tally:
        return Tally(label, list(grades))

    def by_tier(self) -> list[Tally]:
        return [
            self.tally(f"Tier {tier}", [g for g in self.grades if g.tier == tier])
            for tier in sorted({g.tier for g in self.grades})
        ]

    def overall(self) -> Tally:
        return self.tally("Overall", self.grades)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "entry_point": self.entry_point,
            "started_at": self.started_at,
            "by_tier": [t.as_dict() for t in self.by_tier()],
            "overall": self.overall().as_dict(),
            "grades": [g.as_dict() for g in self.grades],
        }


# ---------------------------------------------------------------- execution


def run_cases(
    handle: runner.AdvisorHandle, cases: Sequence[Case], mode: str, console: Console, *, quiet: bool
) -> Run:
    run = Run(
        mode=mode,
        entry_point=handle.label,
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    for case in cases:
        if not quiet:
            console.print(f"[dim]{case.case_id}  T{case.tier}  {case.prompt[:72]}[/dim]")
        try:
            reply, latency_ms = handle.ask(case.prompt, mode=mode, thread_id=None)
        except Exception as exc:
            run.grades.append(grade(case, None, error=f"{type(exc).__name__}: {exc}"))
            continue
        run.grades.append(grade(case, reply, latency_ms=latency_ms))
    return run


# ----------------------------------------------------------------- printing


def print_detail(console: Console, run: Run) -> None:
    table = Table(title=f"Per question, mode={run.mode}", header_style="bold")
    table.add_column("Id", no_wrap=True)
    table.add_column("T", justify="center")
    table.add_column("Outcome", no_wrap=True)
    table.add_column("Recall", justify="right")
    table.add_column("Ground", justify="center")
    table.add_column("ms", justify="right")
    table.add_column("Note / missed facts", overflow="fold")

    for g in run.grades:
        style = _OUTCOME_STYLE[g.outcome]
        note = g.note
        if not note and g.missed:
            note = "missing " + ", ".join(g.missed[:6])
            if len(g.missed) > 6:
                note += f" (+{len(g.missed) - 6} more)"
        if g.outcome is Outcome.ABSTAINED and g.abstention_reason:
            note = f"[{g.abstention_reason}] {note}"
        table.add_row(
            g.case_id,
            str(g.tier),
            f"[{style}]{g.outcome.value}[/{style}]",
            f"{g.primary_recall:.0%}",
            {True: "yes", False: "NO", None: "-"}[g.grounded],
            str(g.latency_ms),
            note,
        )
    console.print(table)


def print_summary(console: Console, run: Run) -> None:
    table = Table(title=f"Scorecard, mode={run.mode}", header_style="bold")
    # Headers stay short so the table survives an 80 column terminal. A
    # scorecard a judge cannot read on a projector is not a scorecard.
    table.add_column("Scope", no_wrap=True)
    table.add_column("n", justify="right")
    table.add_column("ok", justify="right", style="green")
    table.add_column("part", justify="right", style="yellow")
    table.add_column("abst", justify="right", style="cyan")
    table.add_column("wrong", justify="right", style="red")
    table.add_column("acc", justify="right")
    table.add_column("grnd", justify="right")
    table.add_column("ms avg/p95", justify="right")

    for tally in [*run.by_tier(), run.overall()]:
        wrong = tally.count(Outcome.WRONG) + tally.count(Outcome.ERROR)
        table.add_row(
            tally.label,
            str(tally.total),
            str(tally.count(Outcome.CORRECT)),
            str(tally.count(Outcome.PARTIAL)),
            str(tally.count(Outcome.ABSTAINED)),
            str(wrong),
            f"{tally.accuracy_when_answered:.0%}",
            f"{tally.grounded}/{tally.total}",
            f"{tally.mean_ms:.0f}/{tally.p95_ms:.0f}",
        )
    console.print(table)

    console.print(
        "[dim]ok/part/abst/wrong are counts. 'acc' is correct as a share of the "
        "questions the system chose to answer: abstentions are excluded from it "
        "and are never counted as failures, so declining a question the system "
        "would have got wrong raises this number. 'grnd' is how many answers "
        "passed grounding verification.[/dim]"
    )

    unsafe = run.overall().unsafe
    if unsafe:
        lines = [f"{g.case_id}: {g.note}" for g in unsafe]
        console.print(
            Panel(
                "\n".join(lines),
                title=f"[bold red]{len(unsafe)} unsafe answer(s)[/bold red]",
                subtitle="a verdict inversion is worse than an abstention",
                border_style="red",
            )
        )
    else:
        console.print("[green]No verdict inversions. Every failure failed safely.[/green]")


def print_comparison(console: Console, runs: list[Run]) -> None:
    """Agent against deterministic, question by question.

    This is the table that answers the AI Utilization criterion. What matters
    is not the totals but the rows where the two modes disagree: those are the
    questions the agent earns its place on, or fails to.
    """
    if len(runs) < 2:
        return
    by_mode = {run.mode: {g.case_id: g for g in run.grades} for run in runs}
    modes = [run.mode for run in runs]

    table = Table(title="Mode comparison, rows where the modes disagree", header_style="bold")
    table.add_column("Id", no_wrap=True)
    table.add_column("T", justify="center")
    for mode in modes:
        table.add_column(mode, no_wrap=True)
    table.add_column("Reading", overflow="fold")

    disagreements = 0
    for case_id in by_mode[modes[0]]:
        outcomes = [by_mode[m].get(case_id) for m in modes]
        if any(g is None for g in outcomes):
            continue
        values = [g.outcome for g in outcomes if g is not None]
        if len(set(values)) == 1:
            continue
        disagreements += 1
        first, second = outcomes[0], outcomes[1]
        assert first is not None and second is not None
        if second.outcome is Outcome.CORRECT and first.outcome is not Outcome.CORRECT:
            reading = "the agent earns its place here"
        elif first.outcome is Outcome.CORRECT and second.outcome is not Outcome.CORRECT:
            reading = "the deterministic path is better here, investigate"
        else:
            reading = "both imperfect, different failure"
        table.add_row(
            case_id,
            str(first.tier),
            *[f"[{_OUTCOME_STYLE[g.outcome]}]{g.outcome.value}[/]" for g in outcomes if g],
            reading,
        )

    if disagreements == 0:
        console.print(
            Panel(
                "The two modes produced identical outcomes on every question.\n\n"
                "Read this carefully. It means the agent is not currently doing\n"
                "anything the deterministic resolver cannot do, which is the\n"
                "'decorating a lookup' failure the AI Utilization criterion (20%)\n"
                "names, in mirror image. Either find the questions where planning\n"
                "genuinely matters, or say so honestly in the deck.",
                title="[bold yellow]No disagreement between modes[/bold yellow]",
                border_style="yellow",
            )
        )
    else:
        console.print(table)


# ---------------------------------------------------------------------- main


def write_artefact(runs: list[Run], path: Path, *, scope: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the artefact directory out of git without touching the root ignore
    # file, which another workstream owns.
    marker = path.parent / ".gitignore"
    if not marker.exists():
        marker.write_text("*\n!.gitignore\n", encoding="utf-8")
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": scope,
        "runs": [run.as_dict() for run in runs],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crewops.eval.scorecard",
        description="Score the advisor against the shipped answer keys.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "deterministic", "agent", "both"],
        default="auto",
        help="auto runs both when a model provider is configured, deterministic otherwise",
    )
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], action="append")
    parser.add_argument("--only", help="comma separated case ids, for example Q18,Q24")
    parser.add_argument("--scenarios", action="store_true", help="score the 6 worked scenarios too")
    parser.add_argument("--scenarios-only", action="store_true")
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--quiet", action="store_true", help="no per question progress")
    parser.add_argument("--no-detail", action="store_true", help="summary tables only")
    parser.add_argument(
        "--fail-on-unsafe",
        action="store_true",
        help="exit non-zero when any answer inverts a verdict, for CI",
    )
    return parser


def select_cases(args: argparse.Namespace) -> list[Case]:
    cases: list[Case] = []
    if not args.scenarios_only:
        cases.extend(question_cases())
    if args.scenarios or args.scenarios_only:
        cases.extend(scenario_cases())
    if args.tier:
        cases = [c for c in cases if c.tier in set(args.tier)]
    if args.only:
        wanted = {part.strip().upper() for part in args.only.split(",") if part.strip()}
        cases = [c for c in cases if c.case_id.upper() in wanted]
    return cases


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()

    if not dataset_available():
        console.print(
            "[red]Dataset not found.[/red] Expected "
            "data/crew-ops-advisor-dataset/data/questions.json"
        )
        return 1

    runner.load_env()

    handle = runner.probe()
    if handle is None:
        console.print(
            Panel(
                runner.missing_message(),
                title="[yellow]Nothing to score yet[/yellow]",
                border_style="yellow",
            )
        )
        return 0

    if args.mode == "auto":
        modes = list(runner.available_modes())
    elif args.mode == "both":
        modes = [runner.MODE_DETERMINISTIC, runner.MODE_AGENT]
    else:
        modes = [args.mode]

    if runner.MODE_AGENT in modes and not runner.has_api_key():
        console.print(
            "[yellow]No model provider is configured, so agent mode is skipped. "
            "Set ANTHROPIC_API_KEY, OPENAI_API_KEY or OLLAMA_API_KEY. "
            "The deterministic path still runs: that is the point of it.[/yellow]"
        )
        modes = [m for m in modes if m != runner.MODE_AGENT] or [runner.MODE_DETERMINISTIC]

    cases = select_cases(args)
    if not cases:
        console.print("[yellow]No cases selected.[/yellow]")
        return 0

    console.print(f"[bold]{len(cases)} case(s)[/bold] via [cyan]{handle.label}[/cyan]")

    runs: list[Run] = []
    for mode in modes:
        run = run_cases(handle, cases, mode, console, quiet=args.quiet)
        runs.append(run)
        if not args.no_detail:
            print_detail(console, run)
        print_summary(console, run)

    print_comparison(console, runs)

    scope = "scenarios" if args.scenarios_only else "questions"
    default_name = f"scorecard-{'-'.join(m[:4] for m in modes)}.json"
    path = args.json_path or (DEFAULT_ARTEFACT_DIR / default_name)
    written = write_artefact(runs, path, scope=scope)
    console.print(f"[dim]JSON artefact: {written}[/dim]")

    if args.fail_on_unsafe and any(run.overall().unsafe for run in runs):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
