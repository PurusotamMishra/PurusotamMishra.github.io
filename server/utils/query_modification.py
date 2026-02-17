"""
Query modification tool for modifying DQL queries (LangGraph version).
"""
import re
from langchain_core.tools import tool


@tool
def modify_dql_query(
    query: str,
    modification_type: str,
    new_duration: str | None = None
) -> dict:
    """
    Modify DQL queries based on modification type.
    
    Args:
        query: The DQL query string to modify
        modification_type: Type of modification - "duration_change" (currently supported)
        new_duration: New duration value in DQL format (e.g., "2w", "14d", "1h", "30m")
        
    Returns:
        dict with 'success' boolean, 'modified_query' string, and 'message'
    """
    if modification_type == "duration_change":
        if not new_duration:
            return {
                "success": False,
                "modified_query": query,
                "error": "new_duration is required for duration_change modification"
            }
        
        # Pattern to match duration clauses
        # Matches: duration 1h, duration 15m, duration 1w, duration from...to...
        duration_patterns = [
            # Pattern 1: duration <value><unit> (e.g., duration 1h, duration 15m)
            (r'\bduration\s+(\d+[mhdwM])\b', f'duration {new_duration}'),
            # Pattern 2: duration from <datetime> to <datetime>
            (r'\bduration\s+from\s+[\d\-T:]+(?:\s+to\s+[\d\-T:]+)?', f'duration {new_duration}'),
        ]
        
        modified_query = query
        modified = False
        
        for pattern, replacement in duration_patterns:
            if re.search(pattern, modified_query, re.IGNORECASE):
                modified_query = re.sub(pattern, replacement, modified_query, flags=re.IGNORECASE)
                modified = True
                break
        
        if not modified:
            # If no duration clause found, add one at the beginning (after stream=)
            # Try to insert after the first pipe or at the end of stream clause
            stream_match = re.search(r'(stream=[^|]+)', modified_query, re.IGNORECASE)
            if stream_match:
                # Insert duration after stream clause, before any existing pipes
                insert_pos = stream_match.end()
                # Check if there's already a pipe after stream
                if modified_query[insert_pos:insert_pos+1].strip() == '|':
                    # Insert before the pipe
                    modified_query = modified_query[:insert_pos] + f' | duration {new_duration}' + modified_query[insert_pos:]
                else:
                    # Add pipe and duration
                    modified_query = modified_query[:insert_pos] + f' | duration {new_duration}' + modified_query[insert_pos:]
                modified = True
            else:
                # Fallback: append duration at the end
                modified_query = f"{modified_query} | duration {new_duration}"
                modified = True
        
        return {
            "success": True,
            "modified_query": modified_query,
            "message": f"Duration modified to {new_duration}"
        }
    
    else:
        return {
            "success": False,
            "modified_query": query,
            "error": f"Unsupported modification_type: {modification_type}"
        }

