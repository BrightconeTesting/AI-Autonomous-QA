CREATE TABLE IF NOT EXISTS "api_ui_mappings" (
    "mapping_id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "app_id" UUID NOT NULL REFERENCES "applications"("app_id") ON DELETE CASCADE,
    "api_endpoint_id" UUID NOT NULL REFERENCES "api_endpoints"("endpoint_id") ON DELETE CASCADE,
    "page_id" UUID NOT NULL REFERENCES "pages"("page_id") ON DELETE CASCADE,
    "form_id" UUID REFERENCES "forms"("form_id") ON DELETE SET NULL,
    "element_id" UUID REFERENCES "elements"("element_id") ON DELETE SET NULL,
    "flow_id" UUID REFERENCES "flows"("flow_id") ON DELETE SET NULL,
    "trigger_action" JSONB NOT NULL DEFAULT '{}',
    "confidence" NUMERIC(4, 3) NOT NULL DEFAULT 0,
    "correlation_method" VARCHAR(32) NOT NULL DEFAULT 'heuristic',
    "review_required" BOOLEAN NOT NULL DEFAULT FALSE,
    "discovered_at" TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS "idx_api_ui_mappings_app_id" ON "api_ui_mappings" ("app_id");
CREATE INDEX IF NOT EXISTS "idx_api_ui_mappings_endpoint_id" ON "api_ui_mappings" ("api_endpoint_id");
CREATE INDEX IF NOT EXISTS "idx_api_ui_mappings_page_id" ON "api_ui_mappings" ("page_id");
