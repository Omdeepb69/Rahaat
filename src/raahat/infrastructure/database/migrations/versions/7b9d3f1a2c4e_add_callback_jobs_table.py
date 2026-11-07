"""add_callback_jobs_table

Revision ID: 7b9d3f1a2c4e
Revises: 41e7e411f7ee
Create Date: 2026-11-07 18:47:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b9d3f1a2c4e'
down_revision: Union[str, None] = '41e7e411f7ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS callback_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            disaster_id UUID NOT NULL REFERENCES disasters(id) ON DELETE CASCADE,
            phone_number VARCHAR(32) NOT NULL,
            consent_given BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            scheduled_at TIMESTAMPTZ NOT NULL,
            last_attempted_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            provider_call_id VARCHAR(128),
            failure_reason TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS callback_jobs_phone_number_idx ON callback_jobs (phone_number);
        CREATE INDEX IF NOT EXISTS callback_jobs_status_idx ON callback_jobs (status);
        CREATE INDEX IF NOT EXISTS callback_jobs_scheduled_at_idx ON callback_jobs (scheduled_at);
        CREATE INDEX IF NOT EXISTS callback_jobs_disaster_id_idx ON callback_jobs (disaster_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS callback_jobs CASCADE;")

