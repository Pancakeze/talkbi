from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="business")
    hashed_password: Mapped[str] = mapped_column(String(255))


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    source_type: Mapped[str] = mapped_column(String(32))  # mysql/doris/excel
    connection_info: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    owner: Mapped["User"] = relationship()


class ThemeLibrary(Base, TimestampMixin):
    __tablename__ = "theme_libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="published")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    data_source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    owner: Mapped["User"] = relationship()
    data_source: Mapped[Optional["DataSource"]] = relationship()
    joins: Mapped[List["ThemeJoin"]] = relationship(
        back_populates="theme", cascade="all, delete-orphan"
    )


class ThemeField(Base, TimestampMixin):
    __tablename__ = "theme_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme_libraries.id"), index=True)
    table_name: Mapped[str] = mapped_column(String(128))
    field_name: Mapped[str] = mapped_column(String(128))
    alias_zh: Mapped[str] = mapped_column(String(128))
    visible: Mapped[bool] = mapped_column(Boolean, default=True)


class ThemeJoin(Base, TimestampMixin):
    __tablename__ = "theme_joins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    theme_id: Mapped[int] = mapped_column(ForeignKey("theme_libraries.id", ondelete="CASCADE"), index=True)
    left_table: Mapped[str] = mapped_column(String(128))
    right_table: Mapped[str] = mapped_column(String(128))
    left_column: Mapped[str] = mapped_column(String(128))
    right_column: Mapped[str] = mapped_column(String(128))
    join_type: Mapped[str] = mapped_column(String(16), default="inner")

    theme: Mapped["ThemeLibrary"] = relationship(back_populates="joins")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    sql_text: Mapped[str] = mapped_column(Text, default="")
    chart_spec: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="success")


class Chart(Base, TimestampMixin):
    __tablename__ = "charts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    chart_type: Mapped[str] = mapped_column(String(32))
    chart_spec: Mapped[dict] = mapped_column(JSON, default=dict)


class Dashboard(Base, TimestampMixin):
    __tablename__ = "dashboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))


class DashboardItem(Base, TimestampMixin):
    __tablename__ = "dashboard_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("dashboards.id"), index=True)
    chart_id: Mapped[int] = mapped_column(ForeignKey("charts.id"))
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    position_x: Mapped[int] = mapped_column(Integer, default=0)
    position_y: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=6)
    height: Mapped[int] = mapped_column(Integer, default=4)
