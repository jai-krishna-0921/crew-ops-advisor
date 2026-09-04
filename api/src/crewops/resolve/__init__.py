"""The offline path: pattern matched intents, deterministic templates, no model.

Also home to the triage classifier, which both answer paths share so the two
modes never disagree about what is answerable.
"""

from crewops.resolve.intents import INTENTS, Intent, PlannedCall, match_intent
from crewops.resolve.render import render
from crewops.resolve.resolver import SUPPORTED_SHAPES, DeterministicResolver
from crewops.resolve.triage import (
    STATIONS,
    Entities,
    Triage,
    classify_tier,
    extract_entities,
    rank_in,
    triage_question,
)

__all__ = [
    "INTENTS",
    "STATIONS",
    "SUPPORTED_SHAPES",
    "DeterministicResolver",
    "Entities",
    "Intent",
    "PlannedCall",
    "Triage",
    "classify_tier",
    "extract_entities",
    "match_intent",
    "rank_in",
    "render",
    "triage_question",
]
