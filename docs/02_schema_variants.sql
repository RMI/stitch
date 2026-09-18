-- Schema variants and optional extensions
-- Target database: PostgreSQL 15+
--
-- This file is not intended to be executed as a single migration. Each section
-- is an alternative to, or extension of, the canonical schema in 01_schema.sql.

-------------------------------------------------------------------------------
-- Variant A: direct view grants only
-------------------------------------------------------------------------------
-- Use when the only key-scoped permission is "view". The presence of a row
-- means the user can view sources with that key.

CREATE TABLE user_source_key_view_permission (
    user_id uuid NOT NULL,
    source_key_id bigint NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, source_key_id),

    FOREIGN KEY (user_id)
        REFERENCES app_user(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (source_key_id)
        REFERENCES source_key(source_key_id)
        ON DELETE CASCADE
);

-------------------------------------------------------------------------------
-- Variant B: role-based grants
-------------------------------------------------------------------------------
-- Use when many users share the same effective visibility profile. This can
-- substantially reduce duplicate permission rows and enables caching by role
-- or visibility profile instead of by individual user.

CREATE TABLE app_role (
    role_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role_name text NOT NULL UNIQUE
);

CREATE TABLE user_role (
    user_id uuid NOT NULL,
    role_id bigint NOT NULL,

    PRIMARY KEY (user_id, role_id),

    FOREIGN KEY (user_id)
        REFERENCES app_user(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (role_id)
        REFERENCES app_role(role_id)
        ON DELETE CASCADE
);

CREATE TABLE role_source_key_permission (
    role_id bigint NOT NULL,
    source_key_id bigint NOT NULL,
    action source_key_action NOT NULL,

    PRIMARY KEY (role_id, source_key_id, action),

    FOREIGN KEY (role_id)
        REFERENCES app_role(role_id)
        ON DELETE CASCADE,

    FOREIGN KEY (source_key_id)
        REFERENCES source_key(source_key_id)
        ON DELETE CASCADE
);

CREATE VIEW effective_user_source_key_permission AS
SELECT DISTINCT
    ur.user_id,
    rp.source_key_id,
    rp.action
FROM user_role AS ur
JOIN role_source_key_permission AS rp
  ON rp.role_id = ur.role_id;

-------------------------------------------------------------------------------
-- Variant C: groups plus direct grants
-------------------------------------------------------------------------------
-- Effective grants are the union of direct grants and group-derived grants.

CREATE TABLE app_group (
    group_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name text NOT NULL UNIQUE
);

CREATE TABLE user_group (
    user_id uuid NOT NULL,
    group_id bigint NOT NULL,

    PRIMARY KEY (user_id, group_id),

    FOREIGN KEY (user_id)
        REFERENCES app_user(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (group_id)
        REFERENCES app_group(group_id)
        ON DELETE CASCADE
);

CREATE TABLE group_source_key_permission (
    group_id bigint NOT NULL,
    source_key_id bigint NOT NULL,
    action source_key_action NOT NULL,

    PRIMARY KEY (group_id, source_key_id, action),

    FOREIGN KEY (group_id)
        REFERENCES app_group(group_id)
        ON DELETE CASCADE,

    FOREIGN KEY (source_key_id)
        REFERENCES source_key(source_key_id)
        ON DELETE CASCADE
);

CREATE VIEW effective_user_source_key_permission AS
SELECT
    p.user_id,
    p.source_key_id,
    p.action
FROM user_source_key_permission AS p

UNION

SELECT
    ug.user_id,
    gp.source_key_id,
    gp.action
FROM user_group AS ug
JOIN group_source_key_permission AS gp
  ON gp.group_id = ug.group_id;

-------------------------------------------------------------------------------
-- Variant D: retain a wide source-data table
-------------------------------------------------------------------------------
-- If source data must remain in physical columns, use a companion presence
-- table to expose only populated attributes to the priority system. A trigger
-- or ingestion process must keep this table synchronized.

CREATE TABLE source_attribute_presence (
    source_id bigint NOT NULL,
    attribute_id bigint NOT NULL,

    PRIMARY KEY (source_id, attribute_id),

    FOREIGN KEY (source_id)
        REFERENCES source(source_id)
        ON DELETE CASCADE,

    FOREIGN KEY (attribute_id)
        REFERENCES attribute_definition(attribute_id)
);

-- In this variant, replace the priority FK to source_attribute_value with:
--
-- ALTER TABLE resource_attribute_priority
--     DROP CONSTRAINT resource_attribute_priority_source_value_fk,
--     ADD CONSTRAINT resource_attribute_priority_source_presence_fk
--         FOREIGN KEY (source_id, attribute_id)
--         REFERENCES source_attribute_presence(source_id, attribute_id);

-------------------------------------------------------------------------------
-- Variant E: allow multiple source records per key for the same resource
-------------------------------------------------------------------------------
-- The canonical schema already permits this. Add a uniqueness constraint only
-- if the domain requires at most one source per source key per resource.
-- PostgreSQL cannot enforce this using only resource_source because source_key
-- resides on source. A denormalized source_key_id column or trigger is needed.

ALTER TABLE resource_source
    ADD COLUMN source_key_id bigint;

ALTER TABLE resource_source
    ADD CONSTRAINT resource_source_key_fk
        FOREIGN KEY (source_key_id)
        REFERENCES source_key(source_key_id);

ALTER TABLE resource_source
    ADD CONSTRAINT resource_source_one_source_per_key_uq
        UNIQUE (resource_id, source_key_id);

-- Synchronize resource_source.source_key_id with source.source_key_id in the
-- application or with a trigger.

-------------------------------------------------------------------------------
-- Variant F: nullable priority values with automatic fallback
-------------------------------------------------------------------------------
-- Not recommended with the canonical model. The canonical source_attribute_value
-- table stores only populated values, so priority rows always reference a value.
-- If null-valued rows must be retained for audit purposes, separate "observed"
-- from "candidate" values instead of weakening the FK invariant.

CREATE TABLE source_attribute_observation (
    observation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES source(source_id) ON DELETE CASCADE,
    attribute_id bigint NOT NULL REFERENCES attribute_definition(attribute_id),
    value_text text,
    value_num numeric,
    value_json jsonb,
    observed_at timestamptz NOT NULL DEFAULT now(),

    CHECK (num_nonnulls(value_text, value_num, value_json) <= 1),
    CHECK (value_json IS NULL OR value_json <> 'null'::jsonb)
);

-- Only non-null observations should be promoted into source_attribute_value.

-------------------------------------------------------------------------------
-- Variant G: row-level security for source values
-------------------------------------------------------------------------------
-- This variant assumes every transaction sets:
--
--     SET LOCAL app.user_id = '<uuid>';
--
-- The application role must not have BYPASSRLS. Table owners normally bypass
-- RLS unless FORCE ROW LEVEL SECURITY is enabled.

ALTER TABLE source_attribute_value ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_attribute_value FORCE ROW LEVEL SECURITY;

CREATE POLICY source_attribute_value_select_policy
ON source_attribute_value
FOR SELECT
USING (
    EXISTS (
        SELECT 1
        FROM source AS s
        JOIN user_source_key_permission AS p
          ON p.source_key_id = s.source_key_id
         AND p.action = 'view'
        WHERE s.source_id = source_attribute_value.source_id
          AND p.user_id = current_setting('app.user_id', true)::uuid
    )
);

-- Consider corresponding policies on source and resource_attribute_priority if
-- the existence or provenance of restricted sources is itself sensitive.

-------------------------------------------------------------------------------
-- Variant H: permission-aware resolution view
-------------------------------------------------------------------------------
-- A view cannot accept a user_id parameter. This form expects app.user_id to be
-- set transaction-locally. SECURITY INVOKER is the default and is preferred.

CREATE VIEW resolved_resource_attribute AS
SELECT DISTINCT ON (
    p.resource_id,
    p.attribute_id
)
    p.resource_id,
    p.attribute_id,
    p.source_id,
    s.source_key_id,
    p.priority,
    v.value_text,
    v.value_num,
    v.value_json
FROM resource_attribute_priority AS p
JOIN source_attribute_value AS v
  ON v.source_id = p.source_id
 AND v.attribute_id = p.attribute_id
JOIN source AS s
  ON s.source_id = p.source_id
JOIN user_source_key_permission AS permission
  ON permission.source_key_id = s.source_key_id
 AND permission.user_id = current_setting('app.user_id', true)::uuid
 AND permission.action = 'view'
ORDER BY
    p.resource_id,
    p.attribute_id,
    p.priority,
    p.source_id;

-------------------------------------------------------------------------------
-- Variant I: permission-aware resolution function
-------------------------------------------------------------------------------
-- Convenient when the database receives an explicit, trusted user identifier.
-- Do not expose this function to clients that may substitute arbitrary user IDs
-- unless authorization is enforced elsewhere.

CREATE FUNCTION resolved_resource_values(p_user_id uuid)
RETURNS TABLE (
    resource_id bigint,
    attribute_id bigint,
    source_id bigint,
    source_key_id bigint,
    priority integer,
    value_text text,
    value_num numeric,
    value_json jsonb
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT DISTINCT ON (
        p.resource_id,
        p.attribute_id
    )
        p.resource_id,
        p.attribute_id,
        p.source_id,
        s.source_key_id,
        p.priority,
        v.value_text,
        v.value_num,
        v.value_json
    FROM resource_attribute_priority AS p
    JOIN source_attribute_value AS v
      ON v.source_id = p.source_id
     AND v.attribute_id = p.attribute_id
    JOIN source AS s
      ON s.source_id = p.source_id
    JOIN user_source_key_permission AS permission
      ON permission.source_key_id = s.source_key_id
     AND permission.user_id = p_user_id
     AND permission.action = 'view'
    ORDER BY
        p.resource_id,
        p.attribute_id,
        p.priority,
        p.source_id
$$;

-------------------------------------------------------------------------------
-- Variant J: dense, contiguous priority positions
-------------------------------------------------------------------------------
-- UNIQUE(resource_id, attribute_id, priority) prevents duplicates but does not
-- prevent gaps. Enforce contiguous positions in application logic, a deferred
-- constraint trigger, or avoid positional integers entirely by storing a stable
-- rank value that permits insertion between neighbors.
--
-- Examples of alternatives:
--   * numeric rank: 1000, 2000, 3000, insert 1500 between first and second
--   * explicit linked list: predecessor_source_id
--   * full replacement API: delete and reinsert the complete ordered list
