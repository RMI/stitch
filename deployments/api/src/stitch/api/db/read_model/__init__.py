"""Precomputed current-state read model for OG field resources (STIT-766).

``permissions`` declares the exact permission profiles the read model stores. The
``og_field_resource_state`` table (``db.model.og_field_resource_state``) is derived
data, rebuildable at any time from authoritative tables via the live coalescer.
"""
