"""theme data_source link and theme_joins

Revision ID: a1b2c3d4e5f6
Revises: 44bec74d3f21
Create Date: 2026-04-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "44bec74d3f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "theme_libraries",
        sa.Column("data_source_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_theme_libraries_data_source_id",
        "theme_libraries",
        "data_sources",
        ["data_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_theme_libraries_data_source_id"),
        "theme_libraries",
        ["data_source_id"],
        unique=False,
    )
    op.create_table(
        "theme_joins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("theme_id", sa.Integer(), nullable=False),
        sa.Column("left_table", sa.String(length=128), nullable=False),
        sa.Column("right_table", sa.String(length=128), nullable=False),
        sa.Column("left_column", sa.String(length=128), nullable=False),
        sa.Column("right_column", sa.String(length=128), nullable=False),
        sa.Column("join_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["theme_id"], ["theme_libraries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_theme_joins_theme_id"),
        "theme_joins",
        ["theme_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_theme_joins_theme_id"), table_name="theme_joins")
    op.drop_table("theme_joins")
    op.drop_index(op.f("ix_theme_libraries_data_source_id"), table_name="theme_libraries")
    op.drop_constraint("fk_theme_libraries_data_source_id", "theme_libraries", type_="foreignkey")
    op.drop_column("theme_libraries", "data_source_id")
