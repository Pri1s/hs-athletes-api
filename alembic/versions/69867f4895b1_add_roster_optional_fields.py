"""add roster optional fields

Revision ID: 69867f4895b1
Revises: 51a8f037f327
Create Date: 2026-06-17 14:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "69867f4895b1"
down_revision: Union[str, Sequence[str], None] = "51a8f037f327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("rosters")}
    if "grade_level" not in columns:
        op.add_column("rosters", sa.Column("grade_level", sa.SmallInteger(), nullable=True))
    if "height_inches" not in columns:
        op.add_column("rosters", sa.Column("height_inches", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("rosters")}
    if "height_inches" in columns:
        op.drop_column("rosters", "height_inches")
    if "grade_level" in columns:
        op.drop_column("rosters", "grade_level")
