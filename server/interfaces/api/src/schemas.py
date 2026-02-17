"""
Pydantic models for FastAPI request/response validation.
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class QueryRequest(BaseModel):
    """Request schema for query endpoint."""
    query: str
    conversation_id: Optional[str] = None


class SSEEvent(BaseModel):
    """SSE event structure."""
    type: str
    data: Dict[str, Any]


class SessionData(BaseModel):
    """Session data structure."""
    executed_queries: List[str] = []
    previous_queries: List[str] = []
    previous_csv_indices: List[int] = []
    previous_execution_results: List[Dict[str, Any]] = []
    previous_query_confidence: Optional[Dict[str, Any]] = None

