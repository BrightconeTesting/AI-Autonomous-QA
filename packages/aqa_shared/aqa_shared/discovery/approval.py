"""AppMap approval workflow constants and config helpers (§19.3)."""

from __future__ import annotations

from typing import Any

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"


def mark_appmap_pending(config: dict[str, Any]) -> dict[str, Any]:
    """Reset approval fields when a new AppMap is produced."""
    updated = dict(config)
    updated["appmap_approval_status"] = APPROVAL_PENDING
    updated.pop("appmap_approved_at", None)
    updated.pop("appmap_rejection_reason", None)
    return updated
