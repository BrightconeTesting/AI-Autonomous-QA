"""Recommended test area approve/dismiss decisions (Phase E §20.9)."""

from __future__ import annotations

from typing import Any

DECISION_APPROVED = "approved"
DECISION_DISMISSED = "dismissed"


def normalize_decisions(raw: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, str] = {}
    for area_id, status in raw.items():
        key = str(area_id or "").strip()
        value = str(status or "").strip().lower()
        if not key:
            continue
        if value in {DECISION_APPROVED, DECISION_DISMISSED}:
            normalized[key] = value
    return normalized


def apply_test_area_decisions(
    appmap: dict[str, Any],
    decisions: dict[str, str] | None,
) -> dict[str, Any]:
    """Return appmap copy with dismissed areas removed from recommended_test_areas."""
    areas = list(appmap.get("recommended_test_areas") or [])
    if not areas:
        return appmap
    decision_map = normalize_decisions(decisions)
    if not decision_map:
        return appmap
    kept = [area for area in areas if decision_map.get(str(area.get("area_id") or "")) != DECISION_DISMISSED]
    updated = dict(appmap)
    updated["recommended_test_areas"] = kept
    updated["test_area_decisions"] = decision_map
    return updated


def annotate_test_areas_with_decisions(
    areas: list[dict[str, Any]],
    decisions: dict[str, str] | None,
) -> list[dict[str, Any]]:
    decision_map = normalize_decisions(decisions)
    annotated: list[dict[str, Any]] = []
    for area in areas:
        area_id = str(area.get("area_id") or "")
        item = dict(area)
        if area_id in decision_map:
            item["decision"] = decision_map[area_id]
        else:
            item["decision"] = DECISION_APPROVED
        annotated.append(item)
    return annotated
