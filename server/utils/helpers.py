"""
Utility functions for query parsing, similarity comparison, and result formatting (LangGraph version).
"""
import re
from openai import OpenAI
import numpy as np
from tabulate import tabulate


def parse_query_response(response_text: str) -> list:
    """
    Parse the numbered list response containing queries.
    Returns list of query strings.
    
    Args:
        response_text: The text response containing numbered queries
        
    Returns:
        List of query strings
    """
    # Remove any markdown formatting (code blocks with backticks)
    response_text = response_text.strip()
    
    # Remove markdown code blocks (```query``` or ```language\nquery```)
    # Match triple backticks with optional language identifier and optional newline
    response_text = re.sub(r'```[a-z]*\n?', '', response_text)
    # Remove any remaining triple backticks
    response_text = re.sub(r'```', '', response_text)
    # Remove any remaining single backticks that might wrap queries
    response_text = re.sub(r'^`+|`+$', '', response_text, flags=re.MULTILINE)
    
    # Try to extract numbered queries
    # Pattern: "1. query" or "1) query"
    numbered_pattern = r'^\s*\d+[\.\)]\s*(.+?)(?=\n\s*\d+[\.\)]|\Z)'
    matches = re.findall(numbered_pattern, response_text, re.MULTILINE | re.DOTALL)
    
    if matches:
        queries = []
        for m in matches:
            query = m.strip()
            # Remove any remaining markdown formatting (triple backticks)
            query = re.sub(r'```[a-z]*\n?', '', query)
            query = re.sub(r'```', '', query)
            # Remove single backticks at start/end
            query = re.sub(r'^`+|`+$', '', query)
            query = query.strip()
            if query:
                queries.append(query)
        return queries
    
    # Fallback: try to extract queries by stream= pattern
    query_pattern = r'stream=[\w\-]+.*?(?=\n\s*stream=|\Z)'
    queries = re.findall(query_pattern, response_text, re.DOTALL)
    
    if queries:
        cleaned_queries = []
        for q in queries:
            q = q.strip()
            # Remove markdown code blocks (triple backticks)
            q = re.sub(r'```[a-z]*\n?', '', q)
            q = re.sub(r'```', '', q)
            # Remove single backticks at start/end
            q = re.sub(r'^`+|`+$', '', q)
            q = q.strip()
            if q:
                cleaned_queries.append(q)
        return cleaned_queries
    
    # Last resort: return as single query if contains "stream="
    if 'stream=' in response_text:
        cleaned = response_text.strip()
        # Remove markdown code blocks (triple backticks)
        cleaned = re.sub(r'```[a-z]*\n?', '', cleaned)
        cleaned = re.sub(r'```', '', cleaned)
        # Remove single backticks at start/end
        cleaned = re.sub(r'^`+|`+$', '', cleaned, flags=re.MULTILINE)
        return [cleaned.strip()]
    
    # No valid queries found
    return []


def is_likely_follow_up(user_query: str, has_previous_query: bool = False) -> bool:
    """
    Detect if a query is likely a follow-up question using heuristics.
    
    Follow-up questions are typically:
    - Short (< 40 characters)
    - Contain only time-related keywords/phrases
    - Lack verbs or action words
    - Start with common follow-up patterns
    
    Args:
        user_query: The current user query text
        has_previous_query: Whether there is a previous query in context
        
    Returns:
        True if query is likely a follow-up, False otherwise
    """
    if not has_previous_query:
        return False
    
    query_lower = user_query.lower().strip()
    query_length = len(query_lower)
    
    # Very short queries are often follow-ups
    if query_length < 40:
        # Check if it's just a time fragment
        time_keywords = [
            'last', 'days', 'hours', 'weeks', 'minutes', 'for the last',
            'in the last', 'over the last', 'past', 'ago'
        ]
        
        # Check if query starts with common follow-up patterns
        follow_up_patterns = [
            'for the last', 'in the last', 'over the last', 'last',
            'what about', 'can you', 'show me', 'give me', 'how about'
        ]
        
        # Check if it contains only time-related words
        words = query_lower.split()
        has_time_keywords = any(keyword in query_lower for keyword in time_keywords)
        starts_with_pattern = any(query_lower.startswith(pattern) for pattern in follow_up_patterns)
        
        # Common verbs/action words that indicate a new query
        action_words = ['find', 'search', 'detect', 'show', 'list', 'get', 'analyze', 'check']
        has_action_words = any(word in action_words for word in words)
        
        # If it's short, has time keywords or starts with follow-up pattern, and lacks action words
        if (has_time_keywords or starts_with_pattern) and not has_action_words:
            return True
        
        # Very short queries (< 20 chars) without clear structure are likely follow-ups
        if query_length < 20 and not has_action_words:
            return True
    
    return False


def compare_query_similarity(current_query: str, previous_query: str) -> float:
    """
    Compare semantic similarity between current query and previous query using embeddings.
    
    Args:
        current_query: The current user query text
        previous_query: The previous user query text
        
    Returns:
        Similarity score between 0.0 and 1.0
        - >0.8: Highly similar (likely only duration changed)
        - <0.8: Query changed (different entities/intent)
    """
    try:
        # Initialize OpenAI client
        openai_client = OpenAI()
        
        # Get embeddings for both queries
        embeddings_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=[current_query, previous_query]
        )
        
        # Extract embeddings
        current_embedding = np.array(embeddings_response.data[0].embedding)
        previous_embedding = np.array(embeddings_response.data[1].embedding)
        
        # Compute cosine similarity
        similarity = np.dot(current_embedding, previous_embedding) / (
            np.linalg.norm(current_embedding) * np.linalg.norm(previous_embedding)
        )
        
        return float(similarity)
    except Exception as e:
        print(f"[DEBUG] Error computing similarity: {str(e)}")
        # On error, assume queries are different (conservative approach)
        return 0.0


def extract_key_answer(results: list, user_query: str, query: str = None) -> str:
    """
    Extract key answer from results based on user query intent.
    Returns formatted answer like "The top 10 IPs are: [list]" or "Found 7 records."
    
    Args:
        results: List of result dictionaries from DNIF API
        user_query: Original user query to understand intent
        query: Optional DQL query string
        
    Returns:
        Formatted answer string with key information
    """
    if not results:
        return "No results found."
    
    user_query_lower = user_query.lower()
    
    # Detect if user wants specific data (IPs, users, etc.)
    wants_ips = any(term in user_query_lower for term in ['ip', 'ips', 'ip address', 'ip addresses', 'source ip', 'srcip'])
    wants_users = any(term in user_query_lower for term in ['user', 'users', 'username'])
    wants_top_n = any(term in user_query_lower for term in ['top', 'first', 'list', 'show'])
    
    # Extract headers
    headers = list(results[0].keys()) if results else []
    
    # Check if this is an aggregated count query (e.g., select distinct_count(user))
    is_aggregated_count = False
    count_value = None
    count_field = None
    
    if query:
        query_lower = query.lower()
        # Check for distinct_count, count patterns
        if re.search(r'select\s+distinct_count\s*\(', query_lower) or re.search(r'select\s+count\s*\(', query_lower):
            is_aggregated_count = True
            # Find count field in results
            count_fields = [h for h in headers if 'count' in h.lower()]
            if count_fields and results:
                count_field = count_fields[0]
                # Get the count value from the first result
                count_value = results[0].get(count_field)
                try:
                    count_value = int(count_value) if count_value is not None else 0
                except (ValueError, TypeError):
                    count_value = 0
    
    # Find relevant field
    answer_lines = []
    
    if wants_ips:
        # Look for IP fields
        ip_fields = [h for h in headers if 'ip' in h.lower() and 'srcip' in h.lower()]
        if not ip_fields:
            ip_fields = [h for h in headers if 'ip' in h.lower()]
        
        if ip_fields and results:
            ip_field = ip_fields[0]
            ips = [str(r.get(ip_field, '')) for r in results if r.get(ip_field)]
            if ips:
                # Check if there's a count field (for groupby queries)
                count_fields = [h for h in headers if 'count' in h.lower()]
                if count_fields:
                    # Format as: IP (count)
                    answer_lines.append(f"The top {len(results)} IPs are:")
                    for r in results:
                        ip_val = str(r.get(ip_field, ''))
                        count_val = str(r.get(count_fields[0], ''))
                        answer_lines.append(f"  - {ip_val} ({count_val} attempts)")
                else:
                    answer_lines.append(f"The {len(ips)} IP{'s are' if len(ips) > 1 else ' is'}:")
                    for ip in ips:
                        answer_lines.append(f"  - {ip}")
    
    elif wants_users:
        # Check if this is an aggregated count query
        if is_aggregated_count and count_value is not None:
            # For aggregated count queries, use the count value, not the number of result rows
            if count_value == 0:
                return f"Found {count_value} users."
            else:
                return f"Found {count_value} user{'s' if count_value != 1 else ''}."
        
        # Look for user fields
        user_fields = [h for h in headers if 'user' in h.lower()]
        if user_fields and results:
            user_field = user_fields[0]
            users = [str(r.get(user_field, '')) for r in results if r.get(user_field) and r.get(user_field) not in ['', None]]
            if users:
                count_fields = [h for h in headers if 'count' in h.lower()]
                if count_fields:
                    answer_lines.append(f"The top {len(results)} user{'s are' if len(results) > 1 else ' is'}:")
                    for r in results:
                        user_val = str(r.get(user_field, ''))
                        count_val = str(r.get(count_fields[0], ''))
                        answer_lines.append(f"  - {user_val} ({count_val} events)")
                else:
                    answer_lines.append(f"The {len(users)} user{'s are' if len(users) > 1 else ' is'}:")
                    for user in users:
                        answer_lines.append(f"  - {user}")
    
    elif wants_top_n:
        # Generic top N answer
        if results:
            answer_lines.append(f"Found {len(results)} result{'s' if len(results) != 1 else ''}:")
            # Show first few key fields
            key_fields = headers[:3]  # First 3 fields
            for r in results[:10]:  # Limit to first 10
                values = [f"{h}: {r.get(h, '')}" for h in key_fields]
                answer_lines.append(f"  - {', '.join(values)}")
    
    if not answer_lines:
        # Fallback: check if aggregated count query
        if is_aggregated_count and count_value is not None:
            return f"Found {count_value} result{'s' if count_value != 1 else ''}."
        # Regular fallback: just count
        return f"Found {len(results)} result{'s' if len(results) != 1 else ''}."
    
    return "\n".join(answer_lines)


def extract_aggregated_count_info(results: list, query: str = None) -> dict:
    """
    Extract aggregated count information from results.
    
    Args:
        results: List of result dictionaries
        query: Optional DQL query string
        
    Returns:
        Dictionary with:
        - 'is_aggregated': bool
        - 'count_value': int or None (the actual count value)
        - 'count_field': str or None (the field name containing the count)
        - 'entity_type': str or None (what was counted, e.g., 'user', 'ip')
    """
    if not results or not query:
        return {'is_aggregated': False, 'count_value': None, 'count_field': None, 'entity_type': None}
    
    query_lower = query.lower()
    
    # Check if query uses aggregation
    if not (re.search(r'select\s+distinct_count\s*\(', query_lower) or 
            re.search(r'select\s+count\s*\(', query_lower)):
        return {'is_aggregated': False, 'count_value': None, 'count_field': None, 'entity_type': None}
    
    # Extract entity type from query
    entity_type = None
    distinct_count_match = re.search(r'select\s+distinct_count\s*\(\s*(\w+)', query_lower)
    if distinct_count_match:
        entity_type = distinct_count_match.group(1)
    
    # Find count field in results
    headers = list(results[0].keys()) if results else []
    count_fields = [h for h in headers if 'count' in h.lower()]
    
    if count_fields and results:
        count_field = count_fields[0]
        count_value = results[0].get(count_field)
        try:
            count_value = int(count_value) if count_value is not None else 0
        except (ValueError, TypeError):
            count_value = 0
        
        return {
            'is_aggregated': True,
            'count_value': count_value,
            'count_field': count_field,
            'entity_type': entity_type
        }
    
    return {'is_aggregated': False, 'count_value': None, 'count_field': None, 'entity_type': None}


def generate_one_line_summary(results: list, user_query: str, query: str = None) -> str:
    """
    Generate a concise one-line summary/insight from query results.
    Returns a single-line insight like "Analyzed authentication logs: 15 IPs with failed login attempts".
    
    Args:
        results: List of result dictionaries from API
        user_query: Original user query to understand intent
        query: Optional query string to extract context
        
    Returns:
        Single-line summary string with key insight in human-readable language for SOC analysts
    """
    if not results:
        # Try to extract context from query for empty results
        if query:
            query_lower = query.lower()
            # Extract log type from query
            log_type_match = re.search(r'stream=([\w\-]+)', query_lower)
            log_type_name = log_type_match.group(1) if log_type_match else None
            
            # Map to human-readable log types
            log_type_map = {
                'authentication': 'authentication logs',
                'network': 'network logs',
                'firewall': 'firewall logs',
                'dns': 'DNS logs',
                'proxy': 'proxy logs',
                'windows': 'Windows event logs',
                'linux': 'Linux system logs',
                'web': 'web server logs'
            }
            
            readable_log_type = log_type_map.get(log_type_name, f"{log_type_name} logs" if log_type_name else None)
            
            if readable_log_type:
                return f"Analyzed {readable_log_type}: No matching events found"
        
        return "No matching events found in the analyzed logs"
    
    result_count = len(results)
    headers = list(results[0].keys()) if results else []
    
    # Extract context from query string
    query_lower = query.lower() if query else ""
    user_query_lower = user_query.lower()
    
    # Extract log type from query
    log_type_match = re.search(r'stream=([\w\-]+)', query_lower)
    log_type_name = log_type_match.group(1) if log_type_match else None
    
    # Map to human-readable log types
    log_type_map = {
        'authentication': 'authentication logs',
        'network': 'network logs',
        'firewall': 'firewall logs',
        'dns': 'DNS logs',
        'proxy': 'proxy logs',
        'windows': 'Windows event logs',
        'linux': 'Linux system logs',
        'web': 'web server logs'
    }
    readable_log_type = log_type_map.get(log_type_name, f"{log_type_name} logs" if log_type_name else "security logs")
    
    # Extract action from query
    action_match = re.search(r'action=([\w\-]+)', query_lower)
    action = action_match.group(1) if action_match else None
    
    # Extract key entities from results
    ip_fields = [h for h in headers if 'ip' in h.lower() and ('srcip' in h.lower() or 'source' in h.lower())]
    if not ip_fields:
        ip_fields = [h for h in headers if 'ip' in h.lower()]
    
    user_fields = [h for h in headers if 'user' in h.lower()]
    count_fields = [h for h in headers if 'count' in h.lower()]
    
    # Build summary based on what we found
    summary_parts = []
    
    # Start with log type information
    log_info = f"Analyzed {readable_log_type}:"
    summary_parts.append(log_info)
    
    # Determine entity type and count
    if ip_fields and results:
        ip_field = ip_fields[0]
        unique_ips = len(set(str(r.get(ip_field, '')) for r in results if r.get(ip_field)))
        summary_parts.append(f"{unique_ips} IP{'s' if unique_ips != 1 else ''}")
    
    elif user_fields and results:
        user_field = user_fields[0]
        unique_users = len(set(str(r.get(user_field, '')) for r in results if r.get(user_field)))
        summary_parts.append(f"{unique_users} user{'s' if unique_users != 1 else ''}")
    
    else:
        # Generic count
        summary_parts.append(f"{result_count} event{'s' if result_count != 1 else ''}")
    
    # Add context from query
    context_parts = []
    
    if action:
        # Map common actions to readable descriptions
        action_map = {
            'failed': 'failed login attempts',
            'success': 'successful logins',
            'blocked': 'blocked connections',
            'allowed': 'allowed connections',
            'denied': 'access denied events',
            'granted': 'access granted events'
        }
        readable_action = action_map.get(action, action)
        context_parts.append(readable_action)
    
    # Check for specific patterns in user query
    if 'brute force' in user_query_lower or 'bruteforce' in user_query_lower:
        context_parts.append("brute force attempts")
    elif 'failed login' in user_query_lower or 'login failure' in user_query_lower:
        context_parts.append("failed login attempts")
    elif 'malware' in user_query_lower:
        context_parts.append("malware activity")
    elif 'attack' in user_query_lower:
        context_parts.append("attack activity")
    elif 'suspicious' in user_query_lower:
        context_parts.append("suspicious activity")
    
    # Combine parts
    if context_parts:
        summary = f"{' '.join(summary_parts)} with {', '.join(context_parts)}"
    else:
        summary = f"{' '.join(summary_parts)}"
    
    # Ensure it's concise (max 120 chars for better readability)
    if len(summary) > 120:
        # Truncate intelligently
        summary = summary[:117] + "..."
    
    return summary


def should_display_full_results(user_query: str) -> bool:
    """
    Determine if full results table should be displayed.
    Only show full table when user explicitly asks for data/output.
    
    Args:
        user_query: Original user query
        
    Returns:
        True if full results should be displayed, False otherwise
    """
    user_query_lower = user_query.lower()
    
    # Keywords that indicate user wants full output
    display_keywords = [
        'show', 'display', 'list', 'output', 'table', 'results', 
        'all', 'details', 'full', 'complete', 'entire'
    ]
    
    # Keywords that indicate user wants specific answer
    answer_keywords = [
        'what', 'which', 'who', 'how many', 'tell me', 'give me',
        'find', 'get', 'ip', 'ips', 'user', 'users'
    ]
    
    # If user explicitly asks to show/display/list, show full results
    if any(kw in user_query_lower for kw in display_keywords):
        return True
    
    # Otherwise, just give specific answer
    return False


def format_query_results(results: list, query: str = None) -> str:
    """
    Format API results as structured table.
    Handles common query patterns like groupby/top-N queries to display key fields prominently.
    
    Args:
        results: List of result dictionaries from DNIF API
        query: Optional DQL query string to help identify result structure
        
    Returns:
        Formatted string with table display
    """
    if not results:
        return "No results found."
    
    # Extract all unique keys from results
    headers = list(results[0].keys()) if results else []
    
    # Detect groupby queries and prioritize key fields
    is_groupby_query = query and 'groupby' in query.lower() if query else False
    
    if is_groupby_query and headers:
        # For groupby queries, prioritize common fields (srcip, user, count_col1, etc.)
        priority_fields = ['srcip', 'user', 'count_col1', 'count_col2', 'dstip', 'system', 
                          'reason', 'action', 'status', 'dstcn', 'srccn']
        
        # Reorder headers: priority fields first, then others
        ordered_headers = []
        remaining_headers = []
        
        for h in headers:
            h_lower = h.lower()
            if any(pf in h_lower for pf in priority_fields):
                ordered_headers.append(h)
            else:
                remaining_headers.append(h)
        
        headers = ordered_headers + remaining_headers
    
    # Create table data
    table_data = []
    for record in results:
        row = [str(record.get(h, ''))[:50] for h in headers]  # Limit cell width to 50 chars
        table_data.append(row)
    
    # Use tabulate for nice formatting
    table = tabulate(table_data, headers=headers, tablefmt="grid", maxcolwidths=50)
    
    summary = f"Total Records: {len(results)}\n\n"
    return summary + table

