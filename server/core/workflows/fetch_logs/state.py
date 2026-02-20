from typing import List, Dict, Any, Optional, TypedDict

from core.schemas.models import SSEEvent

class WorkflowState(TypedDict):
    """State schema for the LangGraph workflow."""
    
    # Input
    user_query: str  # Original user query
    original_user_query: str  # Stored for summary keyword detection
    
    # Context from previous runs
    executed_queries: List[str]  # Previously executed queries (for deduplication)
    previous_queries: List[str]  # Previous queries from conversation
    previous_csv_indices: List[int]  # CSV indices previously fetched
    previous_execution_results: List[Dict[str, Any]]  # Previous execution results
    previous_query_confidence: Optional[Dict[str, Any]] # Previous query confidence
    
    # Classification
    classification: Optional[str]  # "human to DQL", "SQL to DQL", "enrich_results", "epm", "other"
    classification_output: Optional[Any]  # Full classification result (EnhancedClassificationOutput)
    modification_type: Optional[List[str]] # Modification types detected
    detected_duration: Optional[str]  # Duration string (e.g., "2w", "14d")
    
    # Guardrail
    guardrail_passed: bool  # Whether guardrail check passed
    guardrail_output: Optional[Any]  # Guardrail result (JailbreakCheckOutput)
    
    # Query Clarity
    query_confidence_score: Optional[float]  # Query clarity score (0.0-1.0)
    query_confidence_reasoning: Optional[str] # Reasoning for clarity
    query_confidence_factors: Optional[Dict[str, float]] # Detailed factors
    is_high_confidence: Optional[bool]  # Whether score >= threshold
    
    # Entity Resolution
    entity_resolution: Optional[Any]  # Entity resolution result (EntityResolutionOutput)
    resolved_entities_context: str  # Formatted context string for entities
    
    # Stream Action Context
    stream_action_context: str  # Stream action mapping context
    
    # Query Generation
    queries: List[str]  # Generated DQL queries
    csv_indices: List[int]  # CSV indices used for queries
    query_sources: List[str]  # Source of each query ('csv' or 'generated')
    
    # Enrichment (for enrich_results path)
    is_enrichment: bool  # Whether this is an enrichment request
    enrichment_type: Optional[str]  # Type of enrichment ("hostname", "ip_hostname", etc.)
    original_queries: Optional[List[str]]  # Original queries to enrich
    enriched_queries: Optional[List[str]]  # Enriched queries
    
    # Query Execution
    execution_results: List[Dict[str, Any]]  # Query execution results (includes both DQL and EPM results)
    queries_skipped: List[int]  # Query indices skipped due to early stopping
    
    # EPM Query Generation
    epm_queries: List[str]  # Generated osquery SQL queries
    epm_execution_results: List[Dict[str, Any]]  # EPM query results (tagged with source="epm")
    selected_endpoints: List[Dict[str, str]]  # Selected endpoints for EPM queries
    epm_query_sources: List[str]  # Source tracking for EPM queries
    
    # Summary
    summary: Optional[str]  # Generated summary text
    
    # Final Result
    result: Optional[Dict[str, Any]] # Final formatted result
    status: str  # "completed", "failed", "in_progress"
    failed: bool  # Whether workflow failed
    reason: Optional[str] # Failure reason
    details: Optional[Dict[str, Any]] # Failure details
    
    # Internal tracking
    workflow_id: str  # Unique workflow ID
    conversation_history: List[Dict[str, Any]]  # Conversation history for agents
    
    # Metrics tracking
    workflow_metrics: List[Dict[str, Any]]  # Execution metrics for each node
    
    response: Optional[SSEEvent]  # UI Response from the workflow