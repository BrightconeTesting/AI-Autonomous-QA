"""Crawl scope settings (SPEC §15.1) + CIC Phase 1 settings."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

WaitUntil = Literal["domcontentloaded", "load", "networkidle"]
InteractionWaitStrategy = Literal["network_idle", "dom_stable", "fixed_ms"]
CicMode = Literal["fast", "full"]

# Defaults applied when enable_cic=true and cic_mode=fast (unless explicitly overridden).
_CIC_FAST_DEFAULTS: dict[str, object] = {
    "cic_mode": "fast",
    "interaction_wait_strategy": "fixed_ms",
    "interaction_wait_ms": 350,
    "max_states_per_url": 10,
    "max_interactions_per_url": 12,
    "max_interactions_per_state": 4,
    "max_interaction_depth": 4,
    "cic_in_page_only": True,
    "cic_dom_stable_rounds": 4,
    "cic_screenshot_all_states": False,
}


class CrawlSettings(BaseModel):
    max_depth: int = Field(default=5, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=500)
    allowed_domains: list[str] = Field(default_factory=list)
    excluded_urls: list[str] = Field(default_factory=list)
    page_timeout_ms: int = Field(default=30_000, ge=1000, le=120_000)
    respect_robots_txt: bool = True
    max_scroll_iterations: int = Field(default=10, ge=0, le=50)
    wait_until: WaitUntil = "domcontentloaded"
    wait_for_selector: str | None = None
    enable_cic: bool = False
    cic_mode: CicMode = "fast"
    max_states_per_url: int = Field(default=20, ge=1, le=100)
    max_states_total: int = Field(default=200, ge=1, le=2000)
    max_interactions_per_url: int = Field(default=50, ge=1, le=200)
    max_interactions_per_state: int = Field(default=5, ge=1, le=50)
    max_interaction_depth: int = Field(default=5, ge=1, le=10)
    interaction_wait_strategy: InteractionWaitStrategy = "fixed_ms"
    interaction_wait_ms: int = Field(default=350, ge=50, le=5000)
    cic_in_page_only: bool = True
    cic_dom_stable_rounds: int = Field(default=4, ge=2, le=10)
    cic_screenshot_all_states: bool = False
    safe_form_fill: bool = False
    cic_rich_interactions: bool = True
    cic_enable_iframes: bool = True
    cic_max_options_per_select: int = Field(default=3, ge=1, le=20)
    cic_enable_tables: bool = True
    cic_enable_date_pickers: bool = True
    cic_max_graph_paths_per_page: int = Field(default=5, ge=1, le=20)
    blocked_interaction_patterns: list[str] = Field(default_factory=list)
    headless: bool = True
    browser_channel: str | None = None
    user_agent: str | None = None
    locale: str | None = None
    viewport_width: int | None = Field(default=None, ge=320, le=3840)
    viewport_height: int | None = Field(default=None, ge=240, le=2160)

    @classmethod
    def from_crawl_config(
        cls,
        base_url: str,
        crawl_config: dict | None,
        *,
        overrides: dict | None = None,
    ) -> CrawlSettings:
        base = dict(crawl_config or {})
        over = dict(overrides or {})
        explicit_keys = set(base.keys()) | set(over.keys())

        config = {**base, **over}

        enable_cic = bool(config.get("enable_cic", False))
        cic_mode = config.get("cic_mode", "fast")
        if enable_cic and cic_mode == "fast":
            for key, value in _CIC_FAST_DEFAULTS.items():
                if key not in explicit_keys:
                    config[key] = value

        hostname = urlparse(base_url).hostname
        allowed = config.get("allowed_domains")
        if not allowed and hostname:
            allowed = [hostname.lower()]

        wait_until = config.get("wait_until", config.get("spa_wait_until", "domcontentloaded"))
        if wait_until not in ("domcontentloaded", "load", "networkidle"):
            wait_until = "domcontentloaded"

        interaction_wait = config.get("interaction_wait_strategy", "fixed_ms")
        if interaction_wait not in ("network_idle", "dom_stable", "fixed_ms"):
            interaction_wait = "fixed_ms"

        cic_mode_val = config.get("cic_mode", "fast")
        if cic_mode_val not in ("fast", "full"):
            cic_mode_val = "fast"

        return cls(
            max_depth=int(config.get("max_depth", 5)),
            max_pages=int(config.get("max_pages", 100)),
            allowed_domains=[d.lower() for d in (allowed or [])],
            excluded_urls=list(config.get("excluded_urls") or []),
            page_timeout_ms=int(config.get("page_timeout_ms", 30_000)),
            respect_robots_txt=bool(config.get("respect_robots_txt", True)),
            max_scroll_iterations=int(config.get("max_scroll_iterations", 10)),
            wait_until=wait_until,
            wait_for_selector=config.get("wait_for_selector"),
            enable_cic=enable_cic,
            cic_mode=cic_mode_val,
            max_states_per_url=int(config.get("max_states_per_url", 20)),
            max_states_total=int(config.get("max_states_total", 200)),
            max_interactions_per_url=int(config.get("max_interactions_per_url", 50)),
            max_interactions_per_state=int(config.get("max_interactions_per_state", 5)),
            max_interaction_depth=int(config.get("max_interaction_depth", 5)),
            interaction_wait_strategy=interaction_wait,
            interaction_wait_ms=int(config.get("interaction_wait_ms", 350)),
            cic_in_page_only=bool(config.get("cic_in_page_only", True)),
            cic_dom_stable_rounds=int(config.get("cic_dom_stable_rounds", 4)),
            cic_screenshot_all_states=bool(config.get("cic_screenshot_all_states", False)),
            safe_form_fill=bool(config.get("safe_form_fill", False)),
            cic_rich_interactions=bool(config.get("cic_rich_interactions", True)),
            cic_enable_iframes=bool(config.get("cic_enable_iframes", True)),
            cic_max_options_per_select=int(config.get("cic_max_options_per_select", 3)),
            cic_enable_tables=bool(config.get("cic_enable_tables", True)),
            cic_enable_date_pickers=bool(config.get("cic_enable_date_pickers", True)),
            cic_max_graph_paths_per_page=int(config.get("cic_max_graph_paths_per_page", 5)),
            blocked_interaction_patterns=list(config.get("blocked_interaction_patterns") or []),
            headless=bool(config.get("headless", True)),
            browser_channel=config.get("browser_channel"),
            user_agent=config.get("user_agent"),
            locale=config.get("locale"),
            viewport_width=config.get("viewport_width"),
            viewport_height=config.get("viewport_height"),
        )
