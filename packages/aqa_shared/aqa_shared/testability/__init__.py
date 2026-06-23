"""Element testability classification (DISCOVERY-AGENT-VISION-SPEC §8.7)."""

from aqa_shared.testability.enrichment import (
    classify_button_intent,
    classify_element_kind,
    classify_link_scope,
    classify_testability_tier,
    enrich_element_attributes,
    extract_html5_constraints,
    score_element_testability,
)

__all__ = [
    "classify_button_intent",
    "classify_element_kind",
    "classify_link_scope",
    "classify_testability_tier",
    "enrich_element_attributes",
    "extract_html5_constraints",
    "score_element_testability",
]
