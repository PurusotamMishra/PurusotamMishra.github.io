from pydantic import BaseModel
from typing import AsyncGenerator

from schemas.models import WorkflowInput, SSEEvent
from utils.tracing import ExecutionMetrics, format_workflow_summary
from core.workflow_generator import stream_workflow
from clients.postgres_client import PostgresHelper

pg_client = PostgresHelper()

class FetchLogsWorkflow(BaseModel):

    async def stream_workflow_events(self, workflow_input: WorkflowInput) -> AsyncGenerator[dict, None, None]:
        """
        Stream workflow events as Server-Sent Events using b_copilot.run_workflow().
        
        Args:
            workflow_input: Workflow input
            
        Yields:
            SSE-formatted event strings
        """
        # session_id, session_data = session_manager.get_or_create_session(conversation_id)
        
        try:
            # Prepare workflow input            
            # Track state for incremental updates
            current_state = None
            classification_sent = False
            queries_sent = False
            # previous_execution_results_count = 0
            previous_metrics_count = 0
            streamed_query_indices = set()  # Track which query results have been streamed
            
            # Stream workflow using incremental streaming
            print("[DEBUG] Streaming workflow with b_copilot...")
            async for update in stream_workflow(workflow_input):
                node_name = update.get("node")
                state = update.get("state", {})
                current_state = state
                
                # Handle errors
                if node_name == "ERROR":
                    error_event = SSEEvent(
                        type="error",
                        data={
                            "error": state.get('reason', 'Workflow failed'),
                            "error_code": state.get('reason', 'WORKFLOW_FAILED').upper(),
                            "details": state.get('details', {})
                        }
                    )
                    yield error_event.model_dump()
                
                # Stream classification event when classification node completes
                if node_name == "classification" and not classification_sent:
                    classification = state.get('classification')
                    if classification:
                        classification_output = state.get('classification_output')
                        reasoning = ""
                        if classification_output and hasattr(classification_output, 'reasoning'):
                            reasoning = classification_output.reasoning
                        classification_event = SSEEvent(
                            type="classification",
                            data={
                                "classification": classification,
                                "reasoning": reasoning,
                                "modification_type": state.get('modification_type'),
                                "detected_duration": state.get('detected_duration')
                            }
                        )
                        yield classification_event.model_dump()
                        classification_sent = True
                
                # Stream metrics after each node (if enabled)
                # workflow_metrics = state.get('workflow_metrics', [])
                # if workflow_metrics and len(workflow_metrics) > previous_metrics_count:
                #     # New metrics added - stream all new ones
                #     for metric in workflow_metrics[previous_metrics_count:]:
                #         metrics_event = SSEEvent(
                #             type="metrics",
                #             data={
                #                 "node": node_name,
                #                 "metrics": metric
                #             }
                #         )
                #         yield f"data: {metrics_event.model_dump_json()}\n\n"
                #     previous_metrics_count = len(workflow_metrics)
                
                # Stream queries event when human_to_dql or sql_to_dql node completes
                if node_name in ["human_to_dql", "sql_to_dql"] and not queries_sent:
                    queries = state.get('queries', [])
                    if queries:
                        queries_event = SSEEvent(
                            type="queries",
                            data={
                                "queries": queries,
                                "is_enrichment": state.get('is_enrichment', False),
                                "source": "dql"
                            }
                        )
                        # yield f"data: {queries_event.model_dump_json()}\n\n"
                        queries_sent = True
                
                # Stream EPM queries event when epm_query_generation node completes
                # if node_name == "epm_query_generation":
                #     epm_queries = state.get('epm_queries', [])
                #     if epm_queries:
                #         epm_queries_event = SSEEvent(
                #             type="epm_queries",
                #             data={
                #                 "queries": epm_queries,
                #                 "source": "epm",
                #                 "query_type": "osquery"
                #             }
                #         )
                #         yield f"data: {epm_queries_event.model_dump_json()}\n\n"
                
                # Stream query results incrementally when query_execution node completes
                if node_name == "query_execution":
                    execution_results = state.get('execution_results', [])
                    # Stream only new results (those not yet streamed)
                    results = []
                    for exec_res in execution_results:
                        query_idx = exec_res.get('query_idx', 0)
                        source = exec_res.get('source', 'generated')
                        # Only stream DQL results here (EPM results handled separately)
                        if source != 'epm' and query_idx not in streamed_query_indices:
                            # Stream one-line summary if available
                            # if exec_res.get('one_line_summary'):
                            #     summary_event = SSEEvent(
                            #         type="query_summary",
                            #         data={
                            #             "query_idx": query_idx,
                            #             "summary": exec_res['one_line_summary'],
                            #             "is_enrichment": state.get('is_enrichment', False),
                            #             "source": source
                            #         }
                            #     )
                            #     yield f"data: {summary_event.model_dump_json()}\n\n"
                            
                            # Stream query result
                            query_result_event = SSEEvent(
                                type="query_result",
                                data={
                                    "query_idx": query_idx,
                                    "query": exec_res.get('query', ''),
                                    "original_query": exec_res.get('original_query'),
                                    "source": source,
                                    "result_count": exec_res.get('result_count', 0),
                                    "results": exec_res.get('results', []),
                                    "key_answer": exec_res.get('key_answer', ''),
                                    "one_line_summary": exec_res.get('one_line_summary', ''),
                                    "error": exec_res.get('error'),
                                    "is_enrichment": state.get('is_enrichment', False)
                                }
                            )
                            results.append(query_result_event.model_dump_json())
                            # streamed_query_indices.add(query_idx)
                    print(f"[DEBUG]************************************************** results: {results}")
                    return results
                
                # Stream EPM query results when epm_query_execution node completes
                # if node_name == "epm_query_execution":
                #     epm_execution_results = state.get('epm_execution_results', [])
                #     execution_results = state.get('execution_results', [])
                #     # Stream EPM results
                #     for exec_res in epm_execution_results:
                #         query_idx = exec_res.get('query_idx', 0)
                #         if query_idx not in streamed_query_indices:
                #             # Stream one-line summary if available
                #             if exec_res.get('one_line_summary'):
                #                 summary_event = SSEEvent(
                #                     type="query_summary",
                #                     data={
                #                         "query_idx": query_idx,
                #                         "summary": exec_res['one_line_summary'],
                #                         "source": "epm",
                #                         "query_type": "osquery"
                #                     }
                #                 )
                #                 yield f"data: {summary_event.model_dump_json()}\n\n"
                            
                #             # Stream EPM query result
                #             query_result_event = SSEEvent(
                #                 type="query_result",
                #                 data={
                #                     "query_idx": query_idx,
                #                     "query": exec_res.get('query', ''),
                #                     "source": "epm",
                #                     "query_type": "osquery",
                #                     "result_count": exec_res.get('result_count', 0),
                #                     "results": exec_res.get('results', []),
                #                     "key_answer": exec_res.get('key_answer', ''),
                #                     "one_line_summary": exec_res.get('one_line_summary', ''),
                #                     "error": exec_res.get('error'),
                #                     "endpoints": exec_res.get('endpoints', [])
                #                 }
                #             )
                #             yield f"data: {query_result_event.model_dump_json()}\n\n"
                #             streamed_query_indices.add(query_idx)
                
                # Stream summary event when summary node completes
                # if node_name == "summary":
                #     summary = state.get('summary')
                #     if summary:
                #         summary_event = SSEEvent(
                #             type="summary",
                #             data={"summary": summary}
                #         )
                #         yield f"data: {summary_event.model_dump_json()}\n\n"
                
                # Handle workflow completion
                if node_name == "END":
                    # Update session data from final state
                    queries = current_state.get('queries', []) if current_state else []
                    execution_results = current_state.get('execution_results', []) if current_state else []
                    
                    # if queries:
                    #     session_data.previous_queries.extend(queries)
                    # if current_state and current_state.get('csv_indices'):
                    #     session_data.previous_csv_indices.extend(current_state.get('csv_indices', []))
                    # if execution_results:
                    #     # For enrichment, replace previous results; for new queries, extend
                    #     if current_state and current_state.get('is_enrichment'):
                    #         session_data.previous_execution_results = execution_results
                    #     else:
                    #         session_data.previous_execution_results.extend(execution_results)
                    # if current_state and current_state.get('executed_queries'):
                    #     session_data.executed_queries = current_state.get('executed_queries', [])
                    # if current_state and current_state.get('query_confidence_score') is not None:
                    #     session_data.previous_query_confidence = {
                    #         "score": current_state.get('query_confidence_score'),
                    #         "reasoning": current_state.get('query_confidence_reasoning', ''),
                    #         "factors": current_state.get('query_confidence_factors', {}),
                    #         "is_high_confidence": current_state.get('is_high_confidence', False)
                    #     }
                    
                    # print(f"[DEBUG] Session Update: Saved {len(execution_results)} execution results to session_id={session_id}")
                    # print(f"[DEBUG] Session Update: Session now has {len(session_data.previous_execution_results)} total execution results")
                    # print(f"[DEBUG] Session Update: Session now has {len(session_data.previous_queries)} total queries")
                    
                    # Stream workflow summary metrics if available
                    if current_state:
                        workflow_metrics = current_state.get('workflow_metrics', [])
                        if workflow_metrics:
                            # Convert dict metrics to ExecutionMetrics objects for formatting
                            metrics_objects = []
                            for m_dict in workflow_metrics:
                                m = ExecutionMetrics(m_dict.get('agent_name', ''), m_dict.get('model', 'unknown'))
                                m.execution_time = m_dict.get('execution_time')
                                m.input_tokens = m_dict.get('input_tokens')
                                m.output_tokens = m_dict.get('output_tokens')
                                m.total_tokens = m_dict.get('total_tokens')
                                m.estimated_cost = m_dict.get('estimated_cost')
                                metrics_objects.append(m)
                            
                            summary_text = format_workflow_summary(metrics_objects)
                            workflow_summary_event = SSEEvent(
                                type="workflow_summary",
                                data={
                                    "summary": summary_text,
                                    "metrics": workflow_metrics
                                }
                            )
                            # yield f"data: {workflow_summary_event.model_dump_json()}\n\n"
                    
                    # Stream complete event
                    complete_event = SSEEvent(
                        type="complete",
                        data={
                            # "conversation_id": session_id,
                            "status": "completed",
                            "is_enrichment": current_state.get('is_enrichment', False) if current_state else False
                        }
                    )
                    # yield f"data: {complete_event.model_dump_json()}\n\n"
                    break
            
        except Exception as e:
            import traceback
            print(f"[ERROR] Workflow execution failed: {str(e)}")
            traceback.print_exc()
            error_event = SSEEvent(
                type="error",
                data={
                    "error": str(e),
                    "error_code": "INTERNAL_ERROR",
                    "traceback": traceback.format_exc()
                }
            )
            # yield f"data: {error_event.model_dump_json()}\n\n"
            return {
                "type": "error",
                "data": {
                    "error": str(e),
                    "error_code": "INTERNAL_ERROR",
                    "traceback": traceback.format_exc()
                }
            }

async def fetch_logs(user_query: str) -> AsyncGenerator[list[dict], None, ]:
    """
    Fetches logs from the database based on the user's request.
    """
    try:
        result = []
        # async for event in stream_workflow_events(user_query):
        #     result.append(event)
        result = await FetchLogsWorkflow().stream_workflow_events(WorkflowInput(input_as_text=user_query))
        return result
    except Exception as e:
        raise e