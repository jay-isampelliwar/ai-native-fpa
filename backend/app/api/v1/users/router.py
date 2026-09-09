"""Creating the user row every other table points at, which nothing did before a person hit a commit.

Every record table has a foreign key to ``users``. The import tables do not, so a client identifying
itself as an id nobody had created could upload a statement, watch it extract, review twelve rows and
only then meet a foreign key violation - after all the work, at the one moment that writes. The id
was typed into a gate that stored it in the browser and told no one.

This endpoint is that missing step. A client registers the id it is about to use, and the row exists
before anything references it. It is idempotent because identity here is a number a person chose: the
same number tomorrow is the same person, and a second call is a return visit rather than a conflict.

Nothing is authenticated, and that is stated rather than hidden. Anyone can claim any id, which is
exactly as true as it was when the id was only kept in local storage - this changes where the id is
recorded, not how much it proves. The shape is what a real sign in will replace: one call that turns
a claim into a row, with everything downstream unchanged.
"""

from fastapi import APIRouter

from app.api.v1.users.schemas import UserRead, UserRegistration
from app.db.session import session_scope
from app.models.orm.system import UserRow

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead)
async def register_user(request: UserRegistration) -> UserRead:

    """Create this id if it is new and return it either way, so a client can call it on every visit."""

    async with session_scope() as session:

        existing = await session.get(UserRow, request.user_id)

        if existing is not None:
            return UserRead(id=existing.id, display_name=existing.display_name, created=False)

        display_name = request.display_name or f"User {request.user_id}"

        session.add(UserRow(id=request.user_id, display_name=display_name))

    return UserRead(id=request.user_id, display_name=display_name, created=True)
