"""Errors the profile service raises for the tool to turn into a reply the model can read."""

from app.features.records.exceptions import RecordError


class ProfileError(RecordError):

    """A profile change was refused, with a message that says why."""


class UserNotFound(ProfileError):

    """The signed-in user's row does not exist any more."""
