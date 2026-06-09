"""Engine / session factories for the two database roles.

`engine` / `SessionLocal` use the restricted application role (`mip_app`) — the
role the running service uses, with no UPDATE/DELETE on `observation`.
`owner_engine` uses the schema owner and is reserved for migrations and
administrative seeding, never for request handling.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

# Runtime (restricted) connection — the application's normal role.
engine = create_engine(settings.app_database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

# Owner connection — migrations / admin only.
owner_engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
OwnerSessionLocal = sessionmaker(
    bind=owner_engine, autoflush=False, expire_on_commit=False, future=True
)
