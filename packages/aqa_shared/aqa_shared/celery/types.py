"""Celery task payload and result types."""

from pydantic import BaseModel, Field


class CeleryTaskPayload(BaseModel):
    pipeline_run_id: str = Field(alias="pipelineRunId")
    application_id: str = Field(alias="applicationId")
    plugin_id: str | None = Field(default=None, alias="pluginId")
    mode: str | None = None
    crawl_config_overrides: dict | None = Field(default=None, alias="crawlConfigOverrides")
    discover_config: dict | None = Field(default=None, alias="discoverConfig")
    generate_config: dict | None = Field(default=None, alias="generateConfig")
    execute_config: dict | None = Field(default=None, alias="executeConfig")

    model_config = {"populate_by_name": True}

    def to_worker_dict(self) -> dict:
        """Dict shape expected by Python Celery tasks."""
        data: dict = {
            "pipelineRunId": self.pipeline_run_id,
            "applicationId": self.application_id,
        }
        if self.plugin_id is not None:
            data["pluginId"] = self.plugin_id
        if self.mode is not None:
            data["mode"] = self.mode
        if self.crawl_config_overrides is not None:
            data["crawlConfigOverrides"] = self.crawl_config_overrides
        if self.discover_config is not None:
            data["discoverConfig"] = self.discover_config
        if self.generate_config is not None:
            data["generateConfig"] = self.generate_config
        if self.execute_config is not None:
            data["executeConfig"] = self.execute_config
        return data


class CeleryTaskResult(BaseModel):
    ok: bool
    pipeline_run_id: str = Field(alias="pipelineRunId")

    model_config = {"populate_by_name": True}
