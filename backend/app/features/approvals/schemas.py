"""Request bodies for the approvals route."""

from enum import StrEnum

from pydantic import BaseModel


class ApprovalChoice(StrEnum):

    """What the user clicked on the approval card."""

    approve = "approve"
    reject = "reject"


class ApprovalDecisionRequest(BaseModel):

    """The user's answer to one approval card."""

    decision: ApprovalChoice
