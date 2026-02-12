# from contextlib import asynccontextmanager
# from fastapi.responses import JSONResponse
# from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from fastapi import FastAPI, HTTPException
import logging
from pydantic import BaseModel

from app.core.exceptions import BaseAppException
from app.agent.mcp_client import MCPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# logger = get_logger(level="INFO", name=__name__)

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     try:
#         get_mongo_client()
#         pg_client = PostgresHelper()
#         yield
#     finally:
#         mongo_client = get_mongo_client()
#         mongo_client.close()
#         pg_client.close()
#         logger.info("MongoDB client closed")
        

app = FastAPI(
    title="Application API",
    description="API endpoints for Application",
    openapi_url="/ueba/api/openapi.json",
    docs_url="/ueba/api/docs",  # Custom Swagger URL
    # lifespan=lifespan, 
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# @app.exception_handler(APIException)
# async def global_exception_handler(_: Request, exc: APIException):
#     return JSONResponse(
#         status_code=exc.status_code,
#         content={"name": exc.name, "message": exc.message, "status": exc.status, "result": exc.result}
#     )


class QueryRequest(BaseModel):
    """Request model for agent queries."""
    query: str
    # server_name: Optional[str] = "mitre_attack"


class QueryResponse(BaseModel):
    """Response model for agent queries."""
    result: str
    message: str

@app.post("/bloo/agent", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """
    Send a query to the MCP-powered agent.
    
    The agent will connect to the specified MCP server and use available tools
    to answer the query.
    """
    try:
        logger.info(f"Received query: {request.query[:100]}...")
        
        mcp_client = MCPClient()
        response = await mcp_client.query(request.query)
        
        return QueryResponse(
            result=response,
            message="Query processed successfully"
        )
        
    except BaseAppException as e:
        logger.error(f"Agent error: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))