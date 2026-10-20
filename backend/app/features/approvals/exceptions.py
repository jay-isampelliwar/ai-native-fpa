"""Errors the approvals service raises for the route to turn into HTTP responses."""


class ApprovalNotFound(Exception):

    """The approval does not exist, belongs to another user, or is not part of this run."""


class ApprovalNotPending(Exception):

    """The approval was already approved, rejected, expired or cancelled."""


class ApprovalExpired(Exception):

    """The approval waited longer than its time limit, so it can no longer be decided."""
