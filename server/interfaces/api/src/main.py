from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import logging
import os

from interfaces.api.src.schemas import QueryRequest
from core.engine.executor import WorkflowExecutor
from core.engine.registry import WorkflowRegistry

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Bloo Agent API Starting up...")
    yield
    logging.info("Bloo Agent API Shutting down...")

registry = WorkflowRegistry()

app = FastAPI(
    root_path="/bloo-agent-api",
    title="Bloo Agent API",
    description="Bloo Agent API",
    debug=os.getenv('DEBUG', 'FALSE').lower() == 'true',
    lifespan=lifespan,
    docs_url="/docs" if os.getenv('APP_ENV', 'development').lower() == 'development' else None, 
    redoc_url="/redoc" if os.getenv('APP_ENV', 'development').lower() == 'development' else None,
    openapi_url="/openapi.json" if os.getenv('APP_ENV', 'development').lower() == 'development' else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "healthy"}
    )

@app.post("/api/query")
async def query_endpoint(request: QueryRequest):
    """
    Execute a DQL agent query with SSE streaming using b_copilot.
    
    Returns Server-Sent Events stream with incremental results.
    """
    result = await anext(WorkflowExecutor(registry).execute("fetch_logs", {"user_query": request.query}, stream=False))
    return {
        "type": "query_result",
        "data": result,
        "status": "success",
        "message": "Query executed successfully"
    }
    # return StreamingResponse(
    #     stream_workflow_events(request.query, request.conversation_id),
    #     media_type="text/event-stream",
    #     headers={
    #         "Cache-Control": "no-cache",
    #         "Connection": "keep-alive",
    #         "X-Accel-Buffering": "no"
    #     }
    # )