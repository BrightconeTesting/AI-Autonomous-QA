CREATE TABLE IF NOT EXISTS "api_endpoints" (
    "endpoint_id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "app_id" UUID NOT NULL REFERENCES "applications"("app_id") ON DELETE CASCADE,
    "method" VARCHAR(16) NOT NULL,
    "path" TEXT NOT NULL,
    "path_pattern" TEXT NOT NULL,
    "source" VARCHAR(16) NOT NULL DEFAULT 'network',
    "request_schema" JSONB NOT NULL DEFAULT '{}',
    "response_schema" JSONB NOT NULL DEFAULT '{}',
    "first_seen_page_id" UUID REFERENCES "pages"("page_id") ON DELETE SET NULL,
    "seen_page_ids" JSONB NOT NULL DEFAULT '[]',
    "seen_count" INTEGER NOT NULL DEFAULT 1,
    "discovered_at" TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT "api_endpoints_app_method_pattern_key" UNIQUE ("app_id", "method", "path_pattern")
);

CREATE INDEX IF NOT EXISTS "idx_api_endpoints_app_id" ON "api_endpoints" ("app_id");
