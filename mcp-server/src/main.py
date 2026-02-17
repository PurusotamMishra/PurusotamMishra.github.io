from fastmcp import FastMCP
from core.config import settings
from starlette.requests import Request
from starlette.responses import PlainTextResponse


# For now, create MCP without auth - auth can be added via middleware later
# FastMCP's auth parameter requires specific auth provider objects
mcp = FastMCP(
    name=settings.APP_NAME,
)


@mcp.tool()
def ping() -> str:
    """Health check and connection, returns 'pong'"""
    return "pong"


@mcp.tool(name="query-execute")
def query_execute(query: str) -> str:
    """Execute query"""
    return f"Query executing {query} is done"


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    """
    Health check endpoint (unauthenticated)
    """
    return PlainTextResponse("MCP server is running")
