"""Errors any record service raises for the tool to turn into a reply the model can read."""


class RecordError(Exception):

    """A save was refused, with a message that says why."""


class RecordNotFound(RecordError):

    """The item the change points at is not saved for this user."""


class RecordConflict(RecordError):

    """The change clashes with something already saved, so it was refused."""


class RecordExists(RecordConflict):

    """A matching row is already saved, so a second one was not added."""

    def __init__(
        self,
        label: str,
        record_id: int,
        hint: str | None = None,
        ) -> None:

        """Keep the id of the row already saved, so the model can refer to it, and say what to do instead."""

        message = f"This {label} already exists with id {record_id}."

        super().__init__(f"{message} {hint}" if hint else message)

        self.record_id = record_id


class HoldingMissing(RecordNotFound):

    """A SIP was asked for a stock or fund the user does not hold yet, so nothing was saved."""

    def __init__(self, name: str) -> None:

        """Say which fund is not held and what to do first."""

        super().__init__(
            f"The user does not hold {name} yet, so the SIP was not saved. Ask how many units they hold "
            "or how much they have invested in it, save it with add_stock_or_fund, then add the SIP."
            )


class FamilyMemberNotFound(RecordNotFound):

    """The family member named in a save is not in the user's family list."""

    def __init__(self, name: str) -> None:

        """Say which name was not found, so the model can ask the user."""

        super().__init__(f"No family member named '{name}' is saved. Add them first with add_family_member.")
