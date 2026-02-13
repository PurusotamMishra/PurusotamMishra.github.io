"""
Tracing utilities for capturing execution metrics (timing, tokens, costs) for LangChain/LangGraph.
"""
import time
from typing import Dict, Optional, Any, List
from datetime import datetime


# Model pricing per 1M tokens (input/output)
MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},  # per 1M tokens
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1": {"input": 2.50, "output": 10.00},  # Assuming same as gpt-4o
    "gpt-5": {"input": 5.00, "output": 15.00},  # Estimated, adjust as needed
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}


class ExecutionMetrics:
    """Container for execution metrics."""
    
    def __init__(self, agent_name: str, model: str = "unknown"):
        self.agent_name = agent_name
        self.model = model
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.execution_time: Optional[float] = None
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.total_tokens: Optional[int] = None
        self.estimated_cost: Optional[float] = None
    
    def start(self):
        """Mark the start of execution."""
        self.start_time = time.time()
    
    def end(self):
        """Mark the end of execution and calculate duration."""
        self.end_time = time.time()
        if self.start_time:
            self.execution_time = self.end_time - self.start_time
    
    def set_token_usage(self, input_tokens: int, output_tokens: int):
        """Set token usage and calculate cost."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens
        
        # Calculate cost
        if self.model in MODEL_PRICING:
            pricing = MODEL_PRICING[self.model]
            input_cost = (input_tokens / 1_000_000) * pricing["input"]
            output_cost = (output_tokens / 1_000_000) * pricing["output"]
            self.estimated_cost = input_cost + output_cost
        else:
            # Unknown model - estimate based on average
            avg_cost_per_token = 0.000002  # $0.002 per 1K tokens
            self.estimated_cost = (self.total_tokens / 1000) * avg_cost_per_token
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "agent_name": self.agent_name,
            "model": self.model,
            "execution_time": self.execution_time,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
        }
    
    def format_output(self) -> str:
        """Format metrics for display."""
        lines = [f"[TRACE] {self.agent_name}:"]
        
        if self.execution_time is not None:
            lines.append(f"  - Execution time: {self.execution_time:.2f}s")
        
        if self.input_tokens is not None and self.output_tokens is not None:
            lines.append(f"  - Tokens: {self.input_tokens:,} input / {self.output_tokens:,} output ({self.total_tokens:,} total)")
        elif self.total_tokens is not None:
            lines.append(f"  - Tokens: {self.total_tokens:,} total")
        
        if self.estimated_cost is not None:
            lines.append(f"  - Estimated cost: ${self.estimated_cost:.6f}")
        
        return "\n".join(lines)


def extract_metrics_from_langchain_response(response: Any, agent_name: str, model: str = "unknown") -> Optional[ExecutionMetrics]:
    """
    Extract metrics from a LangChain LLM response (AIMessage or chain output).
    
    Args:
        response: LangChain response object (AIMessage, dict, or chain output)
        agent_name: Name of the agent/node that was executed
        model: Model name used (for cost calculation)
        
    Returns:
        ExecutionMetrics object if metrics could be extracted, None otherwise
    """
    metrics = ExecutionMetrics(agent_name, model)
    
    input_tokens = None
    output_tokens = None
    detected_model = model
    
    # Try to extract model name from response
    if hasattr(response, 'response_metadata'):
        metadata = response.response_metadata
        if isinstance(metadata, dict):
            detected_model = metadata.get('model_name') or metadata.get('model_provider') or model
            # Check for usage_metadata in response_metadata
            usage_meta = metadata.get('usage_metadata') or metadata.get('token_usage')
            if usage_meta:
                if isinstance(usage_meta, dict):
                    input_tokens = usage_meta.get('input_tokens') or usage_meta.get('prompt_tokens')
                    output_tokens = usage_meta.get('output_tokens') or usage_meta.get('completion_tokens')
                elif hasattr(usage_meta, 'input_tokens'):
                    input_tokens = usage_meta.input_tokens
                    output_tokens = usage_meta.output_tokens
    
    # Check for usage_metadata directly on response
    if hasattr(response, 'usage_metadata'):
        usage_meta = response.usage_metadata
        if isinstance(usage_meta, dict):
            input_tokens = input_tokens or usage_meta.get('input_tokens') or usage_meta.get('prompt_tokens')
            output_tokens = output_tokens or usage_meta.get('output_tokens') or usage_meta.get('completion_tokens')
        elif hasattr(usage_meta, 'input_tokens'):
            input_tokens = input_tokens or usage_meta.input_tokens
            output_tokens = output_tokens or usage_meta.output_tokens
    
    # Check for token_usage field
    if hasattr(response, 'token_usage'):
        usage = response.token_usage
        if isinstance(usage, dict):
            input_tokens = input_tokens or usage.get('input_tokens') or usage.get('prompt_tokens')
            output_tokens = output_tokens or usage.get('output_tokens') or usage.get('completion_tokens')
        elif hasattr(usage, 'input_tokens'):
            input_tokens = input_tokens or usage.input_tokens
            output_tokens = output_tokens or usage.output_tokens
    
    # For agent calls, check messages array for aggregated tokens
    if isinstance(response, dict) and 'messages' in response:
        total_input = 0
        total_output = 0
        for msg in response.get('messages', []):
            if hasattr(msg, 'response_metadata'):
                msg_meta = msg.response_metadata
                if isinstance(msg_meta, dict):
                    msg_usage = msg_meta.get('usage_metadata') or msg_meta.get('token_usage')
                    if isinstance(msg_usage, dict):
                        total_input += msg_usage.get('input_tokens', 0) or msg_usage.get('prompt_tokens', 0)
                        total_output += msg_usage.get('output_tokens', 0) or msg_usage.get('completion_tokens', 0)
                    elif hasattr(msg_usage, 'input_tokens'):
                        total_input += msg_usage.input_tokens or 0
                        total_output += msg_usage.output_tokens or 0
            elif hasattr(msg, 'usage_metadata'):
                msg_usage = msg.usage_metadata
                if isinstance(msg_usage, dict):
                    total_input += msg_usage.get('input_tokens', 0) or msg_usage.get('prompt_tokens', 0)
                    total_output += msg_usage.get('output_tokens', 0) or msg_usage.get('completion_tokens', 0)
                elif hasattr(msg_usage, 'input_tokens'):
                    total_input += msg_usage.input_tokens or 0
                    total_output += msg_usage.output_tokens or 0
        if total_input > 0 or total_output > 0:
            input_tokens = total_input if total_input > 0 else input_tokens
            output_tokens = total_output if total_output > 0 else output_tokens
    
    # Update model if detected
    if detected_model != model:
        metrics.model = detected_model
    
    # Set token usage if found
    if input_tokens is not None and output_tokens is not None:
        metrics.set_token_usage(input_tokens, output_tokens)
    elif input_tokens is not None:
        # Only input tokens - estimate output (25% of input)
        metrics.set_token_usage(input_tokens, int(input_tokens * 0.25))
    elif output_tokens is not None:
        # Only output tokens - estimate input (4x output)
        metrics.set_token_usage(int(output_tokens * 4), output_tokens)
    else:
        # No tokens found - return None to indicate no metrics available
        return None
    
    return metrics


def format_workflow_summary(metrics_list: List[ExecutionMetrics]) -> str:
    """
    Format a summary of all execution metrics.
    
    Args:
        metrics_list: List of ExecutionMetrics objects
        
    Returns:
        Formatted string with total metrics
    """
    if not metrics_list:
        return "[TRACE] No metrics available."
    
    total_time = sum(m.execution_time or 0 for m in metrics_list)
    total_input_tokens = sum(m.input_tokens or 0 for m in metrics_list)
    total_output_tokens = sum(m.output_tokens or 0 for m in metrics_list)
    total_tokens = total_input_tokens + total_output_tokens
    total_cost = sum(m.estimated_cost or 0 for m in metrics_list)
    
    lines = ["[TRACE] Total Workflow:"]
    lines.append(f"  - Total time: {total_time:.2f}s")
    lines.append(f"  - Total tokens: {total_input_tokens:,} input / {total_output_tokens:,} output ({total_tokens:,} total)")
    lines.append(f"  - Total cost: ${total_cost:.6f}")
    
    return "\n".join(lines)

