"""Errors any record service raises for the tool to turn into a reply the model can read."""


class RecordError(Exception):

    """A save was refused, with a message that says why."""


class RecordNotFound(RecordError):

    """The item the change points at is not saved for this user."""


class RecordConflict(RecordError):

    """The change clashes with something already saved, so it was refused."""


class RecordExists(RecordConflict):

    """A matching row is already saved, so a second one was not added."""

    def __init__(self, label: str, record_id: int) -> None:

        """Keep the id of the row already saved, so the model can refer to it."""

        super().__init__(f"This {label} already exists with id {record_id}.")

        self.record_id = record_id


class FamilyMemberNotFound(RecordNotFound):

    """The family member named in a save is not in the user's family list."""

    def __init__(self, name: str) -> None:

        """Say which name was not found, so the model can ask the user."""

        super().__init__(f"No family member named '{name}' is saved. Add them first with add_family_member.")
