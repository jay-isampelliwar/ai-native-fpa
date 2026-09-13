"""What a client sends to claim an id and what comes back, which is deliberately almost nothing.

Identity in this phase is an integer a person types. There is no password, no token and no email,
because the product being proven is the planner rather than the login - so the only thing this
surface can honestly report is that the id now exists and what it is called.

``created`` is returned rather than expressed as a status code. Registering is idempotent: the same
id sent twice is the same person, not a conflict, and a client that reopens the app should not have
to treat its second visit differently from its first.
"""

from pydantic import BaseModel, Field


class UserRegistration(BaseModel):

    """A client claiming an id, with the name to show if this is the first time it has been seen."""

    user_id: int = Field(gt=0)
    display_name: str | None = Field(default=None, max_length=80)


class UserRead(BaseModel):

    """The registered person, and whether this call is what brought them into existence."""

    id: int
    display_name: str
    created: bool = False
