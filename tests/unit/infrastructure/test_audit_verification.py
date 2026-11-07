"""Unit tests for tamper-evident audit logging, hash chaining, and cryptographic verification."""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from raahat.infrastructure.audit import (
    AuditService,
    AuditVerifier,
    InMemoryAuditRepository,
    compute_audit_hash,
)
from raahat.infrastructure.database.models.audit import AuditEventModel


class TestComputeAuditHash:
    def test_hash_is_deterministic(self) -> None:
        entity_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        payload = {"incident_id": "123", "priority": "urgent", "count": 5}

        hash1 = compute_audit_hash(
            prev_hash=None,
            action="incident.verified",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=entity_id,
            payload=payload,
        )
        # Differently-ordered dictionary keys must produce identical hash
        payload_reordered = {"count": 5, "priority": "urgent", "incident_id": "123"}
        hash2 = compute_audit_hash(
            prev_hash=None,
            action="incident.verified",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=entity_id,
            payload=payload_reordered,
        )

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string

    def test_hash_differs_when_payload_changes(self) -> None:
        entity_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        hash1 = compute_audit_hash(
            prev_hash="abc",
            action="incident.verified",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=entity_id,
            payload={"status": "verified"},
        )
        hash2 = compute_audit_hash(
            prev_hash="abc",
            action="incident.verified",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=entity_id,
            payload={"status": "in_progress"},
        )

        assert hash1 != hash2

    def test_hash_differs_when_prev_hash_changes(self) -> None:
        entity_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        hash1 = compute_audit_hash(
            prev_hash="hash_a",
            action="resource.status_updated",
            actor_id=actor_id,
            entity_type="resource",
            entity_id=entity_id,
            payload={"status": "assigned"},
        )
        hash2 = compute_audit_hash(
            prev_hash="hash_b",
            action="resource.status_updated",
            actor_id=actor_id,
            entity_type="resource",
            entity_id=entity_id,
            payload={"status": "assigned"},
        )

        assert hash1 != hash2


class TestAuditVerifier:
    @pytest.fixture()
    def repo(self) -> InMemoryAuditRepository:
        return InMemoryAuditRepository()

    @pytest.fixture()
    def verifier(self) -> AuditVerifier:
        return AuditVerifier()

    def test_verify_empty_chain_is_valid(self, verifier: AuditVerifier) -> None:
        entity_id = uuid.uuid4()
        result = verifier.verify_entity_chain("incident", entity_id, [])
        assert result.is_valid is True
        assert result.total_events == 0
        assert result.genesis_hash is None
        assert result.latest_hash is None

    def test_verify_valid_single_event_chain(
        self, repo: InMemoryAuditRepository, verifier: AuditVerifier
    ) -> None:
        entity_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        repo.record_event(
            action="incident.created",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=entity_id,
            payload={"operational_priority": "urgent"},
        )

        chain = repo.get_entity_chain("incident", entity_id)
        assert len(chain) == 1

        result = verifier.verify_entity_chain("incident", entity_id, chain)
        assert result.is_valid is True
        assert result.total_events == 1
        assert result.genesis_hash == chain[0].hash
        assert result.latest_hash == chain[0].hash
        assert result.error_message is None

    def test_verify_valid_multi_event_chain(
        self, repo: InMemoryAuditRepository, verifier: AuditVerifier
    ) -> None:
        entity_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        actions: list[tuple[str, dict[str, Any]]] = [
            ("assignment.proposed", {"notes": "Proposed boat"}),
            ("assignment.approved", {"notes": "Approved by supervisor"}),
            ("assignment.en_route", {"eta_minutes": 15}),
            ("assignment.on_scene", {"arrival_time": "12:30"}),
            ("assignment.rescued", {"victims_rescued": 4}),
        ]
        for act, pl in actions:
            repo.record_event(
                action=act,
                actor_id=actor_id,
                entity_type="assignment",
                entity_id=entity_id,
                payload=pl,
            )

        chain = repo.get_entity_chain("assignment", entity_id)
        assert len(chain) == 5

        result = verifier.verify_entity_chain("assignment", entity_id, chain)
        assert result.is_valid is True
        assert result.total_events == 5
        assert result.genesis_hash == chain[0].hash
        assert result.latest_hash == chain[-1].hash
        assert result.error_message is None

    def test_detect_tampered_payload_in_genesis_event(
        self, repo: InMemoryAuditRepository, verifier: AuditVerifier
    ) -> None:
        entity_id = uuid.uuid4()
        repo.record_event(
            action="incident.created",
            actor_id=uuid.uuid4(),
            entity_type="incident",
            entity_id=entity_id,
            payload={"operational_priority": "urgent"},
        )
        chain = repo.get_entity_chain("incident", entity_id)

        # Tamper with the genesis event payload
        tampered_event = AuditEventModel(
            id=chain[0].id,
            action=chain[0].action,
            actor_id=chain[0].actor_id,
            entity_type=chain[0].entity_type,
            entity_id=chain[0].entity_id,
            prev_hash=chain[0].prev_hash,
            hash=chain[0].hash,  # unchanged recorded hash
            payload={"operational_priority": "low"},  # tampered!
            created_at=chain[0].created_at,
        )

        result = verifier.verify_entity_chain("incident", entity_id, [tampered_event])
        assert result.is_valid is False
        assert result.corrupted_event_id == chain[0].id
        assert result.error_message is not None
        assert "mismatch" in result.error_message.lower()

    def test_detect_tampered_payload_in_middle_event(
        self, repo: InMemoryAuditRepository, verifier: AuditVerifier
    ) -> None:
        entity_id = uuid.uuid4()
        actor = uuid.uuid4()

        for i in range(4):
            repo.record_event(
                action=f"step_{i}",
                actor_id=actor,
                entity_type="process",
                entity_id=entity_id,
                payload={"index": i},
            )

        chain = repo.get_entity_chain("process", entity_id)

        # Clone and tamper with event index 2
        tampered_chain = list(chain)
        ev2 = tampered_chain[2]
        tampered_chain[2] = AuditEventModel(
            id=ev2.id,
            action=ev2.action,
            actor_id=ev2.actor_id,
            entity_type=ev2.entity_type,
            entity_id=ev2.entity_id,
            prev_hash=ev2.prev_hash,
            hash=ev2.hash,
            payload={"index": 999},  # tampered
            created_at=ev2.created_at,
        )

        result = verifier.verify_entity_chain("process", entity_id, tampered_chain)
        assert result.is_valid is False
        assert result.corrupted_event_id == ev2.id
        assert result.error_message is not None
        assert "event index 2" in result.error_message

    def test_detect_omitted_middle_event(
        self, repo: InMemoryAuditRepository, verifier: AuditVerifier
    ) -> None:
        entity_id = uuid.uuid4()
        actor = uuid.uuid4()

        for i in range(3):
            repo.record_event(
                action=f"step_{i}",
                actor_id=actor,
                entity_type="process",
                entity_id=entity_id,
                payload={"index": i},
            )

        chain = repo.get_entity_chain("process", entity_id)
        # Omit event index 1 (middle event)
        broken_chain = [chain[0], chain[2]]

        result = verifier.verify_entity_chain("process", entity_id, broken_chain)
        assert result.is_valid is False
        assert result.corrupted_event_id == chain[2].id
        assert result.error_message is not None
        assert "broken cryptographic hash chain" in result.error_message.lower()

    def test_detect_forged_genesis_with_non_null_prev_hash(
        self, verifier: AuditVerifier
    ) -> None:
        entity_id = uuid.uuid4()
        forged_genesis = AuditEventModel(
            id=uuid.uuid4(),
            action="incident.verified",
            actor_id=uuid.uuid4(),
            entity_type="incident",
            entity_id=entity_id,
            prev_hash="orphaned_hash_abc",  # Should be None for genesis!
            hash="some_hash",
            payload={},
        )
        result = verifier.verify_entity_chain("incident", entity_id, [forged_genesis])
        assert result.is_valid is False
        assert result.error_message is not None
        assert "non-null prev_hash" in result.error_message.lower()

    def test_verify_all_chains_across_entities(
        self, repo: InMemoryAuditRepository, verifier: AuditVerifier
    ) -> None:
        # Entity 1: 3 valid events
        e1 = uuid.uuid4()
        for i in range(3):
            repo.record_event("action_a", None, "entity_a", e1, {"step": i})

        # Entity 2: 2 valid events
        e2 = uuid.uuid4()
        for i in range(2):
            repo.record_event("action_b", None, "entity_b", e2, {"step": i})

        global_res = verifier.verify_all_chains(repo)
        assert global_res.all_valid is True
        assert global_res.total_entities == 2
        assert global_res.total_events == 5
        assert len(global_res.corrupted_chains) == 0

        # Now corrupt Entity 1's last event in repository
        ev = repo.events[2]
        ev_corrupted = AuditEventModel(
            id=ev.id,
            action=ev.action,
            actor_id=ev.actor_id,
            entity_type=ev.entity_type,
            entity_id=ev.entity_id,
            prev_hash=ev.prev_hash,
            hash="forged_hash",
            payload=ev.payload,
            created_at=ev.created_at,
        )
        repo.events[2] = ev_corrupted

        global_res_corrupted = verifier.verify_all_chains(repo)
        assert global_res_corrupted.all_valid is False
        assert len(global_res_corrupted.corrupted_chains) == 1
        assert global_res_corrupted.corrupted_chains[0].entity_id == e1


class TestAuditService:
    def test_query_events_with_filters_and_pagination(self) -> None:
        repo = InMemoryAuditRepository()
        service = AuditService(audit_repo=repo)

        actor1 = uuid.uuid4()
        actor2 = uuid.uuid4()
        e_id1 = uuid.uuid4()
        e_id2 = uuid.uuid4()

        service.record_event("action.1", actor1, "type_a", e_id1, {"v": 1})
        service.record_event("action.2", actor2, "type_a", e_id1, {"v": 2})
        service.record_event("action.1", actor1, "type_b", e_id2, {"v": 3})

        # Query all
        items, total = service.query_events()
        assert total == 3
        assert len(items) == 3

        # Filter by entity_type
        items_a, total_a = service.query_events(entity_type="type_a")
        assert total_a == 2
        assert len(items_a) == 2

        # Filter by actor_id
        items_act1, total_act1 = service.query_events(actor_id=actor1)
        assert total_act1 == 2

        # Pagination
        items_paged, total_paged = service.query_events(limit=1, offset=1)
        assert total_paged == 3
        assert len(items_paged) == 1

    def test_get_event_by_id(self) -> None:
        repo = InMemoryAuditRepository()
        service = AuditService(audit_repo=repo)

        created = service.record_event("action", None, "type", uuid.uuid4(), {})
        fetched = service.get_event(created.id)
        assert fetched is not None
        assert fetched.id == created.id

        assert service.get_event(uuid.uuid4()) is None
