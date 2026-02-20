import sys

from typing import Dict, Any
from core.schemas.state import WorkflowState
from utils.guardrails import check_jailbreak

async def guardrail_check_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Check guardrails before processing user query.
    
    Args:
        state: Current workflow state
        
    Returns:
        Partial state update with guardrail results
    """
    user_query = state.get("user_query", "")
    
    print("[DEBUG] Guardrail: Checking jailbreak...")
    guardrail_result = await check_jailbreak(user_query)
    
    guardrail_passed = not (guardrail_result.is_jailbreak and guardrail_result.confidence >= 0.80)
    
    if not guardrail_passed:
        print(f"[DEBUG] Guardrail tripped. Reasoning: {guardrail_result.reasoning} | Confidence: {guardrail_result.confidence}")
        return {
            "guardrail_passed": False,
            "guardrail_output": guardrail_result,
            "failed": True,
            "reason": "jailbreak_detected",
            "details": {
                "reasoning": guardrail_result.reasoning,
                "confidence": guardrail_result.confidence
            },
            "status": "failed"
        }
    
    print("[DEBUG] Guardrail: Passed")
    return {
        "guardrail_passed": True,
        "guardrail_output": guardrail_result
    }
