"""
Parser for Stream DDM.txt file to get column information for streams (LangGraph version).
"""
from pathlib import Path
from typing import Dict, List, Optional


# Cache for parsed data
_stream_columns_cache: Optional[Dict[str, List[str]]] = None


def parse_stream_ddm_file(file_path: Optional[Path] = None) -> Dict[str, List[str]]:
    """
    Parse Stream DDM.txt file and return a mapping of stream -> list of columns.
    
    Args:
        file_path: Path to Stream DDM.txt file. If None, uses default location.
        
    Returns:
        Dictionary mapping stream name (uppercase) to list of column names (lowercase)
    """
    global _stream_columns_cache
    
    if _stream_columns_cache is not None:
        return _stream_columns_cache
    
    if file_path is None:
        # Default path relative to project root (go up from b_copilot/utils/)
        current_dir = Path(__file__).parent.parent.parent
        file_path = current_dir / "docs" / "Stream DDM.txt"
    
    stream_columns: Dict[str, List[str]] = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Split by tab character
                parts = line.split('\t')
                if len(parts) >= 2:
                    stream_name = parts[0].strip().upper()
                    column_name = parts[1].strip()
                    
                    # Clean up column name (remove trailing spaces, quotes if any)
                    column_name = column_name.strip('"').strip()
                    
                    # Skip if column name is empty
                    if not column_name:
                        continue
                    
                    # Convert column name to lowercase (DQL uses lowercase field names)
                    column_name_lower = column_name.lower()
                    
                    # Initialize list if stream not seen before
                    if stream_name not in stream_columns:
                        stream_columns[stream_name] = []
                    
                    # Add column if not already present (avoid duplicates)
                    if column_name_lower not in stream_columns[stream_name]:
                        stream_columns[stream_name].append(column_name_lower)
    
    except FileNotFoundError:
        print(f"[WARNING] Stream DDM.txt file not found at {file_path}")
        return {}
    except Exception as e:
        print(f"[ERROR] Failed to parse Stream DDM.txt: {e}")
        return {}
    
    _stream_columns_cache = stream_columns
    return stream_columns


def get_stream_columns(stream: str, file_path: Optional[Path] = None) -> Optional[List[str]]:
    """
    Get column names for a given stream (case-insensitive).
    
    Args:
        stream: Stream name (case-insensitive)
        file_path: Path to Stream DDM.txt file. If None, uses default location.
        
    Returns:
        List of column names in lowercase for the stream, or None if stream not found
    """
    stream_columns = parse_stream_ddm_file(file_path)
    stream_upper = stream.upper()
    return stream_columns.get(stream_upper)


def has_stream_columns(stream: str, file_path: Optional[Path] = None) -> bool:
    """
    Check if a stream has column information in DDM file.
    
    Args:
        stream: Stream name (case-insensitive)
        file_path: Path to Stream DDM.txt file. If None, uses default location.
        
    Returns:
        True if stream has columns defined in DDM, False otherwise
    """
    stream_columns = parse_stream_ddm_file(file_path)
    stream_upper = stream.upper()
    return stream_upper in stream_columns and len(stream_columns[stream_upper]) > 0


def clear_cache():
    """Clear the cached parsed data (useful for testing or reloading)."""
    global _stream_columns_cache
    _stream_columns_cache = None

