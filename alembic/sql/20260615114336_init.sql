-- CreateEnum
CREATE TYPE "FlowSource" AS ENUM ('crawler', 'llm', 'manual');

-- CreateEnum
CREATE TYPE "TestPriority" AS ENUM ('critical', 'high', 'medium', 'low');

-- CreateEnum
CREATE TYPE "TestCaseStatus" AS ENUM ('draft', 'approved', 'archived');

-- CreateEnum
CREATE TYPE "TestRunStatus" AS ENUM ('pending', 'running', 'passed', 'failed', 'error', 'flaky');

-- CreateEnum
CREATE TYPE "ResultOutcome" AS ENUM ('passed', 'failed', 'skipped');

-- CreateEnum
CREATE TYPE "PipelineStatus" AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');

-- CreateEnum
CREATE TYPE "PipelineStage" AS ENUM ('discover', 'generate_tests', 'generate_scripts', 'execute', 'report', 'complete');

-- CreateEnum
CREATE TYPE "ArtifactType" AS ENUM ('screenshot', 'trace', 'video', 'report', 'appmap', 'generated_script');

-- CreateEnum
CREATE TYPE "CredentialAuditAction" AS ENUM ('read', 'decrypt', 'inject');

-- CreateTable
CREATE TABLE "applications" (
    "app_id" UUID NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "base_url" TEXT NOT NULL,
    "seed_urls" JSONB NOT NULL DEFAULT '[]',
    "auth_config" JSONB NOT NULL DEFAULT '{}',
    "crawl_config" JSONB NOT NULL DEFAULT '{}',
    "last_crawl_at" TIMESTAMP(3),
    "last_run_at" TIMESTAMP(3),
    "overall_health_score" DECIMAL(5,4),
    "config_version" INTEGER NOT NULL DEFAULT 1,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "applications_pkey" PRIMARY KEY ("app_id")
);

-- CreateTable
CREATE TABLE "pages" (
    "page_id" UUID NOT NULL,
    "app_id" UUID NOT NULL,
    "url" TEXT NOT NULL,
    "title" VARCHAR(512),
    "screenshot_path" TEXT,
    "discovered_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "pages_pkey" PRIMARY KEY ("page_id")
);

-- CreateTable
CREATE TABLE "elements" (
    "element_id" UUID NOT NULL,
    "page_id" UUID NOT NULL,
    "tag_name" VARCHAR(64) NOT NULL,
    "role" VARCHAR(64),
    "text_content" TEXT,
    "semantic_selector" TEXT,
    "xpath_fallback" TEXT,
    "attributes" JSONB NOT NULL DEFAULT '{}',

    CONSTRAINT "elements_pkey" PRIMARY KEY ("element_id")
);

-- CreateTable
CREATE TABLE "flows" (
    "flow_id" UUID NOT NULL,
    "app_id" UUID NOT NULL,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "sequence" JSONB NOT NULL DEFAULT '[]',
    "source" "FlowSource" NOT NULL,

    CONSTRAINT "flows_pkey" PRIMARY KEY ("flow_id")
);

-- CreateTable
CREATE TABLE "test_cases" (
    "testcase_id" UUID NOT NULL,
    "app_id" UUID NOT NULL,
    "flow_id" UUID,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "steps" JSONB NOT NULL DEFAULT '[]',
    "priority" "TestPriority" NOT NULL,
    "status" "TestCaseStatus" NOT NULL DEFAULT 'draft',
    "pipeline_run_id" UUID,

    CONSTRAINT "test_cases_pkey" PRIMARY KEY ("testcase_id")
);

-- CreateTable
CREATE TABLE "test_scripts" (
    "script_id" UUID NOT NULL,
    "testcase_id" UUID NOT NULL,
    "language" VARCHAR(32) NOT NULL DEFAULT 'typescript',
    "framework" VARCHAR(32) NOT NULL DEFAULT 'playwright',
    "code" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "validated_at" TIMESTAMP(3),

    CONSTRAINT "test_scripts_pkey" PRIMARY KEY ("script_id")
);

-- CreateTable
CREATE TABLE "test_runs" (
    "run_id" UUID NOT NULL,
    "app_id" UUID NOT NULL,
    "pipeline_run_id" UUID,
    "status" "TestRunStatus" NOT NULL DEFAULT 'pending',
    "started_at" TIMESTAMP(3),
    "ended_at" TIMESTAMP(3),
    "summary" JSONB NOT NULL DEFAULT '{}',
    "is_flaky" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "test_runs_pkey" PRIMARY KEY ("run_id")
);

-- CreateTable
CREATE TABLE "results" (
    "result_id" UUID NOT NULL,
    "run_id" UUID NOT NULL,
    "script_id" UUID NOT NULL,
    "assertion" TEXT NOT NULL,
    "outcome" "ResultOutcome" NOT NULL,
    "error_msg" TEXT,
    "artifact_ids" JSONB NOT NULL DEFAULT '[]',

    CONSTRAINT "results_pkey" PRIMARY KEY ("result_id")
);

-- CreateTable
CREATE TABLE "pipeline_runs" (
    "id" UUID NOT NULL,
    "application_id" UUID NOT NULL,
    "status" "PipelineStatus" NOT NULL DEFAULT 'pending',
    "current_stage" "PipelineStage" NOT NULL DEFAULT 'discover',
    "config" JSONB NOT NULL DEFAULT '{}',
    "started_at" TIMESTAMP(3),
    "ended_at" TIMESTAMP(3),
    "llm_tokens_used" INTEGER NOT NULL DEFAULT 0,
    "cost_estimate" DECIMAL(10,4) NOT NULL DEFAULT 0,
    "error_message" TEXT,

    CONSTRAINT "pipeline_runs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "artifacts" (
    "id" UUID NOT NULL,
    "run_id" UUID,
    "pipeline_run_id" UUID,
    "type" "ArtifactType" NOT NULL,
    "path" TEXT NOT NULL,
    "size_bytes" BIGINT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "artifacts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "credential_access_audit" (
    "audit_id" UUID NOT NULL,
    "app_id" UUID NOT NULL,
    "pipeline_run_id" UUID,
    "accessor" VARCHAR(128) NOT NULL,
    "action" "CredentialAuditAction" NOT NULL,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "credential_access_audit_pkey" PRIMARY KEY ("audit_id")
);

-- CreateIndex
CREATE INDEX "idx_applications_name" ON "applications"("name");

-- CreateIndex
CREATE INDEX "idx_applications_last_run_at" ON "applications"("last_run_at" DESC);

-- CreateIndex
CREATE INDEX "idx_applications_health_score" ON "applications"("overall_health_score" DESC);

-- CreateIndex
CREATE INDEX "idx_pages_app_id" ON "pages"("app_id");

-- CreateIndex
CREATE INDEX "idx_pages_discovered_at" ON "pages"("app_id", "discovered_at" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "idx_pages_app_url" ON "pages"("app_id", "url");

-- CreateIndex
CREATE INDEX "idx_elements_page_id" ON "elements"("page_id");

-- CreateIndex
CREATE INDEX "idx_flows_app_id" ON "flows"("app_id");

-- CreateIndex
CREATE INDEX "idx_flows_source" ON "flows"("app_id", "source");

-- CreateIndex
CREATE INDEX "idx_test_cases_app_id" ON "test_cases"("app_id");

-- CreateIndex
CREATE INDEX "idx_test_cases_status" ON "test_cases"("app_id", "status");

-- CreateIndex
CREATE INDEX "idx_test_cases_priority" ON "test_cases"("app_id", "priority");

-- CreateIndex
CREATE INDEX "idx_test_scripts_testcase" ON "test_scripts"("testcase_id");

-- CreateIndex
CREATE INDEX "idx_test_scripts_validated" ON "test_scripts"("testcase_id", "validated_at" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "idx_test_scripts_version" ON "test_scripts"("testcase_id", "version");

-- CreateIndex
CREATE INDEX "idx_test_runs_app_id" ON "test_runs"("app_id", "started_at" DESC);

-- CreateIndex
CREATE INDEX "idx_test_runs_pipeline" ON "test_runs"("pipeline_run_id");

-- CreateIndex
CREATE INDEX "idx_test_runs_status" ON "test_runs"("app_id", "status");

-- CreateIndex
CREATE INDEX "idx_results_run_id" ON "results"("run_id");

-- CreateIndex
CREATE INDEX "idx_results_script" ON "results"("script_id");

-- CreateIndex
CREATE INDEX "idx_results_outcome" ON "results"("run_id", "outcome");

-- CreateIndex
CREATE INDEX "idx_pipeline_runs_app" ON "pipeline_runs"("application_id", "started_at" DESC);

-- CreateIndex
CREATE INDEX "idx_pipeline_runs_status" ON "pipeline_runs"("status");

-- CreateIndex
CREATE INDEX "idx_pipeline_runs_stage" ON "pipeline_runs"("current_stage", "status");

-- CreateIndex
CREATE INDEX "idx_artifacts_type" ON "artifacts"("type", "created_at" DESC);

-- CreateIndex
CREATE INDEX "idx_credential_audit_app" ON "credential_access_audit"("app_id", "timestamp" DESC);

-- CreateIndex
CREATE INDEX "idx_credential_audit_pipeline" ON "credential_access_audit"("pipeline_run_id");

-- AddForeignKey
ALTER TABLE "pages" ADD CONSTRAINT "pages_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "elements" ADD CONSTRAINT "elements_page_id_fkey" FOREIGN KEY ("page_id") REFERENCES "pages"("page_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "flows" ADD CONSTRAINT "flows_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "test_cases" ADD CONSTRAINT "test_cases_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "test_cases" ADD CONSTRAINT "test_cases_flow_id_fkey" FOREIGN KEY ("flow_id") REFERENCES "flows"("flow_id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "test_cases" ADD CONSTRAINT "test_cases_pipeline_run_id_fkey" FOREIGN KEY ("pipeline_run_id") REFERENCES "pipeline_runs"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "test_scripts" ADD CONSTRAINT "test_scripts_testcase_id_fkey" FOREIGN KEY ("testcase_id") REFERENCES "test_cases"("testcase_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "test_runs" ADD CONSTRAINT "test_runs_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "test_runs" ADD CONSTRAINT "test_runs_pipeline_run_id_fkey" FOREIGN KEY ("pipeline_run_id") REFERENCES "pipeline_runs"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "results" ADD CONSTRAINT "results_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "test_runs"("run_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "results" ADD CONSTRAINT "results_script_id_fkey" FOREIGN KEY ("script_id") REFERENCES "test_scripts"("script_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "pipeline_runs" ADD CONSTRAINT "pipeline_runs_application_id_fkey" FOREIGN KEY ("application_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "artifacts" ADD CONSTRAINT "artifacts_run_id_fkey" FOREIGN KEY ("run_id") REFERENCES "test_runs"("run_id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "artifacts" ADD CONSTRAINT "artifacts_pipeline_run_id_fkey" FOREIGN KEY ("pipeline_run_id") REFERENCES "pipeline_runs"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "credential_access_audit" ADD CONSTRAINT "credential_access_audit_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "credential_access_audit" ADD CONSTRAINT "credential_access_audit_pipeline_run_id_fkey" FOREIGN KEY ("pipeline_run_id") REFERENCES "pipeline_runs"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- Partial and supplemental indexes (SPEC §34 — not expressible in Prisma schema DSL)
CREATE INDEX idx_pipeline_runs_active ON pipeline_runs (application_id, status)
  WHERE status IN ('pending', 'running');

CREATE INDEX idx_test_cases_pipeline ON test_cases (pipeline_run_id)
  WHERE pipeline_run_id IS NOT NULL;

CREATE INDEX idx_test_runs_flaky ON test_runs (app_id, is_flaky)
  WHERE is_flaky = true;

CREATE INDEX idx_artifacts_run ON artifacts (run_id)
  WHERE run_id IS NOT NULL;

CREATE INDEX idx_artifacts_pipeline ON artifacts (pipeline_run_id)
  WHERE pipeline_run_id IS NOT NULL;

CREATE INDEX idx_elements_app_page ON elements (page_id) INCLUDE (semantic_selector);
