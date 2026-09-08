"""The version 1 API surface, assembled from one router per bounded area.

Everything reachable over HTTP is included here, so the complete public surface of the
backend is one file long. A capability that is not in this list cannot be called, which
makes reviewing what the service exposes a matter of reading twenty lines rather than
searching the tree.

The version lives in the path rather than in a header. Financial clients are long lived
and a mobile app in a user's pocket may lag the server by months, so ``/api/v1`` staying
frozen while ``/api/v2`` is developed is cheaper than negotiating a version on every
request.

``/users`` is mounted first and is the one every other surface assumes. Identity in this phase is an
integer a client sends, and nothing was creating the row it names - so a person could upload, extract
and review, and meet a foreign key violation at the commit. Registering an id is now a call rather
than an assumption.

Seven surfaces follow and they split along one line. ``/workspace`` sits with the readers and
is the standing view rather than an answer to a question: it reports what the planner currently knows
about a person and what it still needs, which is what the panel beside the conversation renders.
 ``/alerts`` sits with the readers: it
observes and never acts, so a finding it raises is dealt with through the ordinary approval path
like any other change.

The rest split as follows. ``/planner`` reads and explains;
``/records``, ``/goals``, ``/assets`` and ``/documents`` write - and ``/documents`` only writes
after a person has reconciled what was extracted. They share this router but not a prefix,
because the separation is the product rule: data enters through validated forms a person
filled in, and the conversation never writes. A single prefix would invite exactly the
confusion the design exists to prevent.
"""

from fastapi import APIRouter

from app.api.v1.alerts.router import router as alerts_router
from app.api.v1.documents.router import router as documents_router
from app.api.v1.goals.router import assets_router, router as goals_router
from app.api.v1.planner.router import router as planner_router
from app.api.v1.records.router import router as records_router
from app.api.v1.users.router import router as users_router
from app.api.v1.workspace.router import router as workspace_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(users_router)
api_router.include_router(planner_router)
api_router.include_router(records_router)
api_router.include_router(goals_router)
api_router.include_router(assets_router)
api_router.include_router(documents_router)
api_router.include_router(alerts_router)
api_router.include_router(workspace_router)
