import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from agent.agent import HostAgent
from test_client import main
from fastapi.middleware.cors import CORSMiddleware

def _parse_external_agent_urls(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


async def _close_remote_connections(host: HostAgent) -> None:
    # Best-effort cleanup (RemoteAgentConnections holds an httpx.AsyncClient)
    for conn in getattr(host, "remote_agent_connections", {}).values():
        httpx_client = getattr(conn, "_httpx_client", None)
        if httpx_client is not None:
            try:
                await httpx_client.aclose()
            except Exception:
                pass


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None

from typing import Any
class ChatResponse(BaseModel):
    session_id: str
    result: Any


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    urls = _parse_external_agent_urls(os.getenv("EXTERNAL_AGENT_URLS"))
    logging.error(f"urls: {urls}")
    if not urls:
        raise RuntimeError(
            'Missing EXTERNAL_AGENT_URLS (e.g. "http://localhost:9999,http://localhost:9998")'
        )

    host = await HostAgent.create(remote_agent_addresses=urls)
    app.state.host = host
    app.state.friend_agents = list(getattr(host, "cards", {}).keys())

    try:
        yield
    finally:
        await _close_remote_connections(host)


app = FastAPI(title="Client Host Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"ok": True, "friend_agents": getattr(app.state, "friend_agents", [])}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    host: HostAgent = getattr(app.state, "host", None)
    if host is None:
        raise HTTPException(status_code=503, detail="Host agent not initialized")

    session_id = req.session_id or str(uuid.uuid4())

    final_text = ""
    async for event in host.stream(query=req.query, session_id=session_id):
        if event.get("is_task_complete"):
            final_text = event.get("content", "") or ""

    return ChatResponse(session_id=session_id, result=final_text)
    
@app.post("/test-client")
async def send_message(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    query = req.query
    try:
        response = await main(query=query, base_url="http://bloo-agent:8080", public_agent_card_path="/.well-known/agent-card.json")
        logging.error(f"respons-test-client: {response}")
        
        return {
            "type": "query_result",
            "data": response,
            "status": "success",
            "message": "Query executed successfully"
        }
    except Exception as e:
        logging.error(f"Error executing query: {e}")
        return {
            "type": "query_result",
            "data": "",
            "status": "error",
            "message": f"Error executing query: {e}"
        }

from fastmcp import Client
import json

client = Client("http://bloo-agent:8081/sse")

@app.post("/mcp/query")
async def mcp_query(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    
    try:
        async with client:
            result = await client.call_tool("query-execute", {"query": req.query})
            logging.error(f"result-mcp: {result}")
            
            # Extract text content from CallToolResult
            if result.content and len(result.content) > 0:
                text_content = result.content[0].text
                # Parse the JSON string if it's a string
                try:
                    data = json.loads(text_content)
                except (json.JSONDecodeError, TypeError):
                    data = text_content
            else:
                data = None
            
            return {
                "type": "query_result",
                "data": data,
                "status": "success",
                "message": "Query executed successfully"
            }
    except Exception as e:
        logging.error(f"Error executing query: {e}")
        return {
            "type": "query_result",
            "data": "",
            "status": "error",
            "message": f"Error executing query: {e}"
        }
