from fastapi_demo import FastAPI
from pydantic import BaseModel


class ChatRequest(BaseModel):
    prompt: str

app = FastAPI()

@app.post("/")
def ai_prompt(request: ChatRequest):
    return {"Your prompt is" : request. prompt}