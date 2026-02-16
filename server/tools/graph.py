"""
LangGraph workflow graph construction and routing.
"""
from langgraph.graph import StateGraph, END
from tools.schemas.state import WorkflowState
import tools.nodes as nodes
from langgraph.checkpoint.memory import MemorySaver


def route_after_guardrail(state: WorkflowState) -> str:
    """
    Route after guardrail check.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "classification" or "END"
    """
    guardrail_passed = state.get("guardrail_passed", True)
    
    if not guardrail_passed:
        return "END"
    
    return "classification"


def route_after_classification(state: WorkflowState) -> str:
    """
    Route after classification based on classification result.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name based on classification
    """
    classification = state.get("classification", "")
    
    if classification == "human to DQL":
        return "query_clarity"
    elif classification == "SQL to DQL":
        return "sql_to_dql"
    elif classification == "enrich_results":
        return "enrich_results"
    elif classification == "epm":
        return "endpoint_selection"
    elif classification == "other":
        return "handle_other"
    else:
        return "END"


def route_after_query_clarity(state: WorkflowState) -> str:
    """
    Route after query clarity assessment.
    Always goes to entity resolution for human_to_dql path.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "entity_resolution"
    """
    return "entity_resolution"


def route_after_entity_resolution(state: WorkflowState) -> str:
    """
    Route after entity resolution.
    Always goes to stream_action_context for human_to_dql path.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "stream_action_context"
    """
    return "stream_action_context"


def route_after_stream_context(state: WorkflowState) -> str:
    """
    Route after stream action context generation.
    Always goes to human_to_dql for human_to_dql path.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "human_to_dql"
    """
    return "human_to_dql"


def route_after_query_generation(state: WorkflowState) -> str:
    """
    Route after query generation.
    Always goes to query execution.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "query_execution"
    """
    return "query_execution"


def route_after_execution(state: WorkflowState) -> str:
    """
    Route after query execution.
    Always goes to summary.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "summary"
    """
    return "summary"


def route_after_summary(state: WorkflowState) -> str:
    """
    Route after summary generation.
    Always goes to format_result.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "format_result"
    """
    return "format_result"


def route_after_enrich_results(state: WorkflowState) -> str:
    """
    Route after enrich_results node.
    Goes to summary for enriched results.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "summary"
    """
    return "summary"


def route_after_sql_to_dql(state: WorkflowState) -> str:
    """
    Route after SQL to DQL conversion.
    Goes directly to END (no execution for SQL conversion).
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "END"
    """
    return "END"


def route_after_handle_other(state: WorkflowState) -> str:
    """
    Route after handle_other node.
    Goes directly to END.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "END"
    """
    return "END"


def route_after_endpoint_selection(state: WorkflowState) -> str:
    """
    Route after endpoint selection.
    Always goes to EPM query generation.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "epm_query_generation"
    """
    return "epm_query_generation"


def route_after_epm_generation(state: WorkflowState) -> str:
    """
    Route after EPM query generation.
    Always goes to EPM query execution.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "epm_query_execution"
    """
    return "epm_query_execution"


def route_after_epm_execution(state: WorkflowState) -> str:
    """
    Route after EPM query execution.
    Always goes to summary.
    
    Args:
        state: Current workflow state
        
    Returns:
        Next node name: "summary"
    """
    return "summary"


def build_workflow_graph():
    """
    Build and compile the LangGraph workflow graph.
    
    Returns:
        Compiled LangGraph application
    """
    
    # Create StateGraph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("guardrail_check", nodes.guardrail_check_node)
    workflow.add_node("classification", nodes.classification_node)
    workflow.add_node("query_clarity", nodes.query_clarity_node)
    workflow.add_node("entity_resolution", nodes.entity_resolution_node)
    workflow.add_node("stream_action_context", nodes.stream_action_context_node)
    workflow.add_node("human_to_dql", nodes.human_to_dql_node)
    workflow.add_node("sql_to_dql", nodes.sql_to_dql_node)
    workflow.add_node("query_execution", nodes.query_execution_node)
    
    # Set entry point
    workflow.set_entry_point("guardrail_check")
    
    # Add edges with routing
    workflow.add_conditional_edges(
        "guardrail_check",
        route_after_guardrail,
        {
            "classification": "classification",
            "END": END
        }
    )
    
    workflow.add_conditional_edges(
        "classification",
        route_after_classification,
        {
            "query_clarity": "query_clarity",
            "sql_to_dql": "sql_to_dql",
            "END": END
        }
    )
    
    # Human to DQL path
    workflow.add_edge("query_clarity", "entity_resolution")
    workflow.add_edge("entity_resolution", "stream_action_context")
    workflow.add_edge("stream_action_context", "human_to_dql")
    workflow.add_edge("human_to_dql", "query_execution")
    workflow.add_edge("query_execution", END)
    
    # SQL to DQL path (no execution)
    workflow.add_conditional_edges(
        "sql_to_dql",
        route_after_sql_to_dql,
        {
            "END": END
        }
    )
        
    # Compile with checkpointing
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    # LangSmith tracing is automatically enabled via environment variables
    # set in b_copilot/__init__.py when config.is_langsmith_enabled() is True
    # LangGraph will automatically trace all node executions, LLM calls, and tool invocations
    
    return app


# Create compiled graph instance
workflow_app = build_workflow_graph()

