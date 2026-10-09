"""Errors the runs service raises for the route to turn into HTTP responses."""


class ConversationNotFound(Exception):

    """The conversation does not exist or belongs to another user."""


class RunAlreadyActive(Exception):

    """The conversation already has a run that is queued, running or being cancelled."""
