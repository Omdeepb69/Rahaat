"""add_pg_trgm_and_landmark_trgm_index

Revision ID: 41e7e411f7ee
Revises: 603b7baf3fc9
Create Date: 2026-11-07 13:05:59.885455

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '41e7e411f7ee'
down_revision: Union[str, None] = '603b7baf3fc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS landmarks_name_trgm_idx "
        "ON landmarks USING gin (name gin_trgm_ops);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS landmarks_name_trgm_idx;")

