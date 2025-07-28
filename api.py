from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from init import Config
import uvicorn
import logging

app = FastAPI()

class ReturnRequest(BaseModel):
    function_name: str
    function_id: int
    result: str

@app.post("/return")
async def tool_call(request: ReturnRequest):
    try:
        Config.Agent_return[request.function_id] = request.result
        return {"message": "successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def main():
    logging.getLogger("uvicorn").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    uvicorn.run(app, host="127.0.0.1", port=Config.port, log_level="error")