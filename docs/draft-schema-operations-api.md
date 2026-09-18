# Source-Prioritized Resource Schema: Operational API

This document describes how application code should operate on the schema in
`01_schema.sql`. It treats the database model as an API: the supported commands,
read semantics, invariants, transaction boundaries, and expected failure modes.

## 1. Core semantics

A **resource** is a minimal logical record assembled from one or more **sources**.
Each source belongs to a **source key**, such as `A`, `B`, or `licensed_vendor`.
A user may view only the source keys for which they have `view` permission.

Source data is represented as populated attribute rows:

```text
(source_id, attribute_id) -> exactly one of value_text, value_num, value_json
```

For each resource and attribute, `resource_attribute_priority` defines an ordered
list of source candidates. Lower numeric priority wins.

The resolved value is therefore:

> the highest-priority populated value whose source key is visible to the user

Permission filtering must happen **before** selecting the winning priority. If a
restricted source at priority 0 contains a value and the user cannot view its
key, the user receives the next visible candidate.

## 2. Important invariants

The schema enforces these relationships:

1. A source can participate in a resource only through `resource_source`.
2. A priority entry can reference only a source attached to the resource.
3. A priority entry can reference only a populated source attribute.
4. A source attribute contains exactly one typed value.
5. Two sources cannot occupy the same priority position for the same resource
   and attribute.
6. A source cannot appear twice in the priority list for the same resource and
   attribute.
7. Visibility is determined by the source's key, not by the resource or
   attribute independently.

The schema does **not** require priorities to be contiguous. Positions `0, 10,
20` are valid and often easier to maintain than `0, 1, 2`.

## 3. Suggested application service surface

A service layer can expose operations similar to the following:

```text
create_resource() -> resource_id
create_source(source_key, external_id?) -> source_id
attach_source(resource_id, source_id)
define_attribute(name, description?, unit?) -> attribute_id
put_source_value(source_id, attribute, typed_value)
delete_source_value(source_id, attribute)
set_attribute_priorities(resource_id, attribute, ordered_source_ids)
grant_source_key_permission(user_id, source_key, action = "view")
revoke_source_key_permission(user_id, source_key, action = "view")
resolve_resource(user_id, resource_id) -> flat object
search_resources(user_id, predicates) -> resource ids or flat objects
explain_resolved_value(user_id, resource_id, attribute) -> provenance
```

Database functions are optional. These can be implemented in application code
using parameterized SQL while preserving the same semantics.

## 4. Creating resources and sources

### Create a resource

```sql
INSERT INTO resource DEFAULT VALUES
RETURNING resource_id;
```

### Resolve or create a source key

```sql
INSERT INTO source_key (key_name)
VALUES ($1)
ON CONFLICT (key_name)
DO UPDATE SET key_name = EXCLUDED.key_name
RETURNING source_key_id;
```

### Create a source

```sql
INSERT INTO source (source_key_id, external_id)
VALUES ($1, $2)
RETURNING source_id;
```

### Attach a source to a resource

```sql
INSERT INTO resource_source (resource_id, source_id)
VALUES ($1, $2)
ON CONFLICT DO NOTHING;
```

Attaching a source does not automatically prioritize every value from that
source. Priority remains explicit per attribute.

## 5. Defining attributes

Use a stable attribute name at the API boundary, but use `attribute_id`
internally.

```sql
INSERT INTO attribute_definition (name, description, unit)
VALUES ($1, $2, $3)
ON CONFLICT (name)
DO UPDATE SET
    description = COALESCE(EXCLUDED.description,
                           attribute_definition.description),
    unit = COALESCE(EXCLUDED.unit, attribute_definition.unit)
RETURNING attribute_id;
```

Renaming an attribute should be treated as a controlled schema operation. The
priority and value tables remain stable because they reference `attribute_id`,
not the textual name.

## 6. Writing source values

A source value exists only when it is populated. SQL `NULL` means "no candidate
value" and should normally be represented by deleting the row.

### Text value

```sql
INSERT INTO source_attribute_value (
    source_id,
    attribute_id,
    value_text
)
VALUES ($1, $2, $3)
ON CONFLICT (source_id, attribute_id)
DO UPDATE SET
    value_text = EXCLUDED.value_text,
    value_num = NULL,
    value_json = NULL,
    updated_at = now();
```

### Numeric value

```sql
INSERT INTO source_attribute_value (
    source_id,
    attribute_id,
    value_num
)
VALUES ($1, $2, $3)
ON CONFLICT (source_id, attribute_id)
DO UPDATE SET
    value_text = NULL,
    value_num = EXCLUDED.value_num,
    value_json = NULL,
    updated_at = now();
```

### JSON value

```sql
INSERT INTO source_attribute_value (
    source_id,
    attribute_id,
    value_json
)
VALUES ($1, $2, $3::jsonb)
ON CONFLICT (source_id, attribute_id)
DO UPDATE SET
    value_text = NULL,
    value_num = NULL,
    value_json = EXCLUDED.value_json,
    updated_at = now();
```

The JSON literal `null` is rejected. Use row deletion to represent absence.

### Delete a value

```sql
DELETE FROM source_attribute_value
WHERE source_id = $1
  AND attribute_id = $2;
```

This deletion fails while a priority row references the value. The application
must first remove or replace that source in affected priority lists. This is an
intentional consistency guard.

A safe transaction is:

```sql
BEGIN;

DELETE FROM resource_attribute_priority
WHERE source_id = $1
  AND attribute_id = $2;

DELETE FROM source_attribute_value
WHERE source_id = $1
  AND attribute_id = $2;

COMMIT;
```

## 7. Managing priority lists

Treat a priority list as one ordered aggregate rather than many unrelated rows.
Replacing the complete list in one transaction is usually safer than issuing
individual moves.

Given an ordered input such as:

```json
[17, 42, 91]
```

assign priorities using ordinality:

```sql
BEGIN;

DELETE FROM resource_attribute_priority
WHERE resource_id = $1
  AND attribute_id = $2;

INSERT INTO resource_attribute_priority (
    resource_id,
    attribute_id,
    source_id,
    priority
)
SELECT
    $1,
    $2,
    input.source_id,
    input.ordinality - 1
FROM unnest($3::bigint[]) WITH ORDINALITY AS input(source_id, ordinality);

COMMIT;
```

The insert fails when:

- a source is not attached to the resource;
- a source lacks a value for the attribute;
- the source appears more than once;
- the input creates duplicate priority positions.

Those failures are useful API validation errors and should normally map to a
client error rather than an internal server error.

### Incremental insertion with sparse ranks

To avoid renumbering, use ranks such as `1000, 2000, 3000`. Insert a new source
between the first and second at `1500`. Renormalize only when no gap remains.

## 8. Granting and revoking visibility

### Grant permission

```sql
INSERT INTO user_source_key_permission (
    user_id,
    source_key_id,
    action
)
VALUES ($1, $2, 'view')
ON CONFLICT DO NOTHING;
```

### Revoke permission

```sql
DELETE FROM user_source_key_permission
WHERE user_id = $1
  AND source_key_id = $2
  AND action = 'view';
```

Permission changes take effect immediately for dynamically resolved reads.
Caches must include the user's effective visibility profile in the cache key or
be invalidated when permissions change.

## 9. Resolving one resource for one user

The permission join removes inaccessible candidates before `DISTINCT ON`
chooses the winner.

```sql
WITH resolved AS (
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
     AND permission.user_id = $1
     AND permission.action = 'view'
    WHERE p.resource_id = $2
    ORDER BY
        p.resource_id,
        p.attribute_id,
        p.priority,
        p.source_id
)
SELECT
    r.resource_id,
    jsonb_object_agg(
        a.name,
        COALESCE(
            to_jsonb(r.value_text),
            to_jsonb(r.value_num),
            r.value_json
        )
    ) AS attributes
FROM resolved AS r
JOIN attribute_definition AS a
  ON a.attribute_id = r.attribute_id
GROUP BY r.resource_id;
```

The result is a user-specific flat JSON object.

### Empty resources

The query above returns no row when the user can see no resolved attributes.
To return the resource with an empty JSON object, start from `resource` and use
a lateral or left join.

## 10. Resolving many resources

The same resolution CTE can omit the `resource_id` predicate. For large result
sets, page by `resource_id` and resolve only the requested page.

Avoid flattening every attribute for every resource before applying selective
filters. Resolve only the attributes needed for filtering or output.

## 11. Provenance and explanation

A useful API should expose why a user received a particular value.

```sql
SELECT
    p.resource_id,
    a.name AS attribute,
    p.source_id,
    sk.key_name AS source_key,
    p.priority,
    v.value_text,
    v.value_num,
    v.value_json
FROM resource_attribute_priority AS p
JOIN source_attribute_value AS v
  ON v.source_id = p.source_id
 AND v.attribute_id = p.attribute_id
JOIN attribute_definition AS a
  ON a.attribute_id = p.attribute_id
JOIN source AS s
  ON s.source_id = p.source_id
JOIN source_key AS sk
  ON sk.source_key_id = s.source_key_id
JOIN user_source_key_permission AS permission
  ON permission.source_key_id = s.source_key_id
 AND permission.user_id = $1
 AND permission.action = 'view'
WHERE p.resource_id = $2
  AND a.name = $3
ORDER BY p.priority, p.source_id;
```

The first row is the visible winner. Remaining rows are visible fallbacks.
Do not reveal hidden candidates or their keys unless the user has separate
permission to inspect restricted provenance.

## 12. Dynamic search by unknown attributes

The search API may accept an arbitrary list of predicates. An extensible input
shape is:

```json
[
  {
    "attribute": "country",
    "operator": "eq",
    "value_text": "US"
  },
  {
    "attribute": "production",
    "operator": "gte",
    "value_num": 1000
  }
]
```

The correct order of operations is:

```text
parse predicates
    -> resolve attribute names to IDs
    -> restrict candidates to visible source keys
    -> choose the highest-priority visible value
    -> apply predicates
    -> require all predicates to match
```

Filtering raw source values before priority resolution answers a different
question: "does any permitted source contain this value?" The usual API should
instead filter the flattened representation the user actually sees.

### Equality-only search

This query accepts typed equality predicates as JSON and requires every
predicate to match.

```sql
WITH requested_filters AS (
    SELECT
        definition.attribute_id,
        filter.attribute,
        filter.value_text,
        filter.value_num,
        filter.value_json
    FROM jsonb_to_recordset($2::jsonb) AS filter(
        attribute text,
        value_text text,
        value_num numeric,
        value_json jsonb
    )
    JOIN attribute_definition AS definition
      ON definition.name = filter.attribute
),
resolved AS (
    SELECT DISTINCT ON (
        p.resource_id,
        p.attribute_id
    )
        p.resource_id,
        p.attribute_id,
        v.value_text,
        v.value_num,
        v.value_json
    FROM resource_attribute_priority AS p
    JOIN requested_filters AS filter
      ON filter.attribute_id = p.attribute_id
    JOIN source_attribute_value AS v
      ON v.source_id = p.source_id
     AND v.attribute_id = p.attribute_id
    JOIN source AS s
      ON s.source_id = p.source_id
    JOIN user_source_key_permission AS permission
      ON permission.source_key_id = s.source_key_id
     AND permission.user_id = $1
     AND permission.action = 'view'
    ORDER BY
        p.resource_id,
        p.attribute_id,
        p.priority,
        p.source_id
),
matched AS (
    SELECT
        resolved.resource_id,
        resolved.attribute_id
    FROM resolved
    JOIN requested_filters AS filter
      ON filter.attribute_id = resolved.attribute_id
     AND (
            (
                filter.value_text IS NOT NULL
                AND resolved.value_text = filter.value_text
            )
         OR (
                filter.value_num IS NOT NULL
                AND resolved.value_num = filter.value_num
            )
         OR (
                filter.value_json IS NOT NULL
                AND resolved.value_json = filter.value_json
            )
     )
)
SELECT matched.resource_id
FROM matched
GROUP BY matched.resource_id
HAVING count(*) = (SELECT count(*) FROM requested_filters)
ORDER BY matched.resource_id;
```

Input validation should require exactly one filter value column per predicate,
just as the value table requires exactly one storage column.

### Supporting comparison operators

Add an `operator` field and dispatch by value type:

```sql
AND CASE filter.operator
    WHEN 'eq' THEN resolved.value_num = filter.value_num
    WHEN 'neq' THEN resolved.value_num <> filter.value_num
    WHEN 'lt' THEN resolved.value_num < filter.value_num
    WHEN 'lte' THEN resolved.value_num <= filter.value_num
    WHEN 'gt' THEN resolved.value_num > filter.value_num
    WHEN 'gte' THEN resolved.value_num >= filter.value_num
    ELSE false
END
```

Do not accept arbitrary SQL operators or column names from clients. Parse a
small allowlisted operator vocabulary and bind all values as parameters.

### Duplicate attributes

Decide explicitly whether repeated predicates for one attribute mean AND, OR,
or invalid input. A simple first version should reject duplicates.

### Unknown attributes

The join to `attribute_definition` silently drops unknown names. For an API,
validate before executing the search and return a clear client error listing
unknown attributes.

## 13. Pagination and result shape

A search endpoint may return only resource IDs first:

```text
search_resources(user, predicates, cursor, limit) -> [resource_id]
```

Then fetch flattened representations for those IDs in a second query. This is
often easier to optimize than resolving and aggregating every matching resource
inside one large statement.

Prefer keyset pagination:

```sql
WHERE resource_id > $cursor
ORDER BY resource_id
LIMIT $limit
```

## 14. Concurrency

Priority-list replacement should occur in one transaction. Concurrent writers
for the same `(resource_id, attribute_id)` can serialize using a row lock or an
advisory transaction lock.

One option is to lock the resource row:

```sql
SELECT 1
FROM resource
WHERE resource_id = $1
FOR UPDATE;
```

A narrower advisory lock can be derived from the resource and attribute IDs:

```sql
SELECT pg_advisory_xact_lock($1, $2);
```

Choose one strategy and use it consistently in all priority mutation paths.

## 15. Row-level security

Application-level permission joins make semantics explicit. PostgreSQL row-level
security can add defense in depth so restricted source values cannot be read by
accident.

A common request transaction is:

```sql
BEGIN;
SET LOCAL app.user_id = '<authenticated-user-uuid>';
-- Execute permission-aware queries.
COMMIT;
```

The authenticated identity must come from trusted server-side authentication,
not a client-controlled query parameter.

RLS does not eliminate the need to reason about provenance leakage. Protect
`source`, `resource_attribute_priority`, and diagnostic views as needed if even
the existence of restricted sources is confidential.

## 16. Caching and materialization

The flattened representation is user-dependent. A cache keyed only by
`resource_id` is incorrect when users have different source-key permissions.

Valid cache keys include:

```text
(resource_id, user_id, permission_version)
(resource_id, role_id, permission_version)
(resource_id, visibility_profile_hash)
```

Role- or profile-based caching is preferable when many users share identical
grants.

A globally materialized resolved table works only for a canonical visibility
profile. For multiple profiles, materialize per profile or resolve dynamically.

## 17. Deletion behavior

Deleting a resource cascades through its attachments and priority rows.

Deleting a source cascades through its values, attachments, and priority rows.
This is convenient but may be too destructive for audited systems. Alternatives
include soft deletion or `ON DELETE RESTRICT` plus explicit archival workflows.

Deleting an attribute definition is restricted while values or priorities refer
to it. Treat attribute deletion as a migration rather than a routine API call.

## 18. Recommended validation errors

Map database constraint failures to stable API errors:

| Condition | Suggested API error |
|---|---|
| Source not attached to resource | `SOURCE_NOT_ATTACHED` |
| Source has no value for attribute | `SOURCE_ATTRIBUTE_MISSING` |
| Duplicate priority position | `PRIORITY_CONFLICT` |
| Duplicate source in list | `DUPLICATE_PRIORITY_SOURCE` |
| No typed value or multiple typed values | `INVALID_TYPED_VALUE` |
| JSON literal null supplied | `INVALID_JSON_NULL` |
| Unknown attribute name | `UNKNOWN_ATTRIBUTE` |
| Unsupported operator | `UNSUPPORTED_OPERATOR` |
| User lacks permission | `FORBIDDEN_SOURCE_KEY` or omit existence details |

For security-sensitive operations, avoid distinguishing "does not exist" from
"exists but forbidden" unless the caller is allowed to know that distinction.

## 19. Recommended initial implementation

A practical first version is:

1. Use the canonical typed EAV tables.
2. Store direct `view` grants by source key.
3. Replace full priority lists transactionally.
4. Resolve with a permission join followed by `DISTINCT ON`.
5. Accept equality-only dynamic filters initially.
6. Resolve only requested attributes during search.
7. Add RLS after application queries and transaction identity handling are
   stable.
8. Add role-based permission profiles if caching or permission-row volume
   becomes significant.

This preserves strong relational constraints while keeping the application API
predictable and extensible.
