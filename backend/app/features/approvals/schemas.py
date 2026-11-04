"""Request bodies for the approvals route."""

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class ApprovalChoice(StrEnum):

    """What the user clicked on the approval card."""

    approve = "approve"
    reject = "reject"


class ApprovalEdits(BaseModel):

    """Values the user fixed on a confirm card before approving it."""

    units: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


class ApprovalDecisionRequest(BaseModel):

    """The user's answer to one approval card, with any values they fixed."""

    decision: ApprovalChoice
    edits: ApprovalEdits | None = None

    @model_validator(mode="after")
    def edits_only_on_approve(self) -> Self:

        """Refuse fixed values on a reject, since nothing runs then."""

        if self.edits is not None and self.decision != ApprovalChoice.approve:
            raise ValueError("Edits can only be sent with approve")

        return self

    def edit_values(self) -> dict[str, str]:

        """The fixed values as plain text, leaving out the ones not sent."""

        if self.edits is None:
            return {}

        return {name: format(value, "f") for name, value in self.edits.model_dump(exclude_none=True).items()}
