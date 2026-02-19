from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.responses import JSONResponse
import logging

from core.engine.executor import WorkflowExecutor
from core.engine.registry import WorkflowRegistry
from interfaces.mcp.auth.validator import CustomTokenVerifier

token_verifier = CustomTokenVerifier()

mcp = FastMCP(
    name="Bloo MCP Server",
    auth=token_verifier
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
