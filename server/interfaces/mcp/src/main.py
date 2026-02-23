"""
fastmcp_google_oauth_server.py

Minimal FastMCP server protected with Google OAuth (OAuth 2.1 via FastMCP's GoogleProvider).

Usage:
  1. Install dependencies (preferably in a venv):
       pip install fastmcp

     (FastMCP's GoogleProvider handles the upstream Google calls; you only need FastMCP itself for this example.)

  2. Create an OAuth client in Google Cloud Console:
     - Configure OAuth consent screen.
     - Create an OAuth Client ID (Application type: Web application).
     - Add your server base URL (e.g. http://localhost:8081/sse) to "Authorized JavaScript origins".
     - Add the redirect URI: <BASE_URL>/auth/callback (FastMCP's proxy will use /auth/callback).
     - Grab CLIENT_ID and CLIENT_SECRET.

  3. Run:
       export GOOGLE_CLIENT_ID="..."
       export GOOGLE_CLIENT_SECRET="..."
       export BASE_URL="http://localhost:8081/sse"
       python fastmcp_google_oauth_server.py

  4. Use an MCP-capable client (or FastMCP Inspector / MCP Inspector UI) to connect. FastMCP will expose the OAuth endpoints and proxy to Google for you.

Notes:
  - This example demonstrates using the built-in GoogleProvider and shows how to read the access token inside a tool using
    `get_access_token()` to customize behavior / return caller identity to the client.
  - In production: use HTTPS, set proper allowed redirect URIs in Google Cloud Console, limit scopes, and enable auditing.

References:
  - FastMCP Google provider + OAuth Proxy integration (used in this example).
  - Google OAuth 2.1 / OAuth for Web Server Apps.

"""

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import JSONResponse
import logging
import os


from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token, AccessToken

# Read configuration from environment variables (simple and convenient for examples)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8081")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    raise RuntimeError("Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")

# Create the GoogleProvider. FastMCP's provider implements an OAuth proxy pattern so you can use
# a pre-registered Google OAuth app and still support MCP clients that expect dynamic DCR flows.
# See the docs for additional configuration options (e.g., required_scopes, base_url override).
auth = GoogleProvider(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    base_url=BASE_URL,
    # required_scopes=["openid", "email", "profile", "https://www.googleapis.com/auth/userinfo.email"]
)



from core.engine.executor import WorkflowExecutor
from core.engine.registry import WorkflowRegistry
from interfaces.mcp.auth.validator import CustomTokenVerifier

token_verifier = CustomTokenVerifier()

mcp = FastMCP(
    name="Bloo MCP Server",
    # auth=token_verifier
    auth=auth
)

registry = WorkflowRegistry()
@mcp.tool()
def ping() -> str:
    """Health check and connection, returns 'pong'"""
    return "pong"


@mcp.tool(name="query-execute")
async def query_execute(query: str):
    """Execute query"""
    try:
        result = await anext(WorkflowExecutor(registry).execute("fetch_logs", {"user_query": query}, stream=False))

        logging.error(f"result-mcp-tool: {result}")
        return {
            "type": "query_result",
            "data": result,
            "status": "success",
            "message": "Query executed successfully"
        }
    except Exception as e:
        logging.error(f"Error executing query: {e}")
        return {
            "type": "error",
            "status": "error",
            "message": f"Error executing query: {e}"
        }

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """
    Health check endpoint (unauthenticated)
    """
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "message": "MCP server is running"}
    )


# @mcp.tool(auth=require_scopes("openid", "https://www.googleapis.com/auth/userinfo.email"))
@mcp.tool(name="whoami")
def whoami() -> dict:
    """Return information about the authenticated caller.

    This uses `get_access_token()` to access the current token that FastMCP validated for us.
    The token object usually provides `claims` and basic fields (implementation varies slightly by provider).
    """
    token: AccessToken | None = get_access_token()

    if token is None:
        return {"error": "not_authenticated"}

    # `token.claims` is provided by FastMCP's token verifier (for OIDC providers, claims will be present)
    claims = getattr(token, "claims", None)

    # Provide a conservative, safe fallback set of identity fields
    identity = {
        "sub": getattr(token, "sub", None) or (claims or {}).get("sub"),
        "email": (claims or {}).get("email"),
        "email_verified": (claims or {}).get("email_verified"),
        "raw_token": getattr(token, "token", None),  # don't expose this in prod
    }

    # Remove None values
    identity = {k: v for k, v in identity.items() if v is not None}

    return {"identity": identity}