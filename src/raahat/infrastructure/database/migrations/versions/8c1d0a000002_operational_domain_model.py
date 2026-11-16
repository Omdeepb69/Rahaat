"""Operational domain model: incident lifecycle, provenance, resources, dispatch decisions.

Revision ID: 8c1d0a000002
Revises: 8c1d0a000001
Create Date: 2026-11-16

Existing rows are preserved. Incidents receive a reference number in creation
order; resources receive a callsign derived from their id; existing location
hypotheses are marked ``unknown`` source because their provenance was never
recorded.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "8c1d0a000002"
down_revision: Union[str, None] = "8c1d0a000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- disasters ---------------------------------------------------------
    op.execute(
        """
        ALTER TABLE disasters
            ADD COLUMN description TEXT,
            ADD COLUMN area_name VARCHAR(255),
            ADD COLUMN map_center geography(POINT, 4326),
            ADD COLUMN closed_at TIMESTAMPTZ;
        """
    )

    # ---- reports -----------------------------------------------------------
    op.execute(
        """
        ALTER TABLE reports
            ADD COLUMN original_text TEXT,
            ADD COLUMN original_language VARCHAR(16),
            ADD COLUMN language_confidence DOUBLE PRECISION,
            ADD COLUMN language_source VARCHAR(64),
            ADD COLUMN translated_text TEXT,
            ADD COLUMN translation_provider VARCHAR(64),
            ADD COLUMN caller_name VARCHAR(160),
            ADD COLUMN caller_contact VARCHAR(64),
            ADD COLUMN created_by UUID,
            ADD COLUMN processing_error TEXT,
            ADD COLUMN processed_at TIMESTAMPTZ;
        CREATE INDEX reports_processing_status_idx ON reports (processing_status, received_at);
        """
    )

    # ---- incidents ---------------------------------------------------------
    op.execute(
        """
        CREATE SEQUENCE incident_reference_seq;

        ALTER TABLE incidents
            ADD COLUMN reference VARCHAR(24),
            ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'unknown',
            ADD COLUMN summary TEXT,
            ADD COLUMN source_channel VARCHAR(32),
            ADD COLUMN fact_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN triage JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN location_description TEXT,
            ADD COLUMN location geography(POINT, 4326),
            ADD COLUMN location_status VARCHAR(16) NOT NULL DEFAULT 'none',
            ADD COLUMN location_source VARCHAR(32),
            ADD COLUMN location_label VARCHAR(255),
            ADD COLUMN location_confidence DOUBLE PRECISION,
            ADD COLUMN location_uncertainty_m DOUBLE PRECISION,
            ADD COLUMN location_hypothesis_id UUID,
            ADD COLUMN created_by UUID,
            ADD COLUMN verified_by UUID,
            ADD COLUMN verified_at TIMESTAMPTZ,
            ADD COLUMN resolved_at TIMESTAMPTZ,
            ADD COLUMN closed_at TIMESTAMPTZ,
            ADD COLUMN closure_reason VARCHAR(64),
            ADD COLUMN merged_into_id UUID REFERENCES incidents(id) ON DELETE SET NULL;

        UPDATE incidents i SET reference = 'INC-' || lpad(n.rn::text, 6, '0')
        FROM (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM incidents
        ) n
        WHERE i.id = n.id;
        SELECT setval(
            'incident_reference_seq',
            COALESCE((SELECT count(*) FROM incidents), 0) + 1,
            false
        );
        ALTER TABLE incidents
            ALTER COLUMN reference SET NOT NULL,
            ALTER COLUMN reference SET DEFAULT
                'INC-' || lpad(nextval('incident_reference_seq')::text, 6, '0');

        -- Incidents closed by a merge become 'duplicate' and point at their target.
        UPDATE incidents
        SET status = 'duplicate',
            merged_into_id = (severity_facts->>'merged_into')::uuid
        WHERE status = 'closed'
          AND severity_facts ? 'merged_into'
          AND EXISTS (
              SELECT 1 FROM incidents t WHERE t.id = (incidents.severity_facts->>'merged_into')::uuid
          );

        ALTER TABLE incidents ADD CONSTRAINT incidents_incidents_status_valid_check CHECK (
            status IN ('unverified','under_review','verified','assigned',
                       'in_progress','resolved','closed','duplicate')
        );
        ALTER TABLE incidents ADD CONSTRAINT incidents_incidents_location_confidence_range_check CHECK (
            location_confidence IS NULL OR (location_confidence >= 0.0 AND location_confidence <= 1.0)
        );
        CREATE UNIQUE INDEX incidents_reference_key ON incidents (reference);
        CREATE INDEX incidents_disaster_status_idx ON incidents (disaster_id, status, created_at);
        CREATE INDEX incidents_location_geo_idx ON incidents USING gist (location);
        CREATE INDEX incident_reports_report_idx ON incident_reports (report_id);
        """
    )

    # ---- incident links ----------------------------------------------------
    op.execute(
        """
        ALTER TABLE incident_links
            ADD COLUMN signals JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN reviewed_by UUID,
            ADD COLUMN reviewed_at TIMESTAMPTZ,
            ADD COLUMN review_reason TEXT;
        CREATE INDEX incident_links_status_idx ON incident_links (status, created_at);
        CREATE INDEX incident_links_a_idx ON incident_links (incident_a_id);
        CREATE INDEX incident_links_b_idx ON incident_links (incident_b_id);
        """
    )

    # ---- location hypotheses and landmarks ---------------------------------
    op.execute(
        """
        ALTER TABLE location_hypotheses
            ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'unknown',
            ADD COLUMN source_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN report_id UUID REFERENCES reports(id) ON DELETE SET NULL,
            ADD COLUMN confirmed_by UUID,
            ADD COLUMN confirmed_at TIMESTAMPTZ;
        ALTER TABLE location_hypotheses
            ADD CONSTRAINT location_hypotheses_location_hypotheses_source_valid_check CHECK (
                source IN ('caller_gps','operator','geocoder','landmark','unknown')
            );
        CREATE INDEX location_hypotheses_incident_idx
            ON location_hypotheses (incident_id, created_at);

        ALTER TABLE landmarks ADD COLUMN source VARCHAR(32) NOT NULL DEFAULT 'operator';
        CREATE UNIQUE INDEX landmarks_source_external_key
            ON landmarks (source, external_id) WHERE external_id IS NOT NULL;
        """
    )

    # ---- resources ---------------------------------------------------------
    op.execute(
        """
        ALTER TABLE resources
            ADD COLUMN callsign VARCHAR(64),
            ADD COLUMN crew_size INTEGER,
            ADD COLUMN capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN status_note TEXT,
            ADD COLUMN base_name VARCHAR(255),
            ADD COLUMN contact VARCHAR(160),
            ADD COLUMN notes TEXT,
            ADD COLUMN position_source VARCHAR(32),
            ADD COLUMN position_updated_at TIMESTAMPTZ,
            ADD COLUMN position_accuracy_m DOUBLE PRECISION,
            ADD COLUMN is_retired BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN created_by UUID,
            ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

        UPDATE resources SET callsign = 'R-' || upper(substr(id::text, 1, 8));
        -- A stored position must carry a timestamp. For rows that predate
        -- position tracking the only honest timestamp is the row's creation.
        UPDATE resources
        SET position_updated_at = created_at, position_source = 'operator'
        WHERE location IS NOT NULL;

        ALTER TABLE resources ALTER COLUMN callsign SET NOT NULL;
        ALTER TABLE resources ADD CONSTRAINT resources_resources_status_valid_check CHECK (
            availability_status IN ('available','assigned','maintenance','offline')
        );
        ALTER TABLE resources ADD CONSTRAINT resources_resources_capacity_nonnegative_check CHECK (
            capacity IS NULL OR capacity >= 0
        );
        ALTER TABLE resources ADD CONSTRAINT resources_resources_position_has_timestamp_check CHECK (
            (location IS NULL) = (position_updated_at IS NULL)
        );
        CREATE INDEX resources_disaster_status_idx ON resources (disaster_id, availability_status);
        CREATE UNIQUE INDEX resources_disaster_callsign_key ON resources (disaster_id, callsign);
        """
    )

    # ---- assignments and decisions ----------------------------------------
    op.execute(
        """
        ALTER TABLE assignments
            ADD COLUMN stage VARCHAR(32) NOT NULL DEFAULT 'proposed',
            ADD COLUMN notes TEXT,
            ADD COLUMN decision_id UUID,
            ADD COLUMN completed_at TIMESTAMPTZ,
            ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

        UPDATE assignments a SET stage = COALESCE(
            (SELECT e.event_type FROM operation_events e
             WHERE e.assignment_id = a.id ORDER BY e.created_at DESC LIMIT 1),
            a.status
        );

        -- Before the one-active-assignment rule can be enforced, older rows
        -- that leave a resource committed twice are demoted to 'cancelled',
        -- keeping the most recent commitment.
        UPDATE assignments SET status = 'cancelled', stage = 'cancelled'
        WHERE status = 'approved' AND id NOT IN (
            SELECT DISTINCT ON (resource_id) id FROM assignments
            WHERE status = 'approved' ORDER BY resource_id, created_at DESC
        );

        CREATE INDEX assignments_incident_idx ON assignments (incident_id, created_at);
        CREATE INDEX assignments_status_idx ON assignments (status, created_at);
        CREATE UNIQUE INDEX assignments_one_active_per_resource
            ON assignments (resource_id) WHERE status = 'approved';
        CREATE INDEX operation_events_assignment_idx
            ON operation_events (assignment_id, created_at);

        CREATE TABLE dispatch_decisions (
            id UUID PRIMARY KEY,
            incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            decision VARCHAR(16) NOT NULL,
            chosen_resource_id UUID REFERENCES resources(id) ON DELETE SET NULL,
            recommended_resource_id UUID,
            followed_recommendation BOOLEAN,
            recommendation JSONB NOT NULL DEFAULT '{}'::jsonb,
            reason TEXT,
            decided_by UUID NOT NULL,
            assignment_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT dispatch_decisions_dispatch_decisions_decision_valid_check
                CHECK (decision IN ('approved','rejected'))
        );
        CREATE INDEX dispatch_decisions_incident_idx
            ON dispatch_decisions (incident_id, created_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE dispatch_decisions;
        DROP INDEX operation_events_assignment_idx;
        DROP INDEX assignments_one_active_per_resource;
        DROP INDEX assignments_status_idx;
        DROP INDEX assignments_incident_idx;
        ALTER TABLE assignments
            DROP COLUMN stage, DROP COLUMN notes, DROP COLUMN decision_id,
            DROP COLUMN completed_at, DROP COLUMN updated_at;

        DROP INDEX resources_disaster_callsign_key;
        DROP INDEX resources_disaster_status_idx;
        ALTER TABLE resources
            DROP CONSTRAINT resources_resources_position_has_timestamp_check,
            DROP CONSTRAINT resources_resources_capacity_nonnegative_check,
            DROP CONSTRAINT resources_resources_status_valid_check,
            DROP COLUMN callsign, DROP COLUMN crew_size, DROP COLUMN capabilities,
            DROP COLUMN status_note, DROP COLUMN base_name, DROP COLUMN contact,
            DROP COLUMN notes, DROP COLUMN position_source, DROP COLUMN position_updated_at,
            DROP COLUMN position_accuracy_m, DROP COLUMN is_retired, DROP COLUMN created_by,
            DROP COLUMN updated_at;

        DROP INDEX landmarks_source_external_key;
        ALTER TABLE landmarks DROP COLUMN source;
        DROP INDEX location_hypotheses_incident_idx;
        ALTER TABLE location_hypotheses
            DROP CONSTRAINT location_hypotheses_location_hypotheses_source_valid_check,
            DROP COLUMN source, DROP COLUMN source_detail, DROP COLUMN report_id,
            DROP COLUMN confirmed_by, DROP COLUMN confirmed_at;

        DROP INDEX incident_links_b_idx;
        DROP INDEX incident_links_a_idx;
        DROP INDEX incident_links_status_idx;
        ALTER TABLE incident_links
            DROP COLUMN signals, DROP COLUMN reviewed_by,
            DROP COLUMN reviewed_at, DROP COLUMN review_reason;

        DROP INDEX incident_reports_report_idx;
        DROP INDEX incidents_location_geo_idx;
        DROP INDEX incidents_disaster_status_idx;
        DROP INDEX incidents_reference_key;
        ALTER TABLE incidents
            DROP CONSTRAINT incidents_incidents_location_confidence_range_check,
            DROP CONSTRAINT incidents_incidents_status_valid_check;
        -- The previous schema had no 'duplicate', 'under_review' or 'assigned'.
        UPDATE incidents SET status = 'closed' WHERE status = 'duplicate';
        UPDATE incidents SET status = 'unverified' WHERE status = 'under_review';
        UPDATE incidents SET status = 'verified' WHERE status = 'assigned';
        ALTER TABLE incidents
            DROP COLUMN reference, DROP COLUMN category, DROP COLUMN summary,
            DROP COLUMN source_channel, DROP COLUMN fact_overrides, DROP COLUMN triage,
            DROP COLUMN location_description, DROP COLUMN location, DROP COLUMN location_status,
            DROP COLUMN location_source, DROP COLUMN location_label,
            DROP COLUMN location_confidence, DROP COLUMN location_uncertainty_m,
            DROP COLUMN location_hypothesis_id, DROP COLUMN created_by, DROP COLUMN verified_by,
            DROP COLUMN verified_at, DROP COLUMN resolved_at, DROP COLUMN closed_at,
            DROP COLUMN closure_reason, DROP COLUMN merged_into_id;
        DROP SEQUENCE incident_reference_seq;

        DROP INDEX reports_processing_status_idx;
        ALTER TABLE reports
            DROP COLUMN original_text, DROP COLUMN original_language,
            DROP COLUMN language_confidence, DROP COLUMN language_source,
            DROP COLUMN translated_text, DROP COLUMN translation_provider,
            DROP COLUMN caller_name, DROP COLUMN caller_contact, DROP COLUMN created_by,
            DROP COLUMN processing_error, DROP COLUMN processed_at;

        ALTER TABLE disasters
            DROP COLUMN description, DROP COLUMN area_name,
            DROP COLUMN map_center, DROP COLUMN closed_at;
        """
    )
