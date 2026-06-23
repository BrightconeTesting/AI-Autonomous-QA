"""Per-stage LLM token budgets for DiscoveryAgent (DISCOVERY-AGENT-VISION-SPEC §19.2)."""

from __future__ import annotations

from typing import Any

DEFAULT_STAGE_BUDGETS: dict[str, int] = {
    "flow_structure": 3000,
    "module_structure": 2500,
    "entities": 2000,
    "test_areas": 2000,
}

DEFAULT_TOTAL_CAP = 8000


def parse_llm_budgets(discover_config: dict[str, Any] | None) -> dict[str, int]:
    """Merge discoverConfig.llm_budgets with defaults."""
    raw = (discover_config or {}).get("llm_budgets") or {}
    budgets = dict(DEFAULT_STAGE_BUDGETS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key == "total_cap":
                continue
            try:
                budgets[str(key)] = max(0, int(value))
            except (TypeError, ValueError):
                continue
    total_raw = (raw.get("total_cap") if isinstance(raw, dict) else None) or (
        (discover_config or {}).get("max_llm_tokens")
    )
    try:
        budgets["total_cap"] = max(0, int(total_raw)) if total_raw is not None else DEFAULT_TOTAL_CAP
    except (TypeError, ValueError):
        budgets["total_cap"] = DEFAULT_TOTAL_CAP
    return budgets


class LlmBudgetTracker:
    """Track per-stage and total token usage during a discovery pipeline run."""

    def __init__(self, budgets: dict[str, int] | None = None) -> None:
        self._budgets = dict(budgets or parse_llm_budgets(None))
        self._used_by_stage: dict[str, int] = {}
        self._total_used = 0

    @classmethod
    def from_discover_config(cls, discover_config: dict[str, Any] | None) -> LlmBudgetTracker:
        return cls(parse_llm_budgets(discover_config))

    @property
    def total_cap(self) -> int:
        return int(self._budgets.get("total_cap", DEFAULT_TOTAL_CAP))

    def remaining_for_stage(self, stage: str) -> int:
        stage_cap = int(self._budgets.get(stage, 0))
        stage_used = self._used_by_stage.get(stage, 0)
        total_remaining = max(0, self.total_cap - self._total_used)
        return max(0, min(stage_cap - stage_used, total_remaining))

    def can_run_stage(self, stage: str) -> bool:
        return self.remaining_for_stage(stage) > 0

    def record_usage(self, stage: str, tokens: int) -> None:
        if tokens <= 0:
            return
        self._used_by_stage[stage] = self._used_by_stage.get(stage, 0) + tokens
        self._total_used += tokens

    def usage_snapshot(self) -> dict[str, Any]:
        stages: dict[str, dict[str, int]] = {}
        for stage, cap in self._budgets.items():
            if stage == "total_cap":
                continue
            used = self._used_by_stage.get(stage, 0)
            stages[stage] = {"used": used, "cap": int(cap)}
        return {
            "stages": stages,
            "total_used": self._total_used,
            "total_cap": self.total_cap,
        }
