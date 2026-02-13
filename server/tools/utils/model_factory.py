"""
Model factory for creating LangChain model instances based on configuration.
Supports OpenAI, Anthropic, and Google providers.
"""
from typing import Optional, Any
from functools import lru_cache
import sys
sys.path.append("/app/server")
from tools.utils.models_config import get_model_config, validate_api_keys, MODEL_NAME_MAP

# Lazy imports to avoid errors if packages aren't installed
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None


@lru_cache(maxsize=32)
def get_model(node_name: str, use_fallback: bool = False) -> Any:
    """
    Get a LangChain model instance for a specific workflow node.
    
    Args:
        node_name: Name of the workflow node (e.g., "classification", "guardrail_check")
        use_fallback: If True, use fallback configuration instead of primary
        
    Returns:
        LangChain model instance (ChatOpenAI, ChatAnthropic, or ChatGoogleGenerativeAI)
        
    Raises:
        ValueError: If provider is not supported or API key is missing
        KeyError: If node_name is not found in configuration
    """
    config = get_model_config(node_name)
    
    # Use fallback if requested or if primary provider is unavailable
    if use_fallback or "fallback" in config:
        api_keys = validate_api_keys()
        primary_provider = config.get("provider")
        
        # Check if we should use fallback
        if use_fallback or not api_keys.get(primary_provider, False):
            if "fallback" in config:
                config = {**config, **config["fallback"]}
            else:
                # Try to find an available provider
                for provider in ["openai", "anthropic", "google"]:
                    if api_keys.get(provider, False):
                        # Use a default model for this provider
                        config["provider"] = provider
                        if provider == "openai":
                            config["model"] = "gpt-4o"
                        elif provider == "anthropic":
                            config["model"] = "claude-3-haiku-20240307"
                        elif provider == "google":
                            config["model"] = "gemini-1.5-flash"
                        break
    
    provider = config.get("provider", "openai")
    model_name = config.get("model", "gpt-4o")
    temperature = config.get("temperature", 0.3)
    max_tokens = config.get("max_tokens")
    
    # Apply model name mapping
    model_name = MODEL_NAME_MAP.get(model_name, model_name)
    
    # Create model instance based on provider
    if provider == "openai":
        if ChatOpenAI is None:
            raise ImportError("langchain-openai is not installed. Install it with: pip install langchain-openai")
        
        kwargs = {
            "model": model_name,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        return ChatOpenAI(**kwargs)
    
    elif provider == "anthropic":
        if ChatAnthropic is None:
            raise ImportError("langchain-anthropic is not installed. Install it with: pip install langchain-anthropic")
        
        kwargs = {
            "model": model_name,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        
        return ChatAnthropic(**kwargs)
    
    elif provider == "google":
        if ChatGoogleGenerativeAI is None:
            raise ImportError("langchain-google-genai is not installed. Install it with: pip install langchain-google-genai")
        
        kwargs = {
            "model": model_name,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        
        return ChatGoogleGenerativeAI(**kwargs)
    
    else:
        raise ValueError(f"Unsupported provider: {provider}. Supported providers: openai, anthropic, google")


def get_model_name(node_name: str, use_fallback: bool = False) -> str:
    """
    Get the model name string for a specific workflow node (for metrics tracking).
    
    Args:
        node_name: Name of the workflow node
        use_fallback: If True, use fallback configuration
        
    Returns:
        Model name string (e.g., "gpt-4o", "claude-3-haiku-20240307")
    """
    config = get_model_config(node_name)
    
    if use_fallback and "fallback" in config:
        config = {**config, **config["fallback"]}
    
    model_name = config.get("model", "gpt-4o")
    return MODEL_NAME_MAP.get(model_name, model_name)


def clear_model_cache():
    """Clear the model instance cache."""
    get_model.cache_clear()

