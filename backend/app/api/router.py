"""The top-level API router that gathers every module's routes under /api."""

from fastapi import APIRouter

from app.features.chat.router import router as chat_router


api_router = APIRouter(prefix="/api")

api_router.include_router(chat_router)
