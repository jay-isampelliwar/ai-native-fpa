"""The version 1 API surface, assembled from one router per bounded area.

Everything reachable over HTTP is included here, so the complete public surface of the
backend is one file long. A capability that is not in this list cannot be called, which
makes reviewing what the service exposes a matter of reading twenty lines rather than
searching the tree.

The version lives in the path rather than in a header. Financial clients are long lived
and a mobile app in a user's pocket may lag the server by months, so ``/api/v1`` staying
frozen while ``/api/v2`` is developed is cheaper than negotiating a version on every
request.

Four surfaces are mounted and they split along one line. ``/planner`` reads and explains;
``/records``, ``/goals`` and ``/assets`` write. They share this router but not a prefix,
because the separation is the product rule: data enters through validated forms a person
filled in, and the conversation never writes. A single prefix would invite exactly the
confusion the design exists to prevent.
"""

from fastapi import APIRouter

from app.api.v1.goals.router import assets_router, router as goals_router
from app.api.v1.planner.router import router as planner_router
from app.api.v1.records.router import router as records_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(planner_router)
api_router.include_router(records_router)
api_router.include_router(goals_router)
api_router.include_router(assets_router)
