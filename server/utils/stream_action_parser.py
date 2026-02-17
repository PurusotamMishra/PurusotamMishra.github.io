"""
Parser for Stream Action.txt file to map actions to streams (LangGraph version).
"""
import re
from pathlib import Path
from typing import Dict, List, Optional


# Cache for parsed data
_action_to_stream_cache: Optional[Dict[str, str]] = None
_stream_to_actions_cache: Optional[Dict[str, List[str]]] = None


def parse_stream_action_file(file_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Parse Stream Action.txt file and return a mapping of action -> stream.
    
    Args:
        file_path: Path to Stream Action.txt file. If None, uses default location.
        
    Returns:
        Dictionary mapping action (uppercase) to stream name (uppercase)
    """
    global _action_to_stream_cache
    
    if _action_to_stream_cache is not None:
        return _action_to_stream_cache
    
    if file_path is None:
        # Default path relative to project root (go up from b_copilot/utils/)
        current_dir = Path(__file__).parent.parent.parent
        file_path = current_dir / "docs" / "Stream Action.txt"
    
    action_to_stream: Dict[str, str] = {}
    current_stream: Optional[str] = None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Check for stream header: "Actions parsed by DNIF Stream ```STREAM_NAME``` :"
                stream_match = re.search(r'Actions parsed by DNIF Stream ```([^`]+)```', line)
                if stream_match:
                    current_stream = stream_match.group(1).strip().upper()
                    continue
                
                # If we have a current stream and line is not empty, it's an action
                if current_stream and line:
                    # Normalize action to uppercase
                    action = line.upper()
                    # Store mapping (if action appears in multiple streams, last one wins)
                    action_to_stream[action] = current_stream
    
    except FileNotFoundError:
        print(f"[WARNING] Stream Action.txt file not found at {file_path}")
        return {}
    except Exception as e:
        print(f"[ERROR] Failed to parse Stream Action.txt: {e}")
        return {}
    
    _action_to_stream_cache = action_to_stream
    return action_to_stream


def get_stream_to_actions_mapping(file_path: Optional[Path] = None) -> Dict[str, List[str]]:
    """
    Parse Stream Action.txt file and return a mapping of stream -> list of actions.
    
    Args:
        file_path: Path to Stream Action.txt file. If None, uses default location.
        
    Returns:
        Dictionary mapping stream name (uppercase) to list of actions (uppercase)
    """
    global _stream_to_actions_cache
    
    if _stream_to_actions_cache is not None:
        return _stream_to_actions_cache
    
    if file_path is None:
        # Default path relative to project root (go up from b_copilot/utils/)
        current_dir = Path(__file__).parent.parent.parent
        file_path = current_dir / "docs" / "Stream Action.txt"
    
    stream_to_actions: Dict[str, List[str]] = {}
    current_stream: Optional[str] = None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Check for stream header: "Actions parsed by DNIF Stream ```STREAM_NAME``` :"
                stream_match = re.search(r'Actions parsed by DNIF Stream ```([^`]+)```', line)
                if stream_match:
                    current_stream = stream_match.group(1).strip().upper()
                    if current_stream not in stream_to_actions:
                        stream_to_actions[current_stream] = []
                    continue
                
                # If we have a current stream and line is not empty, it's an action
                if current_stream and line:
                    # Normalize action to uppercase
                    action = line.upper()
                    stream_to_actions[current_stream].append(action)
    
    except FileNotFoundError:
        print(f"[WARNING] Stream Action.txt file not found at {file_path}")
        return {}
    except Exception as e:
        print(f"[ERROR] Failed to parse Stream Action.txt: {e}")
        return {}
    
    _stream_to_actions_cache = stream_to_actions
    return stream_to_actions


def get_stream_for_action(action: str, file_path: Optional[Path] = None) -> Optional[str]:
    """
    Get the stream name for a given action (case-insensitive).
    
    Args:
        action: Action name (case-insensitive)
        file_path: Path to Stream Action.txt file. If None, uses default location.
        
    Returns:
        Stream name in uppercase, or None if not found
    """
    action_to_stream = parse_stream_action_file(file_path)
    action_upper = action.upper()
    return action_to_stream.get(action_upper)


def get_actions_for_stream(stream: str, file_path: Optional[Path] = None) -> List[str]:
    """
    Get all actions for a given stream (case-insensitive).
    
    Args:
        stream: Stream name (case-insensitive)
        file_path: Path to Stream Action.txt file. If None, uses default location.
        
    Returns:
        List of actions in uppercase for the stream
    """
    stream_to_actions = get_stream_to_actions_mapping(file_path)
    stream_upper = stream.upper()
    return stream_to_actions.get(stream_upper, [])


def clear_cache():
    """Clear the cached parsed data (useful for testing or reloading)."""
    global _action_to_stream_cache, _stream_to_actions_cache
    _action_to_stream_cache = None
    _stream_to_actions_cache = None

