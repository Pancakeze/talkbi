"""add_dashboard_item_title

Revision ID: 7c2a9f0a9b3e
Revises: a1b2c3d4e5f6
Create Date: 2026-04-28 09:32:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c2a9f0a9b3e"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("dashboard_items", sa.Column("title", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("dashboard_items", "title")

