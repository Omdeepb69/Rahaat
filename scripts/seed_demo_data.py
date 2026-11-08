#!/usr/bin/env python3
"""Seed a Kerala Flood 2018 / Pune Monsoon demo scenario into the running PostgreSQL.

Idempotent: re-running does not create duplicates (uses name-based lookup
before inserting).  Writes disaster_id to demo/scenario.json for the demo
runner to consume.

Usage:
    python scripts/seed_demo_data.py [--db-url postgresql://...]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.resources import ResourceStatus, ResourceType
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.location import LandmarkModel
from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
from raahat.infrastructure.database.repositories.resource import PostgresResourceRepository
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DEMO_DISASTER_NAME = "Kerala Floods 2018 — Raahat Demo"

# Real Kerala landmarks: (external_id, name, kind, lat, lon, salience, metadata)
_LANDMARKS = [
    (
        "kl_alappuzha_boat_jetty",
        "Alappuzha Boat Jetty",
        "transport",
        9.4981,
        76.3388,
        1.0,
        {"city": "Alappuzha", "district": "Alappuzha", "state": "Kerala"},
    ),
    (
        "kl_ernakulam_general_hospital",
        "Ernakulam General Hospital",
        "medical",
        9.9816,
        76.2999,
        1.0,
        {"city": "Kochi", "district": "Ernakulam", "state": "Kerala"},
    ),
    (
        "kl_thrissur_shakthan_bus_stand",
        "Shakthan Thampuran Bus Stand",
        "transport",
        10.5276,
        76.2144,
        0.9,
        {"city": "Thrissur", "district": "Thrissur", "state": "Kerala"},
    ),
    (
        "kl_munnar_town",
        "Munnar Town Centre",
        "urban_centre",
        10.0889,
        77.0595,
        0.8,
        {"city": "Munnar", "district": "Idukki", "state": "Kerala"},
    ),
    (
        "kl_kochi_marine_drive",
        "Marine Drive Kochi",
        "urban_centre",
        9.9657,
        76.2824,
        0.95,
        {"city": "Kochi", "district": "Ernakulam", "state": "Kerala"},
    ),
    (
        "kl_pamba_river_ghat",
        "Pamba River Ghat",
        "natural",
        9.3860,
        76.5540,
        0.9,
        {"city": "Ranni", "district": "Pathanamthitta", "state": "Kerala"},
    ),
    (
        "kl_chalakudy_river_bridge",
        "Chalakudy River Bridge",
        "infrastructure",
        10.3024,
        76.3337,
        0.85,
        {"city": "Chalakudy", "district": "Thrissur", "state": "Kerala"},
    ),
]

# Rescue resources: (name, type, lat, lon, capacity)
_RESOURCES = [
    ("NDRF Boat Kerala-01", ResourceType.BOAT, 9.4975, 76.3382, 15),
    ("NDRF Boat Kerala-02", ResourceType.BOAT, 9.9820, 76.3005, 12),
    ("Army Medical Team Kochi", ResourceType.MEDICAL_TEAM, 9.9710, 76.2850, 20),
    ("SDRF Rescue Unit Thrissur", ResourceType.BOAT, 10.5280, 76.2150, 10),
    ("Flood Relief Camp Munnar", ResourceType.SHELTER, 10.0900, 77.0600, 200),
]

SYSTEM_OPERATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _get_or_create_disaster(session: Session) -> DisasterModel:
    existing = session.scalars(
        select(DisasterModel).where(DisasterModel.name == DEMO_DISASTER_NAME)
    ).first()
    if existing is not None:
        log.info("Disaster already exists: %s (%s)", existing.name, existing.id)
        return existing

    disaster = DisasterModel(
        name=DEMO_DISASTER_NAME,
        disaster_type="flood",
        status="active",
    )
    session.add(disaster)
    session.flush()
    log.info("Created disaster: %s (%s)", disaster.name, disaster.id)
    return disaster


def _seed_landmark(session: Session, external_id: str, name: str, kind: str,
                   lat: float, lon: float, salience: float, metadata: dict) -> None:
    existing = session.scalars(
        select(LandmarkModel).where(LandmarkModel.external_id == external_id)
    ).first()
    if existing is not None:
        log.info("  Landmark exists: %s", name)
        return

    lm = LandmarkModel(
        id=uuid.uuid4(),
        external_id=external_id,
        name=name,
        kind=kind,
        location=f"SRID=4326;POINT({lon} {lat})",
        salience=salience,
        metadata_=metadata,
    )
    session.add(lm)
    log.info("  Seeded landmark: %s", name)


def _seed_resources(
    session_factory: sessionmaker[Session],
    disaster_id: uuid.UUID,
    session: Session,
) -> None:
    from raahat.application.resources import ResourceService

    audit_repo = PostgresAuditRepository(session_factory)
    resource_repo = PostgresResourceRepository(session_factory)
    resource_service = ResourceService(
        resource_repo=resource_repo,
        audit_repo=audit_repo,
        session_factory=session_factory,
    )

    # Check how many resources already exist for this disaster
    from raahat.infrastructure.database.models.resource import ResourceModel

    existing_count = session.scalar(
        select(func.count()).select_from(ResourceModel).where(
            ResourceModel.disaster_id == disaster_id
        )
    )
    if existing_count and existing_count >= len(_RESOURCES):
        log.info("  Resources already seeded (%d found)", existing_count)
        return

    for name, rtype, lat, lon, capacity in _RESOURCES:
        resource_service.register_resource(
            disaster_id=disaster_id,
            resource_type=rtype,
            name=name,
            capacity=capacity,
            availability_status=ResourceStatus.AVAILABLE,
            location=PointCoordinates(latitude=lat, longitude=lon),
            registered_by=SYSTEM_OPERATOR_ID,
            session=session,
        )
        log.info("  Seeded resource: %s", name)


def seed(db_url: str) -> dict[str, Any]:
    engine = create_sync_engine(db_url)
    session_factory = get_sync_sessionmaker(engine)

    with session_factory() as session:
        disaster = _get_or_create_disaster(session)

        log.info("Seeding landmarks …")
        for lm_args in _LANDMARKS:
            _seed_landmark(session, *lm_args)

        log.info("Seeding rescue resources …")
        _seed_resources(session_factory, disaster.id, session)

        session.commit()
        disaster_id = disaster.id

    scenario = {
        "disaster_id": str(disaster_id),
        "disaster_name": DEMO_DISASTER_NAME,
        "db_url": db_url,
    }

    out_path = Path(__file__).resolve().parent.parent / "demo" / "scenario.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scenario, indent=2))
    log.info("Wrote scenario to %s", out_path)

    return scenario


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Raahat demo scenario data")
    parser.add_argument(
        "--db-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/raahat",
        ),
        help="PostgreSQL connection URL",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = seed(args.db_url)
    print(json.dumps(result, indent=2))
