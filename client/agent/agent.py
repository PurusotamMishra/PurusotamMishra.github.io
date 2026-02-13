import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterable, List
import os

import httpx
import nest_asyncio
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)
from dotenv import load_dotenv
import google.generativeai as genai
from google.genai import types
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext

import logging
from .remote_agent_connection import RemoteAgentConnections

load_dotenv()
nest_asyncio.apply()

class LLMConfig:
    """
    Configuration for the LLM provider.
    
    Google ADK supports multiple providers via LiteLLM.
    For non-Google models, prefix with 'litellm/' to use LiteLLM routing.
    """
    
    PROVIDERS = {
        "google": {
            "env_key": "GOOGLE_API_KEY",
            "model": "gemini-2.5-flash",  # Native Google model
            "display_name": "Google Gemini",
        },
        "openai": {
            "env_key": "OPENAI_API_KEY",
            "model": "openai/gpt-4o",  # LiteLLM format for OpenAI
            "display_name": "OpenAI GPT-4o",
        },
        "anthropic": {
            "env_key": "ANTHROPIC_API_KEY",
            "model": "anthropic/claude-3-haiku-20240307",  # LiteLLM format for Anthropic
            "display_name": "Anthropic Claude",
        },
    }
    
    def __init__(self):
        self.provider: str | None = None
        self.api_key: str | None = None
        self.model: str | None = None
        self._configure()
    
    def _configure(self):
        """Configure the LLM provider based on available API keys."""
        for provider_name, config in self.PROVIDERS.items():
            api_key = os.getenv(config["env_key"])
            if api_key:
                self.provider = provider_name
                self.api_key = api_key
                self.model = config["model"]
                print(f"✓ Using {config['display_name']} with model: {self.model}")
                break
        
        if not self.provider:
            raise ValueError(
                "No API key found. Please set one of the following environment variables:\n"
                "  - GOOGLE_API_KEY (for Gemini) - https://aistudio.google.com/apikey\n"
                "  - OPENAI_API_KEY (for GPT-4o) - https://platform.openai.com/api-keys\n"
                "  - ANTHROPIC_API_KEY (for Claude) - https://console.anthropic.com/settings/keys"
            )

        self._configure_provider_sdk()
    
    def _configure_provider_sdk(self):
        """Configure the SDK for the selected provider."""
        if self.provider == "google":
            genai.configure(api_key=self.api_key)
        elif self.provider == "openai":
            os.environ["OPENAI_API_KEY"] = self.api_key
        elif self.provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = self.api_key


# Initialize LLM configuration
llm_config = LLMConfig()

class HostAgent:
    """The Host agent."""

    def __init__(
        self,
    ):
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""
        self._agent = self.create_agent()
        self._user_id = "host_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def _async_init_components(self, remote_agent_addresses: List[str]):
        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, base_url=address)
                try:
                    logging.error(f"address: {address}")
                    card = await card_resolver.get_agent_card()
                    logging.error(f"card: {str(card)}")
                    logging.error(f"address: {address}")
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    logging.error(f"remote_connection: {remote_connection}")
                    self.cards[card.name] = card
                except httpx.ConnectError as e:
                    logging.error(f"ERROR: Failed to get agent card from {address}: {e}")
                except Exception as e:
                    logging.error(f"ERROR: Failed to initialize connection for {address}: {e}")

        agent_info = [
            json.dumps({"name": card.name, "description": card.description})
            for card in self.cards.values()
        ]
        logging.error(f"agent_info:{agent_info}")
        self.agents = "\n".join(agent_info) if agent_info else "No friends found"

    @classmethod
    async def create(
        cls,
        remote_agent_addresses: List[str],
    ):
        instance = cls()
        await instance._async_init_components(remote_agent_addresses)
        return instance

    def has_external_agents(self) -> bool:
        """Check if any external agents are connected."""
        return len(self.remote_agent_connections) > 0

    def get_connected_agents(self) -> List[str]:
        """Get list of connected external agent names."""
        return list(self.remote_agent_connections.keys())

    @staticmethod
    def get_llm_info() -> dict:
        """Get information about the current LLM provider and model."""
        return {
            "provider": llm_config.provider,
            "model": llm_config.model,
            "display_name": LLMConfig.PROVIDERS[llm_config.provider]["display_name"],
        }

    def create_agent(self) -> Agent:
        """
        Create the agent using Google ADK.
        
        For non-Google models (OpenAI, Anthropic), Google ADK uses LiteLLM
        under the hood. Model names are prefixed accordingly:
        - Google: "gemini-2.5-flash"
        - OpenAI: "openai/gpt-4o"  
        - Anthropic: "anthropic/claude-3-haiku-20240307"
        """
        tools = [self.check_available_agents]
        
        if self.has_external_agents():
            tools.append(self.send_message)
            
        print(f"Creating agent with provider: {llm_config.provider}, model: {llm_config.model}")
        
        return Agent(
            model=llm_config.model,
            name="Host_Agent",
            instruction=self.root_instruction,
            description="This host agent calls Agents to help the user with their request to execute DQL (DNIF Query Language) and then analyse further",
            tools=tools,
        )
            
    def root_instruction(self, context: ReadonlyContext = None) -> str:
        # return f"""
        # **Role:** You are the Host Agent, you analyse logs based on the user's request. To fetch logs you can call External Agents. Once the logs are fetched, you should analyse them and provide the user with a summary of the logs.

        # **Core Directives:**

        # *   **Initiate Planning:** When asked to schedule a game, first determine who to invite and the desired date range from the user.
        # *   **Task Delegation:** Use the `send_message` tool to ask each friend for their availability.
        #     *   Frame your request clearly (e.g., "Are you available for pickleball between 2024-08-01 and 2024-08-03?").
        #     *   Make sure you pass in the official name of the friend agent for each message request.
        # *   **Analyze Responses:** Once you have availability from all friends, analyze the responses to find common timeslots.
        # *   **Check Court Availability:** Before proposing times to the user, use the `list_court_availabilities` tool to ensure the court is also free at the common timeslots.
        # *   **Propose and Confirm:** Present the common, court-available timeslots to the user for confirmation.
        # *   **Book the Court:** After the user confirms a time, use the `book_pickleball_court` tool to make the reservation. This tool requires a `start_time` and an `end_time`.
        # *   **Transparent Communication:** Relay the final booking confirmation, including the booking ID, to the user. Do not ask for permission before contacting friend agents.
        # *   **Tool Reliance:** Strictly rely on available tools to address user requests. Do not generate responses based on assumptions.
        # *   **Readability:** Make sure to respond in a concise and easy to read format (bullet points are good).
        # *   Each available agent represents a friend. So Bob_Agent represents Bob.
        # *   When asked for which friends are available, you should return the names of the available friends (aka the agents that are active).
        # *   When get

        # **Today's Date (YYYY-MM-DD):** {datetime.now().strftime("%Y-%m-%d")}

        # <Available Agents>
        # {self.agents}
        # </Available Agents>
        # """
        
        has_agents = self.has_external_agents()
        
        if has_agents:
            return f"""
                **Role:** You are the Host Agent, you analyse logs based on the user's request. 
                To fetch logs you can call External Agents using the `send_message` tool. 
                Once the logs are fetched, you should analyse them and provide the user with a summary of the logs.

                **Core Directives:**
                * Use `check_available_agents` to see which external agents are connected.
                * Use `send_message` to delegate tasks to external agents.
                * Analyze responses from external agents and provide clear summaries to the user.
                * Be concise and use bullet points for readability.

                **Today's Date (YYYY-MM-DD):** {datetime.now().strftime("%Y-%m-%d")}

                <Available Agents>
                {self.agents}
                </Available Agents>
                """
        else:
            return f"""
            **Role:** You are the Host Agent. Currently, no external agents are connected.

            **Important:** Since no external agents are available, you should:
            1. Respond directly to the user's queries using your own knowledge and capabilities.
            2. Be helpful, informative, and conversational.
            3. If the user asks about tasks that would normally require external agents (like fetching logs), 
            politely explain that no external agents are currently connected and offer alternative assistance.
            4. You can use `check_available_agents` to verify the current connection status.

            **Today's Date (YYYY-MM-DD):** {datetime.now().strftime("%Y-%m-%d")}

            <Status>
            No external agents are currently connected. Operating in standalone mode.
            </Status>
            """

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        """
        Streams the agent's response to a given query.
        """
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        # logging.error(f"query: {self.remote_agent_connections}")
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        logging.error(f"session: {session}")
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                response = ""
                if (
                    event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    response = "\n".join(
                        [p.text for p in event.content.parts if p.text]
                    )
                yield {
                    "is_task_complete": True,
                    "content": response,
                }
            else:
                yield {
                    "is_task_complete": False,
                    "updates": "The host agent is thinking...",
                }

    def check_available_agents(self) -> dict:
        """
        Check which external agents are currently available and connected.
        Use this tool to see what agents you can delegate tasks to.
        If no agents are available, you should respond directly to the user's query
        using your own knowledge and capabilities.
        
        Returns:
            A dictionary containing:
            - has_agents: boolean indicating if any external agents are connected
            - agents: list of connected agent names and their descriptions
            - message: a helpful message about the current state
        """
        if self.has_external_agents():
            agent_list = [
                {"name": name, "description": card.description}
                for name, card in self.cards.items()
            ]
            return {
                "has_agents": True,
                "agents": agent_list,
                "message": f"You have {len(agent_list)} external agent(s) available to delegate tasks to."
            }
        else:
            return {
                "has_agents": False,
                "agents": [],
                "message": "No external agents are currently connected. You should respond directly to the user using your own knowledge and capabilities. Be helpful and informative based on the user's query."
            }

    async def send_message(self, agent_name: str, task: str, tool_context: ToolContext):
        """Sends a task to a remote friend agent."""
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        client = self.remote_agent_connections[agent_name]

        if not client:
            raise ValueError(f"Client not available for {agent_name}")

        # Simplified task and context ID management
        state = tool_context.state
        task_id = state.get("task_id", str(uuid.uuid4()))
        context_id = state.get("context_id", str(uuid.uuid4()))
        message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task}],
                "messageId": message_id,
                "taskId": task_id,
                "contextId": context_id,
            },
        }

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate(payload)
        )

        send_response: SendMessageResponse = await client.send_message(message_request)
        print("send_response", send_response)

        if not isinstance(
            send_response.root, SendMessageSuccessResponse
        ) or not isinstance(send_response.root.result, Task):
            print("Received a non-success or non-task response. Cannot proceed.")
            return

        response_content = send_response.root.model_dump_json(exclude_none=True)
        json_content = json.loads(response_content)

        resp = []
        if json_content.get("result", {}).get("artifacts"):
            for artifact in json_content["result"]["artifacts"]:
                if artifact.get("parts"):
                    resp.extend(artifact["parts"])
        return resp

    async def close(self):
        """Clean up all remote connections."""
        for conn in self.remote_agent_connections.values():
            await conn.close()

# Below is currently being handled in the main.py file along with the FastAPI lifespan function.

# def _get_initialized_host_agent_sync():
#     """Synchronously creates and initializes the HostAgent."""

#     async def _async_main():
#         # Hardcoded URLs for the friend agents
#         agent_urls = os.getenv("EXTERNAL_AGENT_URLS", "http://localhost:9999,http://localhost:9998")
#         print("agent_urls:", agent_urls)
#         if not agent_urls:
#             raise ValueError("EXTERNAL_AGENT_URLS is not set")
#         friend_agent_urls = agent_urls.split(",")

#         print("initializing host agent")
#         hosting_agent_instance = await HostAgent.create(
#             remote_agent_addresses=friend_agent_urls
#         )
#         print("HostAgent initialized")
#         return hosting_agent_instance.create_agent()

#     try:
#         return asyncio.run(_async_main())
#     except RuntimeError as e:
#         if "asyncio.run() cannot be called from a running event loop" in str(e):
#             print(
#                 f"Warning: Could not initialize HostAgent with asyncio.run(): {e}. "
#                 "This can happen if an event loop is already running (e.g., in Jupyter). "
#                 "Consider initializing HostAgent within an async function in your application."
#             )
#         else:
#             raise


# root_agent = _get_initialized_host_agent_sync()
