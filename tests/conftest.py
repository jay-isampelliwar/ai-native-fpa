"""Shared fixtures, and the one decision every database test depends on.

Tests that touch PostgreSQL are skipped when it is unreachable rather than failing, so the
suite still runs offline on a laptop or in a container that has no database. That is a
convenience, not a licence: the cross backend repository tests exist precisely so the SQL
path is exercised whenever a database is present.

``api_user`` creates a throwaway user with a high id and removes every row it created
afterwards. Tests share one database, and a test that leaves records behind changes the
answers of every other test that reads the seeded user - the failure then appears somewhere
unrelated and gets debugged for an hour.

Cleanup deletes rather than archives. The application never deletes, but a test fixture is
not the application, and leaving archived rows behind would grow the tables indefinitely.

The purge runs before the test as well as after it. A previous run interrupted partway leaves
rows behind, and deleting the user first would then fail on a foreign key from a table the
cleanup list had forgotten - which is exactly how this fixture broke when goals were added.
``CLEANUP_ORDER`` is child before parent throughout, and every user owned table must appear in
it or a new table will reintroduce the same failure.
"""

import asyncio

import pytest
from sqlalchemy import text

TEST_USER_ID = 9001

CLEANUP_ORDER = [
    "goal_fundings",
    "goals",
    "investment_transactions",
    "holdings",
    "deposits",
    "retirement_assets",
    "insurance_policies",
    "expense_transactions",
    "sip_records",
    "emi_records",
    "liabilities",
    "expense_records",
    "income_records",
    "pending_approvals",
    "audit_records",
]


async def database_reachable() -> bool:

    """Report whether the configured database answers, so database tests can skip cleanly."""

    try:
        from app.db.session import session_scope

        async with session_scope() as session:
            await session.execute(text("SELECT 1"))

        return True

    except Exception:
        return False


@pytest.fixture(scope="session")
def postgres_available() -> bool:

    """Check the database once per session rather than once per test."""

    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(database_reachable())


async def purge(user_id: int) -> None:

    """Remove every row belonging to one user, children before parents, then the user itself."""

    from app.db.session import session_scope

    async with session_scope() as session:

        for table in CLEANUP_ORDER:
            await session.execute(text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": user_id})

        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})


@pytest.fixture
async def api_user():

    """Create an isolated test user, yield its id, and remove every row it left behind."""

    if not await database_reachable():
        pytest.skip("postgres is not reachable")

    from app.db.session import session_scope
    from app.models.orm.system import UserRow

    await purge(TEST_USER_ID)

    async with session_scope() as session:
        session.add(UserRow(id=TEST_USER_ID, display_name="Test user"))

    yield TEST_USER_ID

    await purge(TEST_USER_ID)


@pytest.fixture
async def client(api_user):

    """A test client against the real application, with the router stubbed so no model is called."""

    from fastapi.testclient import TestClient

    from app.graphs.orchestrator import graph as graph_module
    from app.main import app

    async def fake_route(state):
        return {"skill_name": "cashflow_summary", "route_confidence": 0.9, "route_reason": "stubbed"}

    original = graph_module.route_request
    graph_module.route_request = fake_route

    with TestClient(app) as test_client:
        yield test_client

    graph_module.route_request = original
