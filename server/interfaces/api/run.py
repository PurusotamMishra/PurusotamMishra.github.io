import uvicorn
import os

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=os.getenv('PORT_API', 8082),
        reload=True
    )