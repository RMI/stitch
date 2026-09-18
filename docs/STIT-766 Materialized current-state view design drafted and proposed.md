- one initial issue: sqlite does not support materialized views, we may need to drop support for sqlite in general

Objective
Alter the database structure to eliminate all slow responses, focusing on `list`, `filter-options`, and `detail` endpoints.

Proposal
- drop the base priority table, all new resources + sources get rows in the `resource_source_priority` table
- add a `og_field_attributes` table: `id`, `attr_name`, `type`(optional)

## Important Invariants

The schema should enforces these relationships:

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
