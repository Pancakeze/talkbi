from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Chart, User
from app.schemas.chart import ChartCreate, ChartOut

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("", response_model=list[ChartOut])
def list_charts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Chart).filter(Chart.user_id == current_user.id).all()


@router.post("", response_model=ChartOut)
def create_chart(
    payload: ChartCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chart = Chart(user_id=current_user.id, **payload.model_dump())
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart
