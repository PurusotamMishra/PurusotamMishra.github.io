"""
Pydantic models and schemas for the DQL Agent System (LangGraph version).
"""
from typing import Any
from pydantic import BaseModel


class WorkflowInput(BaseModel):
    """Input schema for workflow execution."""
    input_as_text: str


class AgentSchema(BaseModel):
    """Schema for agent output."""
    reasoning: str
    classification: str


class EnhancedClassificationOutput(BaseModel):
    """Enhanced classification output with modification detection."""
    reasoning: str
    classification: str  # "human to DQL", "SQL to DQL", "enrich_results", "epm", "other"
    modification_type: list[str] | None = None  # ["more_ways", "duration_change", "query_change", "follow_up", "unrelated"], None
    detected_duration: str | None = None  # e.g., "2w", "14d", "1h"
    confidence: float


class JailbreakCheckOutput(BaseModel):
    """Output schema for jailbreak detection guardrail."""
    is_jailbreak: bool
    reasoning: str
    confidence: float


class StreamActionMapperOutput(BaseModel):
    """Output schema for stream action mapper agent."""
    actions: list[str]
    streams: list[str]
    reasoning: str
    confidence: float


class EntityResolutionOutput(BaseModel):
    """Output schema for entity resolver agent."""
    detected_entity_types: list[str]  # Types mentioned in query: ['user', 'ip', etc.]
    resolved_entities: dict[str, list[str]]  # Map entity type to list of resolved values
    confidence_scores: dict[str, float]  # Confidence for each entity type resolution
    reasoning: str  # Explanation of how entities were resolved
    has_references: bool  # Whether query contains entity references


class QueryClarityFactors(BaseModel):
    """Factors contributing to query clarity assessment."""
    clarity: float  # How clear and unambiguous the query is (0.0-1.0)
    specificity: float  # How specific and detailed the query is (0.0-1.0)
    entity_mentions: float  # Presence of specific entities (IPs, users, actions, etc.) (0.0-1.0)
    technical_terms: float  # Use of technical terms and domain knowledge (0.0-1.0)
    timeframes: float  # Presence of time-related information (0.0-1.0)
    stream_names: float  # Mention of specific stream names (0.0-1.0)
    query_length_score: float  # Query length appropriateness (0.0-1.0)


class QueryClarityOutput(BaseModel):
    """Output schema for query clarity assessment."""
    score: float  # Overall confidence score (0.0-1.0)
    reasoning: str  # Explanation of the assessment
    factors: QueryClarityFactors  # Detailed factor breakdown

class SSEEvent(BaseModel):
    """SSE event structure."""
    type: str
    data: dict[str, Any]

