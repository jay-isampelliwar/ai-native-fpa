"""Request and response bodies for the auth routes."""

from typing import Self

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models import User


class SignUpRequest(BaseModel):

    """A new person's name, email and chosen password."""

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:

        """Drop spaces around the name and refuse a name that is only spaces."""

        value = value.strip()

        if not value:
            raise ValueError("Name cannot be empty")

        return value


class SignInRequest(BaseModel):

    """The email and password someone types to sign in."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):

    """The signed-in user as the frontend sees it, never with the password hash."""

    id: int
    name: str
    email: str

    @classmethod
    def from_user(cls, user: User) -> Self:

        """Build the response body from a user row."""

        return cls(id=user.id, name=user.name, email=user.email)
