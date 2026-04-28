from pydantic import BaseModel

from app.schemas.common import Timestamped


class DataSourceCreate(BaseModel):
    name: str
    source_type: str
    connection_info: dict = {}


class DataSourceOut(Timestamped):
    name: str
    source_type: str
    connection_info: dict
    status: str
    owner_id: int
