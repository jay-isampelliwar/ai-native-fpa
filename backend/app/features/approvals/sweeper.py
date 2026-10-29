"""Expiring approvals nobody decided in time, running their safe calls and ending their runs as cancelled; the agent worker's sweep calls it."""

import logging

from app.db.session import SessionLocal
from app.features.approvals.repository import ApprovalRepository
from app.features.approvals.service import EXPIRED, ApprovalService


log = logging.getLogger(__name__)


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
