import hmac
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from server import mcp

# ---------------------------------------------------------------------------
# Optional secret token middleware
# Set MCP_SECRET env var to restrict access to callers who know the token.
# Callers must include ?token=<secret> in the URL.
# Well-known discovery paths are always public (Claude.ai probes these first).
# ---------------------------------------------------------------------------

_SECRET = os.environ.get("MCP_SECRET", "")

_PUBLIC_PREFIXES = ("/.well-known/",)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _SECRET:
            path = request.url.path
            if not any(path.startswith(p) for p in _PUBLIC_PREFIXES):
                # Accept token via Authorization: Bearer header (preferred)
                # or ?token= query param (fallback for MCP clients).
                auth = request.headers.get("authorization", "")
                if auth.lower().startswith("bearer "):
                    token = auth[7:]
                else:
                    token = request.query_params.get("token", "")
                if not hmac.compare_digest(token, _SECRET):
                    return Response("Unauthorized", status_code=401)
        return await call_next(request)


app = mcp.streamable_http_app()

if _SECRET:
    app.add_middleware(TokenAuthMiddleware)
