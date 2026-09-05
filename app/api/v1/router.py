"""The version 1 API surface, assembled from one router per bounded area.

Everything reachable over HTTP is included here, so the complete public surface of the
backend is one file long. A capability that is not in this list cannot be called, which
makes reviewing what the service exposes a matter of reading twenty lines rather than
searching the tree.

The version lives in the path rather than in a header. Financial clients are long lived
and a mobile app in a user's pocket may lag the server by months, so ``/api/v1`` staying
frozen while ``/api/v2`` is developed is cheaper than negotiating a version on every
request.

Only the planner is mounted in Phase 1. Record entry endpoints arrive with Phase 2 and
are deliberately separate from this router: data goes into the database through ordinary
validated forms, never through the conversation, so the two surfaces should not share a
prefix and invite the confusion.
"""

from fastapi import APIRouter

from app.api.v1.planner.router import router as planner_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(planner_router)
