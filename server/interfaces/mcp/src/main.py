from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import JSONResponse
import logging

from core.engine.executor import WorkflowExecutor
from core.engine.registry import WorkflowRegistry


# For now, create MCP without auth - auth can be added via middleware later
# FastMCP's auth parameter requires specific auth provider objects
mcp = FastMCP(
    name="Bloo MCP Server",
)

registry = WorkflowRegistry()
@mcp.tool()
def ping() -> str:
    """Health check and connection, returns 'pong'"""
    return "pong"


@mcp.tool(name="query-execute")
async def query_execute(query: str) -> JSONResponse:
    """Execute query"""
    try:
        result = await WorkflowExecutor(registry).execute("fetch_logs", {"user_query": query})
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Query executed successfully", "data": result}
        )
    except Exception as e:
        logging.error(f"Error executing query: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Error executing query: {e}"}
        )

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """
    Health check endpoint (unauthenticated)
    """
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "message": "MCP server is running"}
    )
