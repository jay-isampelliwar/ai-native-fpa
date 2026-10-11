"""Business rules for listing, changing and removing any kind of saved item."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select

from app.db.enums import GoalAssetTable
from app.db.models import Goal, InsurancePolicy, Loan
from app.db.models.base import UserOwnedMixin
from app.features.coverage.service import CoverageService
from app.features.planning.repository import PlanningRepository
from app.features.records.base_repository import BaseUserRecordRepository
from app.features.records.exceptions import RecordError
from app.features.records.kinds import KINDS, RecordKind
from app.features.records.service import BaseRecordService


SYSTEM_COLUMNS = {"id", "user_id", "created_at", "updated_at"}
NOT_EDITABLE = {RecordKind.goal_allocations}


def editable_fields(kind: RecordKind) -> list[str]:

    """Return the fields of this kind that are both table columns and checked inputs."""

    info = KINDS[kind]

    columns = set(info.model.__table__.columns.keys()) - SYSTEM_COLUMNS

    return [name for name in info.schema.model_fields if name in columns]


class RecordService(BaseRecordService[BaseUserRecordRepository]):

    """The steps behind the list, update and delete tools for one session."""

    repository_class = BaseUserRecordRepository

    async def get_or_fail(self, user_id: int, kind: RecordKind, record_id: int) -> UserOwnedMixin:

        """Return the user's item of this kind, or refuse with a message the model can read."""

        info = KINDS[kind]

        record = await self.repo.get_for_user(info.model, record_id, user_id)

        if record is None:
            raise RecordError(f"No {info.label} with id {record_id}. Use list_records to see the saved ones.")

        return record

    async def list_records(self, user_id: int, kind: RecordKind) -> Sequence[UserOwnedMixin]:

        """Return every saved item of this kind for the user."""

        return await self.repo.list_for_user(KINDS[kind].model, user_id)

    async def update_record(
        self,
        user_id: int,
        kind: RecordKind,
        record_id: int,
        changes: dict[str, Any],
        ) -> dict[str, Any]:

        """Merge the changes into the saved item, run the same checks as when adding, then save the changed fields."""

        if kind in NOT_EDITABLE:
            raise RecordError("Goal allocations are changed with allocate_goal.")

        if not changes:
            raise RecordError("Nothing to update.")

        allowed = editable_fields(kind)

        unknown = [name for name in changes if name not in allowed]

        if unknown:
            raise RecordError(f"Cannot change {', '.join(unknown)}. Fields you can change: {', '.join(allowed)}.")

        record = await self.get_or_fail(user_id, kind, record_id)

        current = {name: getattr(record, name) for name in allowed}

        checked = KINDS[kind].schema(**{**current, **changes})

        fields = {name: getattr(checked, name) for name in changes}

        await self.repo.update_for_user(KINDS[kind].model, record_id, user_id, fields)

        await self.session.commit()

        return fields

    async def refuse_if_linked(self, user_id: int, kind: RecordKind, record_id: int) -> None:

        """Refuse to remove a family member or property that other saved items still point at."""

        links = []

        if kind == RecordKind.family:
            links = [(Goal, "goal"), (InsurancePolicy, "insurance policy")]
            column = "family_member_id"

        elif kind == RecordKind.physical_assets:
            links = [(Loan, "loan")]
            column = "physical_asset_id"

        for model, label in links:

            query = select(model.id).where(model.user_id == user_id, getattr(model, column) == record_id).limit(1)

            linked_id = await self.session.scalar(query)

            if linked_id is not None:
                raise RecordError(
                    f"Cannot remove this {KINDS[kind].label}: {label} id {linked_id} is linked to it. Change or remove that first."
                    )

    async def delete_record(self, user_id: int, kind: RecordKind, record_id: int) -> UserOwnedMixin:

        """Remove the item and its goal allocations, and put its section back to pending when it was the last one."""

        record = await self.get_or_fail(user_id, kind, record_id)

        await self.refuse_if_linked(user_id, kind, record_id)

        planning = PlanningRepository(self.session)

        if kind == RecordKind.goals:
            await planning.delete_allocations_for_goal(user_id, record_id)

        elif kind.value in GoalAssetTable.__members__:
            await planning.delete_allocations_for_asset(user_id, GoalAssetTable(kind.value), record_id)

        await self.repo.delete_for_user(KINDS[kind].model, record_id, user_id)

        section = KINDS[kind].coverage

        if section is not None:
            await CoverageService(self.session).reset_if_empty(user_id, section)

        await self.session.commit()

        return record
