from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Conversation, User
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse
from app.services.chat_service import run_chat_query

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/query", response_model=ChatQueryResponse)
def query_chat(
    payload: ChatQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = run_chat_query(db, current_user, payload.prompt, payload.theme_ids)
    conv = Conversation(
        user_id=current_user.id,
        prompt=payload.prompt,
        sql_text=result.sql,
        chart_spec={**result.chart_spec, "rows": result.rows},
        status=result.status,
    )
    db.add(conv)
    db.commit()
    return result
