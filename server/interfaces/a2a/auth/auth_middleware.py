from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED
import os

from interfaces.a2a.auth.validator import check_token


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate tokens for A2A server.
    Uses the same token validation logic as the MCP server.
    """
    
    # Paths that don't require authentication
    EXCLUDED_PATHS = ["/health", "/docs", "/openapi.json", "/redoc"]
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return await call_next(request)
        
        # Extract token from Authorization header
        authorization = request.headers.get("Authorization", "")
        
        if not authorization.startswith("Bearer "):
            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"error": "Missing or invalid Authorization header"}
            )
        
        token = authorization.replace("Bearer ", "").strip()
        
        # Validate token using the same logic as MCP server
        is_valid = await check_token(token, ["search"])
        
        if not is_valid:
            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid or expired token"}
            )
        
        # Add token to request state for use in handlers if needed
        request.state.token = token
        
        return await call_next(request)