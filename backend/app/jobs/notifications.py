"""In-app notification generation (E10.3, TDS §17).

Turns thesis invalidation events (challenged/broken alerts) into in-app
notifications for the thesis owner, deduplicated by (type, target, period-ish)
so a flapping signal does not spam the analyst. Idempotent: the unique
``dedup_key`` + ON CONFLICT DO NOTHING means re-running generates no duplicates.
No email, no escalation in V1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Notification, Thesis, ThesisEvent

log = logging.getLogger(__name__)


@dataclass
class NotifyResult:
    created: int


def generate(session: Session) -> NotifyResult:
    """Create notifications from thesis 'alert' events. Deduped per
    (thesis, assumption, to_state) so the same transition notifies once."""
    alerts = session.scalars(
        select(ThesisEvent).where(ThesisEvent.event_type == "alert")
    ).all()

    created = 0
    for ev in alerts:
        thesis = session.get(Thesis, ev.thesis_id)
        if thesis is None:
            continue
        dedup_key = f"thesis_invalidation:{ev.thesis_id}:{ev.assumption_id}:{ev.to_state}"
        ins = pg_insert(Notification).values(
            recipient=thesis.owner,
            kind="thesis_invalidation",
            title=f"Assumption {ev.to_state}: {thesis.claim}",
            body=ev.detail,
            thesis_id=ev.thesis_id,
            assumption_id=ev.assumption_id,
            dedup_key=dedup_key,
        )
        stmt = ins.on_conflict_do_nothing(constraint="uq_notification_dedup")
        result = session.execute(stmt)
        created += result.rowcount or 0

    session.commit()
    log.info("notification generate created=%d", created)
    return NotifyResult(created=created)
