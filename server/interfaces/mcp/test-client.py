import asyncio
from fastmcp import Client
from fastmcp.client.auth import OAuth
import logging
logging.basicConfig(level=logging.DEBUG) # This will show outgoing HTTP headers

MCP_SERVER_URL = "http://localhost:8081/sse"

from key_value.aio.stores.disk import DiskStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from cryptography.fernet import Fernet
import os

# Create encrypted disk storage
encrypted_storage = FernetEncryptionWrapper(
    key_value=DiskStore(directory="~/.fastmcp/oauth-tokens"),
    fernet=Fernet(os.environ["OAUTH_STORAGE_ENCRYPTION_KEY"])
)


oauth = OAuth(
    mcp_url=MCP_SERVER_URL,
    # scopes=[
    #     "openid",
    #     "email",
    #     "profile",
    #     "https://www.googleapis.com/auth/userinfo.email",
    # ],
    token_storage=encrypted_storage
)

async def call_tools():
    try:
        print("calling apis")
        async with Client(MCP_SERVER_URL, auth=oauth) as client:
            # print(client)
            assert await client.ping()
            print("✅ Successfully authenticated!")
            
            tools = await client.list_tools()
            print("Available tools:", tools)

            result = await client.call_tool("ping")
            print("Ping:", result)

            result = await client.call_tool("whoami")
            print("Who am I:", result)
    except Exception as e:
        logging.error(f"Error calling tools: {e}")
        raise e

asyncio.run(call_tools())