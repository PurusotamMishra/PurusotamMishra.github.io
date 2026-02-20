import logging
import os
import httpx
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
# from agent.agent import FetchLogsAgent
# from agent.agent import create_agent
from interfaces.a2a.src.agent_executer import BLOOAgentExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MissingAPIKeyError(Exception):
    """Exception for missing API key."""
    pass


def main():
    """Starts the agent server."""
    HOST_DOMAIN = "bloo-agent"
    HOST_PORT = int(os.getenv("PORT_A2A", "8080"))
    print(f"HOST_PORT: {HOST_PORT}")
    try:
        # Check for API key only if Vertex AI is not configured
        if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE": # TODO: Replace with the correct environment variable
            if not os.getenv("GOOGLE_API_KEY"): # TODO
                raise MissingAPIKeyError(
                    "GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
                )

        capabilities = AgentCapabilities(streaming=True)

        skill = AgentSkill(
            id="fetch_logs",
            name="Logs Fetching Agent",
            description="This agent fetches logs from the database based on the user's request.",
            tags=["logs", "database"],
            examples=["Fetch logs from the database for the last 24 hours", 
            "Fetch the top suspect users performed DDOS in last 3 days"],
        )

        agent_card = AgentCard(
            name="BLOO Agent",
            description="An agent that fetches logs from the database based on the user's request.",
            url=f"http://{HOST_DOMAIN}:{HOST_PORT}/",
            version="1.0.0",
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain"],
            capabilities=capabilities,
            skills=[skill],
        )

        # adk_agent = FetchLogsAgent()
        # adk_agent = create_agent()
        
        # runner = Runner(
        #     app_name=agent_card.name,
        #     agent=BLOOAgent(),
        #     artifact_service=InMemoryArtifactService(),
        #     session_service=InMemorySessionService(),
        #     memory_service=InMemoryMemoryService(),
        # )
        agent_executor = BLOOAgentExecutor()

        # httpx_client = httpx.AsyncClient()

        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=InMemoryTaskStore(),
            # push_notifier=InMemoryPushNotifier(httpx_client),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        uvicorn.run(server.build(), host="0.0.0.0", port=HOST_PORT)
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()
