from typing import Callable

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from dotenv import load_dotenv
import logging
import os
load_dotenv()

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, agent_card: AgentCard, agent_url: str):
        logging.error(f"agent_card: {agent_card}")
        logging.error(f"agent_url: {agent_url}")
        
        # Get token from environment
        public_token = os.getenv('PUBLIC_TOKEN', '')
        
        # Configure httpx client with authentication headers
        headers = {}
        if public_token:
            headers["Authorization"] = f"Bearer {public_token}"
        
        self._httpx_client = httpx.AsyncClient(timeout=30, headers=headers)
        self.agent_client = A2AClient(self._httpx_client, agent_card, url=agent_url)
        self.card = agent_card
        self.conversation_name = None
        self.conversation = None
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(
        self, message_request: SendMessageRequest
    ) -> SendMessageResponse:
        return await self.agent_client.send_message(message_request)
    
    async def close(self):
        """Properly close the httpx client."""
        await self._httpx_client.aclose()
