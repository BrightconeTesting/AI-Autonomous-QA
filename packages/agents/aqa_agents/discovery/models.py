"""Discovery agent I/O models."""

from typing import Any

from pydantic import BaseModel, Field


class DiscoveryInput(BaseModel):
    base_url: str = Field(default="https://example.com")
    seed_urls: list[str] = Field(default_factory=list)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    crawl_config: dict[str, Any] = Field(default_factory=dict)


class DiscoveryOutput(BaseModel):
    pages: list[dict[str, Any]] = Field(default_factory=list)
    flows: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
