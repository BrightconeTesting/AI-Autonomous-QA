-- CIC Phase 1: page_states, state_transitions, page_discoveries, elements.state_id

CREATE TABLE IF NOT EXISTS "page_states" (
    "state_id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "page_id" UUID NOT NULL,
    "state_key" VARCHAR(64) NOT NULL,
    "fingerprint" VARCHAR(64),
    "title" VARCHAR(512),
    "screenshot_path" TEXT,
    "interaction_depth" INTEGER NOT NULL DEFAULT 0,
    "parent_state_key" VARCHAR(64),
    "trigger_action" JSONB NOT NULL DEFAULT '{}',
    "discovered_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "page_states_pkey" PRIMARY KEY ("state_id"),
    CONSTRAINT "page_states_page_id_fkey" FOREIGN KEY ("page_id") REFERENCES "pages"("page_id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "page_states_page_id_state_key_key" UNIQUE ("page_id", "state_key")
);

CREATE INDEX IF NOT EXISTS "idx_page_states_page_id" ON "page_states"("page_id");

CREATE TABLE IF NOT EXISTS "state_transitions" (
    "transition_id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "app_id" UUID NOT NULL,
    "from_state_id" UUID NOT NULL,
    "to_state_id" UUID NOT NULL,
    "action" JSONB NOT NULL DEFAULT '{}',
    "discovered_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "state_transitions_pkey" PRIMARY KEY ("transition_id"),
    CONSTRAINT "state_transitions_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "state_transitions_from_state_id_fkey" FOREIGN KEY ("from_state_id") REFERENCES "page_states"("state_id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "state_transitions_to_state_id_fkey" FOREIGN KEY ("to_state_id") REFERENCES "page_states"("state_id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "idx_state_transitions_app_id" ON "state_transitions"("app_id");
CREATE INDEX IF NOT EXISTS "idx_state_transitions_from_state" ON "state_transitions"("from_state_id");
CREATE INDEX IF NOT EXISTS "idx_state_transitions_to_state" ON "state_transitions"("to_state_id");

CREATE TABLE IF NOT EXISTS "page_discoveries" (
    "discovery_id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "app_id" UUID NOT NULL,
    "url" TEXT NOT NULL,
    "discovered_via" VARCHAR(32) NOT NULL DEFAULT 'link',
    "source_page_id" UUID,
    "source_state_key" VARCHAR(64),
    "trigger_action" JSONB NOT NULL DEFAULT '{}',
    "discovered_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "page_discoveries_pkey" PRIMARY KEY ("discovery_id"),
    CONSTRAINT "page_discoveries_app_id_fkey" FOREIGN KEY ("app_id") REFERENCES "applications"("app_id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "page_discoveries_source_page_id_fkey" FOREIGN KEY ("source_page_id") REFERENCES "pages"("page_id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "page_discoveries_app_id_url_key" UNIQUE ("app_id", "url")
);

CREATE INDEX IF NOT EXISTS "idx_page_discoveries_app_id" ON "page_discoveries"("app_id");

ALTER TABLE "elements" ADD COLUMN IF NOT EXISTS "state_id" UUID;
ALTER TABLE "elements" DROP CONSTRAINT IF EXISTS "elements_state_id_fkey";
ALTER TABLE "elements" ADD CONSTRAINT "elements_state_id_fkey"
    FOREIGN KEY ("state_id") REFERENCES "page_states"("state_id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE INDEX IF NOT EXISTS "idx_elements_state_id" ON "elements"("state_id");
