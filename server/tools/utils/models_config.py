"""
Model configuration for b_copilot workflow nodes.
Uses ONLY OpenAI models from GPT-4.1 family for optimal speed and quality.
"""
import os
import json
from typing import Dict, Any, Optional

# Load environment variables
# Model name mappings for API compatibility
# Maps friendly names to actual API model identifiers
# Using GPT-4.1 family models (released April 2025)
MODEL_NAME_MAP = {
    # OpenAI GPT-4.1 family models
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt-4.1-nano": "gpt-4.1-nano",
    # Legacy GPT-4o models (for fallback/compatibility)
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4o-latest": "gpt-4o-2024-11-20",
}

# Base model configuration for each workflow node
# Using ONLY OpenAI GPT-4.1 family models for optimal speed and quality
# GPT-4.1-mini: Fastest, cheapest (8 nodes)
# GPT-4.1: Highest quality (2 nodes: human_to_dql, summary)
BASE_MODEL_CONFIG: Dict[str, Dict[str, Any]] = {
    "guardrail_check": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0,
        }
    },
    "classification": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0.2,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
        }
    },
    "query_clarity": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0.2,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
        }
    },
    "entity_resolution": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0.2,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
        }
    },
    "stream_action_context": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0.3,
        "max_tokens": 512,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 512,
        }
    },
    "human_to_dql": {
        "provider": "openai",
        "model": "gpt-4.1",
        "temperature": 0,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0,
        }
    },
    "sql_to_dql": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0,
        }
    },
    "summary": {
        "provider": "openai",
        "model": "gpt-4.1",
        "temperature": 0.3,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.3,
        }
    },
    "endpoint_selection": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0.2,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
        }
    },
    "epm_query_generation": {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "temperature": 0,
        "max_tokens": None,
        "fallback": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0,
        }
    },
}


def get_model_config(node_name: str) -> Dict[str, Any]:
    """
    Get model configuration for a specific workflow node.
    
    Args:
        node_name: Name of the workflow node (e.g., "classification", "guardrail_check")
        
    Returns:
        Dictionary with model configuration including provider, model, temperature, etc.
        
    Raises:
        KeyError: If node_name is not found in configuration
    """
    if node_name not in BASE_MODEL_CONFIG:
        raise KeyError(f"Model configuration not found for node: {node_name}")
    
    config = BASE_MODEL_CONFIG[node_name].copy()
    
    # Apply model name mapping
    if "model" in config:
        config["model"] = MODEL_NAME_MAP.get(config["model"], config["model"])
    
    if "fallback" in config and "model" in config["fallback"]:
        config["fallback"]["model"] = MODEL_NAME_MAP.get(
            config["fallback"]["model"], 
            config["fallback"]["model"]
        )
    
    # Apply environment variable overrides
    override_env = os.getenv("MODEL_CONFIG_OVERRIDE")
    if override_env:
        try:
            override_config = json.loads(override_env)
            if node_name in override_config:
                config.update(override_config[node_name])
        except json.JSONDecodeError:
            print(f"[WARNING] Invalid MODEL_CONFIG_OVERRIDE JSON, ignoring")
    
    return config


def get_all_model_configs() -> Dict[str, Dict[str, Any]]:
    """
    Get all model configurations.
    
    Returns:
        Dictionary mapping node names to their model configurations
    """
    return {
        node_name: get_model_config(node_name)
        for node_name in BASE_MODEL_CONFIG.keys()
    }


def validate_api_keys() -> Dict[str, bool]:
    """
    Check which API keys are available.
    Note: Only OpenAI is used, but we check for others for compatibility.
    
    Returns:
        Dictionary mapping provider names to availability (True/False)
    """
    return {
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
    }

