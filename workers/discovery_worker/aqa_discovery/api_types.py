"""Network API observation types (DISCOVERY-AGENT-VISION-SPEC §8.3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ApiEndpointSource = Literal["network", "openapi", "both"]


class ApiEndpointSnapshot(BaseModel):
    method: str
    path: str
    path_pattern: str
    url: str | None = None
    resource_type: str | None = None
    status: int | None = None
    request_headers: dict[str, str] = Field(default_factory=dict)
    body_hash: str | None = None
    body_keys: list[str] = Field(default_factory=list)
    source: ApiEndpointSource = "network"
    request_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    seen_count: int = 1


class NetworkEventSnapshot(BaseModel):
    method: str
    path: str
    path_pattern: str
    url: str
    timestamp_ms: float = 0.0
    body_keys: list[str] = Field(default_factory=list)
    resource_type: str | None = None


class InteractionEventSnapshot(BaseModel):
    timestamp_ms: float = 0.0
    interaction_key: str
    action_type: str = "click"
    semantic_selector: str | None = None
    text_content: str | None = None
    form_key: str | None = None
    element_id: str | None = None
    trigger_action: dict[str, Any] = Field(default_factory=dict)


class ApiUiMappingSnapshot(BaseModel):
    api_endpoint_key: str
    page_url: str
    form_key: str | None = None
    element_id: str | None = None
    trigger_action: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    correlation_method: str = "heuristic"
    review_required: bool = False
    method: str | None = None
    path_pattern: str | None = None
