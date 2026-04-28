from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.common import Timestamped


class ThemeCreate(BaseModel):
    name: str
    description: str = ""
    data_source_id: Optional[int] = None


class ThemeOut(Timestamped):
    name: str
    description: str
    status: str
    owner_id: int
    data_source_id: Optional[int] = None


class ThemeFieldCreate(BaseModel):
    table_name: str
    field_name: str
    alias_zh: str
    visible: bool = True


class ThemeFieldPatch(BaseModel):
    alias_zh: Optional[str] = None
    visible: Optional[bool] = None


class ThemeFieldOut(Timestamped):
    theme_id: int
    table_name: str
    field_name: str
    alias_zh: str
    visible: bool


class ThemeJoinCreate(BaseModel):
    left_table: str
    right_table: str
    left_column: str
    right_column: str
    join_type: Literal["inner", "left"] = "inner"


class ThemeJoinOut(Timestamped):
    theme_id: int
    left_table: str
    right_table: str
    left_column: str
    right_column: str
    join_type: str
