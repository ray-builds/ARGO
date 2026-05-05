"""Store Microsoft Graph tokens server-side on users.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-05 14:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("graph_access_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("graph_refresh_token", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("graph_token_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "graph_token_expires_at")
    op.drop_column("users", "graph_refresh_token")
    op.drop_column("users", "graph_access_token")
