"""
Node functions for LangGraph workflow execution.
Each node reads from WorkflowState and returns partial state updates.
"""
import json
import asyncio
from typing import Dict, Any

from langchain_core.messages import ToolMessage
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.prompts import ChatPromptTemplate


import sys
sys.path.append("/app/server")

from tools.utils.entity_extraction import (
    extract_entities_from_results,
    extract_entities_from_queries,
    detect_aggregated_query,
    has_only_count_fields,
    modify_query_to_fetch_entities
)

from tools.utils.helpers import (
    parse_query_response,
    is_likely_follow_up,
    extract_key_answer,
    generate_one_line_summary,
)

from tools.utils.dnif_client import execute_query_with_external_polling

from tools.utils.config import config
from tools.utils.knowledge_base import BASE_DQL
from tools.utils.csv_search import search_dql_csv
from tools.utils.query_modification import modify_dql_query
from tools.utils.tracing import ExecutionMetrics, extract_metrics_from_langchain_response
from tools.utils.model_factory import get_model, get_model_name

from tools.schemas.state import WorkflowState

from tools.utils.guardrails import check_jailbreak
from tools.schemas.models import EnhancedClassificationOutput, EntityResolutionOutput
from tools.utils.query_clarity_scorer import assess_query_clarity
from tools.utils.query_generation_helper import format_stream_action_context


async def guardrail_check_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Check guardrails before processing user query.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with guardrail results
    """
    user_query = state.get("user_query", "")
    
    print("[DEBUG] Guardrail: Checking jailbreak...")
    guardrail_result = await check_jailbreak(user_query)
    
    guardrail_passed = not (guardrail_result.is_jailbreak and guardrail_result.confidence >= 0.80)
    
    if not guardrail_passed:
        print(f"[DEBUG] Guardrail tripped. Reasoning: {guardrail_result.reasoning} | Confidence: {guardrail_result.confidence}")
        return {
            "guardrail_passed": False,
            "guardrail_output": guardrail_result,
            "failed": True,
            "reason": "jailbreak_detected",
            "details": {
                "reasoning": guardrail_result.reasoning,
                "confidence": guardrail_result.confidence
            },
            "status": "failed"
        }
    
    print("[DEBUG] Guardrail: Passed")
    return {
        "guardrail_passed": True,
        "guardrail_output": guardrail_result
    }


async def classification_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Classify user query into categories: "human to DQL", "SQL to DQL", "enrich_results", "other".
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with classification results
    """
    user_query = state.get("user_query", "")
    previous_queries = state.get("previous_queries", [])
    previous_execution_results = state.get("previous_execution_results", [])
    
    # Build context for classification
    user_message_text = user_query
    if previous_queries:
        context_text = "\n\nPrevious queries from this conversation:\n"
        for i, pq in enumerate(previous_queries, 1):
            context_text += f"{i}. {pq}\n"
        
        if previous_execution_results:
            context_text += "\n\n[PREVIOUS QUERY RESULTS AVAILABLE FOR ENRICHMENT]\n"
            context_text += f"There are {len(previous_execution_results)} previous query execution results.\n"
            results_with_data = [r for r in previous_execution_results if r.get('result_count', 0) > 0]
            if results_with_data:
                # Separate DQL and EPM results
                dql_results = [r for r in results_with_data if r.get('source') != 'epm']
                epm_results = [r for r in results_with_data if r.get('source') == 'epm']
                
                context_text += f"Previous queries returned {sum(r.get('result_count', 0) for r in results_with_data)} total records.\n"
                if dql_results:
                    context_text += f"- {len(dql_results)} DQL query result(s)\n"
                if epm_results:
                    context_text += f"- {len(epm_results)} EPM/osquery query result(s)\n"
                
                if results_with_data[0].get('results'):
                    sample_result = results_with_data[0]['results'][0]
                    if isinstance(sample_result, dict):
                        context_text += f"Sample fields in previous results: {', '.join(list(sample_result.keys())[:5])}\n"
            context_text += "\nIf the user asks to enrich, add details, or get more information about these previous results (e.g., 'show hostnames', 'give me names for those IPs', 'what are the hostnames for these IPs'), classify as 'enrich_results'.\n"
            context_text += "Previous results may be from DQL queries (log analysis) or EPM queries (endpoint system state). Both can be enriched.\n"
        
        user_message_text = context_text + "\n\n" + user_message_text
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Classify each user prompt to determine if the required action is (a) "Convert human language to DQL query", (b) "Convert SQL to DQL query", (c) "Enrich previous results", (d) "EPM query (endpoint management)", or (e) "Other".

**CRITICAL: Detect classifications in this order:**

1. **"enrich_results"** - User asks to enrich, analyze, or get additional information about PREVIOUS query results (e.g., "give me names for these IPs", "show me hostnames", "what are the names for these IPs", "give me hostnames for the IPs", "show me more details about these results")
   - If user references previous results (e.g., "these IPs", "the IPs from before", "names for the IPs", "hostnames"), and there are previous queries in the conversation context, classify as "enrich_results"
   - Enrichment requests are about ADDING data to existing results, not creating new queries

2. **"epm"** - User asks about CURRENT SYSTEM STATE on endpoints (not historical log analysis). EPM queries are about:
   - **Keywords**: "process", "processes", "endpoint", "endpoints", "osquery", "system info", "installed software", "firewall", "network connections", "running processes", "list", "show me", "check", "what processes", "which endpoints"
   - **Intent patterns**: Queries about current system state vs historical log analysis
   - **Examples**: 
     * "Show me all running processes"
     * "List installed software"
     * "Check firewall status"
     * "What processes are running on endpoint X?"
     * "Show network connections"
     * "List processes executing from temp directory"
   - **NOT EPM**: Queries about historical events, logs, security incidents over time, "last 2 weeks", "brute force attempts", "failed logins in the past"
   - If confidence is low (< 0.7), default to "human to DQL"

3. **"human to DQL"** - User provides a request or question in plain language that should be converted to a DQL query (historical log analysis, security events, etc.)

4. **"SQL to DQL"** - User provides a SQL query that should be converted to a DQL equivalent

5. **"other"** - Neither of the above applies

Additionally, detect modification intent for follow-up queries:
- "more_ways": User asks for more alternatives, additional ways, or similar queries (e.g., "give me more ways", "show me alternatives", "other ways to check")
- "duration_change": User mentions changing time period ONLY (e.g., "for the last 3 days", "last 2 weeks instead", "change to 2 weeks"). IMPORTANT: If the query is ONLY a duration change (like "for the last 3 days" after "give brute force for the last 2 days"), mark as ONLY "duration_change", NOT "query_change"
- "follow_up": User asks a vague, short, context-dependent follow-up question that relies on previous query context (e.g., "can you run checks on authentication stream?", "what about that?", "show me more"). These are typically short (< 40 chars), lack specific entities/verbs, and depend on previous context
- "query_change": The user's query intent/entities have changed significantly compared to previous query (e.g., different topic, different entities, different actions). Only mark as "query_change" if the query is substantially different, not just a duration change
- "unrelated": Completely different topic from previous query (e.g., "now search for malware", "what about firewall logs")
- None: New query or first query in conversation

If the model detects a valid modification_type (e.g., more_ways, duration_change, unrelated) in the user's message, set classification to "human to DQL" regardless of the original intent classification (unless it's "epm" with high confidence).

**Duration Detection:**
- Extract duration expressions: "2 weeks" → "2w", "14 days" → "14d", "1 hour" → "1h", "30 minutes" → "30m"
- Convert to DQL duration format: weeks (w), days (d), hours (h), minutes (m)
- Set detected_duration field if duration is mentioned

Output must be a JSON object with fields:
- "reasoning": a brief explanation of why you selected the classification and modification types
- "classification": one of these values exactly: "human to DQL", "SQL to DQL", "enrich_results", "epm", "other"
- "modification_type": a list of modification types like ["duration_change", "query_change"], ["more_ways"], ["duration_change"], ["follow_up"], or null
- "detected_duration": duration string in DQL format (e.g., "2w", "14d") or null
- "confidence": confidence score between 0.0 and 1.0

All reasoning must precede the classification."""),
        ("human", "{input}")
    ])
    
    model = get_model("classification")
    model_name = get_model_name("classification")
    
    # Track metrics
    metrics = ExecutionMetrics("Classification Agent", model=model_name)
    workflow_metrics = state.get("workflow_metrics", [])
    
    try:
        if config.enable_detailed_tracing:
            metrics.start()
        
        chain = prompt | model
        response = await chain.ainvoke({"input": user_message_text})
        
        # Extract metrics from response
        if config.enable_detailed_tracing:
            metrics.end()
            extracted = extract_metrics_from_langchain_response(response, "Classification Agent", model_name)
            if extracted:
                metrics = extracted
            workflow_metrics.append(metrics.to_dict())
            print(metrics.format_output())
        
        content = response.content.strip()
        
        # Extract JSON
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        
        result = json.loads(content)
        
        classification_output = EnhancedClassificationOutput(
            reasoning=result.get("reasoning", ""),
            classification=result.get("classification", "other"),
            modification_type=result.get("modification_type"),
            detected_duration=result.get("detected_duration"),
            confidence=result.get("confidence", 0.5)
        )
        
        classification = classification_output.classification
        modification_type = classification_output.modification_type
        detected_duration = classification_output.detected_duration
        
        # Handle backward compatibility: convert single string to list if needed
        if modification_type and isinstance(modification_type, str):
            modification_type = [modification_type]
        
        print(f"[DEBUG] Classification: {classification}")
        print(f"[DEBUG] Modification type: {modification_type}")
        if detected_duration:
            print(f"[DEBUG] Detected duration: {detected_duration}")
        
        result_dict = {
            "classification": classification,
            "classification_output": classification_output,
            "modification_type": modification_type,
            "detected_duration": detected_duration
        }
        
        if config.enable_detailed_tracing:
            result_dict["workflow_metrics"] = workflow_metrics
        
        return result_dict
    except Exception as e:
        print(f"[DEBUG] Classification: Error - {str(e)}")
        if config.enable_detailed_tracing:
            metrics.end()
            workflow_metrics.append(metrics.to_dict())
        # Default to "human to DQL" on error
        result_dict = {
            "classification": "human to DQL",
            "classification_output": EnhancedClassificationOutput(
                reasoning=f"Error during classification: {str(e)}",
                classification="human to DQL",
                modification_type=None,
                detected_duration=None,
                confidence=0.5
            ),
            "modification_type": None,
            "detected_duration": None
        }
        if config.enable_detailed_tracing:
            result_dict["workflow_metrics"] = workflow_metrics
        return result_dict


async def query_clarity_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Assess query clarity confidence score.
    Skips assessment for follow-ups and duration-only changes.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with query clarity results
    """
    user_query = state.get("original_user_query", state.get("user_query", ""))
    modification_type = state.get("modification_type")
    previous_query_confidence = state.get("previous_query_confidence")
    
    # Determine if we should skip clarity assessment
    should_skip_clarity = False
    skip_reason = None
    
    if modification_type:
        mod_types = modification_type if isinstance(modification_type, list) else [modification_type]
        # Skip if it's only a duration change (no query_change)
        if "duration_change" in mod_types and "query_change" not in mod_types:
            should_skip_clarity = True
            skip_reason = "duration_change only"
        # Skip if it's a follow-up
        elif "follow_up" in mod_types:
            should_skip_clarity = True
            skip_reason = "follow_up"
    
    # Also check heuristics for follow-up detection
    previous_queries = state.get("previous_queries", [])
    if not should_skip_clarity and previous_queries:
        if is_likely_follow_up(user_query, has_previous_query=True):
            should_skip_clarity = True
            skip_reason = "heuristics detected follow-up"
    
    # Calculate query clarity confidence (or reuse previous)
    if should_skip_clarity and previous_query_confidence:
        print(f"[DEBUG] Query Clarity: Skipping assessment ({skip_reason}) - reusing previous confidence score")
        query_confidence_score = previous_query_confidence.get("score", 0.5)
        query_confidence_reasoning = previous_query_confidence.get("reasoning", "Reused from previous query")
        query_confidence_factors_dict = previous_query_confidence.get("factors", {})
        is_high_confidence = previous_query_confidence.get("is_high_confidence", False)
        print(f"[DEBUG] Query Clarity: Reused score = {query_confidence_score:.3f} (threshold = {config.confidence_threshold})")
        print(f"[DEBUG] Query Clarity: {'HIGH' if is_high_confidence else 'LOW'} confidence - {'Sequential execution with early stopping' if is_high_confidence else 'Run all queries'}")
    else:
        print("[DEBUG] Query Clarity: Assessing query clarity confidence...")
        
        # Track metrics
        workflow_metrics = state.get("workflow_metrics", [])
        model_name = get_model_name("query_clarity")
        metrics = ExecutionMetrics("Query Clarity Assessment", model=model_name)
        
        if config.enable_detailed_tracing:
            metrics.start()
        
        query_clarity_result, llm_response = await assess_query_clarity(user_query, return_response=True)
        
        # Extract metrics from LLM response
        if config.enable_detailed_tracing:
            metrics.end()
            if llm_response:
                extracted = extract_metrics_from_langchain_response(llm_response, "Query Clarity Assessment", model_name)
                if extracted:
                    metrics = extracted
            workflow_metrics.append(metrics.to_dict())
            print(metrics.format_output())
        
        query_confidence_score = query_clarity_result.score
        query_confidence_reasoning = query_clarity_result.reasoning
        query_confidence_factors_dict = {
            "clarity": query_clarity_result.factors.clarity,
            "specificity": query_clarity_result.factors.specificity,
            "entity_mentions": query_clarity_result.factors.entity_mentions,
            "technical_terms": query_clarity_result.factors.technical_terms,
            "timeframes": query_clarity_result.factors.timeframes,
            "stream_names": query_clarity_result.factors.stream_names,
            "query_length_score": query_clarity_result.factors.query_length_score
        }
        is_high_confidence = query_confidence_score >= config.confidence_threshold
        
        print(f"[DEBUG] Query Clarity: Confidence score = {query_confidence_score:.3f} (threshold = {config.confidence_threshold})")
        print(f"[DEBUG] Query Clarity: Reasoning = {query_confidence_reasoning[:200]}...")
        print(f"[DEBUG] Query Clarity: {'HIGH' if is_high_confidence else 'LOW'} confidence - {'Sequential execution with early stopping' if is_high_confidence else 'Run all queries'}")
    
    result_dict = {
        "query_confidence_score": query_confidence_score,
        "query_confidence_reasoning": query_confidence_reasoning,
        "query_confidence_factors": query_confidence_factors_dict,
        "is_high_confidence": is_high_confidence
    }
    
    if config.enable_detailed_tracing and not should_skip_clarity:
        result_dict["workflow_metrics"] = workflow_metrics
    
    return result_dict


async def entity_resolution_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Resolve entity references from previous execution results.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with entity resolution results
    """
    user_query = state.get("original_user_query", state.get("user_query", ""))
    previous_execution_results = state.get("previous_execution_results", [])
    previous_queries = state.get("previous_queries", [])
    
    if not previous_execution_results:
        return {
            "entity_resolution": None,
            "resolved_entities_context": ""
        }
    
    print("[DEBUG] Entity Resolution: Checking for entity references in query...")
    
    try:
        # Extract entities from previous results
        extracted_entities = extract_entities_from_results(previous_execution_results)
        
        # Also extract entity fields from previous queries
        if previous_queries:
            print("[DEBUG] Entity Resolution: Extracting entities from previous query structures...")
            query_entities = extract_entities_from_queries(previous_queries)
            
            # Merge query entities with result entities
            for entity_type, entity_data in query_entities.items():
                if entity_type not in extracted_entities:
                    extracted_entities[entity_type] = entity_data
                else:
                    # Merge fields
                    existing_fields = set(extracted_entities[entity_type].get('fields', []))
                    query_fields = set(entity_data.get('fields', []))
                    merged_fields = sorted(list(existing_fields | query_fields))
                    extracted_entities[entity_type]['fields'] = merged_fields
        
        # Check for aggregated queries that need entity fetching
        if not extracted_entities and previous_execution_results:
            print("[DEBUG] Entity Resolution: No entities found, checking for aggregated queries...")
            
            for exec_res in previous_execution_results:
                query = exec_res.get('query', '')
                results = exec_res.get('results', [])
                result_count = exec_res.get('result_count', 0)
                
                if not query or result_count == 0:
                    continue
                
                # Check if query is aggregated
                agg_info = detect_aggregated_query(query)
                if agg_info and agg_info.get('is_aggregated'):
                    entity_field = agg_info.get('entity_field')
                    
                    # Check if results only contain counts
                    if has_only_count_fields(results) and entity_field:
                        print(f"[DEBUG] Entity Resolution: Found aggregated query with count > 0, fetching entities for field '{entity_field}'...")
                        
                        # Modify query to fetch entities
                        modified_query = modify_query_to_fetch_entities(query, entity_field)
                        print(f"[DEBUG] Entity Resolution: Modified query: {modified_query}")
                        
                        # Re-run query to get entities
                        try:
                            exec_result = await execute_query_with_external_polling(query=modified_query)
                            
                            if exec_result.get('success'):
                                entity_results = exec_result.get('results', [])
                                if entity_results:
                                    # Extract entities from re-run results
                                    temp_exec_res = {
                                        'results': entity_results,
                                        'result_count': len(entity_results),
                                        'query': modified_query
                                    }
                                    
                                    fetched_entities = extract_entities_from_results([temp_exec_res])
                                    
                                    # Merge with existing extracted_entities
                                    for entity_type, entity_data in fetched_entities.items():
                                        if entity_type not in extracted_entities:
                                            extracted_entities[entity_type] = entity_data
                                        else:
                                            # Merge values
                                            existing_values = set(extracted_entities[entity_type].get('values', []))
                                            new_values = set(entity_data.get('values', []))
                                            extracted_entities[entity_type]['values'] = sorted(list(existing_values | new_values))
                                            # Update fields if needed
                                            existing_fields = set(extracted_entities[entity_type].get('fields', []))
                                            new_fields = set(entity_data.get('fields', []))
                                            extracted_entities[entity_type]['fields'] = sorted(list(existing_fields | new_fields))
                                    
                                    print(f"[DEBUG] Entity Resolution: Fetched {len(entity_results)} entity records")
                                    break
                        except Exception as e:
                            print(f"[DEBUG] Entity Resolution: Error fetching entities from aggregated query: {str(e)}")
        
        # Build context for agent
        entity_context = ""
        if extracted_entities:
            entity_context = "\n[PREVIOUS QUERY RESULTS AND QUERIES - EXTRACTED ENTITIES]\n"
            entity_context += "The following entities were found in previous query results and/or query structures:\n"
            for entity_type, entity_data in extracted_entities.items():
                values = entity_data.get('values', [])
                fields = entity_data.get('fields', [])
                
                if values:
                    entity_context += f"\n{entity_type.upper()} entities found ({len(values)} values):\n"
                    for val in values[:10]:
                        entity_context += f"  - {val}\n"
                    if len(values) > 10:
                        entity_context += f"  ... and {len(values) - 10} more\n"
                    entity_context += f"  Fields: {', '.join(fields[:3])}\n"
                    entity_context += f"  Confidence: {entity_data.get('confidence', 0.0):.2f}\n"
                elif fields:
                    entity_context += f"\n{entity_type.upper()} fields found in previous queries:\n"
                    entity_context += f"  Fields: {', '.join(fields[:5])}\n"
                    entity_context += f"  Note: These fields were found in query structures (e.g., groupby {fields[0]}). "
                    entity_context += f"The query references '{entity_type}' entities, but actual values need to be fetched.\n"
                    entity_context += f"  Confidence: {entity_data.get('confidence', 0.0):.2f}\n"
        else:
            entity_context = "\n[PREVIOUS QUERY RESULTS AND QUERIES]\nNo entities extracted from previous results or queries.\n"
        
        # Build agent input
        agent_input = f"""User Query: "{user_query}"

{entity_context}

Analyze the user query and determine if it references entities from previous results. If so, resolve those references to actual entity values.

Return a JSON object with:
- "detected_entity_types": List of entity types mentioned in query (e.g., ["user", "ip"])
- "resolved_entities": Dictionary mapping entity type to list of resolved values
- "confidence_scores": Dictionary mapping entity type to confidence (0.0-1.0)
- "reasoning": Explanation of how entities were detected and resolved
- "has_references": Boolean indicating if query contains entity references"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an Entity Resolution Agent that analyzes user queries to detect entity references and resolves them to actual values from previous query results.

**Your Task:**
1. Analyze the user query to detect entity references (explicit or implicit)
2. Extract entities from previous query results
3. Resolve references to actual entity values based on query context
4. Return resolved entities with confidence scores

**Entity Reference Detection:**
- Explicit references: "this user", "that user", "the user", "this IP", "that IP", "the IP", "those hostnames", "these IPs", "the users"
- Implicit references: "user" when only one user exists in previous results

**Entity Types to Detect:**
- user: users, usernames, accounts
- ip: IP addresses (source, destination, etc.)
- hostname: hostnames, systems, machines
- domain: domain names, FQDNs
- filepath: file paths, filenames

**Resolution Logic:**
1. Extract all entities of relevant types from previous results
2. When multiple entities exist, select most relevant based on query context
3. For plural references ("users", "IPs"), extract all matching entities
4. For singular references ("this user", "the IP"), select the most relevant single entity

**IMPORTANT:**
- Only resolve entities if previous results/queries are provided
- Explicit references like "this user", "that user", "the user", "this IP" ALWAYS indicate a reference to previous results
- If the context shows "USER entities found" and the query says "this user" or "that user", you MUST set has_references: true and resolve the entities"""),
            ("human", "{input}")
        ])
        
        # Track metrics
        workflow_metrics = state.get("workflow_metrics", [])
        model = get_model("entity_resolution")
        model_name = get_model_name("entity_resolution")
        metrics = ExecutionMetrics("Entity Resolution Agent", model=model_name)
        
        if config.enable_detailed_tracing:
            metrics.start()
        
        chain = prompt | model
        response = await chain.ainvoke({"input": agent_input})
        
        # Extract metrics from response
        if config.enable_detailed_tracing:
            metrics.end()
            extracted = extract_metrics_from_langchain_response(response, "Entity Resolution Agent", model_name)
            if extracted:
                metrics = extracted
            workflow_metrics.append(metrics.to_dict())
            print(metrics.format_output())
        
        content = response.content.strip()
        
        # Extract JSON
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        
        result = json.loads(content)
        
        entity_resolution = EntityResolutionOutput(
            detected_entity_types=result.get("detected_entity_types", []),
            resolved_entities=result.get("resolved_entities", {}),
            confidence_scores=result.get("confidence_scores", {}),
            reasoning=result.get("reasoning", ""),
            has_references=result.get("has_references", False)
        )
        
        if entity_resolution.has_references and entity_resolution.resolved_entities:
            print(f"[DEBUG] Entity Resolution: Detected references to {entity_resolution.detected_entity_types}")
            print(f"[DEBUG] Entity Resolution: Resolved entities: {entity_resolution.resolved_entities}")
            print(f"[DEBUG] Entity Resolution: Reasoning: {entity_resolution.reasoning}")
            
            # Build context string for query generation
            resolved_entities_context = "\n[RESOLVED ENTITIES FROM PREVIOUS RESULTS]\n"
            resolved_entities_context += "The following entities were found in previous query results and are referenced in your query:\n\n"
            
            for entity_type, values in entity_resolution.resolved_entities.items():
                if values:
                    resolved_entities_context += f"{entity_type.upper()}:\n"
                    for val in values[:5]:
                        resolved_entities_context += f"  - {val}\n"
                    if len(values) > 5:
                        resolved_entities_context += f"  ... and {len(values) - 5} more\n"
                    confidence = entity_resolution.confidence_scores.get(entity_type, 0.0)
                    resolved_entities_context += f"  Confidence: {confidence:.2f}\n\n"
            
            resolved_entities_context += "**IMPORTANT**: When generating DQL queries, use these actual entity values instead of placeholders like '<user>' or '<ip>'.\n"
            resolved_entities_context += "For example, if user='john.doe@example.com' is provided, use 'john.doe@example.com' directly in your queries.\n"
            resolved_entities_context += f"Reasoning: {entity_resolution.reasoning}\n"
        else:
            print("[DEBUG] Entity Resolution: No entity references detected in query")
            resolved_entities_context = ""
        
        result_dict = {
            "entity_resolution": entity_resolution,
            "resolved_entities_context": resolved_entities_context
        }
        
        if config.enable_detailed_tracing:
            result_dict["workflow_metrics"] = workflow_metrics
        
        return result_dict
    except Exception as e:
        print(f"[DEBUG] Entity Resolution: Error during entity resolution: {str(e)}")
        if config.enable_detailed_tracing:
            metrics.end()
            workflow_metrics = state.get("workflow_metrics", [])
            workflow_metrics.append(metrics.to_dict())
        result_dict = {
            "entity_resolution": None,
            "resolved_entities_context": ""
        }
        if config.enable_detailed_tracing:
            result_dict["workflow_metrics"] = workflow_metrics
        return result_dict


async def stream_action_context_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Generate stream action context for query generation.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with stream action context
    """
    user_query = state.get("original_user_query", state.get("user_query", ""))
    
    print("[DEBUG] Stream Identification: Starting stream identification process...")
    stream_action_context = await format_stream_action_context(user_query)
    
    print(f"[DEBUG] Stream Identification: Generated context ({len(stream_action_context)} chars)")
    
    return {
        "stream_action_context": stream_action_context
    }


async def human_to_dql_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Convert human language to DQL queries using LangChain agent with tools.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with generated queries
    """
    user_query = state.get("original_user_query", state.get("user_query", ""))
    modification_type = state.get("modification_type")
    detected_duration = state.get("detected_duration")
    previous_queries = state.get("previous_queries", [])
    previous_csv_indices = state.get("previous_csv_indices", [])
    resolved_entities_context = state.get("resolved_entities_context", "")
    stream_action_context = state.get("stream_action_context", "")
    
    # Build user message with context
    user_message_text = user_query
    
    # Add modification context
    if modification_type:
        mod_types = modification_type if isinstance(modification_type, list) else [modification_type]
        mod_context = f"\n[Modification context: {', '.join(mod_types)}"
        
        if "more_ways" in mod_types:
            mod_context += " - User wants more alternatives. Exclude previously fetched queries."
        if "duration_change" in mod_types and detected_duration:
            mod_context += f" - User wants to change duration to: {detected_duration}"
        if "query_change" in mod_types:
            mod_context += " - Query intent/entities changed. Generate new queries."
        if "unrelated" in mod_types:
            mod_context += " - This is a completely unrelated query. Perform fresh search."
        
        if "duration_change" in mod_types and "query_change" in mod_types:
            mod_context += " - Combination: Generate new queries with new duration."
        elif "duration_change" in mod_types and "query_change" not in mod_types:
            mod_context += " - Only duration changed. Use modify_dql_query to update existing queries."
        elif "duration_change" in mod_types and "more_ways" in mod_types:
            mod_context += " - Modify duration AND exclude previous CSV indices."
        
        mod_context += "]"
        user_message_text = user_message_text + "\n" + mod_context
    
    # Add stream action context
    if stream_action_context:
        user_message_text = user_message_text + "\n" + stream_action_context
    
    # Add resolved entities context
    if resolved_entities_context:
        user_message_text = user_message_text + "\n" + resolved_entities_context
    
    # Create LangChain agent with tools
    # Import from installed langchain package (no conflict now that local folder is renamed to b_copilot)
    
    tools = [search_dql_csv, modify_dql_query]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are the "DNIF-Chat" assistant for https://www.dnif.it/en/kb DNIF.
DQL Knowledge Base: {BASE_DQL}

**STREAM ACTION MAPPING GUIDANCE:**

When generating queries (especially when CSV search returns no results), use the Stream Action mapping to determine which stream to query:

1. **Stream selection**: Use the Stream Action mapping provided in context to identify the correct stream(s)
2. **Query diversity**: Generate diverse queries - don't just filter by action:
   - Some queries can use action filters: `where action='USER_LOCKED'` or `where action in ('USER_LOCKED','USER_LOCKOUT')`
   - Some queries can filter by other fields: `where status='FAILED'` or `where reason like '%LOCK%'` or `where targetuser is not null`
   - Some queries can query the stream without action filters: `stream=iam | duration 3d | groupby user`
   - Use different groupby fields, different filters, different approaches
   - Vary the query patterns to provide comprehensive coverage
3. **Use correct columns**: 
   - For IAM and CONFIGURATION streams, use ONLY the columns listed in Stream DDM.txt (provided in context)
   - For other streams, use columns from the DQL Knowledge Base
4. **Action format**: Actions in DQL queries should be in UPPERCASE with underscores (e.g., 'LOGIN', 'USER_CREATED')
5. **Column format**: Column names in DQL queries should be in lowercase (e.g., 'user', 'srcip', 'action')

{stream_action_context}

**ENTITY RESOLUTION - CRITICAL:**

If the context includes "[RESOLVED ENTITIES FROM PREVIOUS RESULTS]", this means the user's query references entities (users, IPs, hostnames, etc.) from previous query results.

**YOU MUST:**
- Use the ACTUAL entity values provided in the resolved entities section
- DO NOT use placeholders like '<user>', '<ip>', '<hostname>' in your queries
- Replace any placeholders with the actual values from the resolved entities

**CONTEXT-AWARE WORKFLOW:**

Check conversation history for context:
- If user asks for "more ways" or alternatives → Use search_dql_csv with exclude_query_indices to exclude previously fetched queries
- If user mentions duration change (e.g., "2 weeks", "last 2 weeks") → Use modify_dql_query to modify existing queries
- If completely unrelated topic → Fresh CSV search (no exclusions)
- Otherwise → Normal CSV search

**CRITICAL WORKFLOW - FOLLOW STRICTLY:**

1. **Check conversation history** for previous queries and modification intent

2. **For "more_ways" requests:**
   - Call search_dql_csv with exclude_query_indices containing previously fetched CSV indices
   - Get next batch of queries (next top 3)
   - If CSV returns queries: Use them
   - If CSV returns empty or low confidence: Generate new queries

3. **For "duration_change" requests:**
   - Find previous queries in conversation history
   - Use modify_dql_query tool to modify each query's duration
   - Return modified queries as numbered list

4. **For normal/new queries:**
   - Call search_dql_csv tool FIRST with the user's query (no exclusions)
   - Use the default min_confidence threshold (0.7) when calling search_dql_csv
   - If CSV returns queries (non-empty matches):
     - Use ONLY the queries from CSV (up to 3)
     - DO NOT generate your own queries
   - If CSV returns NO queries or empty matches OR fallback_needed=True:
     - THEN generate exactly 3 DQL queries yourself
     - When generating queries, use the Stream Action mapping context provided above to determine correct streams and actions

5. **Always return queries as a simple numbered list**, one per line.
   - DO NOT use markdown code blocks (no ``` backticks)
   - DO NOT wrap queries in backticks or code formatting
   - Just plain text queries, one per line

Example output:
1. stream=authentication where action='LOGIN' and status='FAILED' | duration 2w | groupby user
2. stream=firewall where action='PACKET_BLOCKED' | duration 2w | groupby srcip
3. stream=signals where detectionseverity='HIGH' | duration 2w

NO JSON, NO explanations, NO markdown formatting, JUST plain numbered queries."""),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])
    
    llm = get_model("human_to_dql")
    model_name = get_model_name("human_to_dql")
    
    # Build system prompt from the ChatPromptTemplate
    try:
        formatted_messages = prompt.format_messages(input=user_message_text)
        system_prompt = formatted_messages[0].content if formatted_messages else None
    except:
        # Fallback: build system prompt manually
        system_prompt = f"""You are the "DNIF-Chat" assistant for https://www.dnif.it/en/kb DNIF.
DQL Knowledge Base: {BASE_DQL}

{stream_action_context}

**CRITICAL WORKFLOW - FOLLOW STRICTLY:**

1. Call search_dql_csv tool FIRST with the user's query (no exclusions)
2. Use the default min_confidence threshold (0.7) when calling search_dql_csv
3. If CSV returns queries (non-empty matches):
   - Use ONLY the queries from CSV (up to 3)
   - DO NOT generate your own queries
4. If CSV returns NO queries or empty matches OR fallback_needed=True:
   - THEN generate exactly 3 DQL queries yourself

5. **Always return queries as a simple numbered list**, one per line.
   - DO NOT use markdown code blocks (no ``` backticks)
   - DO NOT wrap queries in backticks or code formatting
   - Just plain text queries, one per line

NO JSON, NO explanations, NO markdown formatting, JUST plain numbered queries."""
    
    # Track metrics
    workflow_metrics = state.get("workflow_metrics", [])
    metrics = ExecutionMetrics("Human to DQL Agent", model=model_name)
    
    # Create agent using LangChain 1.2+ API
    agent_graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        debug=True
    )
    
    try:
        if config.enable_detailed_tracing:
            metrics.start()
        
        # Invoke agent graph (LangChain 1.2+ returns a graph, not an executor)
        # The graph expects messages in LangChain message format
        result = await agent_graph.ainvoke({
            "messages": [HumanMessage(content=user_message_text)]
        })
        
        # Extract metrics from agent result
        if config.enable_detailed_tracing:
            metrics.end()
            extracted = extract_metrics_from_langchain_response(result, "Human to DQL Agent", model_name)
            if extracted:
                metrics = extracted
            workflow_metrics.append(metrics.to_dict())
            print(metrics.format_output())
        
        # Extract output from result (LangChain 1.2+ format)
        # Result structure: {"messages": [...], ...}
        messages = result.get("messages", [])
        
        # Find the last assistant message with the output
        queries_text = ""
        for msg in reversed(messages):
            if hasattr(msg, 'content') and msg.content:
                queries_text = str(msg.content)
                break
        
        if not queries_text:
            # Fallback: try to get from result directly
            queries_text = result.get("output", "") or result.get("response", "") or str(result)
        
        # Parse queries
        queries = parse_query_response(queries_text)
        queries = queries[:3]  # Ensure max 3 queries
        
        print(f"[DEBUG] Retrieved {len(queries)} queries")
        for i, q in enumerate(queries, 1):
            print(f"[DEBUG]   Query {i}: {q}")
        
        if not queries:
            print("[DEBUG] No valid queries found")
            return {
                "queries": [],
                "csv_indices": [],
                "query_sources": [],
                "status": "error"
            }
        
        # Extract CSV indices and query sources from tool calls
        csv_indices = []
        csv_matches = []  # Store CSV matches with their queries
        
        # Parse messages to find tool calls (LangChain 1.2+ format)
        # Tool calls are in ToolMessage objects
        for msg in messages:
            if isinstance(msg, ToolMessage):
                # Check if this is a search_dql_csv tool call
                tool_name = getattr(msg, 'name', None) or getattr(msg, 'tool', None) or getattr(msg, 'tool_call_id', None)
                # Also check the content for tool name
                if tool_name == 'search_dql_csv' or (hasattr(msg, 'name') and msg.name == 'search_dql_csv'):
                    # Extract CSV matches from tool output
                    tool_output = msg.content
                    if isinstance(tool_output, dict) and tool_output.get('success') and 'matches' in tool_output:
                        matches = tool_output.get('matches', [])
                        for match in matches:
                            if 'csv_index' in match and match['csv_index'] is not None:
                                csv_indices.append(match['csv_index'])
                                csv_matches.append({
                                    'csv_index': match['csv_index'],
                                    'query': match.get('query', ''),
                                    'name': match.get('name', '')
                                })
                    elif isinstance(tool_output, str):
                        # Try to parse JSON string
                        try:
                            import json
                            tool_output_dict = json.loads(tool_output)
                            if tool_output_dict.get('success') and 'matches' in tool_output_dict:
                                matches = tool_output_dict.get('matches', [])
                                for match in matches:
                                    if 'csv_index' in match and match['csv_index'] is not None:
                                        csv_indices.append(match['csv_index'])
                                        csv_matches.append({
                                            'csv_index': match['csv_index'],
                                            'query': match.get('query', ''),
                                            'name': match.get('name', '')
                                        })
                        except:
                            pass
        
        # Track which queries came from CSV vs generated
        # Match queries to CSV matches by comparing query strings
        query_sources = []  # List of 'csv' or 'generated' for each query
        for query in queries:
            query_from_csv = False
            for csv_match in csv_matches:
                # Compare queries (normalize whitespace)
                csv_query = csv_match['query'].strip()
                if csv_query and csv_query.strip() == query.strip():
                    query_from_csv = True
                    break
            query_sources.append('csv' if query_from_csv else 'generated')
        
        print(f"[DEBUG] Query Sources: {query_sources}")
        csv_query_count = sum(1 for s in query_sources if s == 'csv')
        print(f"[DEBUG] Query Sources: {csv_query_count} from CSV, {len(queries) - csv_query_count} generated")
        
        result_dict = {
            "queries": queries,
            "csv_indices": csv_indices,
            "query_sources": query_sources
        }
        
        if config.enable_detailed_tracing:
            result_dict["workflow_metrics"] = workflow_metrics
        
        return result_dict
    except Exception as e:
        print(f"[DEBUG] Human to DQL: Error - {str(e)}")
        if config.enable_detailed_tracing:
            metrics.end()
            workflow_metrics = state.get("workflow_metrics", [])
            workflow_metrics.append(metrics.to_dict())
        result_dict = {
            "queries": [],
            "csv_indices": [],
            "query_sources": [],
            "status": "error"
        }
        if config.enable_detailed_tracing:
            result_dict["workflow_metrics"] = workflow_metrics
        return result_dict


async def sql_to_dql_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Convert SQL query to DQL query.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with converted query
    """
    user_query = state.get("user_query", "")
    
    print("[DEBUG] Converting SQL to DQL...")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are the "DNIF-Chat" assistant for https://www.dnif.it/en/kb DNIF.
DQL Knowledge Base: {BASE_DQL}
Your task is to learn this new query language and convert SQL queries to DQL.
Output should be in text format"""),
        ("human", "{input}")
    ])
    
    model = get_model("sql_to_dql")
    chain = prompt | model
    
    try:
        response = await chain.ainvoke({"input": user_query})
        output_text = response.content
        
        print(output_text)
        
        return {
            "result": {
                "output_text": output_text
            },
            "status": "completed"
        }
    except Exception as e:
        print(f"[DEBUG] SQL to DQL: Error - {str(e)}")
        return {
            "result": {
                "output_text": f"Error converting SQL to DQL: {str(e)}"
            },
            "status": "error"
        }


async def query_execution_tool(state: WorkflowState) -> Dict[str, Any]:
    """
    Execute DQL queries with early stopping for high confidence queries.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with execution results
    """
    queries = state.get("queries", [])
    query_sources = state.get("query_sources", [])
    executed_queries = state.get("executed_queries", [])
    original_user_query = state.get("original_user_query", state.get("user_query", ""))
    is_high_confidence = state.get("is_high_confidence", False)
    
    if not queries:
        return {
            "execution_results": [],
            "queries_skipped": []
        }
    
    print("[DEBUG] Executing queries...")
    execution_results = []
    queries_skipped = []
    
    # Filter out already executed queries
    tasks = {}
    tasks_to_execute = []
    for idx, query in enumerate(queries, 1):
        if query in executed_queries:
            print(f"[DEBUG] Query {idx} already executed previously, skipping")
            continue
        
        source = query_sources[idx - 1] if idx <= len(query_sources) else 'generated'
        
        task = asyncio.create_task(
            _execute_single_query(
                idx=idx,
                query=query,
                source=source,
                original_user_query=original_user_query,
                executed_queries=executed_queries
            )
        )
        tasks[idx] = task
        tasks_to_execute.append(idx)
    
    if not tasks:
        print("[DEBUG] No queries to execute (all already executed)")
        return {
            "execution_results": [],
            "queries_skipped": []
        }
    
    print(f"[DEBUG] Executing {len(tasks)} queries...")
    
    # Process results sequentially for early stopping
    for query_idx in sorted(tasks.keys()):
        task = tasks[query_idx]
        
        try:
            result = await task
            
            if result.get('success'):
                execution_results.append(result)
                executed_queries.append(result['query'])
                
                result_count = result.get('result_count', 0)
                
                # High confidence: stop early if query returned results (>0 records)
                if is_high_confidence and result_count > 0:
                    print(f"[DEBUG] High confidence query {query_idx} returned {result_count} records - stopping early")
                    
                    # Cancel remaining tasks
                    for remaining_idx in sorted(tasks.keys()):
                        if remaining_idx > query_idx:
                            remaining_task = tasks[remaining_idx]
                            if not remaining_task.done():
                                remaining_task.cancel()
                                remaining_query = queries[remaining_idx - 1]
                                if remaining_query not in executed_queries:
                                    queries_skipped.append({
                                        'query_idx': remaining_idx,
                                        'query': remaining_query,
                                        'source': query_sources[remaining_idx - 1] if remaining_idx <= len(query_sources) else 'generated',
                                        'reason': 'skipped_due_to_early_stop'
                                    })
                    
                    # Wait for cancellations to complete
                    for remaining_idx in sorted(tasks.keys()):
                        if remaining_idx > query_idx:
                            remaining_task = tasks[remaining_idx]
                            if not remaining_task.done():
                                try:
                                    await remaining_task
                                except asyncio.CancelledError:
                                    pass
                    
                    break
            else:
                # Query failed or returned 0 results
                execution_results.append(result)
        
        except asyncio.CancelledError:
            print(f"[DEBUG] Query {query_idx} was cancelled due to early stop")
            pass
        except Exception as e:
            error_msg = str(e)
            print(f"[DEBUG] Unexpected error processing Query {query_idx}: {error_msg}")
            execution_results.append({
                'query_idx': query_idx,
                'query': queries[query_idx - 1],
                'source': query_sources[query_idx - 1] if query_idx <= len(query_sources) else 'generated',
                'error': error_msg,
                'result_count': 0,
                'success': False
            })
    
    # Ensure all remaining tasks are awaited/cancelled
    for query_idx in sorted(tasks.keys()):
        task = tasks[query_idx]
        if not task.done():
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    
    if queries_skipped:
        print(f"[DEBUG] Skipped {len(queries_skipped)} queries due to early stop (high confidence)")
    
    return {
        "execution_results": execution_results,
        "queries_skipped": queries_skipped,
        "executed_queries": executed_queries
    }


async def _execute_single_query(
    idx: int,
    query: str,
    source: str,
    original_user_query: str,
    executed_queries: list
) -> dict:
    """
    Execute a single query and return result.
    
    Args:
        idx: Query index (1-based)
        query: DQL query string
        source: Query source ('csv' or 'generated')
        original_user_query: Original user query for context
        executed_queries: List of executed queries (for tracking)
        
    Returns:
        Dictionary with query execution result
    """
    print(f"[DEBUG] Executing Query {idx} (source: {source})...")
    try:
        exec_result = await execute_query_with_external_polling(query=query)
        
        if exec_result.get('success'):
            query_results = exec_result.get('results', [])
            result_count = len(query_results)
            key_answer = extract_key_answer(
                query_results,
                original_user_query,
                query=query
            )
            one_line_summary = generate_one_line_summary(
                query_results,
                original_user_query,
                query=query
            )
            print(f"[DEBUG] Query {idx} completed: {result_count} records")
            return {
                'query_idx': idx,
                'query': query,
                'source': source,
                'result_count': result_count,
                'results': query_results,
                'key_answer': key_answer,
                'one_line_summary': one_line_summary,
                'success': True
            }
        else:
            error_msg = exec_result.get('error', 'Unknown error')
            print(f"[DEBUG] Error executing Query {idx}: {error_msg}")
            return {
                'query_idx': idx,
                'query': query,
                'source': source,
                'error': error_msg,
                'result_count': 0,
                'success': False
            }
    except Exception as e:
        error_msg = str(e)
        print(f"[DEBUG] Error executing Query {idx}: {error_msg}")
        return {
            'query_idx': idx,
            'query': query,
            'source': source,
            'error': error_msg,
            'result_count': 0,
            'success': False
        }