from google.adk.agents import LlmAgent

from tools.tools import guardrail_check_tool, classification_tool, query_clarity_tool, entity_resolution_tool, stream_action_context_tool, \
    human_to_dql_tool, sql_to_dql_tool, query_execution_tool

def create_agent() -> LlmAgent:
    """Constructs the ADK agent for BLOO Agent."""
    agent = LlmAgent(
        model="gemini-2.5-flash",
        name="BLOO_Agent",
        instruction="""
            **Role:** You are BLOO Agent's personal assistant. 
            Your sole responsibility is to fetch logs from the database based on the user's request.

            **Core Directives:**
            *    **Guardrail Check:** Use the `guardrail_check_tool` tool to check if the user's request is safe and compliant.
            *    **Classification:** Use the `classification_tool` tool to classify the user's request into a category.
            *    **Query Clarity:** Use the `query_clarity_tool` tool to check if the user's request is clear and concise.
            *    **Entity Resolution:** Use the `entity_resolution_tool` tool to resolve the entities in the user's request.
            *    **Stream Action Context:** Use the `stream_action_context_tool` tool to generate a context for the user's request.
            *    **Human to DQL:** Use the `human_to_dql_tool` tool to generate a DQL query from the user's request.
            *    **SQL to DQL:** Use the `sql_to_dql_tool` tool to generate a DQL query from the user's request.
            *    **Query Execution:** Use the `query_execution_tool` tool to execute the user's request.
        """,
        tools=[guardrail_check_tool, classification_tool, query_clarity_tool, entity_resolution_tool, stream_action_context_tool, human_to_dql_tool, sql_to_dql_tool, query_execution_tool],
    )

    return agent
