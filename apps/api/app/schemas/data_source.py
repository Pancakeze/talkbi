from pydantic import BaseModel, Field

from app.schemas.common import Timestamped


class DataSourceCreate(BaseModel):
    name: str
    source_type: str
    connection_info: dict = Field(default_factory=dict)


class DataSourceOut(Timestamped):
    name: str
    source_type: str
    connection_info: dict
    status: str
    owner_id: int
