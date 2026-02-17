from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import logging

from core.config import settings
from src.schemas import QueryRequest

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Bloo Agent API Starting up...")
    yield
    logging.info("Bloo Agent API Shutting down...")

app = FastAPI(
    root_path="/bloo-agent-api",
    title=settings.APP_NAME,
    description="Bloo Agent API",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
    openapi_url="/openapi.json" if settings.APP_ENV == "development" else None
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
    return JSONResponse(
        status_code=200,
        content={"status": "query executed"}
    )
    # return StreamingResponse(
    #     stream_workflow_events(request.query, request.conversation_id),
    #     media_type="text/event-stream",
    #     headers={
    #         "Cache-Control": "no-cache",
    #         "Connection": "keep-alive",
    #         "X-Accel-Buffering": "no"
    #     }
    # )