"""The model was shown 2.7% of the answer and asked to write about all of it.

Measured, not guessed. `find_cover_options(pairing_id="P-2291",
include_rejected=True)` serialises to **223,156 characters**. The budget handed
to the model is 6,000. So on every tier 3 turn the model received rank 1, part
of rank 2, and the string "...[truncated]".

Three symptoms, one cause:

  "A tool result was capped for the prompt budget."  on every recommendation
  "This answer needed one correction pass ..."       most of them
  36 seconds, budget exceeded                        some of them

The repairs are the tell. The model writes prose about five options and a
cancellation from a blob that stops inside option two, so it reaches for the
`facts` channel and the rejected count, gets a figure slightly wrong, and the
verifier sends it back. That correction pass costs a whole model round trip,
which is most of the way to the 30 second budget on its own.

Raising the cap is the wrong fix: 223KB of rule traces would bury the prompt
and cost more time than it saves. The right one is that **the model does not
need the traces at all.** The UI renders them structurally, the verifier checks
them from the full envelope, and `agent/prompts.py` already tells the model the
interface draws the payload beside its prose. What the model needs is every
option's identity, verdict, price and reason: complete, and small.

So a large payload is COMPACTED rather than cut. Nothing is dropped that the
model needs to name; what goes is the per-rule per-day arithmetic that it must
never restate anyway.
"""

from __future__ import annotations

import json

import pytest

from crewops.agent.compact import model_view


@pytest.fixture(scope="module")
def tools():
    from crewops.agent.factory import load_tools

    return load_tools()


@pytest.fixture(scope="module")
def recommendation(tools):
    envelope = tools.find_cover_options(pairing_id="P-2291", include_rejected=True)
    assert envelope.ok, envelope.error
    return envelope.payload


def _chars(value: object) -> int:
    return len(json.dumps(value, default=str))


def test_the_full_payload_really_is_that_big(recommendation) -> None:
    """The premise of this module, asserted so it cannot rot quietly."""
    assert _chars(recommendation.model_dump(mode="json")) > 100_000


def test_the_compaction_removes_almost_all_of_it(recommendation) -> None:
    """223KB to about 11KB. The remainder is identity, verdict, price and
    reason for six options and nineteen rejects, which is what the prose is
    written from and none of it can be dropped."""
    before = _chars(recommendation.model_dump(mode="json"))
    after = _chars(model_view(recommendation))
    assert after < before * 0.1, f"{before} -> {after}"


def test_the_compacted_view_fits_its_budget(recommendation) -> None:
    """A larger allowance than the raw cap, deliberately. Compacted content is
    all signal; truncated content is a JSON string that stops mid-object."""
    from crewops.agent.graph import _COMPACT_CHAR_BUDGET, _PAYLOAD_CHAR_BUDGET

    assert _COMPACT_CHAR_BUDGET > _PAYLOAD_CHAR_BUDGET
    assert _chars(model_view(recommendation)) < _COMPACT_CHAR_BUDGET


def test_every_ranked_option_survives(recommendation) -> None:
    """Complete, not merely small. Cutting to the first five would be the
    truncation bug with better manners."""
    view = model_view(recommendation)
    assert len(view["options"]) == len(recommendation.options)
    seen = {option["crew_id"] for option in view["options"]}
    assert seen == {option.crew_id for option in recommendation.options}


def test_each_option_keeps_what_the_prose_has_to_name(recommendation) -> None:
    top = model_view(recommendation)["options"][0]
    for key in ("rank", "action", "crew_id", "legal", "cost_inr", "reasoning"):
        assert key in top, f"{key} is missing and the prose needs it"
    assert top["cost_inr"] == recommendation.options[0].cost.total_inr


def test_a_breach_keeps_the_rule_that_binds(recommendation) -> None:
    """An illegal candidate with no reason is not an explanation."""
    view = model_view(recommendation)
    rejected = view["rejected"]
    assert rejected, "the rejects are the proof the search was real"
    assert any(entry.get("breaches") for entry in rejected)
    for entry in rejected:
        assert entry.get("breaches") or entry.get("reason"), (
            f"{entry['crew_id']} was excluded and the view says nothing about why"
        )


def test_the_per_day_arithmetic_is_what_goes(recommendation) -> None:
    """The traces are rendered by the UI and checked by the verifier. Restating
    them in the prose is the thing the prompt forbids."""
    rendered = json.dumps(model_view(recommendation), default=str)
    assert "arithmetic" not in rendered


def test_the_counts_that_carry_the_search_survive(recommendation) -> None:
    view = model_view(recommendation)
    assert view["candidates_evaluated"] == recommendation.candidates_evaluated
    assert view["ranking_basis"] == recommendation.ranking_basis


def test_a_small_payload_is_returned_untouched(tools) -> None:
    """Compaction is for the payloads that need it. A pairing already fits."""
    envelope = tools.get_pairing(pairing_id="P-2291")
    assert envelope.ok
    view = model_view(envelope.payload)
    assert view == envelope.payload.model_dump(mode="json")


def test_an_unknown_shape_is_not_mangled() -> None:
    assert model_view({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}
    assert model_view(None) is None
