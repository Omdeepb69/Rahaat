"""Identity, sequence-ordered event log, operational bookkeeping.

Revision ID: 8c1d0a000001
Revises: 7b9d3f1a2c4e
Create Date: 2026-11-16

Adds user accounts, turns audit_events into a sequence-ordered log with a
NOTIFY trigger, adds worker heartbeat / processing run / integration check /
external observation tables, and drops callback_jobs and sync_cursors (stub
outbound telephony and unauthenticated device sync were removed from the
application; both tables were empty bookkeeping).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "8c1d0a000001"
down_revision: Union[str, None] = "7b9d3f1a2c4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            username VARCHAR(64) NOT NULL,
            full_name VARCHAR(160) NOT NULL,
            role VARCHAR(32) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
            token_version INTEGER NOT NULL DEFAULT 0,
            failed_login_count INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMPTZ,
            last_login_at TIMESTAMPTZ,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT users_users_role_valid_check CHECK (
                role IN ('admin','operator','dispatcher','resource_coordinator','observer')
            )
        );
        CREATE UNIQUE INDEX users_username_lower_key ON users (lower(username));
        """
    )

    # audit_events becomes the ordered event log. Existing rows are numbered in
    # their recorded order before the sequence takes over.
    op.execute(
        """
        ALTER TABLE audit_events
            ADD COLUMN seq BIGINT,
            ADD COLUMN disaster_id UUID,
            ADD COLUMN incident_id UUID;

        UPDATE audit_events a SET seq = n.rn
        FROM (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM audit_events
        ) n
        WHERE a.id = n.id;

        CREATE SEQUENCE audit_events_seq_seq OWNED BY audit_events.seq;
        SELECT setval(
            'audit_events_seq_seq',
            COALESCE((SELECT max(seq) FROM audit_events), 0) + 1,
            false
        );
        ALTER TABLE audit_events
            ALTER COLUMN seq SET DEFAULT nextval('audit_events_seq_seq'),
            ALTER COLUMN seq SET NOT NULL;

        UPDATE audit_events SET incident_id = entity_id WHERE entity_type = 'incident';

        CREATE UNIQUE INDEX audit_events_seq_key ON audit_events (seq);
        CREATE INDEX audit_events_incident_seq_idx ON audit_events (incident_id, seq);
        CREATE INDEX audit_events_disaster_seq_idx ON audit_events (disaster_id, seq);

        CREATE FUNCTION raahat_notify_event() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('raahat_events', NEW.seq::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER audit_events_notify
            AFTER INSERT ON audit_events
            FOR EACH ROW EXECUTE FUNCTION raahat_notify_event();
        """
    )

    op.execute(
        """
        CREATE TABLE worker_heartbeats (
            worker_name VARCHAR(64) PRIMARY KEY,
            pid INTEGER NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            last_beat_at TIMESTAMPTZ NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        );

        CREATE TABLE processing_runs (
            id UUID PRIMARY KEY,
            report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            stage VARCHAR(32) NOT NULL,
            provider VARCHAR(64) NOT NULL,
            model VARCHAR(128),
            status VARCHAR(32) NOT NULL,
            duration_ms DOUBLE PRECISION,
            confidence DOUBLE PRECISION,
            error TEXT,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX processing_runs_report_idx ON processing_runs (report_id, created_at);
        CREATE INDEX processing_runs_stage_idx ON processing_runs (stage, provider, created_at);

        CREATE TABLE integration_checks (
            integration VARCHAR(64) PRIMARY KEY,
            status VARCHAR(32) NOT NULL,
            detail TEXT,
            latency_ms DOUBLE PRECISION,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_success_at TIMESTAMPTZ,
            last_error TEXT,
            last_error_at TIMESTAMPTZ
        );

        CREATE TABLE external_observations (
            id UUID PRIMARY KEY,
            provider VARCHAR(64) NOT NULL,
            external_id VARCHAR(255) NOT NULL,
            kind VARCHAR(32) NOT NULL,
            authority VARCHAR(16) NOT NULL,
            headline TEXT NOT NULL,
            severity VARCHAR(32),
            area_description TEXT,
            issued_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            source_url TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX external_observations_provider_key
            ON external_observations (provider, external_id);
        CREATE INDEX external_observations_kind_idx ON external_observations (kind, issued_at);
        """
    )

    op.execute("DROP TABLE IF EXISTS callback_jobs CASCADE;")
    # Offline device sync was removed with the unauthenticated endpoint that fed it.
    op.execute("DROP TABLE IF EXISTS sync_cursors CASCADE;")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS callback_jobs (
            id UUID PRIMARY KEY,
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
        CREATE TABLE IF NOT EXISTS sync_cursors (
            id UUID PRIMARY KEY,
            device_id UUID NOT NULL UNIQUE,
            last_sequence BIGINT NOT NULL DEFAULT 0,
            last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            sync_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        DROP TABLE external_observations;
        DROP TABLE integration_checks;
        DROP TABLE processing_runs;
        DROP TABLE worker_heartbeats;

        DROP TRIGGER audit_events_notify ON audit_events;
        DROP FUNCTION raahat_notify_event();
        DROP INDEX audit_events_disaster_seq_idx;
        DROP INDEX audit_events_incident_seq_idx;
        DROP INDEX audit_events_seq_key;
        ALTER TABLE audit_events
            DROP COLUMN seq,
            DROP COLUMN disaster_id,
            DROP COLUMN incident_id;

        DROP TABLE users;
        """
    )
