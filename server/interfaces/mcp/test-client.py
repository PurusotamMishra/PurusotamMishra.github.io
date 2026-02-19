import asyncio
from fastmcp import Client
# from fastmcp.client.auth import OAuth
from fastmcp.client.auth import BearerAuth
import os

token = os.getenv('PUBLIC_TOKEN', '')
client = Client("http://localhost:8081/sse", auth=BearerAuth(token=token))

async def call_tool(name: str):
    try:
        async with client:
            result = await client.list_tools()
            # result = await client.call_tool("ping")
            # result = await client.call_tool("list-tools")
            # result = await client.call_tool("query-execute", {"query":"Give me the brute force attack logs for the last 5 minutes"})
            print(result)
    except Exception as e:
        print(f"Error calling tool: {e}")

asyncio.run(call_tool("Ford"))