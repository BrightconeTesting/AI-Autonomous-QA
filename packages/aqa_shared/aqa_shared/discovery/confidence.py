"""Confidence scoring for DiscoveryAgent intelligence artifacts (§19.1)."""

from __future__ import annotations

REVIEW_THRESHOLD = 0.6


def attach_confidence(
    item: dict,
    *,
    confidence: float,
    factors: list[str],
) -> dict:
    """Attach confidence fields to a flow/module/entity dict."""
    score = max(0.0, min(1.0, float(confidence)))
    item["confidence"] = round(score, 3)
    item["confidence_factors"] = list(factors)
    item["review_required"] = score < REVIEW_THRESHOLD
    return item


def rule_flow_confidence(*, is_rule_based: bool = True) -> tuple[float, list[str]]:
    if is_rule_based:
        return 1.0, ["rule:deterministic", "grounded:crawl_data"]
    return 0.85, ["rule:heuristic"]


def llm_grounded_flow_confidence(*, accepted_count: int) -> tuple[float, list[str]]:
    factors = ["llm:grounding_passed", "grounded:appmap_steps"]
    if accepted_count > 0:
        factors.append(f"llm:flows_accepted={accepted_count}")
    return 0.9, factors
