from typing import Optional

from pydantic import BaseModel

from app.schemas.common import Timestamped


class DashboardCreate(BaseModel):
    name: str


class DashboardOut(Timestamped):
    user_id: int
    name: str


class DashboardLayoutItem(BaseModel):
    chart_id: int
    title: Optional[str] = None
    position_x: int
    position_y: int
    width: int = 6
    height: int = 4


class DashboardLayoutUpdate(BaseModel):
    items: list[DashboardLayoutItem]


class DashboardLayoutItemResponse(BaseModel):
    chart_id: int
    position_x: int
    position_y: int
    width: int
    height: int
    title: str


class DashboardLayoutResponse(BaseModel):
    items: list[DashboardLayoutItemResponse]
