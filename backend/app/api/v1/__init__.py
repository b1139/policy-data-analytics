"""API v1 routers and route registry."""

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.health import router as health_router
from app.api.v1.websocket import router as websocket_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(analysis_router)
api_v1_router.include_router(websocket_router)

__all__ = ["api_v1_router", "health_router", "analysis_router", "websocket_router"]
