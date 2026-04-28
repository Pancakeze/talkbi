from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Chart, Dashboard, DashboardItem, User
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardLayoutItemResponse,
    DashboardLayoutResponse,
    DashboardLayoutUpdate,
    DashboardOut,
)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _get_owned_dashboard(db: Session, dashboard_id: int, user: User) -> Dashboard:
    dash = (
        db.query(Dashboard)
        .filter(Dashboard.id == dashboard_id, Dashboard.user_id == user.id)
        .first()
    )
    if not dash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
    return dash


@router.get("", response_model=list[DashboardOut])
def list_dashboards(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return db.query(Dashboard).filter(Dashboard.user_id == current_user.id).all()


@router.post("", response_model=DashboardOut)
def create_dashboard(
    payload: DashboardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dashboard = Dashboard(user_id=current_user.id, name=payload.name)
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return dashboard


@router.get("/{dashboard_id}/layout", response_model=DashboardLayoutResponse)
def get_layout(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_dashboard(db, dashboard_id, current_user)
    items = db.query(DashboardItem).filter(DashboardItem.dashboard_id == dashboard_id).all()
    out: list[DashboardLayoutItemResponse] = []
    for it in items:
        chart = db.query(Chart).filter(Chart.id == it.chart_id).first()
        title = it.title or (chart.title if chart else "")
        out.append(
            DashboardLayoutItemResponse(
                chart_id=it.chart_id,
                position_x=it.position_x,
                position_y=it.position_y,
                width=it.width,
                height=it.height,
                title=title,
            )
        )
    return DashboardLayoutResponse(items=out)


@router.patch("/{dashboard_id}/layout")
def update_layout(
    dashboard_id: int,
    payload: DashboardLayoutUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_dashboard(db, dashboard_id, current_user)
    for item in payload.items:
        chart = (
            db.query(Chart)
            .filter(Chart.id == item.chart_id, Chart.user_id == current_user.id)
            .first()
        )
        if not chart:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chart {item.chart_id} not found or not owned by user",
            )
    db.query(DashboardItem).filter(DashboardItem.dashboard_id == dashboard_id).delete()
    for item in payload.items:
        db_item = DashboardItem(
            dashboard_id=dashboard_id,
            chart_id=item.chart_id,
            title=item.title,
            position_x=item.position_x,
            position_y=item.position_y,
            width=item.width,
            height=item.height,
        )
        db.add(db_item)
    db.commit()
    return {"ok": True, "count": len(payload.items)}
