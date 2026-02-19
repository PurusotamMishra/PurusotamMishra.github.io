import uuid
import os

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    TextPart,
)

PUBLIC_AGENT_CARD_PATH = "/.well-known/agent-card.json"
BASE_URL = "http://bloo-agent:8080"


async def main(query: str, base_url: str=BASE_URL, public_agent_card_path: str=PUBLIC_AGENT_CARD_PATH) -> None:
    # Get token from environment
    public_token = os.getenv('PUBLIC_TOKEN', '')
    
    # Configure httpx client with authentication headers
    headers = {}
    if public_token:
        headers["Authorization"] = f"Bearer {public_token}"
    timeout = httpx.Timeout(300.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as httpx_client:
        # Initialize A2ACardResolver
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=BASE_URL,
        )

        final_agent_card_to_use: AgentCard | None = None

        try:
            print(
                f"Fetching public agent card from: {BASE_URL}{PUBLIC_AGENT_CARD_PATH}"
            )
            _public_card = await resolver.get_agent_card()
            print("Fetched public agent card")
            print(_public_card.model_dump_json(indent=2))

            final_agent_card_to_use = _public_card

        except Exception as e:
            print(f"Error fetching public agent card: {e}")
            raise RuntimeError("Failed to fetch public agent card")

        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )
        print("A2AClient initialized")

        message_payload = Message(
            role=Role.user,
            messageId=str(uuid.uuid4()),
            parts=[Part(root=TextPart(text=query))],
        )
        request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message=message_payload,
            ),
        )
        print("Sending message")

        response = await client.send_message(request)
        print("Response:")
        print(response)
        print("**************************************************")
        print(response.model_dump_json(indent=2))
        print("**************************************************")
        return response


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
