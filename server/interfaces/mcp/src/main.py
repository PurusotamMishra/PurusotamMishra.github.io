from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import JSONResponse

from core.workflows.fetch_logs import fetch_logs


# For now, create MCP without auth - auth can be added via middleware later
# FastMCP's auth parameter requires specific auth provider objects
mcp = FastMCP(
    name="Bloo MCP Server",
)


@mcp.tool()
def ping() -> str:
    """Health check and connection, returns 'pong'"""
    return "pong"


@mcp.tool(name="query-execute")
async def query_execute(query: str) -> str:
    """Execute query"""
    result = await fetch_logs(query)
    return {
        "type": "query_result",
        "data": result,
        "status": "success",
        "message": "Query executed successfully"
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
