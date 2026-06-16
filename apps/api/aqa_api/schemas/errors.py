"""RFC 7807 Problem Details for HTTP APIs (SPEC §16.1)."""

from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    field: str
    message: str


class ProblemDetail(BaseModel):
    type: str = "https://autonomous-qa.dev/errors/validation"
    title: str
    status: int
    detail: str
    instance: str | None = None
    errors: list[FieldError] = Field(default_factory=list)
    active_pipeline_run_id: str | None = None

    def to_response_body(self) -> dict[str, Any]:
        body = self.model_dump(exclude_none=True)
        if not body.get("errors"):
            body.pop("errors", None)
        return body
