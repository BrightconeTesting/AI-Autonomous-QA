"""Pipeline stage and status enums (mirrors PostgreSQL enums)."""

import enum


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
