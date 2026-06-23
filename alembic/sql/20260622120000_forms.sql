CREATE TABLE IF NOT EXISTS "forms" (
    "form_id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "app_id" UUID NOT NULL REFERENCES "applications"("app_id") ON DELETE CASCADE,
    "page_id" UUID NOT NULL REFERENCES "pages"("page_id") ON DELETE CASCADE,
    "state_id" UUID REFERENCES "page_states"("state_id") ON DELETE CASCADE,
    "action" TEXT,
    "method" VARCHAR(16) NOT NULL DEFAULT 'get',
    "attributes" JSONB NOT NULL DEFAULT '{}',
    "field_element_ids" JSONB NOT NULL DEFAULT '[]',
    "discovered_at" TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS "idx_forms_app_id" ON "forms" ("app_id");
CREATE INDEX IF NOT EXISTS "idx_forms_page_id" ON "forms" ("page_id");
CREATE INDEX IF NOT EXISTS "idx_forms_state_id" ON "forms" ("state_id");
