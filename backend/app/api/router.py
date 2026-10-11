"""The top-level API router that gathers every module's routes under /api."""

from fastapi import APIRouter

from app.features.auth.router import router as auth_router
from app.features.conversations.router import router as conversations_router
from app.features.runs.router import router as runs_router


api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(runs_router)
api_router.include_router(conversations_router)
