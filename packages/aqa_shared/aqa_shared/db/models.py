"""SQLAlchemy ORM models — Phase 1 data model (SPEC §14.2)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aqa_shared.db.base import Base


class FlowSource(str, enum.Enum):
    crawler = "crawler"
    llm = "llm"
    manual = "manual"


class TestPriority(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TestCaseStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    archived = "archived"


class TestRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"
    error = "error"
    flaky = "flaky"


class ResultOutcome(str, enum.Enum):
    passed = "passed"
    failed = "failed"
    skipped = "skipped"


class PipelineStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class PipelineStage(str, enum.Enum):
    discover = "discover"
    generate_tests = "generate_tests"
    generate_scripts = "generate_scripts"
    execute = "execute"
    report = "report"
    complete = "complete"


class ArtifactType(str, enum.Enum):
    screenshot = "screenshot"
    trace = "trace"
    video = "video"
    report = "report"
    appmap = "appmap"
    generated_script = "generated_script"


class CredentialAuditAction(str, enum.Enum):
    read = "read"
    decrypt = "decrypt"
    inject = "inject"


class Application(Base):
    __tablename__ = "applications"

    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    base_url: Mapped[str] = mapped_column("base_url", Text)
    seed_urls: Mapped[Any] = mapped_column("seed_urls", JSONB, server_default="[]")
    auth_config: Mapped[Any] = mapped_column("auth_config", JSONB, server_default="{}")
    crawl_config: Mapped[Any] = mapped_column("crawl_config", JSONB, server_default="{}")
    last_crawl_at: Mapped[datetime | None] = mapped_column("last_crawl_at", DateTime(timezone=False))
    last_run_at: Mapped[datetime | None] = mapped_column("last_run_at", DateTime(timezone=False))
    overall_health_score: Mapped[Decimal | None] = mapped_column(
        "overall_health_score", Numeric(5, 4)
    )
    config_version: Mapped[int] = mapped_column("config_version", Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=False), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    pages: Mapped[list[Page]] = relationship(back_populates="application", passive_deletes=True)
    forms: Mapped[list["Form"]] = relationship(back_populates="application", passive_deletes=True)
    api_endpoints: Mapped[list["ApiEndpoint"]] = relationship(
        back_populates="application", passive_deletes=True
    )
    api_ui_mappings: Mapped[list["ApiUiMapping"]] = relationship(
        back_populates="application", passive_deletes=True
    )
    flows: Mapped[list[Flow]] = relationship(back_populates="application", passive_deletes=True)
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="application", passive_deletes=True)
    test_runs: Mapped[list[TestRun]] = relationship(back_populates="application", passive_deletes=True)
    pipeline_runs: Mapped[list[PipelineRun]] = relationship(
        back_populates="application", passive_deletes=True
    )
    credential_audits: Mapped[list[CredentialAccessAudit]] = relationship(
        back_populates="application", passive_deletes=True
    )

    __table_args__ = (
        Index("idx_applications_name", "name"),
        Index("idx_applications_last_run_at", last_run_at.desc()),
        Index("idx_applications_health_score", overall_health_score.desc()),
    )


class Page(Base):
    __tablename__ = "pages"

    page_id: Mapped[uuid.UUID] = mapped_column(
        "page_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(512))
    screenshot_path: Mapped[str | None] = mapped_column("screenshot_path", Text)
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="pages")
    elements: Mapped[list[Element]] = relationship(back_populates="page")
    states: Mapped[list[PageState]] = relationship(back_populates="page")
    forms: Mapped[list["Form"]] = relationship(back_populates="page")

    __table_args__ = (
        UniqueConstraint("app_id", "url", name="idx_pages_app_url"),
        Index("idx_pages_app_id", "app_id"),
        Index("idx_pages_discovered_at", "app_id", discovered_at.desc()),
    )


class PageState(Base):
    __tablename__ = "page_states"

    state_id: Mapped[uuid.UUID] = mapped_column(
        "state_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        "page_id", UUID(as_uuid=True), ForeignKey("pages.page_id", ondelete="CASCADE")
    )
    state_key: Mapped[str] = mapped_column("state_key", String(64))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(512))
    screenshot_path: Mapped[str | None] = mapped_column("screenshot_path", Text)
    interaction_depth: Mapped[int] = mapped_column("interaction_depth", Integer, server_default="0")
    parent_state_key: Mapped[str | None] = mapped_column("parent_state_key", String(64))
    trigger_action: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    page: Mapped[Page] = relationship(back_populates="states")
    elements: Mapped[list[Element]] = relationship(back_populates="state")
    forms: Mapped[list["Form"]] = relationship(back_populates="state")

    __table_args__ = (
        UniqueConstraint("page_id", "state_key", name="page_states_page_id_state_key_key"),
        Index("idx_page_states_page_id", "page_id"),
    )


class StateTransition(Base):
    __tablename__ = "state_transitions"

    transition_id: Mapped[uuid.UUID] = mapped_column(
        "transition_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    from_state_id: Mapped[uuid.UUID] = mapped_column(
        "from_state_id", UUID(as_uuid=True), ForeignKey("page_states.state_id", ondelete="CASCADE")
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(
        "to_state_id", UUID(as_uuid=True), ForeignKey("page_states.state_id", ondelete="CASCADE")
    )
    action: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_state_transitions_app_id", "app_id"),
        Index("idx_state_transitions_from_state", "from_state_id"),
        Index("idx_state_transitions_to_state", "to_state_id"),
    )


class PageDiscovery(Base):
    __tablename__ = "page_discoveries"

    discovery_id: Mapped[uuid.UUID] = mapped_column(
        "discovery_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text)
    discovered_via: Mapped[str] = mapped_column("discovered_via", String(32), server_default="link")
    source_page_id: Mapped[uuid.UUID | None] = mapped_column(
        "source_page_id", UUID(as_uuid=True), ForeignKey("pages.page_id", ondelete="SET NULL")
    )
    source_state_key: Mapped[str | None] = mapped_column("source_state_key", String(64))
    trigger_action: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("app_id", "url", name="page_discoveries_app_id_url_key"),
        Index("idx_page_discoveries_app_id", "app_id"),
    )


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        "endpoint_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    method: Mapped[str] = mapped_column("method", String(16))
    path: Mapped[str] = mapped_column(Text)
    path_pattern: Mapped[str] = mapped_column("path_pattern", Text)
    source: Mapped[str] = mapped_column("source", String(16), server_default="network")
    request_schema: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    response_schema: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    first_seen_page_id: Mapped[uuid.UUID | None] = mapped_column(
        "first_seen_page_id", UUID(as_uuid=True), ForeignKey("pages.page_id", ondelete="SET NULL")
    )
    seen_page_ids: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    seen_count: Mapped[int] = mapped_column("seen_count", Integer, server_default="1")
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="api_endpoints")

    __table_args__ = (
        UniqueConstraint("app_id", "method", "path_pattern", name="api_endpoints_app_method_pattern_key"),
        Index("idx_api_endpoints_app_id", "app_id"),
    )


class ApiUiMapping(Base):
    __tablename__ = "api_ui_mappings"

    mapping_id: Mapped[uuid.UUID] = mapped_column(
        "mapping_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    api_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        "api_endpoint_id", UUID(as_uuid=True), ForeignKey("api_endpoints.endpoint_id", ondelete="CASCADE")
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        "page_id", UUID(as_uuid=True), ForeignKey("pages.page_id", ondelete="CASCADE")
    )
    form_id: Mapped[uuid.UUID | None] = mapped_column(
        "form_id", UUID(as_uuid=True), ForeignKey("forms.form_id", ondelete="SET NULL")
    )
    element_id: Mapped[uuid.UUID | None] = mapped_column(
        "element_id", UUID(as_uuid=True), ForeignKey("elements.element_id", ondelete="SET NULL")
    )
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        "flow_id", UUID(as_uuid=True), ForeignKey("flows.flow_id", ondelete="SET NULL")
    )
    trigger_action: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    confidence: Mapped[float] = mapped_column("confidence", Numeric(4, 3), server_default="0")
    correlation_method: Mapped[str] = mapped_column("correlation_method", String(32), server_default="heuristic")
    review_required: Mapped[bool] = mapped_column("review_required", Boolean, server_default="false")
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="api_ui_mappings")

    __table_args__ = (
        Index("idx_api_ui_mappings_app_id", "app_id"),
        Index("idx_api_ui_mappings_endpoint_id", "api_endpoint_id"),
        Index("idx_api_ui_mappings_page_id", "page_id"),
    )


class Form(Base):
    __tablename__ = "forms"

    form_id: Mapped[uuid.UUID] = mapped_column(
        "form_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        "page_id", UUID(as_uuid=True), ForeignKey("pages.page_id", ondelete="CASCADE")
    )
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        "state_id", UUID(as_uuid=True), ForeignKey("page_states.state_id", ondelete="CASCADE")
    )
    action: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column("method", String(16), server_default="get")
    attributes: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    field_element_ids: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    discovered_at: Mapped[datetime] = mapped_column(
        "discovered_at", DateTime(timezone=False), server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="forms")
    page: Mapped[Page] = relationship(back_populates="forms")
    state: Mapped[PageState | None] = relationship(back_populates="forms")

    __table_args__ = (
        Index("idx_forms_app_id", "app_id"),
        Index("idx_forms_page_id", "page_id"),
        Index("idx_forms_state_id", "state_id"),
    )


class Element(Base):
    __tablename__ = "elements"

    element_id: Mapped[uuid.UUID] = mapped_column(
        "element_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        "page_id", UUID(as_uuid=True), ForeignKey("pages.page_id", ondelete="CASCADE")
    )
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        "state_id", UUID(as_uuid=True), ForeignKey("page_states.state_id", ondelete="CASCADE")
    )
    tag_name: Mapped[str] = mapped_column("tag_name", String(64))
    role: Mapped[str | None] = mapped_column(String(64))
    text_content: Mapped[str | None] = mapped_column("text_content", Text)
    semantic_selector: Mapped[str | None] = mapped_column("semantic_selector", Text)
    xpath_fallback: Mapped[str | None] = mapped_column("xpath_fallback", Text)
    attributes: Mapped[Any] = mapped_column(JSONB, server_default="{}")

    page: Mapped[Page] = relationship(back_populates="elements")
    state: Mapped[PageState | None] = relationship(back_populates="elements")

    __table_args__ = (
        Index("idx_elements_page_id", "page_id"),
        Index("idx_elements_state_id", "state_id"),
    )


class Flow(Base):
    __tablename__ = "flows"

    flow_id: Mapped[uuid.UUID] = mapped_column(
        "flow_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    source: Mapped[FlowSource]

    application: Mapped[Application] = relationship(back_populates="flows")
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="flow")

    __table_args__ = (
        Index("idx_flows_app_id", "app_id"),
        Index("idx_flows_source", "app_id", "source"),
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    testcase_id: Mapped[uuid.UUID] = mapped_column(
        "testcase_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    flow_id: Mapped[uuid.UUID | None] = mapped_column(
        "flow_id", UUID(as_uuid=True), ForeignKey("flows.flow_id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    priority: Mapped[TestPriority]
    status: Mapped[TestCaseStatus] = mapped_column(server_default="draft")
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        "pipeline_run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )

    application: Mapped[Application] = relationship(back_populates="test_cases")
    flow: Mapped[Flow | None] = relationship(back_populates="test_cases")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="test_cases")
    test_scripts: Mapped[list[TestScript]] = relationship(back_populates="test_case")

    __table_args__ = (
        Index("idx_test_cases_app_id", "app_id"),
        Index("idx_test_cases_status", "app_id", "status"),
        Index("idx_test_cases_priority", "app_id", "priority"),
    )


class TestScript(Base):
    __tablename__ = "test_scripts"

    script_id: Mapped[uuid.UUID] = mapped_column(
        "script_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    testcase_id: Mapped[uuid.UUID] = mapped_column(
        "testcase_id", UUID(as_uuid=True), ForeignKey("test_cases.testcase_id", ondelete="CASCADE")
    )
    language: Mapped[str] = mapped_column(String(32), server_default="typescript")
    framework: Mapped[str] = mapped_column(String(32), server_default="playwright")
    code: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    validated_at: Mapped[datetime | None] = mapped_column("validated_at", DateTime(timezone=False))

    test_case: Mapped[TestCase] = relationship(back_populates="test_scripts")
    results: Mapped[list[Result]] = relationship(back_populates="test_script")

    __table_args__ = (
        UniqueConstraint("testcase_id", "version", name="idx_test_scripts_version"),
        Index("idx_test_scripts_testcase", "testcase_id"),
        Index("idx_test_scripts_validated", "testcase_id", validated_at.desc()),
    )


class TestRun(Base):
    __tablename__ = "test_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        "run_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        "pipeline_run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    status: Mapped[TestRunStatus] = mapped_column(server_default="pending")
    started_at: Mapped[datetime | None] = mapped_column("started_at", DateTime(timezone=False))
    ended_at: Mapped[datetime | None] = mapped_column("ended_at", DateTime(timezone=False))
    summary: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    is_flaky: Mapped[bool] = mapped_column("is_flaky", Boolean, server_default="false")

    application: Mapped[Application] = relationship(back_populates="test_runs")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="test_runs")
    results: Mapped[list[Result]] = relationship(back_populates="test_run")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="test_run")

    __table_args__ = (
        Index("idx_test_runs_app_id", "app_id", started_at.desc()),
        Index("idx_test_runs_pipeline", "pipeline_run_id"),
        Index("idx_test_runs_status", "app_id", "status"),
    )


class Result(Base):
    __tablename__ = "results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        "result_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        "run_id", UUID(as_uuid=True), ForeignKey("test_runs.run_id", ondelete="CASCADE")
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        "script_id", UUID(as_uuid=True), ForeignKey("test_scripts.script_id", ondelete="CASCADE")
    )
    assertion: Mapped[str] = mapped_column(Text)
    outcome: Mapped[ResultOutcome]
    error_msg: Mapped[str | None] = mapped_column("error_msg", Text)
    artifact_ids: Mapped[Any] = mapped_column("artifact_ids", JSONB, server_default="[]")

    test_run: Mapped[TestRun] = relationship(back_populates="results")
    test_script: Mapped[TestScript] = relationship(back_populates="results")

    __table_args__ = (
        Index("idx_results_run_id", "run_id"),
        Index("idx_results_script", "script_id"),
        Index("idx_results_outcome", "run_id", "outcome"),
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        "application_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    status: Mapped[PipelineStatus] = mapped_column(server_default="pending")
    current_stage: Mapped[PipelineStage] = mapped_column(
        "current_stage", server_default="discover"
    )
    config: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column("started_at", DateTime(timezone=False))
    ended_at: Mapped[datetime | None] = mapped_column("ended_at", DateTime(timezone=False))
    llm_tokens_used: Mapped[int] = mapped_column("llm_tokens_used", Integer, server_default="0")
    cost_estimate: Mapped[Decimal] = mapped_column(
        "cost_estimate", Numeric(10, 4), server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column("error_message", Text)

    application: Mapped[Application] = relationship(back_populates="pipeline_runs")
    test_cases: Mapped[list[TestCase]] = relationship(back_populates="pipeline_run")
    test_runs: Mapped[list[TestRun]] = relationship(back_populates="pipeline_run")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="pipeline_run")
    credential_audits: Mapped[list[CredentialAccessAudit]] = relationship(
        back_populates="pipeline_run"
    )

    __table_args__ = (
        Index("idx_pipeline_runs_app", "application_id", started_at.desc()),
        Index("idx_pipeline_runs_status", "status"),
        Index("idx_pipeline_runs_stage", "current_stage", "status"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        "run_id", UUID(as_uuid=True), ForeignKey("test_runs.run_id", ondelete="SET NULL")
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        "pipeline_run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    type: Mapped[ArtifactType]
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column("size_bytes", BigInteger, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=False), server_default=func.now()
    )

    test_run: Mapped[TestRun | None] = relationship(back_populates="artifacts")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="artifacts")

    __table_args__ = (Index("idx_artifacts_type", "type", created_at.desc()),)


class CredentialAccessAudit(Base):
    __tablename__ = "credential_access_audit"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        "audit_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        "app_id", UUID(as_uuid=True), ForeignKey("applications.app_id", ondelete="CASCADE")
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        "pipeline_run_id", UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    accessor: Mapped[str] = mapped_column(String(128))
    action: Mapped[CredentialAuditAction]
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="credential_audits")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="credential_audits")

    __table_args__ = (
        Index("idx_credential_audit_app", "app_id", timestamp.desc()),
        Index("idx_credential_audit_pipeline", "pipeline_run_id"),
    )
