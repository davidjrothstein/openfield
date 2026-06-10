"""Ingestion & normalization for public structured sources (TDS §4.1, §4.2, §6).

V1 lands exactly one real source end-to-end — the Census Building Permits Survey
(CLAUDE.md: the ONLY external data client at 60 days). Everything here sits
behind interfaces so the rest stays mockable, and so the licensed-data wall
(invariant #6) is never crossed: there are no vendor clients in this package,
only the public Census fetcher.
"""
