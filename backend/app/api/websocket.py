"""WebSocket API module re-exporting v1 WebSocket router."""

from app.api.v1.websocket import router, websocket_analysis_endpoint

__all__ = ["router", "websocket_analysis_endpoint"]
