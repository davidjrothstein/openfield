"""Background jobs (E10): the idempotent nightly recompute DAG, freshness scan,
and in-app notification generation. Scheduled via RQ + APScheduler; every job is
re-runnable after failure (TDS §16).
"""
