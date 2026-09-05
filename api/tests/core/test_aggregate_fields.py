"""A tool that cannot do a thing has to say so, not report success.

"Who is my most used captain?" cost 37 seconds and ended in a timeout
abstention. The agent's first move was right:

    aggregate(collection="pairings", metric="count", group_by="captain")

`aggregate` answered `ok=True`, `matched=39`, `groups=(("None", 39.0),)`. It
said it had grouped all thirty-nine pairings by captain and found them all in a
single group called None. Pairing rows carried no crew at all, so
`row.get("captain")` was None on every row and `str(None)` became the key.

That is a false success, and it is expensive. The model asked again, got the
same non-answer, abandoned aggregation and read the pairings one at a time:
fifteen `get_pairing` calls at a model round trip each, twenty-three tool calls
and eight model calls in total. The tools took 7ms of the 37 seconds. Every
other millisecond was the loop, going the long way round because a tool told it
a lie it could not detect.

Two fixes, and they are separate.

  * An unknown field is an error naming what the collection does have. This is
    the rule the whole system is built on, "abstain over guess", applied to a
    tool rather than to an answer. A wrong-shaped result the caller cannot
    distinguish from a real one is the worst thing a tool can return.
  * Pairing rows carry their crew. Every pairing in the dataset has exactly one
    Captain, verified, so `captain` is a clean scalar to group on and the
    question the agent asked on turn one is answerable in one call.
"""

from __future__ import annotations

import pytest

from crewops.domain import WorldState
from crewops.tools.registry import Tools


@pytest.fixture(scope="module")
def tools(world: WorldState) -> Tools:
    return Tools(world)


# ------------------------------------------------------- an unknown field errors


def test_an_unknown_group_by_is_an_error_not_a_none_bucket(tools: Tools) -> None:
    envelope = tools.aggregate(collection="pairings", metric="count", group_by="nonsense")
    assert not envelope.ok
    assert envelope.payload is None


def test_an_unknown_metric_field_is_an_error(tools: Tools) -> None:
    envelope = tools.aggregate(collection="crew", metric="sum", field="nonsense")
    assert not envelope.ok


def test_an_unknown_filter_key_says_the_key_is_wrong(tools: Tools) -> None:
    """This already failed, but for the wrong reason and with the wrong words.

    Filtering on a key no row has removed every row, so the caller was told
    "No crew rows match filters {'nonsense': 'Captain'}". That reads as a
    finding about the data ("there are no such crew") when it is a broken
    query, and a caller acting on it would conclude the roster is empty.
    """
    envelope = tools.aggregate(
        collection="crew", metric="count", filters={"nonsense": "Captain"}
    )
    assert not envelope.ok
    assert envelope.error is not None
    assert "nonsense" in envelope.error
    assert "no field" in envelope.error
    assert "match" not in envelope.error


def test_the_error_names_the_fields_the_collection_actually_has(tools: Tools) -> None:
    envelope = tools.aggregate(collection="pairings", metric="count", group_by="nonsense")
    assert envelope.error is not None
    # Enough to fix the call on the next attempt rather than guess again.
    assert "nonsense" in envelope.error
    for field in ("pairing_id", "duty_days", "total_legs"):
        assert field in envelope.error


def test_a_known_group_by_still_works(tools: Tools) -> None:
    envelope = tools.aggregate(collection="crew", metric="count", group_by="rank")
    assert envelope.ok, envelope.error
    ranks = dict(envelope.payload.groups)
    assert ranks["Captain"] == 28


# ------------------------------------------------ a pairing knows who flies it


def test_pairings_carry_their_captain(tools: Tools) -> None:
    envelope = tools.aggregate(collection="pairings", metric="count", group_by="captain")
    assert envelope.ok, envelope.error
    groups = dict(envelope.payload.groups)
    assert "None" not in groups, "captain is still unresolved on every row"
    assert envelope.payload.matched == 39
    # Verified against the dataset: four captains hold three pairings each.
    assert groups["C-5837"] == 3
    assert groups["C-2143"] == 3


def test_pairings_can_be_summed_by_captain(tools: Tools) -> None:
    """The measure a controller means by 'most used' is legs flown, not
    pairings held. Both are one call once the field exists."""
    envelope = tools.aggregate(
        collection="pairings", metric="sum", field="total_legs", group_by="captain"
    )
    assert envelope.ok, envelope.error
    by_legs = dict(envelope.payload.groups)
    assert by_legs["C-5837"] == 12
    assert max(by_legs.values()) == 12


def test_pairings_carry_the_first_officer_too(tools: Tools) -> None:
    envelope = tools.aggregate(
        collection="pairings", metric="count", group_by="first_officer"
    )
    assert envelope.ok, envelope.error
    assert "None" not in dict(envelope.payload.groups)
