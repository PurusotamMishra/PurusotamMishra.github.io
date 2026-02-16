from typing import Dict, Any, AsyncGenerator, Optional
from tools.schemas.models import WorkflowInput
from tools.schemas.state import WorkflowState
from tools.utils.config import generate_workflow_id, TRACE_SOURCE
from tools.graph import workflow_app

async def stream_workflow(
    workflow_input: WorkflowInput,
    executed_queries: list = None,
    previous_queries: list = None,
    previous_csv_indices: list = None,
    previous_execution_results: list = None,
    previous_query_confidence: dict = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream workflow state updates as nodes complete (incremental streaming).
    Yields state updates after each node execution.
    
    Args:
        workflow_input: User's input query
        executed_queries: List to track previously executed queries (for deduplication)
        previous_queries: List of previous queries from conversation (for context)
        previous_csv_indices: List of CSV indices that were previously fetched (for exclusion)
        previous_execution_results: List of previous execution results (for enrichment)
        previous_query_confidence: Previous query confidence dict (for reuse)
        
    Yields:
        Dictionary with state updates and node name after each node completes
    """
    if executed_queries is None:
        executed_queries = []
    if previous_queries is None:
        previous_queries = []
    if previous_csv_indices is None:
        previous_csv_indices = []
    if previous_execution_results is None:
        previous_execution_results = []
    
    workflow_id = generate_workflow_id()
    
    # Build initial state (same as run_workflow)
    user_query = workflow_input.input_as_text
    
    initial_state: WorkflowState = {
        "user_query": user_query,
        "original_user_query": user_query,
        "executed_queries": executed_queries,
        "previous_queries": previous_queries,
        "previous_csv_indices": previous_csv_indices,
        "previous_execution_results": previous_execution_results,
        "previous_query_confidence": previous_query_confidence,
        "classification": None,
        "classification_output": None,
        "modification_type": None,
        "detected_duration": None,
        "guardrail_passed": False,
        "guardrail_output": None,
        "query_confidence_score": None,
        "query_confidence_reasoning": None,
        "query_confidence_factors": None,
        "is_high_confidence": None,
        "entity_resolution": None,
        "resolved_entities_context": "",
        "stream_action_context": "",
        "queries": [],
        "csv_indices": [],
        "query_sources": [],
        "is_enrichment": False,
        "enrichment_type": None,
        "original_queries": None,
        "enriched_queries": None,
        "execution_results": [],
        "queries_skipped": [],
        "epm_queries": [],
        "epm_execution_results": [],
        "selected_endpoints": [],
        "epm_query_sources": [],
        "summary": None,
        "result": None,
        "status": "in_progress",
        "failed": False,
        "reason": None,
        "details": None,
        "workflow_id": workflow_id,
        "conversation_history": [],
        "workflow_metrics": []
    }
    
    # Create thread ID for checkpointing
    thread_id = f"workflow-{workflow_id}"
    run_config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "__trace_source__": TRACE_SOURCE,
            "workflow_id": workflow_id,
        }
    }
    
    # Track previous state to detect which node completed
    previous_state: Optional[WorkflowState] = None
    
    try:
        # Stream workflow state updates as nodes complete
        async for state_update in workflow_app.astream(initial_state, config=run_config):
            # state_update is a dict mapping node names to their output state
            # Format: {"node_name": {state_updates}}
            
            # Determine which node(s) just completed
            for node_name, node_state in state_update.items():
                # Merge node_state into our tracking state
                if previous_state is None:
                    current_state = {**initial_state, **node_state}
                else:
                    current_state = {**previous_state, **node_state}
                
                # Yield state update with node name
                yield {
                    "node": node_name,
                    "state": current_state
                }
                
                # Update previous_state for next iteration
                previous_state = current_state
                
                # Check for early stopping conditions
                if node_name == "query_execution":
                    # Check if we should stop early (high confidence + results found)
                    is_high_confidence = current_state.get("is_high_confidence", False)
                    execution_results = current_state.get("execution_results", [])
                    
                    # Check if any query returned results
                    has_results = any(
                        res.get('result_count', 0) > 0 and 'error' not in res
                        for res in execution_results
                    )
                    
                    if is_high_confidence and has_results:
                        # Early stopping triggered - remaining queries will be skipped
                        # The query_execution_node handles this internally
                        pass
        
        # After streaming completes, yield final state
        if previous_state:
            yield {
                "node": "END",
                "state": previous_state
            }
            
    except Exception as e:
        print(f"[DEBUG] Workflow streaming error: {str(e)}")
        import traceback
        traceback.print_exc()
        yield {
            "node": "ERROR",
            "state": {
                "status": "error",
                "failed": True,
                "reason": "execution_error",
                "details": {
                    "error": str(e)
                }
            }
        }
