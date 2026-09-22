-- NMOS: runtime configuration editable from the plugin UI (overrides environment defaults).

CREATE TABLE app_config (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
