"""Discovery worker data types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


from aqa_discovery.api_types import ApiEndpointSnapshot, InteractionEventSnapshot, NetworkEventSnapshot


class FormSnapshot(BaseModel):
    form_key: str
    name: str
    action: str | None = None
    method: str = "get"
    attributes: dict[str, Any] = Field(default_factory=dict)
    field_xpaths: list[str] = Field(default_factory=list)


class ElementSnapshot(BaseModel):
    tag_name: str
    role: str | None = None
    text_content: str | None = None
    semantic_selector: str | None = None
    xpath_fallback: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    interaction_key: str | None = None
    is_visible: bool = True


class InteractionAction(BaseModel):
    action_type: Literal["click", "select", "hover", "fill"] = "click"
    interaction_key: str
    semantic_selector: str | None = None
    xpath_fallback: str | None = None
    role: str | None = None
    text_content: str | None = None
    value: str | None = None


class DiscoveredUrl(BaseModel):
    url: str
    discovered_via: Literal["link", "interaction"] = "interaction"
    source_page_url: str
    source_state_key: str | None = None
    trigger_interaction: InteractionAction | None = None


class SpaRouteEvent(BaseModel):
    from_url: str = ""
    to_url: str
    title: str = ""
    timestamp_ms: float = 0
    discovery_method: str = "pushstate_listener"
    source_page_url: str | None = None


class UIStateSnapshot(BaseModel):
    state_key: str
    parent_state_key: str | None = None
    trigger_interaction: InteractionAction | None = None
    url: str
    title: str
    status: int = 0
    html_length: int = Field(default=0, ge=0)
    interaction_depth: int = Field(default=0, ge=0)
    elements: list[ElementSnapshot] = Field(default_factory=list)
    forms: list[FormSnapshot] = Field(default_factory=list)
    screenshot_path: str | None = None
    fingerprint: str | None = None


class StateTransition(BaseModel):
    from_state_key: str
    to_state_key: str
    action: InteractionAction


class PageSnapshot(BaseModel):
    url: str
    title: str
    status: int
    html_length: int = Field(ge=0)
    depth: int = Field(default=0, ge=0)
    elements: list[ElementSnapshot] = Field(default_factory=list)
    forms: list[FormSnapshot] = Field(default_factory=list)
    api_endpoints: list[ApiEndpointSnapshot] = Field(default_factory=list)
    screenshot_path: str | None = None
    states: list[UIStateSnapshot] = Field(default_factory=list)
    transitions: list[StateTransition] = Field(default_factory=list)
    discovered_urls: list[DiscoveredUrl] = Field(default_factory=list)
    har_entries: list[dict[str, Any]] = Field(default_factory=list)
    interaction_events: list[InteractionEventSnapshot] = Field(default_factory=list)
    network_events: list[NetworkEventSnapshot] = Field(default_factory=list)
    spa_route_events: list[SpaRouteEvent] = Field(default_factory=list)


class CrawlStats(BaseModel):
    pages_crawled: int = 0
    states_discovered: int = 0
    interactions_executed: int = 0
    skipped_off_domain: int = 0
    skipped_excluded: int = 0
    skipped_duplicate: int = 0
    skipped_safety: int = 0
    skipped_interaction_safety: int = 0
    skipped_duplicate_state: int = 0
    skipped_robots: int = 0
    max_pages: int = 0
    max_depth: int = 0


class CrawlResult(BaseModel):
    pages: list[PageSnapshot] = Field(default_factory=list)
    api_endpoints: list[ApiEndpointSnapshot] = Field(default_factory=list)
    har_entries: list[dict[str, Any]] = Field(default_factory=list)
    stats: CrawlStats = Field(default_factory=CrawlStats)
    halted: bool = False
    halt_reason: str | None = None
    halt_url: str | None = None
    authenticated: bool = False
    auth_signals: dict[str, Any] = Field(default_factory=dict)
    persona_visibility: dict[str, Any] = Field(default_factory=dict)
    spa_route_events: list[SpaRouteEvent] = Field(default_factory=list)


class CrawlHaltError(Exception):
    """Raised when crawl must stop (CAPTCHA, MFA, etc.) — SPEC §15.8–15.9."""

    def __init__(self, message: str, *, url: str | None = None, reason: str = "blocked") -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.reason = reason
