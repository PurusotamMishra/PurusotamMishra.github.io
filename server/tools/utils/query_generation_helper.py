"""
Helper functions for query generation using Stream Action and DDM mappings (LangGraph version).
Hybrid approach: rule-based (fast) + agent-based (accurate) fallback.
"""
import re
from typing import Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append("/app/server")

from tools.schemas.models import StreamActionMapperOutput
from tools.utils.model_factory import get_model
from tools.utils.stream_action_parser import (
    parse_stream_action_file,
)
from tools.utils.stream_ddm_parser import (
    parse_stream_ddm_file,
    get_stream_columns,
    has_stream_columns
)


def extract_action_keywords(user_query: str) -> List[str]:
    """
    Extract potential action keywords from user query.
    
    This function looks for:
    - Explicit action mentions (e.g., "LOGIN", "USER_CREATED")
    - Common action-related phrases that might map to actions
    
    Args:
        user_query: User's natural language query
        
    Returns:
        List of potential action keywords found in the query
    """
    print(f"[DEBUG] Stream Identification: Extracting actions from query: '{user_query}'")
    query_upper = user_query.upper()
    potential_actions: List[str] = []
    
    # Get all known actions from Stream Action mapping
    action_to_stream = parse_stream_action_file()
    all_actions = set(action_to_stream.keys())
    print(f"[DEBUG] Stream Identification: Loaded {len(all_actions)} known actions from Stream Action mapping")
    
    # Context-aware action patterns (check these first for better accuracy)
    # These patterns consider context like "user locked" -> USER_LOCKED
    # Handle variations like "users that got locked out", "user locked", "locked out users"
    context_aware_patterns = [
        (r'\b(USER|USERS|ACCOUNT|ACCOUNTS)\b.*?\b(LOCKED|LOCK\s+OUT|LOCKOUT)\b', ['USER_LOCKED', 'USER_LOCKOUT']),
        (r'\b(LOCKED|LOCK\s+OUT|LOCKOUT)\b.*?\b(USER|USERS|ACCOUNT|ACCOUNTS)\b', ['USER_LOCKED', 'USER_LOCKOUT']),
        (r'\b(USER|USERS)\s+(CREATED|CREATION)\b', ['USER_CREATED']),
        (r'\b(USER|USERS)\s+(DELETED|DELETION)\b', ['USER_DELETED']),
        (r'\b(USER|USERS)\s+(UPDATED|UPDATE)\b', ['USER_UPDATED']),
        (r'\b(USER|USERS)\s+(ACTIVATED|ACTIVATION)\b', ['USER_ACTIVATED']),
        (r'\b(USER|USERS)\s+(DEACTIVATED|DEACTIVATION)\b', ['USER_DEACTIVATED']),
        (r'\b(USER|USERS)\s+(SUSPENDED|SUSPENSION)\b', ['USER_SUSPENDED']),
        (r'\b(USER|USERS)\s+(UNLOCKED|UNLOCK)\b', ['USER_UNLOCKED']),
        (r'\b(PASSWORD)\s+(CHANGED|CHANGE)\b', ['PASSWORD_CHANGED']),
        (r'\b(PASSWORD)\s+(CREATED|CREATE)\b', ['PASSWORD_CREATED']),
        (r'\b(PASSWORD)\s+(DELETED|DELETE)\b', ['PASSWORD_DELETED']),
    ]
    
    # Check context-aware patterns first
    for pattern_str, possible_actions in context_aware_patterns:
        matches = re.findall(pattern_str, query_upper, re.IGNORECASE)
        if matches:
            for action in possible_actions:
                if action in all_actions:
                    potential_actions.append(action)
                    print(f"[DEBUG] Stream Identification: Context-aware match: pattern '{pattern_str}' -> action '{action}'")
    
    # Common action-related phrases to look for (fallback)
    action_patterns = [
        r'\b(LOGIN|LOGOUT|LOG\s+IN|LOG\s+OUT)\b',
        r'\b(USER\s+CREATED|USER\s+DELETED|USER\s+UPDATED)\b',
        r'\b(PASSWORD\s+CHANGED|PASSWORD\s+CREATED|PASSWORD\s+DELETED)\b',
        r'\b(PACKET\s+BLOCKED|PACKET\s+ALLOWED)\b',
        r'\b(CONNECTION\s+ESTABLISHED|CONNECTION\s+TERMINATED)\b',
        r'\b(FILE\s+CREATED|FILE\s+DELETED|FILE\s+MODIFIED)\b',
        r'\b(PROCESS\s+CREATED|PROCESS\s+STARTED|PROCESS\s+STOPPED)\b',
        r'\b(THREAT\s+DETECTED|THREAT\s+BLOCKED)\b',
        r'\b(EMAIL\s+SENT|EMAIL\s+RECEIVED|EMAIL\s+DELIVERED)\b',
        r'\b(URL\s+BLOCKED|URL\s+ALLOWED|URL\s+ACCESSED)\b',
        r'\b(CONFIGURATION\s+CHANGED)\b',
        r'\b(ROLE\s+ADDED|ROLE\s+REMOVED|ROLE\s+UPDATED)\b',
        r'\b(GROUP\s+CREATED|GROUP\s+DELETED|GROUP\s+UPDATED)\b',
    ]
    
    # Check for explicit action mentions (exact matches or with underscores/spaces)
    # Prioritize USER_* actions over generic ones when "user" context is present
    user_context_present = re.search(r'\b(USER|USERS|ACCOUNT|ACCOUNTS)\b', query_upper, re.IGNORECASE)
    
    for action in all_actions:
        # Skip generic LOCKED if we already found USER_LOCKED or USER_LOCKOUT
        if action == 'LOCKED' and ('USER_LOCKED' in potential_actions or 'USER_LOCKOUT' in potential_actions):
            continue
        
        # Convert action to search patterns (handle underscores and spaces)
        action_pattern = action.replace('_', r'[\s_]+')
        pattern = re.compile(rf'\b{re.escape(action)}\b|\b{action_pattern}\b', re.IGNORECASE)
        if pattern.search(user_query):
            potential_actions.append(action)
    
    # Also check for common patterns
    for pattern_str in action_patterns:
        matches = re.findall(pattern_str, query_upper)
        for match in matches:
            if isinstance(match, tuple):
                match = ' '.join(match)
            # Normalize to action format (uppercase, underscores)
            normalized = match.replace(' ', '_').upper()
            if normalized in all_actions:
                # Skip generic LOCKED if we already have USER_LOCKED
                if normalized == 'LOCKED' and ('USER_LOCKED' in potential_actions or 'USER_LOCKOUT' in potential_actions):
                    continue
                potential_actions.append(normalized)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_actions = []
    for action in potential_actions:
        if action not in seen:
            seen.add(action)
            unique_actions.append(action)
    
    if unique_actions:
        print(f"[DEBUG] Stream Identification: Found {len(unique_actions)} action(s): {', '.join(unique_actions)}")
    else:
        print(f"[DEBUG] Stream Identification: No actions detected in query")
    
    return unique_actions


def get_stream_from_action_rules(user_query: str) -> Dict[str, any]:
    """
    Rule-based extraction of actions from user query and stream mapping.
    Fast path - uses pattern matching.
    
    Args:
        user_query: User's natural language query
        
    Returns:
        Dictionary with:
        - 'suggested_streams': List of stream names (uppercase) that match actions
        - 'matched_actions': List of actions found and their streams
        - 'stream_action_map': Dict mapping stream -> list of matched actions
        - 'confidence': Confidence score (0.0-1.0)
    """
    print(f"[DEBUG] Stream Identification (Rules): Mapping actions to streams for query: '{user_query}'")
    
    # Extract potential actions from query
    potential_actions = extract_action_keywords(user_query)
    
    # Map actions to streams
    action_to_stream = parse_stream_action_file()
    stream_action_map: Dict[str, List[str]] = {}
    matched_actions: List[Dict[str, str]] = []
    
    for action in potential_actions:
        stream = action_to_stream.get(action)
        if stream:
            if stream not in stream_action_map:
                stream_action_map[stream] = []
            stream_action_map[stream].append(action)
            matched_actions.append({
                'action': action,
                'stream': stream
            })
            print(f"[DEBUG] Stream Identification (Rules): Action '{action}' -> Stream '{stream}'")
        else:
            print(f"[DEBUG] Stream Identification (Rules): Action '{action}' not found in Stream Action mapping")
    
    suggested_streams = list(stream_action_map.keys())
    
    # Calculate confidence based on results
    confidence = 0.9 if suggested_streams and len(potential_actions) > 0 else 0.5
    
    if suggested_streams:
        print(f"[DEBUG] Stream Identification (Rules): Identified {len(suggested_streams)} stream(s): {', '.join(suggested_streams)}")
        for stream, actions in stream_action_map.items():
            print(f"[DEBUG] Stream Identification (Rules):   Stream '{stream}' has {len(actions)} action(s): {', '.join(actions)}")
    else:
        print(f"[DEBUG] Stream Identification (Rules): No streams identified from actions")
    
    return {
        'suggested_streams': suggested_streams,
        'matched_actions': matched_actions,
        'stream_action_map': stream_action_map,
        'confidence': confidence,
        'method': 'rules'
    }


async def get_stream_from_action_agent(user_query: str) -> Dict[str, any]:
    """
    Agent-based extraction of actions from user query and stream mapping.
    Accurate path - uses LLM for better context understanding.
    
    Args:
        user_query: User's natural language query
        
    Returns:
        Dictionary with:
        - 'suggested_streams': List of stream names (uppercase) that match actions
        - 'matched_actions': List of actions found and their streams
        - 'stream_action_map': Dict mapping stream -> list of matched actions
        - 'confidence': Confidence score from agent (0.0-1.0)
    """
    print(f"[DEBUG] Stream Identification (Agent): Using agent to map actions to streams for query: '{user_query}'")
    
    try:
        # Get mappings for context
        action_to_stream = parse_stream_action_file()
        stream_to_actions: Dict[str, List[str]] = {}
        for action, stream in action_to_stream.items():
            if stream not in stream_to_actions:
                stream_to_actions[stream] = []
            stream_to_actions[stream].append(action)
        
        # Build a summary of key mappings for the agent
        key_mappings = []
        for action, stream in list(action_to_stream.items())[:50]:  # Sample of mappings
            key_mappings.append(f"- {action} → {stream}")
        
        # Group by stream for better context
        stream_summary = []
        for stream, actions in list(stream_to_actions.items())[:20]:  # Top streams
            stream_summary.append(f"- {stream}: {len(actions)} actions (e.g., {', '.join(actions[:5])})")
        
        # Create prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a Stream Action Mapper for DNIF SIEM platform. Your task is to analyze user queries and identify which actions and streams are relevant.

**STREAM ACTION MAPPING:**
The following mappings show which actions belong to which streams:

{chr(10).join(key_mappings[:30])}
... (and {len(action_to_stream)} total action mappings)

**KEY STREAMS AND THEIR ACTIONS:**
{chr(10).join(stream_summary)}

**YOUR TASK:**
1. Analyze the user query to understand the intent
2. Identify relevant actions mentioned or implied in the query
3. Map those actions to the correct streams using the mapping above
4. Consider context carefully:
   - "users locked out" → USER_LOCKED or USER_LOCKOUT → IAM stream (NOT DOCUMENTS)
   - "failed login" → LOGIN with FAILED status → AUTHENTICATION stream
   - "packet blocked" → PACKET_BLOCKED → FIREWALL stream
   - "user created" → USER_CREATED → IAM stream
   - "configuration changed" → CONFIGURATION_CHANGED → CONFIGURATION stream

**IMPORTANT RULES:**
- When user mentions "user" or "users" + "locked", prioritize USER_LOCKED/USER_LOCKOUT over generic LOCKED
- When user mentions "user" + any action, prioritize USER_* actions over generic ones
- Consider the context: "locked out users" means USER_LOCKED, not document LOCKED
- Return actions in UPPERCASE with underscores (e.g., USER_LOCKED, PACKET_BLOCKED)
- Return streams in UPPERCASE (e.g., IAM, AUTHENTICATION, FIREWALL)"""),
            ("human", "{input}")
        ])
        
        llm = get_model("stream_action_context")
        chain = prompt | llm.with_structured_output(StreamActionMapperOutput)
        
        result: StreamActionMapperOutput = await chain.ainvoke({"input": user_query})
        
        actions = result.actions if result.actions else []
        streams = result.streams if result.streams else []
        confidence = result.confidence if result.confidence else 0.8
        reasoning = result.reasoning if result.reasoning else ''
        
        print(f"[DEBUG] Stream Identification (Agent): Agent reasoning: {reasoning}")
        print(f"[DEBUG] Stream Identification (Agent): Found {len(actions)} action(s): {', '.join(actions)}")
        print(f"[DEBUG] Stream Identification (Agent): Found {len(streams)} stream(s): {', '.join(streams)}")
        print(f"[DEBUG] Stream Identification (Agent): Confidence: {confidence}")
        
        # Build stream_action_map
        stream_action_map: Dict[str, List[str]] = {}
        matched_actions: List[Dict[str, str]] = []
        
        for action in actions:
            # Verify action exists in mapping
            stream = action_to_stream.get(action.upper())
            if stream:
                if stream not in stream_action_map:
                    stream_action_map[stream] = []
                stream_action_map[stream].append(action.upper())
                matched_actions.append({
                    'action': action.upper(),
                    'stream': stream
                })
            else:
                # Use stream from agent if action not found
                if streams:
                    stream = streams[0].upper() if streams else None
                    if stream:
                        if stream not in stream_action_map:
                            stream_action_map[stream] = []
                        stream_action_map[stream].append(action.upper())
        
        # Also add streams directly from agent
        for stream in streams:
            stream_upper = stream.upper()
            if stream_upper not in stream_action_map:
                stream_action_map[stream_upper] = []
        
        return {
            'suggested_streams': [s.upper() for s in streams] if streams else list(stream_action_map.keys()),
            'matched_actions': matched_actions,
            'stream_action_map': stream_action_map,
            'confidence': confidence,
            'method': 'agent',
            'reasoning': reasoning
        }
        
    except Exception as e:
        print(f"[DEBUG] Stream Identification (Agent): Error - {str(e)}")
        # Fallback to rules on error
        print(f"[DEBUG] Stream Identification (Agent): Falling back to rule-based approach")
        return get_stream_from_action_rules(user_query)


def should_use_agent(user_query: str, rule_result: Dict[str, any]) -> bool:
    """
    Determine if agent should be used based on rule-based results.
    
    Args:
        user_query: User's natural language query
        rule_result: Result from rule-based extraction
        
    Returns:
        True if agent should be used, False otherwise
    """
    # Use agent if:
    # 1. No streams found (rules failed)
    if not rule_result.get('suggested_streams'):
        print(f"[DEBUG] Stream Identification: Using agent - no streams found by rules")
        return True
    
    # 2. Low confidence
    if rule_result.get('confidence', 1.0) < 0.7:
        print(f"[DEBUG] Stream Identification: Using agent - low confidence ({rule_result.get('confidence')})")
        return True
    
    # 3. Ambiguous results (multiple streams or actions)
    streams = rule_result.get('suggested_streams', [])
    actions = rule_result.get('matched_actions', [])
    
    if len(streams) > 2:
        print(f"[DEBUG] Stream Identification: Using agent - too many streams ({len(streams)})")
        return True
    
    # 4. User context present but generic action found (e.g., "users locked" but found generic LOCKED)
    query_upper = user_query.upper()
    user_context = re.search(r'\b(USER|USERS|ACCOUNT|ACCOUNTS)\b', query_upper, re.IGNORECASE)
    if user_context:
        action_names = [a.get('action', '') for a in actions]
        # If user context but found generic actions (not USER_*)
        has_user_actions = any(a.startswith('USER_') for a in action_names)
        has_generic_actions = any(not a.startswith('USER_') and a in ['LOCKED', 'CREATED', 'DELETED', 'UPDATED'] for a in action_names)
        
        if has_generic_actions and not has_user_actions:
            print(f"[DEBUG] Stream Identification: Using agent - user context but generic actions found")
            return True
    
    # 5. Complex phrasing (long query with multiple clauses)
    # Only use agent if rules didn't find good results AND query is complex
    if len(user_query.split()) > 15 and not rule_result.get('suggested_streams'):
        print(f"[DEBUG] Stream Identification: Using agent - complex query with no rule matches")
        return True
    
    return False


async def get_stream_from_action(user_query: str, force_agent: bool = False) -> Dict[str, any]:
    """
    Hybrid approach: Try rule-based first, fallback to agent if needed.
    
    Args:
        user_query: User's natural language query
        force_agent: If True, skip rules and use agent directly
        
    Returns:
        Dictionary with suggested_streams, matched_actions, stream_action_map, confidence, method
    """
    if force_agent:
        print(f"[DEBUG] Stream Identification: Force using agent")
        return await get_stream_from_action_agent(user_query)
    
    # Try rule-based first (fast path)
    rule_result = get_stream_from_action_rules(user_query)
    
    # Decide if we need agent
    if should_use_agent(user_query, rule_result):
        print(f"[DEBUG] Stream Identification: Switching to agent-based approach")
        return await get_stream_from_action_agent(user_query)
    
    print(f"[DEBUG] Stream Identification: Using rule-based result (confidence: {rule_result.get('confidence')})")
    return rule_result


def get_stream_columns_info(stream: str) -> Optional[List[str]]:
    """
    Get column information for a stream from DDM file.
    Only returns columns for streams that have DDM data (IAM and CONFIGURATION).
    For other streams, returns None (columns are in knowledge base).
    
    Args:
        stream: Stream name (case-insensitive)
        
    Returns:
        List of column names in lowercase, or None if stream not in DDM
    """
    # Check if stream has columns in DDM file
    if has_stream_columns(stream):
        return get_stream_columns(stream)
    return None


async def format_stream_action_context(user_query: str, force_agent: bool = False) -> str:
    """
    Format Stream Action and DDM context for inclusion in agent instructions.
    Uses hybrid approach (rules + agent fallback).
    
    Args:
        user_query: User's natural language query
        force_agent: If True, skip rules and use agent directly
        
    Returns:
        Formatted string with stream suggestions and column information
    """
    print(f"[DEBUG] Stream Identification: Formatting context for query: '{user_query}'")
    result = await get_stream_from_action(user_query, force_agent=force_agent)
    
    method = result.get('method', 'unknown')
    confidence = result.get('confidence', 0.0)
    print(f"[DEBUG] Stream Identification: Used {method} method (confidence: {confidence:.2f})")
    
    if not result['suggested_streams']:
        print(f"[DEBUG] Stream Identification: No streams identified, returning empty context")
        return ""
    
    context_parts = []
    context_parts.append("\n[STREAM ACTION MAPPING CONTEXT]")
    if method == 'agent' and result.get('reasoning'):
        context_parts.append(f"Reasoning: {result['reasoning']}")
    context_parts.append("Based on the user query, the following stream(s) are likely relevant:")
    
    for stream in result['suggested_streams']:
        actions = result['stream_action_map'].get(stream, [])
        context_parts.append(f"\n- Stream: {stream}")
        
        # Make it more flexible - suggest actions but don't require them
        if actions:
            context_parts.append(f"  Relevant actions may include: {', '.join(actions)}")
            context_parts.append(f"  Note: You can use these actions OR generate queries without action filters, OR use other relevant fields")
        else:
            context_parts.append(f"  (Stream identified by {method} - generate diverse queries)")
        
        # Add column information if available in DDM
        columns = get_stream_columns_info(stream)
        if columns:
            context_parts.append(f"  Available columns (from DDM): {', '.join(columns[:10])}...")
            context_parts.append(f"  (Total {len(columns)} columns available - use any relevant columns)")
            print(f"[DEBUG] Stream Identification: Stream '{stream}' has {len(columns)} columns from DDM")
        else:
            print(f"[DEBUG] Stream Identification: Stream '{stream}' columns not in DDM (use knowledge base)")
    
    context_parts.append("\n**IMPORTANT**: Generate diverse queries - some with action filters, some without, using different fields and approaches.")
    
    context_str = "\n".join(context_parts)
    print(f"[DEBUG] Stream Identification: Generated context ({len(context_str)} chars)")
    return context_str


def get_all_stream_action_mappings() -> Dict[str, Dict[str, any]]:
    """
    Get complete Stream Action and DDM mappings for agent context.
    
    Returns:
        Dictionary with:
        - 'action_to_stream': Mapping of action -> stream
        - 'stream_to_actions': Mapping of stream -> list of actions
        - 'stream_columns': Mapping of stream -> list of columns (for IAM and CONFIGURATION only)
    """
    action_to_stream = parse_stream_action_file()
    
    # Build reverse mapping
    stream_to_actions: Dict[str, List[str]] = {}
    for action, stream in action_to_stream.items():
        if stream not in stream_to_actions:
            stream_to_actions[stream] = []
        stream_to_actions[stream].append(action)
    
    # Get column mappings for streams that have DDM data
    stream_columns = parse_stream_ddm_file()
    
    return {
        'action_to_stream': action_to_stream,
        'stream_to_actions': stream_to_actions,
        'stream_columns': stream_columns
    }
