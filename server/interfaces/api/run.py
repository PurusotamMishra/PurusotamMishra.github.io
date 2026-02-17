from fastapi import FastAPI
from fastapi.responses import JSONResponse
from core.workflows.fetch_logs import FetchLogsWorkflow

app = FastAPI()

@app.post("/api/v1/agent/logs/fetch")
async def fetch_logs(query: str):
    workflow = FetchLogsWorkflow()
    return await workflow.stream_workflow_events(workflow_input)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)