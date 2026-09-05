"""Endpoints for goals and the assets that fund them, on the write side of the product line.

Goals are entered here rather than through the conversation, for the same reason every other
record is. A goal is a large commitment stated once and referred to for years, and the model's
job is to project it, not to decide what it says. When Phase 5 lets a conversation propose a
goal, the approved proposal will call the same repository behind an approval token.

Funding is a link, never a copy. ``POST /goals/{id}/fundings`` earmarks an existing asset; it
does not move money or record a balance on the goal. That is why a goal read has to value its
assets at request time and why the response says ``valued_at_cost``.

Reads return the full evidence set. A client displaying "on track" without being able to show
which holdings and SIPs produced that verdict cannot honestly present it, so the ids come back
with the figures rather than being available on a second call.

Ownership failures are 404 throughout, matching the records endpoints: a goal the caller does
not own is reported exactly as one that does not exist.

``GET /assets/holdings`` returns what a user owns together with what their statements said it was
worth, dated by ``valued_at``. That date is not decoration: nothing refreshes these figures, and an
interface showing a two month old valuation as though it were current would be making a claim the
backend never made.
"""

from fastapi import APIRouter, HTTPException

from app.api.v1.goals.schemas import (
    DepositCreate,
    FundingLink,
    GoalCreate,
    GoalRead,
    HoldingCreate,
    RetirementAssetCreate,
)
from app.api.v1.records.schemas import RecordCreated
from app.db.session import session_scope
from app.repositories.goals_repository import goals_repository
from app.repositories.holdings_repository import HoldingsSummary, holdings_repository
from app.repositories.records_repository import records_repository

router = APIRouter(prefix="/goals", tags=["goals"])
assets_router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("", response_model=RecordCreated, status_code=201)
async def create_goal(request: GoalCreate) -> RecordCreated:

    """Record a savings target with the inflation rate that applies to this kind of goal."""

    async with session_scope() as session:
        row = await goals_repository.create_goal(
            session,
            user_id=request.user_id,
            label=request.label,
            target_amount=request.target_amount,
            target_date=request.target_date,
            kind=request.kind,
            priority=request.priority,
            inflation_percent=request.inflation_percent,
        )

        return RecordCreated(id=row.id, kind="goal")


@router.get("", response_model=list[GoalRead])
async def list_goals(user_id: int) -> list[GoalRead]:

    """List this user's active goals, each with its funding valued at request time."""

    snapshots = await goals_repository.list_snapshots(user_id)

    return [GoalRead(**snapshot.model_dump()) for snapshot in snapshots]


@router.get("/{goal_id}", response_model=GoalRead)
async def read_goal(goal_id: str, user_id: int) -> GoalRead:

    """Read one goal with the assets currently earmarked for it and the ids behind the figures."""

    snapshot = await goals_repository.get_snapshot(user_id, goal_id)

    if snapshot is None:
        raise HTTPException(status_code=404, detail="no such goal")

    return GoalRead(**snapshot.model_dump())


@router.post("/{goal_id}/fundings", response_model=RecordCreated, status_code=201)
async def link_funding(goal_id: str, request: FundingLink) -> RecordCreated:

    """Earmark an existing asset for a goal without moving money or storing a balance on it."""

    async with session_scope() as session:
        row = await goals_repository.link_funding(
            session,
            user_id=request.user_id,
            goal_id=goal_id,
            asset_table=request.asset_table,
            asset_id=request.asset_id,
            allocation_pct=request.allocation_pct,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="no such goal")

    return RecordCreated(id=row.id, kind="funding")


@assets_router.post("/deposits", response_model=RecordCreated, status_code=201)
async def create_deposit(request: DepositCreate) -> RecordCreated:

    """Record a term or recurring deposit, whose kind decides which amount column is required."""

    async with session_scope() as session:
        row = await records_repository.create_deposit(
            session,
            user_id=request.user_id,
            kind=request.kind,
            institution=request.institution,
            interest_rate_percent=request.interest_rate_percent,
            opened_on=request.opened_on,
            matures_on=request.matures_on,
            principal=request.principal,
            monthly_contribution=request.monthly_contribution,
            compounding=request.compounding,
        )

        return RecordCreated(id=row.id, kind="deposit")


@assets_router.post("/holdings", response_model=RecordCreated, status_code=201)
async def create_holding(request: HoldingCreate) -> RecordCreated:

    """Record a position in one instrument, as units and cost rather than as a current value."""

    async with session_scope() as session:
        row = await records_repository.create_holding(
            session,
            user_id=request.user_id,
            kind=request.kind,
            instrument_name=request.instrument_name,
            units=request.units,
            average_cost=request.average_cost,
            as_of=request.as_of,
            isin=request.isin,
            scheme_code=request.scheme_code,
            folio_id=request.folio_id,
        )

        return RecordCreated(id=row.id, kind="holding")


@assets_router.post("/retirement", response_model=RecordCreated, status_code=201)
async def create_retirement_asset(request: RetirementAssetCreate) -> RecordCreated:

    """Record an accumulation scheme with the balance as of the date it was last confirmed."""

    async with session_scope() as session:
        row = await records_repository.create_retirement_asset(
            session,
            user_id=request.user_id,
            scheme=request.scheme,
            balance=request.balance,
            as_of=request.as_of,
            monthly_contribution=request.monthly_contribution,
            employer_contribution=request.employer_contribution,
            interest_rate_percent=request.interest_rate_percent,
            account_reference=request.account_reference,
        )

        return RecordCreated(id=row.id, kind="retirement_asset")


@assets_router.get("/holdings", response_model=HoldingsSummary)
async def list_holdings(user_id: int, limit: int = 500) -> HoldingsSummary:

    """Return this user's active positions and their totals, dated by the statement they came from."""

    return await holdings_repository.summary(user_id, limit=limit)
