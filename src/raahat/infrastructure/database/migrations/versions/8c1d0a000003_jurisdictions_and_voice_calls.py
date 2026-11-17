"""Jurisdictions on accounts and operations; guided voice call sessions.

Revision ID: 8c1d0a000003
Revises: 8c1d0a000002
Create Date: 2026-11-17

Existing accounts and operations receive no jurisdiction. An operation without
one is visible only to national accounts until an administrator assigns it.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "8c1d0a000003"
down_revision: Union[str, None] = "8c1d0a000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN state_code VARCHAR(8),
            ADD COLUMN district_code VARCHAR(8),
            ADD CONSTRAINT users_district_needs_state
                CHECK (district_code IS NULL OR state_code IS NOT NULL);
        ALTER TABLE users DROP CONSTRAINT users_users_role_valid_check;
        ALTER TABLE users ADD CONSTRAINT users_users_role_valid_check CHECK (
            role IN ('admin','control_room','operator','dispatcher','resource_coordinator','observer')
        );

        ALTER TABLE disasters
            ADD COLUMN state_code VARCHAR(8),
            ADD COLUMN district_code VARCHAR(8),
            ADD COLUMN is_standing BOOLEAN NOT NULL DEFAULT false,
            ADD CONSTRAINT disasters_district_needs_state
                CHECK (district_code IS NULL OR state_code IS NOT NULL);
        CREATE INDEX disasters_jurisdiction_idx ON disasters (state_code, district_code, status);

        CREATE TABLE voice_calls (
            id UUID PRIMARY KEY,
            token_hash VARCHAR(64) NOT NULL,
            state_code VARCHAR(8) NOT NULL,
            district_code VARCHAR(8) NOT NULL,
            language VARCHAR(8) NOT NULL DEFAULT 'hi',
            language_source VARCHAR(16) NOT NULL DEFAULT 'default',
            status VARCHAR(16) NOT NULL DEFAULT 'open',
            step VARCHAR(32) NOT NULL,
            slots JSONB NOT NULL DEFAULT '{}'::jsonb,
            turns JSONB NOT NULL DEFAULT '[]'::jsonb,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            location_accuracy_m DOUBLE PRECISION,
            client_ip VARCHAR(64),
            report_id UUID REFERENCES reports(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            submitted_at TIMESTAMPTZ,
            CONSTRAINT voice_calls_voice_calls_status_valid_check CHECK (status IN ('open','submitted','abandoned'))
        );
        CREATE INDEX voice_calls_open_idx ON voice_calls (status, updated_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE voice_calls;
        DROP INDEX disasters_jurisdiction_idx;
        ALTER TABLE disasters
            DROP CONSTRAINT disasters_district_needs_state,
            DROP COLUMN is_standing,
            DROP COLUMN district_code,
            DROP COLUMN state_code;
        UPDATE users SET role = 'admin' WHERE role = 'control_room';
        ALTER TABLE users DROP CONSTRAINT users_users_role_valid_check;
        ALTER TABLE users ADD CONSTRAINT users_users_role_valid_check CHECK (
            role IN ('admin','operator','dispatcher','resource_coordinator','observer')
        );
        ALTER TABLE users
            DROP CONSTRAINT users_district_needs_state,
            DROP COLUMN district_code,
            DROP COLUMN state_code;
        """
    )
