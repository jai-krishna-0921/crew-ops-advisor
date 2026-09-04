"""Checking six crew should cost one round trip, not six.

Tier 2 abstained on six of fourteen questions purely on the 25 second turn
budget, and the reason was almost never that a computation was slow. It was
that the agent asked the same question once per crew member. Q20 made ten tool
calls, six of them `check_legality` against the same pairing on the same date,
differing only in `crew_id`. Each is a model round trip to decide the next one.

The fix is a plural argument, not a new tool: the agent already knows how to
call `check_legality`, and a second name for the same computation is a second
thing to get wrong.

The property that matters is equality. A batch must return exactly what the
individual calls return, because the moment the two can disagree there are two
legality engines and only one of them is tested.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.contracts import LegalityReport, RuleTrace
from crewops.domain import load_world
from crewops.tools.registry import Tools

#: P-2203 on 2026-09-16, the pairing behind Q20, and its six rostered crew.
PAIRING = "P-2203"
ON_DATE = dt.date(2026, 9, 16)
CREW = ["C-3187", "C-5375", "C-3211", "C-2876", "C-1542", "C-5089"]


@pytest.fixture(scope="module")
def tools() -> Tools:
    from crewops.agent.factory import default_data_dir

    return Tools(load_world(default_data_dir()))


def reports_of(payload: object) -> list[LegalityReport]:
    from crewops.agent.reply import _walk_for

    return list(_walk_for(payload, LegalityReport))


def test_a_batch_returns_one_report_per_crew_member(tools: Tools) -> None:
    envelope = tools.check_legality(crew_ids=CREW, pairing_id=PAIRING, on_date=ON_DATE)
    assert envelope.ok, envelope.error
    reports = reports_of(envelope.payload)
    assert [r.crew_id for r in reports] == CREW, (
        "the batch must answer for every crew member, in the order asked"
    )


def test_a_batch_equals_the_individual_calls(tools: Tools) -> None:
    """The property that makes this a round trip saving and not a second engine."""
    batched = {
        r.crew_id: r
        for r in reports_of(
            tools.check_legality(crew_ids=CREW, pairing_id=PAIRING, on_date=ON_DATE).payload
        )
    }
    for crew_id in CREW:
        single = tools.check_legality(crew_id=crew_id, pairing_id=PAIRING, on_date=ON_DATE)
        assert single.ok, single.error
        one = reports_of(single.payload)[0]
        assert batched[crew_id].overall is one.overall, (
            f"{crew_id}: batch says {batched[crew_id].overall}, "
            f"the individual call says {one.overall}"
        )
        assert [t.rule_id for t in _traces(batched[crew_id])] == [
            t.rule_id for t in _traces(one)
        ], f"{crew_id}: the batch checked a different set of rules"


def _traces(report: LegalityReport) -> list[RuleTrace]:
    from crewops.agent.reply import _walk_for

    return list(_walk_for(report, RuleTrace))


def test_a_batch_carries_every_crew_members_rule_traces(tools: Tools) -> None:
    """The rule traces are the reasoning trail. Losing five sixths of it is not
    a saving, it is a silent downgrade of the explanation."""
    envelope = tools.check_legality(crew_ids=CREW, pairing_id=PAIRING, on_date=ON_DATE)
    from crewops.agent.reply import _walk_for

    traces = list(_walk_for(envelope.payload, RuleTrace))
    assert len({t.rule_id for t in traces}) >= 5, (
        f"only {sorted({t.rule_id for t in traces})} survived the batch"
    )


def test_the_single_crew_form_is_unchanged(tools: Tools) -> None:
    """Every existing caller and every golden test uses this form."""
    envelope = tools.check_legality(crew_id="C-3187", pairing_id=PAIRING, on_date=ON_DATE)
    assert envelope.ok, envelope.error
    reports = reports_of(envelope.payload)
    assert len(reports) == 1
    assert reports[0].crew_id == "C-3187"


def test_an_unknown_crew_id_does_not_poison_the_whole_batch(tools: Tools) -> None:
    """One bad id must not lose the five good answers.

    It must also not be silently dropped: a caller has to be able to tell
    "checked and legal" from "never checked".
    """
    envelope = tools.check_legality(
        crew_ids=["C-3187", "C-9999"], pairing_id=PAIRING, on_date=ON_DATE
    )
    assert envelope.ok, envelope.error
    reports = reports_of(envelope.payload)
    assert [r.crew_id for r in reports] == ["C-3187"]
    assert isinstance(envelope.payload, dict)
    unresolved = envelope.payload.get("unresolved")
    assert unresolved and "C-9999" in str(unresolved), (
        f"the unknown id was dropped without trace: {envelope.payload!r}"
    )


def test_naming_neither_crew_id_nor_crew_ids_is_an_error(tools: Tools) -> None:
    envelope = tools.check_legality(pairing_id=PAIRING, on_date=ON_DATE)
    assert not envelope.ok
    assert "crew" in (envelope.error or "").lower()
