"""The loop that expires approvals nobody decided in time, runs their safe calls and ends their runs as cancelled."""

import asyncio
import logging

from app.db.session import SessionLocal
from app.features.approvals.repository import ApprovalRepository
from app.features.approvals.service import EXPIRED, ApprovalService


log = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60


async def expire_one() -> bool:

    """Expire the oldest overdue pending approval, carry its run to the end, and say whether there was one."""

    async with SessionLocal() as session:

        overdue = await ApprovalRepository(session).lock_expired(limit=1)

        if not overdue:
            return False

        await ApprovalService(session).close(overdue[0], EXPIRED)

    return True


async def expire_due() -> int:

    """Expire every overdue pending approval one at a time, and return how many were expired."""

    count = 0

    while await expire_one():
        count += 1

    return count


async def sweep_forever() -> None:

    """Expire overdue approvals at startup and then every minute, until cancelled, so the API lifespan can run it as a task."""

    while True:

        try:

            expired = await expire_due()

            if expired:
                log.info("expired %s approvals", expired)

        except Exception:
            log.exception("approval sweep failed")

        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
