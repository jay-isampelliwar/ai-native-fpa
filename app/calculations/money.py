"""The single rounding and currency policy every calculator in the backend obeys.

Money is ``Decimal``, never ``float``. A float cannot represent 0.1 exactly, so a
retirement projection built from floats drifts by rupees over three hundred monthly
compounding steps and two runs of the same input can disagree. Every amount entering a
calculator passes through ``to_money`` and every amount leaving one is quantised, which
makes results reproducible and comparable across runs.

The quantum is one paisa and the mode is ROUND_HALF_UP, matching how Indian financial
statements round rather than Python's default banker's rounding. This is a product
decision as much as a technical one: a user checking our number against their bank's
statement must see the same paisa.

Rounding happens at the boundary, not in the middle. Intermediate arithmetic inside a
calculator stays at full ``Decimal`` precision and only the returned figures are
quantised, because rounding each step compounds the error the policy exists to prevent.

``to_money`` accepts strings and ints but deliberately refuses floats. Accepting one
would silently import the imprecision this module exists to keep out, so a float reaching
a calculator is a bug to fix at the source rather than to paper over here.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISA = Decimal("0.01")
ZERO = Decimal("0.00")


class MoneyError(ValueError):

    """Raised when a value cannot be treated as a currency amount under the house policy."""


def to_money(value: Decimal | int | str) -> Decimal:

    """Convert a safe input into a Decimal amount, refusing floats so imprecision cannot enter."""

    if isinstance(value, float):
        raise MoneyError("floats are not accepted as money, pass a Decimal, int or string")

    try:
        return Decimal(value)

    except (InvalidOperation, TypeError) as exc:
        raise MoneyError(f"{value!r} is not a valid currency amount") from exc


def quantise(value: Decimal) -> Decimal:

    """Round one amount to paisa using the house mode, applied only to figures leaving a calculator."""

    return value.quantize(PAISA, rounding=ROUND_HALF_UP)


def total(values: list[Decimal]) -> Decimal:

    """Sum amounts at full precision and quantise once, so a long list rounds a single time."""

    return quantise(sum(values, ZERO))


def percentage(part: Decimal, whole: Decimal) -> Decimal:

    """Express one amount as a percentage of another, returning zero rather than dividing by zero."""

    if whole == ZERO:
        return ZERO

    return quantise(part / whole * Decimal("100"))
