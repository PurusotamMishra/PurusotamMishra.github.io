import os
from interfaces.mcp.src.main import mcp

if __name__ == "__main__":
    mcp.run(
        transport=os.getenv('MCP_SERVER_TRANSPORT', 'sse'),
        host="0.0.0.0",
        port=int(os.getenv('PORT_MCP', '8081'))
    )