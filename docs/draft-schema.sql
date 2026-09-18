-- Source-prioritized, permission-aware EAV schema
-- Target database: PostgreSQL 15+
--
-- Core assumptions:
--   * Lower integer values represent higher priority.
--   * A source attribute row exists only when the source has a value.
--   * Exactly one typed value column is populated per source attribute.
--   * Source visibility is granted by source key and action.
--   * Permission filtering occurs before priority resolution.

BEGIN;

CREATE TYPE source_key_action AS ENUM (
    'view',
    'edit'
);

CREATE TABLE users (
    user_id uuid PRIMARY KEY
);

CREATE TABLE og_field_resources (
    resource_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_keys (
    source_key_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key_name text NOT NULL UNIQUE
);

CREATE TABLE oil_gas_field_sources (
    source_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key_id bigint NOT NULL,
    external_id text,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT source_source_key_fk
        FOREIGN KEY (source_key_id)
        REFERENCES source_keys(source_key_id)
);

CREATE TABLE attribute_definition (
    attribute_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    description text,
    unit text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    resource_id bigint NOT NULL,
    source_id bigint NOT NULL,
    attached_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (resource_id, source_id),

    CONSTRAINT resource_source_resource_fk
        FOREIGN KEY (resource_id)
        REFERENCES og_field_resources(resource_id)
        ON DELETE CASCADE,

    CONSTRAINT resource_source_source_fk
        FOREIGN KEY (source_id)
        REFERENCES oil_gas_field_sources(source_id)
        ON DELETE CASCADE
);

CREATE TABLE oil_gas_field_source_values (
    source_id bigint NOT NULL,
    attribute_id bigint NOT NULL,

    value_text text,
    value_num numeric,
    value_json jsonb,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (source_id, attribute_id),

    CONSTRAINT oil_gas_field_source_values_source_fk
        FOREIGN KEY (source_id)
        REFERENCES oil_gas_field_sources(source_id)
        ON DELETE CASCADE,

    CONSTRAINT oil_gas_field_source_values_attribute_fk
        FOREIGN KEY (attribute_id)
        REFERENCES attribute_definition(attribute_id),

    CONSTRAINT oil_gas_field_source_values_exactly_one_value_ck
        CHECK (num_nonnulls(value_text, value_num, value_json) = 1),

    CONSTRAINT oil_gas_field_source_values_nonnull_json_ck
        CHECK (value_json IS NULL OR value_json <> 'null'::jsonb)
);

CREATE TABLE og_field_resource_attribute_priority (
    resource_id bigint NOT NULL,
    attribute_id bigint NOT NULL,
    source_id bigint NOT NULL,
    priority integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (resource_id, attribute_id, source_id),

    CONSTRAINT resource_attribute_priority_position_uq
        UNIQUE (resource_id, attribute_id, priority),

    CONSTRAINT resource_attribute_priority_nonnegative_ck
        CHECK (priority >= 0),

    -- The source must be attached to the resource.
    CONSTRAINT resource_attribute_priority_resource_source_fk
        FOREIGN KEY (resource_id, source_id)
        REFERENCES memberships(resource_id, source_id)
        ON DELETE CASCADE,

    -- The source must have a populated value for the selected attribute.
    CONSTRAINT resource_attribute_priority_source_value_fk
        FOREIGN KEY (source_id, attribute_id)
        REFERENCES oil_gas_field_source_values(source_id, attribute_id)
);

-- handles the permissions for a user associated with a given source key
-- user_id | src_key_id | action
--    1    |    1 (wm)  |  view   -> only wm + public
--    1    |    2 (rmi) |  view
--    1    |    3 (gem) |  view
--    1    |    4 (alb) |  view
--    1    |    5 (bc)  |  view
--    1    |    6 (llm) |  view

--    2    |    7 (cc)  |  view   -> only cc + public
--    2    |    2 (rmi) |  view
--    2    |    3 (gem) |  view
--    2    |    4 (alb) |  view
--    2    |    5 (bc)  |  view
--    2    |    6 (llm) |  view

--    3    |    2 (rmi) |  view   -> only public
--    3    |    3 (gem) |  view
--    3    |    4 (alb) |  view
--    3    |    5 (bc)  |  view
--    3    |    6 (llm) |  view

--    4    |    1 (wm)  |  view   -> all: wm + cc + public
--    4    |    7 (cc)  |  view 
--    4    |    2 (rmi) |  view
--    4    |    3 (gem) |  view
--    4    |    4 (alb) |  view
--    4    |    5 (bc)  |  view
--    4    |    6 (llm) |  view
CREATE TABLE user_source_key_permission (
    user_id uuid NOT NULL,
    source_key_id bigint NOT NULL,
    action source_key_action NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, source_key_id, action),

    CONSTRAINT user_source_key_permission_user_fk
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT user_source_key_permission_key_fk
        FOREIGN KEY (source_key_id)
        REFERENCES source_keys(source_key_id)
        ON DELETE CASCADE
);

-- Resolution path: resource/attribute -> priority -> source -> source key.
CREATE INDEX resource_attribute_priority_resolution_idx
    ON og_field_resource_attribute_priority (
        resource_id,
        attribute_id,
        priority,
        source_id
    );

CREATE INDEX resource_attribute_priority_source_idx
    ON og_field_resource_attribute_priority (
        source_id,
        attribute_id
    );

CREATE INDEX source_key_lookup_idx
    ON oil_gas_field_sources (
        source_key_id,
        source_id
    );

CREATE INDEX user_source_key_view_idx
    ON user_source_key_permission (
        user_id,
        source_key_id
    )
    WHERE action = 'view';

-- Optional lookup indexes for filtering before or after resolution.
CREATE INDEX oil_gas_field_source_values_text_lookup_idx
    ON oil_gas_field_source_values (
        attribute_id,
        value_text,
        source_id
    )
    WHERE value_text IS NOT NULL;

CREATE INDEX oil_gas_field_source_values_num_lookup_idx
    ON oil_gas_field_source_values (
        attribute_id,
        value_num,
        source_id
    )
    WHERE value_num IS NOT NULL;

CREATE INDEX oil_gas_field_source_values_json_gin_idx
    ON oil_gas_field_source_values
    USING gin (value_json)
    WHERE value_json IS NOT NULL;

COMMIT;
