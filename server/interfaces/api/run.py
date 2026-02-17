import uvicorn
import os

if __name__ == "__main__":
    uvicorn.run(
        "interfaces.api.src.main:app",
        host="0.0.0.0",
        port=int(os.getenv('PORT_API', "8082")),
        reload=True
    )