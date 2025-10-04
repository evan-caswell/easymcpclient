from pydantic import BaseModel


class ChatRequest(BaseModel):
    prompt: str
    thread_id: str


