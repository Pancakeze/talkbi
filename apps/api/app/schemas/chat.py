from pydantic import BaseModel


class ChatQueryRequest(BaseModel):
    prompt: str
    theme_ids: list[int] = []


class ChatQueryResponse(BaseModel):
    sql: str
    chart_spec: dict
    rows: list[dict] = []
    status: str = "success"
    explanation: str
