"""State for the SIP modification subgraph, carrying a proposal from request to approval card.

Every field below the request is filled by exactly one node, so a partly completed run says where
it stopped. A state with ``target_sip`` set but no ``proposed_amount`` is a request that found the
SIP and could not work out what to change it to, and ``failure_reason`` says which.

``before_state`` and ``after_state`` are built here in the shape the approval table stores and the
approval card renders. Building them once, in the node that decided the change, means the figure a
user approves, the figure written to the database, and the figure applied by the write tool are the
same object rather than three derivations of it.

Nothing here holds a model message list. The subgraph makes no model call: the amount is parsed
deterministically and the affordability decision is arithmetic.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.calculations.cashflow.v1 import CashflowResult
from app.models.finance import SipRecord
from app.ui.blocks import Block


class SipModificationState(BaseModel):

    """Accumulating state for one SIP change request as it moves through parse, assess and propose."""

    model_config = {"arbitrary_types_allowed": True}

    user_id: int
    conversation_id: str
    correlation_id: str
    message: str

    requested_amount: Decimal | None = None
    requested_action: str = "set_amount"

    target_sip: SipRecord | None = None
    cashflow: CashflowResult | None = None

    affordable: bool | None = None
    headroom: Decimal | None = None

    approval_id: str | None = None
    before_state: dict | None = None
    after_state: dict | None = None

    evidence_ids: list[str] = Field(default_factory=list)
    calculator_versions: list[str] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    proposed_changes: list[dict] = Field(default_factory=list)

    failure_reason: str | None = None
    answer: str | None = None
