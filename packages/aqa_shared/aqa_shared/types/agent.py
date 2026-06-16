"""Agent context and result types for core AI agents."""

from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

CoreAgentId = Literal[
    "discovery",
    "test-design",
    "script-generation",
    "intelligence",
    "healing",
]

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class AgentContext(BaseModel):
    pipeline_run_id: str = Field(alias="pipelineRunId")
    application_id: str = Field(alias="applicationId")
    plugin_id: str = Field(alias="pluginId")
    mode: str
    token_budget_remaining: int = Field(alias="tokenBudgetRemaining")
    app_map: Any | None = Field(default=None, alias="appMap")
    prior_errors: list[str] | None = Field(default=None, alias="priorErrors")

    model_config = {"populate_by_name": True}


class AgentResult(BaseModel):
    output: Any
    tokens_used: int = Field(alias="tokensUsed")
    cost_estimate: float = Field(alias="costEstimate")
    validation_passed: bool = Field(alias="validationPassed")

    model_config = {"populate_by_name": True}


class CoreAgent(Protocol[TInput, TOutput]):
    id: CoreAgentId

    def run(self, input: TInput, ctx: AgentContext) -> AgentResult: ...
