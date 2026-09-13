"""The version 1 API surface, assembled from one router per bounded area.

Everything reachable over HTTP is included here, so the complete public surface of the
backend is one file long. A capability that is not in this list cannot be called, which
makes reviewing what the service exposes a matter of reading ten lines rather than
searching the tree.

The version lives in the path rather than in a header. Financial clients are long lived
and a mobile app in a user's pocket may lag the server by months, so ``/api/v1`` staying
frozen while ``/api/v2`` is developed is cheaper than negotiating a version on every
request.

There are two surfaces left: who you are, and the conversation. ``/records``, ``/goals``,
``/assets``, ``/documents``, ``/alerts`` and ``/workspace`` were removed with the skills and
calculators that answered through them - forms, imports, findings and the standing panel are each a
feature to bring back deliberately rather than a route left open against code nothing calls.

``/users`` stays mounted first and is the one the other assumes. Identity in this phase is an integer
a client sends, and nothing else creates the row it names, so registering an id is a call rather than
an assumption.

``/planner`` is the conversation and writes nothing. That used to be a product rule enforced by
prefix - data entered through validated forms while the chat only read - and with the forms gone it is
simply what the agent can do: answer in prose.
"""

from fastapi import APIRouter

from app.api.v1.planner.router import router as planner_router
from app.api.v1.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(users_router)
api_router.include_router(planner_router)
