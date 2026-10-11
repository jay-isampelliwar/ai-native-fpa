"""The statuses the agent may set on a coverage section, and the missing-data answer."""

from enum import StrEnum

from pydantic import BaseModel


class CoverageChoice(StrEnum):

    """A status the agent may set; provided is left out because only a real save sets it."""

    pending = "pending"
    none = "none"
    declined = "declined"


class MissingData(BaseModel):

    """The sections still to ask about, and the profile details still empty."""

    pending_sections: list[str]
    missing_profile_fields: list[str]
