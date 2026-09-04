"""The terminal interface.

The problem statement accepts a well built CLI as a conversational interface,
so this one is built properly: rule traces and ranked options render as real
tables with the arithmetic visible, because "trust me, it breaches" is not an
explanation a controller can challenge.

Commands:

    crewops ask "..."          one question
    crewops chat               interactive, with thread memory
    crewops brief 2026-09-15   the proactive watchlist
    crewops serve              the web interface
    crewops health             what is configured and what is not

`--offline` forces the deterministic path on any of them, so a demo can show
the rules engine answering with the API key unset.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from crewops.agent.advisor import Advisor
from crewops.agent.config import AgentConfig, llm_configured
from crewops.agent.factory import CoreUnavailableError, build_model, load_tools
from crewops.agent.memory import Memory
from crewops.agent.toolspecs import call_tool
from crewops.contracts import (
    Recommendation,
    Reply,
    ReplyKind,
    RuleTrace,
    ToolSurface,
    Verdict,
    VerificationStatus,
    Watchlist,
)

app = typer.Typer(
    name="crewops",
    help="Crew Ops Advisor: a decision aid for an airline Crew Control desk.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_VERDICT_STYLE = {
    Verdict.PASS: "green",
    Verdict.BREACH: "bold red",
    Verdict.NOT_APPLICABLE: "dim",
    Verdict.INSUFFICIENT_DATA: "yellow",
}

_STATUS_STYLE = {
    VerificationStatus.VERIFIED: "green",
    VerificationStatus.REPAIRED: "yellow",
    VerificationStatus.REJECTED: "bold red",
    VerificationStatus.SKIPPED: "dim",
}


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def _build_advisor(
    *, offline: bool, data_dir: Path | None, memory: Memory | None = None
) -> Advisor:
    tools = _load_tools(data_dir)
    model = None if offline else build_model()
    return Advisor(
        tools,
        model=model,
        plan_model=model,
        memory=memory,
        checkpointer=memory.checkpointer if memory is not None else None,
        force_mode="deterministic" if offline else None,
    )


def _load_tools(data_dir: Path | None) -> ToolSurface:
    try:
        return load_tools(data_dir)
    except CoreUnavailableError as exc:
        console.print(
            Panel(
                Text(str(exc), style="red"),
                title="The deterministic core is not available",
                border_style="red",
            )
        )
        raise typer.Exit(code=2) from exc


def _parse_as_of(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except ValueError as exc:
        raise typer.BadParameter(f"{value!r} is not an ISO datetime") from exc


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_reply(reply: Reply, *, show_evidence: bool = True) -> None:
    """The answer, then the working, then the grounding verdict."""
    border = "red" if reply.kind is ReplyKind.ABSTAIN else "cyan"
    mode_note = (
        "agent" if reply.mode.value == "agent" else "deterministic, no model"
    )
    tier = f"tier {reply.tier}" if reply.tier else "tier unknown"

    if reply.headline:
        console.print(
            Panel(
                Text(reply.headline, style="bold"),
                title=f"{tier} | {mode_note}",
                border_style=border,
            )
        )

    if reply.abstention is not None:
        _render_abstention(reply)
    elif reply.text:
        console.print(Markdown(reply.text))

    if show_evidence:
        if reply.rule_traces:
            console.print(_rule_table(reply.rule_traces))
        if reply.recommendation is not None:
            console.print(_options_table(reply.recommendation))
        if reply.impact is not None and reply.impact.downstream_risks:
            console.print(_risk_table(reply))

    _render_verification(reply)

    if reply.caveats:
        console.print(
            Panel(
                "\n".join(f"- {c}" for c in reply.caveats),
                title="Caveats",
                border_style="yellow",
            )
        )
    if reply.follow_ups:
        console.print(
            Text("  ".join(f"[{f}]" for f in reply.follow_ups), style="dim italic")
        )


def _render_abstention(reply: Reply) -> None:
    abstention = reply.abstention
    if abstention is None:  # pragma: no cover - guarded by the caller
        return
    body: list[Any] = [Text(abstention.message)]
    if abstention.did_establish:
        body.append(Text("\nWhat I did establish:", style="bold"))
        body.extend(Text(f"  {line}") for line in abstention.did_establish)
    if abstention.missing:
        body.append(Text("\nWhat was missing:", style="bold"))
        body.extend(Text(f"  {line}") for line in abstention.missing)
    if abstention.suggestions:
        body.append(Text("\nTry instead:", style="bold"))
        body.extend(Text(f"  {line}", style="cyan") for line in abstention.suggestions)
    console.print(
        Panel(
            Group(*body),
            title=f"Declined: {abstention.reason.value}",
            border_style="red",
        )
    )


def _rule_table(traces: list[RuleTrace]) -> Table:
    table = Table(
        title="Rule evaluation, with the arithmetic",
        header_style="bold",
        show_lines=False,
    )
    table.add_column("Rule")
    table.add_column("Date")
    table.add_column("Verdict")
    table.add_column("Limit", justify="right")
    table.add_column("Observed", justify="right")
    table.add_column("Margin")
    table.add_column("Working", overflow="fold")
    for trace in traces:
        table.add_row(
            trace.rule_id,
            str(trace.duty_date) if trace.duty_date else "",
            Text(trace.verdict.value, style=_VERDICT_STYLE.get(trace.verdict, "")),
            f"{trace.limit:.2f}" if trace.limit is not None else "",
            f"{trace.observed:.2f}" if trace.observed is not None else "",
            trace.margin_human or "",
            trace.arithmetic,
        )
    return table


def _options_table(recommendation: Recommendation) -> Group:
    table = Table(title="Ranked options", header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Action")
    table.add_column("Crew")
    table.add_column("Legal")
    table.add_column("Cost INR", justify="right")
    table.add_column("Coverage")
    table.add_column("Delay", justify="right")
    table.add_column("Reasoning", overflow="fold")
    for option in recommendation.options:
        table.add_row(
            str(option.rank),
            option.action,
            f"{option.crew_id} ({option.crew_rank}, {option.crew_base})",
            Text("yes" if option.legal else "no", style="green" if option.legal else "red"),
            f"{option.cost.total_inr:,.0f}",
            option.coverage_summary,
            f"{option.delay_minutes}m" if option.delay_minutes else "",
            option.reasoning,
        )

    parts: list[Any] = [table]
    if recommendation.rejected:
        rejects = Table(
            title="Rejected candidates, and the rule that excluded each",
            header_style="bold",
        )
        rejects.add_column("Crew")
        rejects.add_column("Rank")
        rejects.add_column("Rule")
        rejects.add_column("Working", overflow="fold")
        for option in recommendation.rejected:
            breach = option.legality.breaches
            rejects.add_row(
                option.crew_id,
                option.crew_rank,
                breach[0].rule_id if breach else "",
                breach[0].arithmetic if breach else "no legal path found",
            )
        parts.append(rejects)
    if recommendation.ranking_basis:
        parts.append(Text(f"Ranked by: {recommendation.ranking_basis}", style="dim"))
    return Group(*parts)


def _risk_table(reply: Reply) -> Table:
    table = Table(title="Downstream consequences", header_style="bold")
    table.add_column("Severity")
    table.add_column("Subject")
    table.add_column("Rule")
    table.add_column("Detail", overflow="fold")
    impact = reply.impact
    if impact is None:  # pragma: no cover - guarded by the caller
        return table
    for risk in impact.downstream_risks:
        table.add_row(
            risk.severity.value,
            risk.crew_id or risk.flight_no or risk.pairing_id or "",
            risk.rule_id or "",
            risk.detail,
        )
    return table


def _render_verification(reply: Reply) -> None:
    report = reply.verification
    style = _STATUS_STYLE.get(report.status, "")
    line = Text()
    line.append("Grounding: ", style="bold")
    line.append(report.status.value, style=style)
    if report.checked_atoms:
        line.append(
            f"  {report.attested_atoms}/{report.checked_atoms} figures traced to a "
            "tool result"
        )
    line.append(
        f"  |  {reply.timings.tool_calls} tool calls, "
        f"{reply.timings.model_calls} model calls, {reply.timings.total_ms} ms",
        style="dim",
    )
    console.print(line)
    if report.unattested:
        table = Table(title="Rejected as unattested", header_style="bold red")
        table.add_column("Token")
        table.add_column("Kind")
        table.add_column("In", overflow="fold")
        for item in report.unattested:
            table.add_row(item.atom, item.kind, item.context)
        console.print(table)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="The question, in plain language")],
    offline: Annotated[
        bool, typer.Option("--offline", help="Force the deterministic path")
    ] = False,
    thread: Annotated[
        str | None, typer.Option("--thread", help="Continue an existing thread")
    ] = None,
    as_of: Annotated[
        str | None, typer.Option("--as-of", help="Override the snapshot, ISO datetime")
    ] = None,
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", help="Dataset directory")
    ] = None,
    json_out: Annotated[
        bool, typer.Option("--json", help="Emit the Reply as JSON instead")
    ] = False,
    evidence: Annotated[
        bool, typer.Option("--evidence/--no-evidence", help="Show the working")
    ] = True,
) -> None:
    """Answer one question."""

    async def run() -> Reply:
        memory = await Memory(AgentConfig.from_env().memory_path).open()
        try:
            advisor = _build_advisor(offline=offline, data_dir=data_dir, memory=memory)
            return await advisor.ask(
                question, thread_id=thread, as_of=_parse_as_of(as_of)
            )
        finally:
            await memory.close()

    reply = asyncio.run(run())
    if json_out:
        console.print_json(reply.model_dump_json())
    else:
        render_reply(reply, show_evidence=evidence)
        console.print(Text(f"thread {reply.thread_id}", style="dim"))
    if reply.kind is ReplyKind.ABSTAIN:
        raise typer.Exit(code=1)


@app.command()
def chat(
    offline: Annotated[
        bool, typer.Option("--offline", help="Force the deterministic path")
    ] = False,
    thread: Annotated[
        str | None, typer.Option("--thread", help="Resume an existing thread")
    ] = None,
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", help="Dataset directory")
    ] = None,
) -> None:
    """Interactive session. Memory persists per thread, across restarts."""

    async def run() -> None:
        memory = await Memory(AgentConfig.from_env().memory_path).open()
        try:
            advisor = _build_advisor(offline=offline, data_dir=data_dir, memory=memory)
            thread_id = thread
            mode = advisor.mode
            console.print(
                Panel(
                    Text(
                        "Crew Ops Advisor. dCortex Air, hub BLR, week 2026-09-14 to "
                        "2026-09-20, all times UTC.\n"
                        f"Mode: {mode}. Type a question, or 'exit'.",
                    ),
                    border_style="cyan",
                )
            )
            while True:
                try:
                    question = console.input("[bold cyan]> [/bold cyan]").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print()
                    break
                if not question:
                    continue
                if question.lower() in {"exit", "quit", ":q"}:
                    break
                with console.status("thinking", spinner="dots"):
                    reply = await advisor.ask(question, thread_id=thread_id)
                thread_id = reply.thread_id
                render_reply(reply)
                console.print()
        finally:
            await memory.close()

    asyncio.run(run())


@app.command()
def brief(
    for_date: Annotated[
        datetime, typer.Argument(formats=["%Y-%m-%d"], help="The date to brief on")
    ],
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", help="Dataset directory")
    ] = None,
) -> None:
    """The proactive watchlist. Deterministic: no model call on this path."""
    tools = _load_tools(data_dir)
    target: date_cls = for_date.date()
    envelope = call_tool(tools, "get_watchlist", {"for_date": target})
    if not envelope.ok:
        console.print(Text(envelope.error or "The watchlist could not be built", style="red"))
        raise typer.Exit(code=1)

    watchlist = envelope.payload
    if not isinstance(watchlist, Watchlist):
        console.print(Text("The watchlist tool returned an unexpected payload", style="red"))
        raise typer.Exit(code=1)

    console.print(
        Panel(
            Text(watchlist.headline, style="bold"),
            title=f"Brief for {target}",
            border_style="cyan",
        )
    )
    table = Table(header_style="bold")
    table.add_column("Severity")
    table.add_column("What")
    table.add_column("Who")
    table.add_column("Rule")
    table.add_column("Detail", overflow="fold")
    table.add_column("Ask", overflow="fold", style="cyan")
    for alert in watchlist.alerts:
        table.add_row(
            alert.severity.value,
            alert.title,
            alert.crew_id or alert.flight_no or alert.pairing_id or "",
            alert.rule_id or "",
            alert.detail,
            alert.suggested_question or "",
        )
    console.print(table)
    if watchlist.scanned:
        scanned = ", ".join(f"{v} {k}" for k, v in watchlist.scanned.items())
        console.print(Text(f"Scanned: {scanned}.", style="dim"))


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Reload on change")] = False,
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", help="Dataset directory")
    ] = None,
) -> None:
    """Serve the HTTP API the web interface talks to."""
    import uvicorn

    if data_dir is not None:
        os.environ["CREWOPS_DATA_DIR"] = str(data_dir)
    console.print(
        Text(
            f"Crew Ops Advisor on http://{host}:{port}  "
            f"(mode: {'agent' if llm_configured() else 'deterministic'})",
            style="cyan",
        )
    )
    uvicorn.run(
        "crewops.server.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


@app.command()
def health(
    data_dir: Annotated[
        Path | None, typer.Option("--data-dir", help="Dataset directory")
    ] = None,
) -> None:
    """What is configured, what is loaded, and which mode is active."""
    table = Table(header_style="bold", title="Crew Ops Advisor")
    table.add_column("Check")
    table.add_column("Value")

    key = llm_configured()
    table.add_row(
        "ANTHROPIC_API_KEY",
        Text("set" if key else "not set", style="green" if key else "yellow"),
    )
    table.add_row("Mode", "agent" if key else "deterministic")
    table.add_row("Model", AgentConfig.from_env().model)

    try:
        tools = load_tools(data_dir)
        summary = tools.get_world_summary()
        table.add_row(
            "Dataset",
            Text("loaded", style="green")
            if summary.ok
            else Text(summary.error or "failed", style="red"),
        )
        if summary.ok and isinstance(summary.payload, dict):
            for key_name in ("snapshot", "hub", "currency"):
                if key_name in summary.payload:
                    table.add_row(key_name, str(summary.payload[key_name]))
            counts = summary.payload.get("counts")
            if isinstance(counts, dict):
                table.add_row(
                    "Counts", ", ".join(f"{v} {k}" for k, v in counts.items())
                )
    except CoreUnavailableError as exc:
        table.add_row("Dataset", Text(str(exc), style="red"))

    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
