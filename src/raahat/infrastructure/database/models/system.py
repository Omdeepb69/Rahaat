"""Operational bookkeeping: worker liveness, AI processing runs, integration checks."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class WorkerHeartbeatModel(Base):
    """One row per worker process, refreshed every tick."""

    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ProcessingRunModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One attempt by one provider at one processing stage of a report.

    This is the provenance record for machine-derived content: which provider
    and model produced it, how long it took, and how it ended.
    """

    __tablename__ = "processing_runs"
    __table_args__ = (
        Index("processing_runs_report_idx", "report_id", "created_at"),
        Index("processing_runs_stage_idx", "stage", "provider", "created_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    # transcription | language_id | translation | extraction | location
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # succeeded | failed | not_configured | skipped
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class IntegrationCheckModel(Base):
    """Latest probe result per integration. Written only by real probes and real calls."""

    __tablename__ = "integration_checks"

    integration: Mapped[str] = mapped_column(String(64), primary_key=True)
    # operational | degraded | unavailable | not_configured
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExternalObservationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A record fetched from an external situational-data provider.

    Stored verbatim with its provenance so the interface can state where it
    came from, when the provider issued it and when it was fetched.
    """

    __tablename__ = "external_observations"
    __table_args__ = (
        Index("external_observations_provider_key", "provider", "external_id", unique=True),
        Index("external_observations_kind_idx", "kind", "issued_at"),
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # alert | rainfall_forecast
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # official | model — whether the provider is an issuing authority
    authority: Mapped[str] = mapped_column(String(16), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    area_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
