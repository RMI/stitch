"""Precomputed current-state read model for OG field resources (STIT-766).

``state`` builds and maintains the ``og_field_resource_state`` table; ``permissions``
encodes the ``permission_mask`` used to key it. The table is derived data --
rebuildable at any time from memberships, source values, and priorities.
"""
