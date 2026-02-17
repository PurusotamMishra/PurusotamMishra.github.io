"""
Query Clarity Confidence Scorer for assessing user query clarity and specificity (LangGraph version).
Uses LLM to evaluate how clear, specific, and actionable a user query is.
"""
from typing import Any
import json
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append("/app/server")

from schemas.models import QueryClarityOutput, QueryClarityFactors
from utils.model_factory import get_model


async def assess_query_clarity(user_query: str, return_response: bool = False) -> QueryClarityOutput | tuple[QueryClarityOutput, Any]:
    """
    Assess the clarity and confidence of a user query.
    
    Args:
        user_query: The user's natural language query
        return_response: If True, return tuple of (QueryClarityOutput, response) for metrics extraction
        
    Returns:
        QueryClarityOutput with score, reasoning, and factors, or tuple if return_response=True
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Query Clarity Assessor for DNIF SIEM platform. Your task is to evaluate how clear, specific, and actionable a user's query is.

**ASSESSMENT CRITERIA:**

1. **Clarity (0.0-1.0)**: How clear and unambiguous is the query?
2. **Specificity (0.0-1.0)**: How specific and detailed is the query?
3. **Entity Mentions (0.0-1.0)**: Does the query mention specific entities?
4. **Technical Terms (0.0-1.0)**: Does the query use technical/domain terms?
5. **Timeframes (0.0-1.0)**: Does the query specify time-related information?
6. **Stream Names (0.0-1.0)**: Does the query mention specific stream names?
7. **Query Length Score (0.0-1.0)**: Is the query length appropriate?

**OUTPUT FORMAT:**
Return a JSON object with:
{{
  "score": 0.0-1.0,
  "reasoning": "Detailed explanation",
  "factors": {{
    "clarity": 0.0-1.0,
    "specificity": 0.0-1.0,
    "entity_mentions": 0.0-1.0,
    "technical_terms": 0.0-1.0,
    "timeframes": 0.0-1.0,
    "stream_names": 0.0-1.0,
    "query_length_score": 0.0-1.0
  }}
}}"""),
        ("human", "{input}")
    ])
    
    model = get_model("query_clarity")
    
    try:
        chain = prompt | model
        response = await chain.ainvoke({"input": user_query})
        
        content = response.content.strip()
        
        # Extract JSON
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        
        result = json.loads(content)
        
        factors = QueryClarityFactors(
            clarity=result["factors"]["clarity"],
            specificity=result["factors"]["specificity"],
            entity_mentions=result["factors"]["entity_mentions"],
            technical_terms=result["factors"]["technical_terms"],
            timeframes=result["factors"]["timeframes"],
            stream_names=result["factors"]["stream_names"],
            query_length_score=result["factors"]["query_length_score"]
        )
        
        output = QueryClarityOutput(
            score=result["score"],
            reasoning=result["reasoning"],
            factors=factors
        )
        
        if return_response:
            return output, response
        return output
    except Exception as e:
        print(f"[DEBUG] Query Clarity: Error assessing clarity - {str(e)}")
        # Return default medium confidence on error
        output = QueryClarityOutput(
            score=0.5,
            reasoning=f"Error during assessment: {str(e)}",
            factors=QueryClarityFactors(
                clarity=0.5,
                specificity=0.5,
                entity_mentions=0.5,
                technical_terms=0.5,
                timeframes=0.5,
                stream_names=0.5,
                query_length_score=0.5
            )
        )
        if return_response:
            return output, None
        return output

