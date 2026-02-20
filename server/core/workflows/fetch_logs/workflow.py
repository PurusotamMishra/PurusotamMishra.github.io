from core.engine.registry import WorkflowRegistry
from core.workflows.base import BaseWorkflow
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from datetime import datetime
import uuid

from core.nodes.guardrail_check import guardrail_check_node
import core.workflows.fetch_logs.nodes as nodes
from core.workflows.fetch_logs.state import WorkflowState

@WorkflowRegistry.register("fetch_logs")
class FetchLogsWorkflow(BaseWorkflow):
    name = "fetch_logs"
    description = "Fetch and analyze logs using DQL queries"
    
    def generate_workflow_id(self) -> str:
        """Generate a unique workflow ID."""
        return f"dql-query-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"

    
    def get_initial_state(self, input_data: dict) -> dict:
        state: WorkflowState = {
            "user_query": input_data.get("user_query", ""),
            "original_user_query": input_data.get("user_query", ""),
            "executed_queries": input_data.get("executed_queries", []),
            "previous_queries": input_data.get("previous_queries", []),
            "previous_csv_indices": input_data.get("previous_csv_indices", []),
            "previous_execution_results": input_data.get("previous_execution_results", []),
            "previous_query_confidence": input_data.get("previous_query_confidence", []),
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
            "workflow_id": input_data["workflow_id"],
            "conversation_history": [],
            "workflow_metrics": []
        }
        return state
    
    def route_after_guardrail(self, state: WorkflowState) -> str:
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


    def route_after_classification(self, state: WorkflowState) -> str:
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


    def route_after_sql_to_dql(self, state: WorkflowState) -> str:
        """
        Route after SQL to DQL conversion.
        Goes directly to END (no execution for SQL conversion).
        
        Args:
            state: Current workflow state
            
        Returns:
            Next node name: "END"
        """
        return "END"

    def build_graph(self) -> StateGraph:
        try:
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
                self.route_after_guardrail,
                {
                    "classification": "classification",
                    "END": END
                }
            )
            
            workflow.add_conditional_edges(
                "classification",
                self.route_after_classification,
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
                self.route_after_sql_to_dql,
                {
                    "END": END
                }
            )
                
            # Compile with checkpointing
            memory = MemorySaver()
            app = workflow.compile(checkpointer=memory)            
            return app

        except Exception as e:
            # logging.error(f"Error building workflow: {e}")
            raise e