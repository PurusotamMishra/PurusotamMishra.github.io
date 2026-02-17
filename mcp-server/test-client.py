import asyncio
from fastmcp import Client

client = Client("http://localhost:80/sse")

async def call_tool(name: str):
    async with client:
        result = await client.list_tools()
        # result = await client.call_tool("ping")
        # result = await client.call_tool("query-execute", {"query":"hello!"})
        print(result)

asyncio.run(call_tool("Ford"))