from pydantic import BaseModel

from app.schemas.common import Timestamped


class ChartCreate(BaseModel):
    title: str
    chart_type: str
    chart_spec: dict


class ChartOut(Timestamped):
    user_id: int
    title: str
    chart_type: str
    chart_spec: dict
