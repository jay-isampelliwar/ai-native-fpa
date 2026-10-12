"""Basic money helpers: turn any payment into a monthly amount, round to rupees, and write Indian-style numbers."""

from decimal import ROUND_HALF_UP, Decimal

from app.db.enums import PaymentFrequency


MONTHS_PER_PAYMENT = {
    PaymentFrequency.monthly: 1,
    PaymentFrequency.quarterly: 3,
    PaymentFrequency.half_yearly: 6,
    PaymentFrequency.yearly: 12,
    }


def to_monthly(
    amount: Decimal | float,
    frequency: PaymentFrequency,
    ) -> float:

    """Spread one payment evenly over the months it covers, so a yearly ₹12,000 becomes ₹1,000 a month."""

    return float(amount) / MONTHS_PER_PAYMENT[frequency]


def rupees(value: float) -> int:

    """Round to the nearest whole rupee, halves going up."""

    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def indian_number(value: float) -> str:

    """Write a rupee amount with Indian grouping, so 1000000 becomes 10,00,000."""

    whole = rupees(value)
    sign = "-" if whole < 0 else ""
    digits = str(abs(whole))

    if len(digits) <= 3:
        return f"{sign}{digits}"

    head, tail = digits[:-3], digits[-3:]
    pairs = []

    while len(head) > 2:

        pairs.insert(0, head[-2:])

        head = head[:-2]

    return f"{sign}{','.join([head, *pairs])},{tail}"
