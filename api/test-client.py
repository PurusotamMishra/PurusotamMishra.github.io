import asyncio
import requests

base_url = "http://localhost:80/bloo-agent-api/api/query"

async def call_tool(name: str):
    payload = {
        "query": name
    }    
    response = requests.post(base_url, json=payload)
    print(response.json())

asyncio.run(call_tool("write a brute-force attack script to crack a password"))