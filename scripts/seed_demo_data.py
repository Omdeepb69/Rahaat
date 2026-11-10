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

from sqlalchemy import select
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
    (
        "kl_aluva_shiva_temple",
        "Aluva Shiva Temple (Mahadeva Temple)",
        "place_of_worship",
        10.1165,
        76.3533,
        1.0,
        {"city": "Aluva", "district": "Ernakulam", "state": "Kerala", "ward": "5", "near": "Aluva Bypass (NH 544)"},
    ),
    (
        "kl_aluva_bypass",
        "Aluva Bypass Junction (NH 544)",
        "infrastructure",
        10.1112,
        76.3568,
        0.95,
        {"city": "Aluva", "district": "Ernakulam", "state": "Kerala", "ward": "5"},
    ),
    (
        "kl_chalakudy_st_thomas_church",
        "St. Thomas Church Chalakudy",
        "place_of_worship",
        10.3072,
        76.3335,
        1.0,
        {
            "city": "Chalakudy",
            "district": "Thrissur",
            "state": "Kerala",
            "ward": "4",
            "aliases": ["St Thomas Church", "St Thomas Church Ward 4", "Chalakudy Forane Church"]
        },
    ),
    (
        "kl_chalakudy_railway_station",
        "Chalakudy Railway Station",
        "transport",
        10.3015,
        76.3312,
        0.95,
        {"city": "Chalakudy", "district": "Thrissur", "state": "Kerala"},
    ),
    (
        "kl_chalakudy_puthenvelikkara_road",
        "Puthenvelikkara Road (behind Chalakudy Station)",
        "infrastructure",
        10.2980,
        76.3265,
        0.9,
        {"city": "Chalakudy", "district": "Thrissur", "state": "Kerala", "near": "Chalakudy Railway Station"},
    ),
    # Goa landmarks
    (
        "ga_margao_railway_station",
        "Margao Railway Station",
        "transport",
        15.2762,
        73.9573,
        0.95,
        {"city": "Margao", "district": "South Goa", "state": "Goa"},
    ),
    (
        "ga_south_goa_district_hospital",
        "South Goa District Hospital",
        "medical",
        15.2787,
        73.9612,
        1.0,
        {"city": "Margao", "district": "South Goa", "state": "Goa"},
    ),
    (
        "ga_mobor_beach_colva",
        "Mobor Beach (Colva Coastal Area)",
        "natural",
        15.1655,
        73.9399,
        0.8,
        {"city": "Colva", "district": "South Goa", "state": "Goa"},
    ),
    (
        "ga_panaji_secretariat",
        "Goa State Secretariat Panaji",
        "government",
        15.4989,
        73.8278,
        1.0,
        {"city": "Panaji", "district": "North Goa", "state": "Goa"},
    ),
    (
        "ga_mapusa_bus_terminal",
        "Mapusa Bus Terminal",
        "transport",
        15.5944,
        73.8085,
        0.85,
        {"city": "Mapusa", "district": "North Goa", "state": "Goa"},
    ),
    (
        "ga_north_goa_district_hospital",
        "North Goa District Hospital Mapusa",
        "medical",
        15.5921,
        73.8097,
        0.9,
        {"city": "Mapusa", "district": "North Goa", "state": "Goa"},
    ),
    (
        "ga_zuari_river_bridge",
        "Zuari River Bridge (NH 66)",
        "infrastructure",
        15.3706,
        73.9980,
        0.9,
        {"city": "Cortalim", "district": "South Goa", "state": "Goa"},
    ),
    (
        "ga_mandovi_river_bridge",
        "Mandovi River Bridge Panaji",
        "infrastructure",
        15.5000,
        73.8300,
        0.9,
        {"city": "Panaji", "district": "North Goa", "state": "Goa"},
    ),
]

# Rescue resources: (name, type, lat, lon, capacity)
_RESOURCES = [
    # Kerala resources
    ("NDRF Boat Kerala-01", ResourceType.BOAT, 9.4975, 76.3382, 15),
    ("NDRF Boat Kerala-02", ResourceType.BOAT, 9.9820, 76.3005, 12),
    ("Army Medical Team Kochi", ResourceType.MEDICAL_TEAM, 9.9710, 76.2850, 20),
    ("SDRF Rescue Unit Thrissur", ResourceType.BOAT, 10.5280, 76.2150, 10),
    ("Flood Relief Camp Munnar", ResourceType.SHELTER, 10.0900, 77.0600, 200),
    # South Goa (Margao) resources
    ("NDRF Rescue Boat South Goa-01", ResourceType.BOAT, 15.2762, 73.9573, 12),
    ("SDRF Inflatable Boat Margao", ResourceType.BOAT, 15.3100, 74.0000, 8),
    ("Army Medical Team Goa (INHS Asvini Det.)", ResourceType.MEDICAL_TEAM, 15.2787, 73.9612, 15),
    ("Goa State Rescue Unit South-01", ResourceType.BOAT, 15.1655, 73.9399, 10),
    ("Flood Relief Camp Margao (SDC)", ResourceType.SHELTER, 15.2800, 73.9600, 300),
    # North Goa (Panaji) resources
    ("NDRF Rescue Boat North Goa-01", ResourceType.BOAT, 15.4989, 73.8278, 12),
    ("Coast Guard Inflatable Unit Panaji", ResourceType.BOAT, 15.5000, 73.8300, 8),
    ("Army Medical Team North Goa", ResourceType.MEDICAL_TEAM, 15.5921, 73.8097, 20),
    ("Goa State Rescue Unit North-01", ResourceType.BOAT, 15.5944, 73.8085, 10),
    ("Flood Relief Camp Mapusa (SDC)", ResourceType.SHELTER, 15.5900, 73.8100, 250),
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

    # Insert only resources that do not already exist by name for this disaster.
    from raahat.infrastructure.database.models.resource import ResourceModel

    existing_names: set[str] = set(
        session.scalars(
            select(ResourceModel.name).where(ResourceModel.disaster_id == disaster_id)
        ).all()
    )

    added = 0
    for name, rtype, lat, lon, capacity in _RESOURCES:
        if name in existing_names:
            log.info("  Resource already exists: %s", name)
            continue
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
        added += 1

    if added == 0:
        log.info("  All resources already present — nothing to seed.")


def _seed_demo_incidents(session: Session, disaster_id: uuid.UUID) -> None:
    """Seed the Malayalam live call demo incident (Manju Nair, Chalakudy)."""
    from raahat.infrastructure.database.models.incident import IncidentModel
    from raahat.infrastructure.database.models.location import LocationHypothesisModel

    existing_inc = session.scalars(
        select(IncidentModel).where(
            IncidentModel.disaster_id == disaster_id,
            IncidentModel.severity_facts["caller_name"].astext == "Manju Nair",
        )
    ).first()

    if existing_inc is not None:
        log.info("  Incident for Manju Nair already exists: %s", existing_inc.id)
        return

    inc_id = uuid.uuid4()
    incident = IncidentModel(
        id=inc_id,
        disaster_id=disaster_id,
        status="verified",
        operational_priority="critical_review",
        severity_facts={
            "caller_name": "Manju Nair",
            "caller_phone": "+91 94471 23456",
            "people_count": 3,
            "medical_needs": ["diabetic_insulin_deprived_since_0800"],
            "vulnerabilities": ["elderly_unambulatory", "child_7yo"],
            "floor_level": "second_floor",
            "water_level": "second_floor_window_sill_rising",
            "landmark": "St. Thomas Church, Ward 4, Chalakudy",
            "rescue_assigned": "SDRF Rescue Unit Thrissur",
            "signal": "Yellow dupatta in window",
            "language": "ml-IN",
        },
    )
    session.add(incident)

    hyp = LocationHypothesisModel(
        id=uuid.uuid4(),
        incident_id=inc_id,
        location="SRID=4326;POINT(76.3335 10.3072)",
        candidate_label="St. Thomas Church, Ward 4, Chalakudy",
        probability=1.0,
        uncertainty_radius_m=150.0,
        verification_status="confirmed",
    )
    session.add(hyp)
    log.info("  Seeded P0 live call incident for Manju Nair at Chalakudy (lat=10.3072, lon=76.3335)")


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

        log.info("Seeding demo incidents …")
        _seed_demo_incidents(session, disaster.id)

        session.commit()
        disaster_id = disaster.id

    scenario = {
        "disaster_id": str(disaster_id),
        "disaster_name": DEMO_DISASTER_NAME,
        "db_url": db_url,
    }

    try:
        out_path = Path(__file__).resolve().parent.parent / "demo" / "scenario.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(scenario, indent=2))
        log.info("Wrote scenario to %s", out_path)
    except Exception as exc:
        log.warning("Could not persist scenario.json to demo dir: %s", exc)
        try:
            tmp_path = Path("/tmp/scenario.json")
            tmp_path.write_text(json.dumps(scenario, indent=2))
        except Exception:
            pass

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
