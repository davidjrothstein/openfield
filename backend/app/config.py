"""Runtime configuration.

Two connection roles exist by design (TDS §2, §18, CLAUDE.md invariant #1):

* ``DATABASE_URL`` — the *owner / migration* role. Owns the schema, runs
  Alembic, seeds the registry. Has full DDL rights. Never used by request
  handlers.
* ``APP_DATABASE_URL`` — the *application* role (``mip_app``). The role the
  FastAPI process connects with at runtime. It holds INSERT + SELECT on
  ``observation`` and **no UPDATE/DELETE** — the append-only invariant is a
  database privilege, not a convention.

Both default to a local dev cluster so the migration and tests run out of the
box. Real deployments inject these from the environment / secret store.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MIP_", extra="ignore")

    # Owner / migration connection. Full rights; used by Alembic and admin tasks.
    database_url: str = "postgresql+psycopg2://mip_owner:mip_owner_pw@localhost:5432/mip"

    # Restricted application connection. INSERT+SELECT on observation only.
    app_database_url: str = (
        "postgresql+psycopg2://mip_app_login:mip_app_pw@localhost:5432/mip"
    )

    # Name of the restricted privilege (group) role created by the migration.
    app_role_name: str = "mip_app"


settings = Settings()
