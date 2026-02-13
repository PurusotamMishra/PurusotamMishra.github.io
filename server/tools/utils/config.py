"""
Configuration and constants for the DQL Agent System (LangGraph version).
"""
import os
import uuid
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.append("/app/server")

from tools.utils.models_config import validate_api_keys

# Load environment variables
# Trace configuration
TRACE_SOURCE = "dql-agent-system-langgraph"


def generate_workflow_id() -> str:
    """Generate a unique workflow ID."""
    return f"dql-query-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"


@dataclass
class Config:
    """Configuration for DNIF API and system settings."""
    # DNIF API settings
    console_domain: str = os.getenv('DNIF_CONSOLE_DOMAIN', '')
    cluster_id: str = os.getenv('DNIF_CLUSTER_ID', '')
    api_token: str = os.getenv('DNIF_API_TOKEN', '')
    timezone: str = os.getenv('DNIF_TIMEZONE', 'Asia/Kolkata')
    scope_id: str = os.getenv('DNIF_SCOPE_ID', 'training')
    
    # CSV settings
    csv_path: Path = Path(__file__).parent.parent / "Data" / "OOTB 2025 Sheet1.csv"
    
    # Polling settings
    poll_interval: int = 5  # seconds
    max_wait_time: int = 180  # seconds
    
    # Tracing settings
    # Note: SSL handshake timeout warnings from tracing are non-fatal and can be safely ignored.
    # To disable tracing and avoid these warnings, set ENABLE_DETAILED_TRACING=false
    enable_detailed_tracing: bool = os.getenv('ENABLE_DETAILED_TRACING', 'true').lower() == 'true'
    
    # Query confidence threshold
    confidence_threshold: float = 0.5  # Threshold for high vs low confidence queries
    
    # Model configuration settings
    enable_model_fallback: bool = os.getenv('ENABLE_MODEL_FALLBACK', 'true').lower() == 'true'
    model_cache_enabled: bool = os.getenv('MODEL_CACHE_ENABLED', 'true').lower() == 'true'
    
    # LangSmith tracing settings
    langsmith_tracing: bool = os.getenv('LANGSMITH_TRACING', 'false').lower() == 'true'
    langsmith_api_key: str = os.getenv('LANGSMITH_API_KEY', '')
    langsmith_project: str = os.getenv('LANGSMITH_PROJECT', 'dql-agent-system')
    langsmith_endpoint: str = os.getenv('LANGSMITH_ENDPOINT', 'https://api.smith.langchain.com')
    
    def is_langsmith_enabled(self) -> bool:
        """Check if LangSmith tracing is enabled and configured."""
        return self.langsmith_tracing and bool(self.langsmith_api_key)
    
    # EPM API settings
    epm_endpoint_list_url: str = os.getenv('EPM_ENDPOINT_LIST_URL', 'https://114.143.64.202:8110/api/v1/endpoint/list')
    epm_query_schedule_url: str = os.getenv('EPM_QUERY_SCHEDULE_URL', 'https://172.25.1.97:8000/api/v1/distributed/schedule_query')
    epm_pending_queries_url: str = os.getenv('EPM_PENDING_QUERIES_URL', 'https://172.25.1.97:8000/api/v1/distributed/pending_queries')
    epm_query_results_url: str = os.getenv('EPM_QUERY_RESULTS_URL', 'https://172.25.1.97:8000/api/v1/distributed/query_results')
    epm_api_timeout: int = int(os.getenv('EPM_API_TIMEOUT', '300'))
    epm_poll_interval: int = int(os.getenv('EPM_POLL_INTERVAL', '5'))
    epm_max_wait_time: int = int(os.getenv('EPM_MAX_WAIT_TIME', '180'))
    
    def validate(self) -> bool:
        """Validate that required DNIF API credentials are present."""
        return all([self.console_domain, self.cluster_id, self.api_token])
    
    def validate_model_api_keys(self) -> dict:
        """Validate that at least one model provider API key is available."""
        api_keys = validate_api_keys()
        if not any(api_keys.values()):
            print("[WARNING] No model provider API keys found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY")
        return api_keys


# Global config instance
config = Config()

