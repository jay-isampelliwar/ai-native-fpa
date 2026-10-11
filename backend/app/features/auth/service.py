"""Business rules for signing up and signing in with email and password."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.features.auth.exceptions import EmailTaken, InvalidCredentials
from app.features.auth.repository import UserRepository
from app.features.auth.schemas import SignInRequest, SignUpRequest
from app.features.auth.security import hash_password, verify_password


class AuthService:

    """The steps behind the auth routes for one request, sharing that request's session."""

    def __init__(self, session: AsyncSession) -> None:

        """Keep the request's session and build the repository on top of it."""

        self.session = session
        self.repo = UserRepository(session)

    async def sign_up(self, body: SignUpRequest) -> User:

        """Create the user with a hashed password, refusing an email that is already used."""

        if await self.repo.get_by_email(body.email) is not None:
            raise EmailTaken

        try:
            user = await self.repo.create_user(body.name, body.email, hash_password(body.password))

            await self.session.commit()

        except IntegrityError as exc:

            await self.session.rollback()

            raise EmailTaken from exc

        return user

    async def sign_in(self, body: SignInRequest) -> User:

        """Return the user when the email and password match, otherwise raise one same error."""

        user = await self.repo.get_by_email(body.email)

        password_hash = user.password_hash if user is not None else None

        if not verify_password(body.password, password_hash) or user is None:
            raise InvalidCredentials

        return user
