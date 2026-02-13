"""
CSV search tool for semantic similarity search in DQL query database (LangGraph version).
"""
from langchain_core.tools import tool
from openai import OpenAI
import pandas as pd
import numpy as np
import pickle
import hashlib
from pathlib import Path
from typing import Optional

import sys
sys.path.append("/app/server")

import tools.utils.config as config_module

config = config_module.config

# Module-level cache variables
_csv_df_cache: Optional[pd.DataFrame] = None
_csv_embeddings_cache: Optional[dict] = None  # Stores dict with 'name_embeddings', 'description_window_embeddings', and 'detection_technique_embeddings'
_csv_cache_hash: Optional[str] = None
_CACHE_VERSION = 3  # Version for cache format compatibility


def _get_csv_cache_path() -> Path:
    """Get the path to the CSV embeddings cache file."""
    cache_dir = Path(__file__).parent.parent.parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "csv_embeddings.pkl"


def generate_csv_cache(force_regenerate: bool = False) -> bool:
    """
    Generate CSV embeddings cache. Can be called directly to pre-generate cache.
    
    Args:
        force_regenerate: If True, regenerate cache even if it exists
        
    Returns:
        True if cache was generated successfully, False otherwise
    """
    global _csv_df_cache, _csv_embeddings_cache, _csv_cache_hash
    
    try:
        # Load CSV
        if _csv_df_cache is None:
            print("[CACHE GEN] Loading CSV file...")
            csv_path = str(config.csv_path)
            df = pd.read_csv(csv_path)
            df = df.reset_index(drop=True)
            df = df[df['Query'].notna() & (df['Query'].str.strip() != '')]
            df['search_text'] = (
                df['Name'].fillna('') + ' ' + 
                df['Description'].fillna('') + ' ' + 
                df['DetectionTechnique'].fillna('')
            )
            _csv_df_cache = df
            _csv_cache_hash = _compute_csv_hash(df)
            print(f"[CACHE GEN] Loaded {len(df)} queries from CSV")
        
        cache_path = _get_csv_cache_path()
        
        # Check if cache exists and is valid (unless forcing regeneration)
        if not force_regenerate and cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    cache_data = pickle.load(f)
                cache_version = cache_data.get('cache_version', 1)
                cached_hash = cache_data.get('csv_hash')
                cached_df_length = cache_data.get('df_length')
                
                if (cache_version == _CACHE_VERSION and 
                    cached_hash == _csv_cache_hash and 
                    cached_df_length == len(_csv_df_cache)):
                    print("[CACHE GEN] Cache already exists and is valid. Use force_regenerate=True to regenerate.")
                    return True
            except Exception as e:
                print(f"[CACHE GEN] Error checking existing cache: {e}, will regenerate...")
        
        # Generate embeddings (reuse the logic from search_dql_csv)
        print("[CACHE GEN] Generating embeddings for Name, Description (sliding windows), and DetectionTechnique...")
        openai_client = OpenAI()
        
        name_texts = _csv_df_cache['Name'].fillna('').tolist()
        description_texts = _csv_df_cache['Description'].fillna('').tolist()
        detection_technique_texts = _csv_df_cache['DetectionTechnique'].fillna('').tolist()
        
        # Generate Name embeddings
        print("[CACHE GEN] Generating Name embeddings...")
        name_embeddings_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=name_texts
        )
        name_embeddings = np.array([item.embedding for item in name_embeddings_response.data])
        
        # Generate Description window embeddings
        print("[CACHE GEN] Extracting sliding windows from descriptions...")
        all_description_windows = []
        window_indices_per_row = []
        
        for desc_text in description_texts:
            windows = _extract_sliding_windows(desc_text, window_size=3)
            all_description_windows.extend(windows)
            window_indices_per_row.append(len(windows))
        
        print(f"[CACHE GEN] Extracted {len(all_description_windows)} windows from {len(description_texts)} descriptions")
        
        # Generate embeddings for all description windows in batches
        description_window_embeddings_list = []
        batch_size = 100
        for i in range(0, len(all_description_windows), batch_size):
            batch = all_description_windows[i:i+batch_size]
            batch_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=batch
            )
            batch_embeddings = [item.embedding for item in batch_response.data]
            description_window_embeddings_list.extend(batch_embeddings)
            if (i // batch_size + 1) % 10 == 0:
                print(f"[CACHE GEN] Processed {min(i+batch_size, len(all_description_windows))}/{len(all_description_windows)} windows")
        
        # Organize window embeddings by row
        description_window_embeddings = []
        idx = 0
        for num_windows in window_indices_per_row:
            row_windows = [np.array(description_window_embeddings_list[idx+j]) for j in range(num_windows)]
            description_window_embeddings.append(row_windows)
            idx += num_windows
        
        # Generate DetectionTechnique embeddings
        print("[CACHE GEN] Generating DetectionTechnique embeddings...")
        detection_technique_embeddings_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=detection_technique_texts
        )
        detection_technique_embeddings = np.array([item.embedding for item in detection_technique_embeddings_response.data])
        
        _csv_embeddings_cache = {
            'name_embeddings': name_embeddings,
            'description_window_embeddings': description_window_embeddings,
            'detection_technique_embeddings': detection_technique_embeddings
        }
        
        # Save cache
        cache_data = {
            'cache_version': _CACHE_VERSION,
            'name_embeddings': name_embeddings,
            'description_window_embeddings': description_window_embeddings,
            'detection_technique_embeddings': detection_technique_embeddings,
            'csv_hash': _csv_cache_hash,
            'df_length': len(_csv_df_cache)
        }
        with open(cache_path, 'wb') as f:
            pickle.dump(cache_data, f)
        
        print(f"[CACHE GEN] Successfully saved cache:")
        print(f"[CACHE GEN]   - {len(name_embeddings)} name embeddings")
        print(f"[CACHE GEN]   - {len(all_description_windows)} description window embeddings")
        print(f"[CACHE GEN]   - {len(detection_technique_embeddings)} detection technique embeddings")
        print(f"[CACHE GEN] Cache file: {cache_path}")
        
        return True
        
    except Exception as e:
        print(f"[CACHE GEN] Error generating cache: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def _compute_csv_hash(df: pd.DataFrame) -> str:
    """Compute hash of Name, Description, and DetectionTechnique columns for cache validation."""
    names = df['Name'].fillna('').tolist()
    descriptions = df['Description'].fillna('').tolist()
    detection_techniques = df['DetectionTechnique'].fillna('').tolist()
    content_str = '\n'.join(f"{name}|||{desc}|||{dt}" for name, desc, dt in zip(names, descriptions, detection_techniques))
    return hashlib.sha256(content_str.encode()).hexdigest()


def _extract_sliding_windows(text: str, window_size: int = 3) -> list[str]:
    """
    Extract overlapping n-gram windows from text.
    
    Args:
        text: Input text to extract windows from
        window_size: Number of words per window (default: 3)
        
    Returns:
        List of window strings
    """
    if not text or not text.strip():
        return []
    words = text.strip().split()
    if len(words) < window_size:
        return [' '.join(words)] if words else []
    windows = []
    for i in range(len(words) - window_size + 1):
        windows.append(' '.join(words[i:i+window_size]))
    return windows


@tool
def search_dql_csv(
    user_query: str,
    exclude_query_indices: list[int] | None = None,
    top_k: int = 3,
    min_confidence: float = 0.7
) -> dict:
    """
    Search the DQL query CSV database using semantic similarity.
    Uses separate embeddings for Name, Description (with sliding windows), and DetectionTechnique fields,
    then combines similarity scores using a weighted average (25% Name, 35% Description, 40% DetectionTechnique).
    Description similarity uses sliding windows to better match short queries against long descriptions.
    
    Args:
        user_query: The user's natural language query
        exclude_query_indices: List of CSV row indices to exclude from results (0-based)
        top_k: Number of top results to return (default: 3)
        min_confidence: Minimum confidence score threshold (default: 0.7)
        
    Returns:
        dict with 'success' boolean and 'matches' list containing top results
    """
    global _csv_df_cache, _csv_embeddings_cache, _csv_cache_hash
    
    try:
        print(f"[DEBUG] CSV Search: Searching for '{user_query}'")
        if exclude_query_indices:
            print(f"[DEBUG] CSV Search: Excluding {len(exclude_query_indices)} previously fetched queries")
        
        # Load CSV once and cache (or use cached version)
        if _csv_df_cache is None:
            print("[DEBUG] CSV Search: Loading CSV file...")
            csv_path = str(config.csv_path)
            df = pd.read_csv(csv_path)
            
            # Reset index to ensure we have sequential indices
            df = df.reset_index(drop=True)
            
            # Filter out rows with empty Query field
            df = df[df['Query'].notna() & (df['Query'].str.strip() != '')]
            
            # Create combined text for each row
            df['search_text'] = (
                df['Name'].fillna('') + ' ' + 
                df['Description'].fillna('') + ' ' + 
                df['DetectionTechnique'].fillna('')
            )
            
            _csv_df_cache = df
            _csv_cache_hash = _compute_csv_hash(df)
            print(f"[DEBUG] CSV Search: Loaded and cached {len(df)} queries")
        else:
            df = _csv_df_cache.copy()
            print(f"[DEBUG] CSV Search: Using cached CSV ({len(df)} queries)")
        
        if len(df) == 0:
            print("[DEBUG] CSV Search: No valid queries found in CSV")
            return {
                "success": True,
                "matches": [],
                "message": "No queries found in CSV database"
            }
        
        # Exclude previously fetched queries if specified
        if exclude_query_indices:
            # Filter out invalid indices (out of bounds)
            max_valid_idx = len(df) - 1
            valid_exclude_indices = [idx for idx in exclude_query_indices if 0 <= idx <= max_valid_idx]
            
            if len(valid_exclude_indices) != len(exclude_query_indices):
                invalid_count = len(exclude_query_indices) - len(valid_exclude_indices)
                print(f"[DEBUG] CSV Search: Filtered out {invalid_count} invalid exclude indices")
            
            # Convert to set for faster lookup
            exclude_set = set(valid_exclude_indices)
            # Filter out excluded rows
            df = df[~df.index.isin(exclude_set)]
            print(f"[DEBUG] CSV Search: After exclusions, {len(df)} queries remain")
        
        if len(df) == 0:
            print("[DEBUG] CSV Search: All queries excluded, no results available")
            return {
                "success": True,
                "matches": [],
                "message": "All matching queries have been excluded",
                "fallback_needed": True
            }
        
        # Load or generate embeddings cache
        if _csv_embeddings_cache is None:
            cache_path = _get_csv_cache_path()
            
            # Try to load from cache
            if cache_path.exists():
                try:
                    print("[DEBUG] CSV Search: Loading embeddings from cache...")
                    with open(cache_path, 'rb') as f:
                        cache_data = pickle.load(f)
                    
                    # Check cache version for backward compatibility
                    cache_version = cache_data.get('cache_version', 1)
                    
                    # Verify cache matches current CSV
                    cached_hash = cache_data.get('csv_hash')
                    cached_df_length = cache_data.get('df_length')
                    
                    if cache_version == _CACHE_VERSION and cached_hash == _csv_cache_hash and cached_df_length == len(_csv_df_cache):
                        # Version 3 format: name, description_window, and detection_technique embeddings
                        name_embeddings = cache_data.get('name_embeddings')
                        description_window_embeddings = cache_data.get('description_window_embeddings')
                        detection_technique_embeddings = cache_data.get('detection_technique_embeddings')
                        
                        if (name_embeddings is not None and 
                            description_window_embeddings is not None and 
                            detection_technique_embeddings is not None):
                            _csv_embeddings_cache = {
                                'name_embeddings': np.array(name_embeddings),
                                'description_window_embeddings': description_window_embeddings,  # List of lists
                                'detection_technique_embeddings': np.array(detection_technique_embeddings)
                            }
                            print(f"[DEBUG] CSV Search: Loaded {len(_csv_embeddings_cache['name_embeddings'])} name, description window, and detection technique embeddings from cache")
                        else:
                            print("[DEBUG] CSV Search: Cache format invalid, regenerating...")
                            _csv_embeddings_cache = None
                    elif cache_version == 2:
                        # Old format: separate name and description embeddings - regenerate with new format
                        print("[DEBUG] CSV Search: Old cache format (v2) detected, regenerating with sliding windows and separate DetectionTechnique...")
                        _csv_embeddings_cache = None
                    elif cache_version == 1:
                        # Old format: single combined embeddings - regenerate with new format
                        print("[DEBUG] CSV Search: Old cache format (v1) detected, regenerating with sliding windows and separate DetectionTechnique...")
                        _csv_embeddings_cache = None
                    else:
                        print("[DEBUG] CSV Search: Cache invalid (CSV changed or version mismatch), regenerating...")
                        _csv_embeddings_cache = None
                except Exception as e:
                    print(f"[DEBUG] CSV Search: Error loading cache: {e}, regenerating...")
                    _csv_embeddings_cache = None
            
            # Generate embeddings if cache missing/invalid
            if _csv_embeddings_cache is None:
                print("[DEBUG] CSV Search: Generating embeddings for Name, Description (sliding windows), and DetectionTechnique...")
                openai_client = OpenAI()
                
                # Prepare Name texts (handle empty/null values)
                name_texts = _csv_df_cache['Name'].fillna('').tolist()
                
                # Prepare Description texts (without DetectionTechnique for sliding windows)
                description_texts = _csv_df_cache['Description'].fillna('').tolist()
                
                # Prepare DetectionTechnique texts (separate)
                detection_technique_texts = _csv_df_cache['DetectionTechnique'].fillna('').tolist()
                
                # Generate embeddings for Name
                print("[DEBUG] CSV Search: Generating Name embeddings...")
                name_embeddings_response = openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=name_texts
                )
                name_embeddings = np.array([item.embedding for item in name_embeddings_response.data])
                
                # Generate embeddings for Description windows
                print("[DEBUG] CSV Search: Extracting sliding windows from descriptions and generating embeddings...")
                all_description_windows = []
                window_indices_per_row = []  # Track which windows belong to which row
                
                for desc_text in description_texts:
                    windows = _extract_sliding_windows(desc_text, window_size=3)
                    all_description_windows.extend(windows)
                    window_indices_per_row.append(len(windows))
                
                print(f"[DEBUG] CSV Search: Extracted {len(all_description_windows)} windows from {len(description_texts)} descriptions")
                
                # Generate embeddings for all description windows in batches
                description_window_embeddings_list = []
                batch_size = 100  # Process in batches to avoid API limits
                for i in range(0, len(all_description_windows), batch_size):
                    batch = all_description_windows[i:i+batch_size]
                    batch_response = openai_client.embeddings.create(
                        model="text-embedding-3-small",
                        input=batch
                    )
                    batch_embeddings = [item.embedding for item in batch_response.data]
                    description_window_embeddings_list.extend(batch_embeddings)
                    if (i // batch_size + 1) % 10 == 0:
                        print(f"[DEBUG] CSV Search: Processed {min(i+batch_size, len(all_description_windows))}/{len(all_description_windows)} windows")
                
                # Organize window embeddings by row
                description_window_embeddings = []
                idx = 0
                for num_windows in window_indices_per_row:
                    row_windows = [np.array(description_window_embeddings_list[idx+j]) for j in range(num_windows)]
                    description_window_embeddings.append(row_windows)
                    idx += num_windows
                
                # Generate embeddings for DetectionTechnique
                print("[DEBUG] CSV Search: Generating DetectionTechnique embeddings...")
                detection_technique_embeddings_response = openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=detection_technique_texts
                )
                detection_technique_embeddings = np.array([item.embedding for item in detection_technique_embeddings_response.data])
                
                _csv_embeddings_cache = {
                    'name_embeddings': name_embeddings,
                    'description_window_embeddings': description_window_embeddings,
                    'detection_technique_embeddings': detection_technique_embeddings
                }
                
                # Save cache
                try:
                    cache_data = {
                        'cache_version': _CACHE_VERSION,
                        'name_embeddings': name_embeddings,
                        'description_window_embeddings': description_window_embeddings,
                        'detection_technique_embeddings': detection_technique_embeddings,
                        'csv_hash': _csv_cache_hash,
                        'df_length': len(_csv_df_cache)
                    }
                    with open(cache_path, 'wb') as f:
                        pickle.dump(cache_data, f)
                    print(f"[DEBUG] CSV Search: Saved {len(name_embeddings)} name, {len(all_description_windows)} description window, and {len(detection_technique_embeddings)} detection technique embeddings to cache")
                except Exception as e:
                    print(f"[DEBUG] CSV Search: Warning - failed to save cache: {e}")
        
        # Get embeddings for the filtered dataframe (after exclusions)
        # Map original indices to cached embeddings
        # Ensure indices are valid (within bounds of cached embeddings)
        df_indices = df.index.values
        name_embeddings_all = _csv_embeddings_cache['name_embeddings']
        description_window_embeddings_all = _csv_embeddings_cache['description_window_embeddings']
        detection_technique_embeddings_all = _csv_embeddings_cache['detection_technique_embeddings']
        max_valid_idx = len(name_embeddings_all) - 1
        
        # Filter out any indices that are out of bounds
        valid_mask = (df_indices >= 0) & (df_indices <= max_valid_idx)
        
        if not np.any(valid_mask):
            print("[DEBUG] CSV Search: No valid indices after filtering")
            return {
                "success": True,
                "matches": [],
                "message": "No valid queries after filtering",
                "fallback_needed": True
            }
        
        # Filter dataframe to only include valid indices
        df = df.loc[df_indices[valid_mask]]
        valid_indices = df_indices[valid_mask]
        name_embeddings = name_embeddings_all[valid_indices]
        description_window_embeddings = [description_window_embeddings_all[i] for i in valid_indices]
        detection_technique_embeddings = detection_technique_embeddings_all[valid_indices]
        
        # Initialize OpenAI client for query embedding
        openai_client = OpenAI()
        
        # Get embedding for user query (this is fast, only one embedding)
        query_embedding_response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=user_query
        )
        query_embedding = np.array(query_embedding_response.data[0].embedding)
        
        # Compute cosine similarity for Name embeddings
        # Handle case where name_embeddings might be 1D (single row)
        if name_embeddings.ndim == 1:
            name_embeddings = name_embeddings.reshape(1, -1)
        
        name_similarities = np.dot(name_embeddings, query_embedding) / (
            np.linalg.norm(name_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Compute cosine similarity for Description embeddings using sliding windows
        # For each row, compute similarity with all windows and take the maximum
        description_similarities = []
        for row_windows in description_window_embeddings:
            if not row_windows:
                description_similarities.append(0.0)
                continue
            
            # Compute similarity for each window
            window_similarities = []
            for window_emb in row_windows:
                window_emb = np.array(window_emb)
                if window_emb.ndim == 0:
                    continue
                similarity = np.dot(window_emb, query_embedding) / (
                    np.linalg.norm(window_emb) * np.linalg.norm(query_embedding)
                )
                window_similarities.append(float(similarity))
            
            # Use maximum similarity across all windows (or 0 if no windows)
            description_similarities.append(max(window_similarities) if window_similarities else 0.0)
        
        description_similarities = np.array(description_similarities)
        
        # Compute cosine similarity for DetectionTechnique embeddings
        # Handle case where detection_technique_embeddings might be 1D (single row)
        if detection_technique_embeddings.ndim == 1:
            detection_technique_embeddings = detection_technique_embeddings.reshape(1, -1)
        
        detection_technique_similarities = np.dot(detection_technique_embeddings, query_embedding) / (
            np.linalg.norm(detection_technique_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Combine similarities using weighted average: 25% Name, 35% Description, 40% DetectionTechnique
        combined_similarities = (
            0.25 * name_similarities + 
            0.35 * description_similarities + 
            0.40 * detection_technique_similarities
        )
        
        # Store individual and combined similarities for debugging
        df['name_similarity'] = name_similarities
        df['description_similarity'] = description_similarities
        df['detection_technique_similarity'] = detection_technique_similarities
        df['similarity'] = combined_similarities
        
        # Display top 3 match scores before filtering
        top_3_all = df.nlargest(3, 'similarity')
        print(f"[DEBUG] CSV Search: Top 3 match scores (before threshold filter):")
        for i, (idx, row) in enumerate(top_3_all.iterrows(), 1):
            print(f"[DEBUG]   {i}. Combined: {row['similarity']:.4f} (Name: {row['name_similarity']:.4f}, Desc: {row['description_similarity']:.4f}, DT: {row['detection_technique_similarity']:.4f}) | Name: {row['Name']} | Index: {int(idx)}")
        
        df_filtered = df[df['similarity'] >= min_confidence]
        
        if len(df_filtered) == 0:
            print(f"[DEBUG] CSV Search: No queries meet confidence threshold {min_confidence}")
            print(f"[DEBUG] CSV Search: Max similarity score was {float(np.max(combined_similarities)):.4f}")
            return {
                "success": True,
                "matches": [],
                "message": f"No queries meet minimum confidence threshold {min_confidence}",
                "fallback_needed": True,
                "max_confidence": float(np.max(combined_similarities))
            }
        
        # Get top_k matches (or fewer if not enough available)
        top_k_actual = min(top_k, len(df_filtered))
        top_rows = df_filtered.nlargest(top_k_actual, 'similarity')
        
        matches = []
        for idx, row in top_rows.iterrows():
            match = {
                "name": row['Name'],
                "query": row['Query'],
                "description": row['Description'],
                "detection_technique": row['DetectionTechnique'],
                "score": float(row['similarity']),
                "csv_index": int(idx)  # Original CSV index after reset
            }
            matches.append(match)
        
        print(f"[DEBUG] CSV Search: Found {len(matches)} matches (threshold: {min_confidence})")
        for i, (idx, row) in enumerate(top_rows.iterrows(), 1):
            name_score = row['name_similarity']
            desc_score = row['description_similarity']
            dt_score = row['detection_technique_similarity']
            combined_score = row['similarity']
            print(f"[DEBUG]   {i}. {row['Name']} (combined: {combined_score:.3f}, name: {name_score:.3f}, desc: {desc_score:.3f}, dt: {dt_score:.3f})")
        
        # Determine if fallback is needed
        fallback_needed = len(matches) < top_k or (matches and matches[-1]['score'] < min_confidence + 0.1)
        
        return {
            "success": True,
            "matches": matches,
            "message": f"Found {len(matches)} matching queries",
            "fallback_needed": fallback_needed if len(matches) < top_k else False
        }
        
    except Exception as e:
        print(f"[DEBUG] CSV Search: Error - {str(e)}")
        return {
            "success": False,
            "matches": [],
            "error": f"CSV search failed: {str(e)}"
        }

