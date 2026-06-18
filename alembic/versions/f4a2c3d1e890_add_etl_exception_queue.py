"""add etl exception queue

Revision ID: f4a2c3d1e890
Revises: 9b4cb8f5a2d1
Create Date: 2026-06-17 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f4a2c3d1e890"
down_revision: Union[str, Sequence[str], None] = "9b4cb8f5a2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "etl_exceptions" not in tables and "pending_unresolved_box_score_rows" in tables:
        op.rename_table("pending_unresolved_box_score_rows", "etl_exceptions")
        tables.remove("pending_unresolved_box_score_rows")
        tables.add("etl_exceptions")

    if "etl_exceptions" not in tables:
        op.create_table(
            "etl_exceptions",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("source_system", sa.Text(), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("external_game_id", sa.Text(), nullable=True),
            sa.Column("game_date", sa.Date(), nullable=True),
            sa.Column("team_name", sa.Text(), nullable=True),
            sa.Column("opponent_name", sa.Text(), nullable=True),
            sa.Column("player_name", sa.Text(), nullable=True),
            sa.Column("external_source_id", sa.Text(), nullable=True),
            sa.Column("profile_url", sa.Text(), nullable=True),
            sa.Column("parsing_stage", sa.Text(), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=False),
            sa.Column("raw_row_data", postgresql.JSONB(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    else:
        _upgrade_existing_table()

    op.execute("alter table etl_exceptions drop constraint if exists uq_pending_unresolved_box_score_row")
    op.execute(
        """
        do $$
        begin
            if not exists (
                select 1
                from pg_constraint
                where conname = 'ck_etl_exceptions_status'
            ) then
                alter table etl_exceptions
                add constraint ck_etl_exceptions_status
                check (status in ('pending', 'resolved', 'discarded'));
            end if;

            if not exists (
                select 1
                from pg_constraint
                where conname = 'uq_etl_exception_row'
            ) then
                alter table etl_exceptions
                add constraint uq_etl_exception_row
                unique (source_url, parsing_stage, team_name, player_name, failure_reason);
            end if;
        end
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "etl_exceptions" not in tables:
        return

    op.execute("alter table etl_exceptions drop constraint if exists uq_etl_exception_row")
    op.execute("alter table etl_exceptions drop constraint if exists ck_etl_exceptions_status")

    columns = {column["name"] for column in inspect(bind).get_columns("etl_exceptions")}
    if "raw_row_data" in columns and "row_payload" not in columns:
        op.alter_column("etl_exceptions", "raw_row_data", new_column_name="row_payload")
    if "failure_reason" in columns and "reason" not in columns:
        op.alter_column("etl_exceptions", "failure_reason", new_column_name="reason")

    for column_name in ("status", "parsing_stage"):
        if column_name in {column["name"] for column in inspect(bind).get_columns("etl_exceptions")}:
            op.drop_column("etl_exceptions", column_name)

    op.create_unique_constraint(
        "uq_pending_unresolved_box_score_row",
        "etl_exceptions",
        ["source_url", "team_name", "player_name", "reason"],
    )
    op.rename_table("etl_exceptions", "pending_unresolved_box_score_rows")


def _upgrade_existing_table() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("etl_exceptions")}

    if "reason" in columns and "failure_reason" not in columns:
        op.alter_column("etl_exceptions", "reason", new_column_name="failure_reason")
        columns.remove("reason")
        columns.add("failure_reason")

    if "row_payload" in columns and "raw_row_data" not in columns:
        op.alter_column("etl_exceptions", "row_payload", new_column_name="raw_row_data")
        columns.remove("row_payload")
        columns.add("raw_row_data")

    if "parsing_stage" not in columns:
        op.add_column(
            "etl_exceptions",
            sa.Column("parsing_stage", sa.Text(), nullable=False, server_default="box_score_stat_loader"),
        )

    if "status" not in columns:
        op.add_column("etl_exceptions", sa.Column("status", sa.Text(), nullable=False, server_default="pending"))

    nullable_columns = {column["name"]: column["nullable"] for column in inspect(bind).get_columns("etl_exceptions")}
    for column_name in ("game_date", "team_name", "opponent_name", "player_name"):
        if column_name in nullable_columns and not nullable_columns[column_name]:
            op.alter_column("etl_exceptions", column_name, nullable=True)
