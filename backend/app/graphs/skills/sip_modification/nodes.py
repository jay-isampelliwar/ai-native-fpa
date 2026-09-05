"""The four steps that turn a request to change an SIP into a proposal awaiting approval.

The amount is parsed with a regular expression, not with a model, and that is a deliberate
trade. A model would handle more phrasings; it would also occasionally read "raise it by five
thousand" as fifteen thousand, and the failure mode of a misread amount on a mandate is a wrong
debit every month until someone notices. When the pattern does not match, the skill refuses and
says what it could not read, which a user can correct in one message.

``by`` and ``to`` mean different things and both are common. "Raise my SIP by 5000" is an
increment; "raise it to 15000" is a target. Treating them the same is the single most likely way
to propose a change nobody asked for, so the preposition is matched explicitly and an ambiguous
phrasing is refused rather than guessed.

Affordability is judged against ``investable_surplus`` rather than ``free_surplus``, because the
amount already going into this SIP is redirectable and should not be counted against the increase.
The check does not block the proposal - a user may knowingly stretch - but it is stated on the
card they approve.

``propose_change`` writes the pending approval row before returning. The graph interrupts
immediately afterwards, and a proposal that existed only in graph state would be unrecoverable if
the process restarted while the user was deciding.
"""

import re
from decimal import Decimal, InvalidOperation

from app.calculations.cashflow.v1 import CALCULATOR_VERSION as CASHFLOW_VERSION
from app.calculations.cashflow.v1 import CashflowInput, run_cashflow
from app.approvals.store import approval_store
from app.db.session import session_scope
from app.graphs.skills.sip_modification.definition import DEFINITION
from app.graphs.skills.sip_modification.schemas import SipModificationState
from app.repositories import get_cashflow_repository
from app.ui.builders import kpi, note, rupees

AMOUNT_PATTERN = re.compile(
    r"(?P<preposition>\bby\b|\bto\b)?\s*(?:inr|rs\.?|₹)?\s*(?P<amount>\d[\d,]*(?:\.\d{1,2})?)\s*(?P<unit>k|lakh|lakhs|l)?",
    re.IGNORECASE,
)

STOP_WORDS = frozenset({"pause", "stop", "halt", "cancel"})

UNIT_MULTIPLIERS = {"k": Decimal("1000"), "lakh": Decimal("100000"), "lakhs": Decimal("100000"), "l": Decimal("100000")}


def parse_amount(message: str) -> tuple[Decimal | None, str | None, str | None]:

    """Read the requested amount and whether it is an increment or a target, refusing when unclear."""

    lowered = message.lower()

    if any(word in lowered.split() for word in STOP_WORDS):
        return None, "pause", None

    match = AMOUNT_PATTERN.search(lowered)

    if match is None:
        return None, None, "I could not find an amount in that request"

    try:
        amount = Decimal(match.group("amount").replace(",", ""))

    except InvalidOperation:
        return None, None, "I could not read the amount in that request"

    unit = match.group("unit")

    if unit:
        amount *= UNIT_MULTIPLIERS[unit.lower()]

    preposition = match.group("preposition")

    if preposition is None:
        return None, None, "I could not tell whether you meant to raise it by that amount or to that amount"

    return amount, "increase_by" if preposition.lower() == "by" else "set_amount", None


async def parse_request(state: SipModificationState) -> dict:

    """Work out which SIP is meant and what the user wants it changed to, refusing an unclear request."""

    amount, action, failure = parse_amount(state.message)

    if failure:
        return {"failure_reason": failure}

    records = await get_cashflow_repository().get_cashflow_records(state.user_id)

    if not records.sips:
        return {"failure_reason": "you do not have any active SIPs"}

    words = {word.strip(".,?!").lower() for word in state.message.split()}

    chosen = records.sips[0]

    for sip in records.sips:

        if words & {word.lower() for word in sip.scheme_name.split()}:
            chosen = sip
            break

    if action == "pause":
        return {"target_sip": chosen, "requested_action": "pause", "evidence_ids": [chosen.id]}

    target = chosen.amount + amount if action == "increase_by" else amount

    return {
        "target_sip": chosen,
        "requested_amount": target,
        "requested_action": "set_amount",
        "evidence_ids": [chosen.id],
    }


async def assess_affordability(state: SipModificationState) -> dict:

    """Compute what the change costs against real surplus, so the card states it rather than implying it."""

    if state.target_sip is None:
        return {}

    records = await get_cashflow_repository().get_cashflow_records(state.user_id)

    result = run_cashflow(
        CashflowInput(
            income=[record.monthly_amount for record in records.income],
            expenses=[record.monthly_amount for record in records.expenses],
            emis=[record.monthly_amount for record in records.emis],
            sips=[record.monthly_amount for record in records.sips],
        )
    )

    if state.requested_action == "pause":
        return {
            "cashflow": result,
            "affordable": True,
            "headroom": result.free_surplus + state.target_sip.amount,
            "evidence_ids": state.evidence_ids + records.evidence_ids,
            "calculator_versions": [CASHFLOW_VERSION],
        }

    increase = (state.requested_amount or Decimal("0")) - state.target_sip.amount
    headroom = result.free_surplus - increase

    return {
        "cashflow": result,
        "affordable": headroom >= Decimal("0"),
        "headroom": headroom,
        "evidence_ids": state.evidence_ids + records.evidence_ids,
        "calculator_versions": [CASHFLOW_VERSION],
    }


async def propose_change(state: SipModificationState) -> dict:

    """Persist the proposal so it survives a restart, and build the card the user will approve."""

    sip = state.target_sip

    if sip is None:
        return {}

    if state.requested_action == "pause":
        before_state = {"status": "active"}
        after_state = {"status": "paused"}
        changes = [{"label": sip.scheme_name, "before": "Active", "after": "Paused"}]

    else:
        before_state = {"amount": str(sip.amount)}
        after_state = {"amount": str(state.requested_amount)}
        changes = [
            {
                "label": f"{sip.scheme_name} monthly amount",
                "before": rupees(sip.amount),
                "after": rupees(state.requested_amount or Decimal("0")),
            }
        ]

    async with session_scope() as session:
        approval = await approval_store.create(
            session,
            user_id=state.user_id,
            conversation_id=state.conversation_id,
            correlation_id=state.correlation_id,
            skill_name=DEFINITION.name,
            skill_version=DEFINITION.version,
            action_kind="update_sip_instruction",
            after_state=after_state,
            before_state=before_state,
            target_table="sip_records",
            target_id=sip.id,
            evidence_ids=state.evidence_ids,
        )

        approval_id = approval.id

    blocks = [kpi("Surplus after this change", state.headroom or Decimal("0"), state.evidence_ids)]

    if state.affordable is False:
        blocks.append(
            note(
                "This would take you past your current surplus, so something else has to give.",
                level="warning",
                evidence=state.evidence_ids,
            )
        )

    answer = (
        f"Pause {sip.scheme_name}?"
        if state.requested_action == "pause"
        else f"Change {sip.scheme_name} from {rupees(sip.amount)} to {rupees(state.requested_amount or Decimal('0'))} a month?"
    )

    return {
        "approval_id": approval_id,
        "before_state": before_state,
        "after_state": after_state,
        "proposed_changes": changes,
        "blocks": blocks,
        "answer": answer,
    }
