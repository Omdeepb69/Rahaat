"""Cryptographic verification engine for tamper-evident audit logs."""
from __future__ import annotations

import logging
import uuid
from typing import Sequence

from raahat.infrastructure.audit.models import (
    ChainVerificationResult,
    GlobalVerificationResult,
)
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    compute_audit_hash,
)

logger = logging.getLogger(__name__)


class AuditVerifier:
    """Verifies cryptographic integrity and hash continuity of append-only audit logs."""

    @staticmethod
    def verify_entity_chain(
        entity_type: str,
        entity_id: uuid.UUID,
        events: Sequence[AuditEventModel],
    ) -> ChainVerificationResult:
        """Verify the cryptographic hash chain for a specific entity.

        Detects:
        - Payload modifications
        - Action or actor alterations
        - Event deletions or omissions anywhere in the chain
        - Spliced, reordered, or inserted records
        - Forged genesis events
        """
        if not events:
            return ChainVerificationResult(
                entity_type=entity_type,
                entity_id=entity_id,
                is_valid=True,
                total_events=0,
                genesis_hash=None,
                latest_hash=None,
            )

        # 1. First event in chain must be genesis (prev_hash is None or empty)
        genesis = events[0]
        if genesis.prev_hash is not None and genesis.prev_hash != "":
            return ChainVerificationResult(
                entity_type=entity_type,
                entity_id=entity_id,
                is_valid=False,
                total_events=len(events),
                genesis_hash=genesis.hash,
                latest_hash=events[-1].hash,
                error_message=(
                    f"Genesis event {genesis.id} contains non-null prev_hash '{genesis.prev_hash}'. "
                    f"Preceding historical records may have been omitted or deleted."
                ),
                corrupted_event_id=genesis.id,
                expected_hash=None,
                actual_hash=genesis.prev_hash,
            )

        expected_genesis_hash = compute_audit_hash(
            prev_hash=None,
            action=genesis.action,
            actor_id=genesis.actor_id,
            entity_type=genesis.entity_type,
            entity_id=genesis.entity_id,
            payload=dict(genesis.payload),
        )
        if genesis.hash != expected_genesis_hash:
            return ChainVerificationResult(
                entity_type=entity_type,
                entity_id=entity_id,
                is_valid=False,
                total_events=len(events),
                genesis_hash=genesis.hash,
                latest_hash=events[-1].hash,
                error_message=(
                    f"Cryptographic hash mismatch on genesis event {genesis.id}: "
                    f"recomputed {expected_genesis_hash}, recorded {genesis.hash}. "
                    f"Event payload or attributes were tampered with."
                ),
                corrupted_event_id=genesis.id,
                expected_hash=expected_genesis_hash,
                actual_hash=genesis.hash,
            )

        current_prev_hash = genesis.hash

        # 2. Verify subsequent events
        for index, event in enumerate(events[1:], start=1):
            if event.prev_hash != current_prev_hash:
                return ChainVerificationResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    is_valid=False,
                    total_events=len(events),
                    genesis_hash=genesis.hash,
                    latest_hash=events[-1].hash,
                    error_message=(
                        f"Broken cryptographic hash chain at event index {index} ({event.id}): "
                        f"prev_hash '{event.prev_hash}' does not match preceding event hash "
                        f"'{current_prev_hash}'. An intermediate record was omitted or modified."
                    ),
                    corrupted_event_id=event.id,
                    expected_hash=current_prev_hash,
                    actual_hash=event.prev_hash,
                )

            expected_hash = compute_audit_hash(
                prev_hash=event.prev_hash,
                action=event.action,
                actor_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                payload=dict(event.payload),
            )
            if event.hash != expected_hash:
                return ChainVerificationResult(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    is_valid=False,
                    total_events=len(events),
                    genesis_hash=genesis.hash,
                    latest_hash=events[-1].hash,
                    error_message=(
                        f"Cryptographic hash mismatch at event index {index} ({event.id}): "
                        f"recomputed {expected_hash}, recorded {event.hash}. "
                        f"Event payload or attributes were tampered with."
                    ),
                    corrupted_event_id=event.id,
                    expected_hash=expected_hash,
                    actual_hash=event.hash,
                )

            current_prev_hash = event.hash

        return ChainVerificationResult(
            entity_type=entity_type,
            entity_id=entity_id,
            is_valid=True,
            total_events=len(events),
            genesis_hash=genesis.hash,
            latest_hash=events[-1].hash,
        )

    def verify_all_chains(self, repository: AuditRepository) -> GlobalVerificationResult:
        """Inspect and verify every entity hash chain present in the audit repository."""
        distinct_entities = repository.list_distinct_entities()
        total_events = 0
        corrupted_chains: list[ChainVerificationResult] = []

        for entity_type, entity_id in distinct_entities:
            chain = repository.get_entity_chain(entity_type, entity_id)
            total_events += len(chain)
            res = self.verify_entity_chain(entity_type, entity_id, chain)
            if not res.is_valid:
                corrupted_chains.append(res)

        return GlobalVerificationResult(
            all_valid=len(corrupted_chains) == 0,
            total_entities=len(distinct_entities),
            total_events=total_events,
            corrupted_chains=corrupted_chains,
        )
