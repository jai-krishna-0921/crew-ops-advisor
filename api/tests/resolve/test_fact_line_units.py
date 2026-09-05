"""A fact line prints a value, not the name of its type.

`Fact.unit` carries two different kinds of thing. Some values are dimensional
(`hours`, `minutes`, `days`, `percent`) and the unit belongs in the sentence.
The rest are type tags telling the verifier how to compare a value: `flight_no`,
`crew_id`, `pairing_id`, `rule_id`, `station`, `aircraft_type`, `rank`, `date`.
`_fact_line` suffixed everything outside a three-item exemption list, so a
controller read:

    Legs that need another crew: DX404 flight_no
    Cost to re-crew those legs from reserve: 75000 inr

Money is the third case. `inr` is dimensional, but it goes in front and it is
grouped, because 250000 and 2500000 are one glance apart and one is ten times
the other. Every other module that states money already writes `INR 250,000`.

Grouping is not the renderer computing anything: the digits are the attested
value, and the verifier reads through the separators, which is why the ranked
options renderer has written money this way from the start.
"""

from __future__ import annotations

from crewops.contracts import Fact, Provenance
from crewops.resolve.render import _fact_line


def _fact(value: object, unit: str) -> Fact:
    return Fact(
        key="k",
        label="Label",
        value=value,  # type: ignore[arg-type]
        unit=unit,  # type: ignore[arg-type]
        provenance=Provenance.COMPUTED,
        source="test",
    )


def test_a_dimensional_unit_is_kept() -> None:
    assert _fact_line(_fact(12.75, "hours")) == "Label: 12.75 hours"


def test_a_type_tag_is_not_printed() -> None:
    for unit in ("flight_no", "crew_id", "pairing_id", "rule_id", "station", "rank"):
        line = _fact_line(_fact("DX404", unit))
        assert line == "Label: DX404", f"{unit} leaked into the sentence: {line}"


def test_money_is_grouped_and_prefixed() -> None:
    assert _fact_line(_fact(250000.0, "inr")) == "Label: INR 250,000"


def test_the_derivation_still_follows_the_value() -> None:
    fact = _fact(75000.0, "inr")
    fact = fact.model_copy(update={"derivation": "2 x 18,500 + 4 x 9,500"})
    assert _fact_line(fact) == "Label: INR 75,000  [2 x 18,500 + 4 x 9,500]"
