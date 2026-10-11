"""Database reads and writes for users during sign up and sign in."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:

    """All user queries for one request, sharing that request's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the session this request opened, so every method talks through it."""

        self.session = session

    async def get_by_email(self, email: str) -> User | None:

        """Return the user with this email, matching without caring about upper or lower case."""

        query = select(User).where(func.lower(User.email) == email.lower())

        return await self.session.scalar(query)

    async def get_by_id(self, user_id: int) -> User | None:

        """Return the user with this id, or None when there is none."""

        return await self.session.get(User, user_id)

    async def create_user(
        self,
        name: str,
        email: str,
        password_hash: str,
        ) -> User:

        """Insert a new user and flush, so the database gives it an id."""

        user = User(name=name, email=email.lower(), password_hash=password_hash)

        self.session.add(user)

        await self.session.flush()

        return user
