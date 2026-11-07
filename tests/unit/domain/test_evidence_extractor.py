"""Unit tests for StructuredEvidenceExtractor decomposing reports into atomic claims with spans."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from raahat.domain.evidence.extractor import StructuredEvidenceExtractor
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import ProcessingStatus, SourceType


def _make_report(payload: dict, source_type: SourceType = SourceType.WEB) -> Report:
    return Report(
        id=uuid.uuid4(),
        disaster_id=uuid.uuid4(),
        source_type=source_type,
        raw_payload=payload,
        received_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        client_created_at=datetime(2026, 8, 15, 11, 55, 0, tzinfo=timezone.utc),
        idempotency_key=f"test-{uuid.uuid4().hex}",
        processing_status=ProcessingStatus.PENDING,
    )


def test_extract_web_sos_payload() -> None:
    extractor = StructuredEvidenceExtractor()
    report = _make_report(
        {
            "location_text": "Shiv Mandir, Sector 3",
            "people_count": 4,
            "medical_emergency": True,
            "water_level": "rising rapidly",
            "water_depth_cm": 120,
            "needs": ["rescue", "drinking_water"],
            "hazard": "power line submerged",
        },
        source_type=SourceType.WEB,
    )

    items = extractor.extract(report)
    assert len(items) >= 6

    # Verify all items link back to this report
    for item in items:
        assert item.report_id == report.id
        assert item.observed_at == report.client_created_at
        assert len(item.spans) >= 1
        assert "source_field" in item.spans[0].reference

    # Verify specific decomposed claims
    item_map = {item.attribute: item for item in items}
    assert item_map["people_count"].value == 4
    assert item_map["people_count"].subject_type == "household"

    assert item_map["water_level_trend"].value == "rising"
    assert item_map["water_level_trend"].subject_type == "environment"

    assert item_map["water_depth_cm"].value == 120.0

    assert item_map["medical_emergency"].value is True

    assert item_map["landmark_mention"].value == "Shiv Mandir, Sector 3"

    assert item_map["hazard"].value == "power line submerged"

    # Needs
    need_items = [it for it in items if it.attribute == "relief_need"]
    assert len(need_items) == 2
    assert {it.value for it in need_items} == {"rescue", "drinking_water"}


def test_extract_volunteer_offline_payload() -> None:
    extractor = StructuredEvidenceExtractor()
    report = _make_report(
        {
            "location": "Panchayat Ghar",
            "trapped_count": 5,
            "trapped_status": True,
            "water_level_trend": "receded",
            "needs": ["food"],
        },
        source_type=SourceType.VOLUNTEER,
    )

    items = extractor.extract(report)
    item_map = {item.attribute: item for item in items}

    assert item_map["people_count"].value == 5
    assert item_map["trapped_status"].value is True
    assert item_map["water_level_trend"].value == "receded"
    assert item_map["landmark_mention"].value == "Panchayat Ghar"


def test_extract_nested_sms_payload() -> None:
    extractor = StructuredEvidenceExtractor()
    report = _make_report(
        {
            "sender": "+919876543210",
            "text": "Water receded to knee level, 2 people safe",
            "parsed": {
                "water_level_trend": "receded",
                "headcount": "2",
                "trapped": False,
            },
        },
        source_type=SourceType.SMS,
    )

    items = extractor.extract(report)
    item_map = {item.attribute: item for item in items}

    assert item_map["water_level_trend"].value == "receded"
    assert item_map["people_count"].value == 2
    assert item_map["trapped_status"].value is False


def test_extract_ivr_with_audio_turns() -> None:
    extractor = StructuredEvidenceExtractor()
    report = _make_report(
        {
            "transcript": "paani bohot badh raha hai 6 log phas gaye hain",
            "extracted": {
                "headcount": 6,
                "water_level_trend": "rising",
                "trapped": True,
            },
            "turns": [
                {
                    "turn": 1,
                    "speaker": "caller",
                    "text": "paani bohot badh raha hai",
                    "start_ms": 1200,
                    "end_ms": 3400,
                },
                {
                    "turn": 2,
                    "speaker": "caller",
                    "text": "6 log phas gaye hain",
                    "start_ms": 4000,
                    "end_ms": 6100,
                },
            ],
        },
        source_type=SourceType.IVR,
    )

    items = extractor.extract(report)
    item_map = {item.attribute: item for item in items}

    # Headcount should capture turn 2 span
    hc_span = item_map["people_count"].spans[0]
    assert hc_span.reference.get("turn") == 2
    assert hc_span.start_ms == 4000
    assert hc_span.end_ms == 6100
    assert "6 log" in (hc_span.text or "")

    # Water level should capture turn 1 span
    wl_span = item_map["water_level_trend"].spans[0]
    assert wl_span.reference.get("turn") == 1
    assert wl_span.start_ms == 1200
    assert wl_span.end_ms == 3400
    assert "badh raha" in (wl_span.text or "")


def test_hindi_trend_normalization() -> None:
    extractor = StructuredEvidenceExtractor()
    report1 = _make_report({"flood_trend": "paani badh raha hai"})
    items1 = extractor.extract(report1)
    assert items1[0].value == "rising"

    report2 = _make_report({"water_level": "ghat raha hai"})
    items2 = extractor.extract(report2)
    assert items2[0].value == "falling"

    report3 = _make_report({"water_level": "paani utar gaya"})
    items3 = extractor.extract(report3)
    assert items3[0].value == "receded"

    report4 = _make_report({"water_level": "ruka hua hai"})
    items4 = extractor.extract(report4)
    assert items4[0].value == "stable"

