from src.main import mcp
from core.config import settings

if __name__ == "__main__":
    mcp.run(
        transport=settings.APP_TRANSPORT,
        host="0.0.0.0",
        port=settings.APP_PORT
    )