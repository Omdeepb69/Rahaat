"""Unit tests for RaahatBench benchmark dataset generator and ground truth schema (RAAHAT_SPEC §9.1)."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from evaluation.generator import BENCHMARK_DISASTER_ID, RaahatBenchGenerator
from evaluation.models import GroundTruthIncident, RaahatBenchDataset
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType


@pytest.fixture
def benchmark_dataset() -> RaahatBenchDataset:
    generator = RaahatBenchGenerator(seed=42)
    return generator.generate()


def test_generator_determinism() -> None:
    """Same seed must produce identical reports, incidents, and IDs."""
    gen1 = RaahatBenchGenerator(seed=42)
    gen2 = RaahatBenchGenerator(seed=42)

    ds1 = gen1.generate()
    ds2 = gen2.generate()

    assert ds1.num_reports == ds2.num_reports == 1000
    assert ds1.num_incidents == ds2.num_incidents == 100

    # Verify first 10 reports and incidents are identical
    for r1, r2 in zip(ds1.reports[:10], ds2.reports[:10]):
        assert r1.report_id == r2.report_id
        assert r1.raw_text == r2.raw_text
        assert r1.ground_truth_incident_id == r2.ground_truth_incident_id
        assert r1.source_type == r2.source_type

    for inc1, inc2 in zip(ds1.incidents[:10], ds2.incidents[:10]):
        assert inc1.incident_id == inc2.incident_id
        assert inc1.latitude == inc2.latitude
        assert inc1.longitude == inc2.longitude
        assert inc1.total_people == inc2.total_people


def test_generator_different_seed_produces_variance() -> None:
    """Different seed must produce different report IDs and incident details."""
    gen1 = RaahatBenchGenerator(seed=42)
    gen2 = RaahatBenchGenerator(seed=999)

    ds1 = gen1.generate()
    ds2 = gen2.generate()

    assert ds1.reports[0].report_id != ds2.reports[0].report_id
    assert ds1.incidents[0].incident_id != ds2.incidents[0].incident_id


def test_specification_distribution_targets(benchmark_dataset: RaahatBenchDataset) -> None:
    """Verify exact dataset distributions align with RAAHAT_SPEC §9.1 targets."""
    summary = benchmark_dataset.distribution_summary
    assert summary["total_reports"] == 1000
    assert summary["total_ground_truth_incidents"] == 100

    # Relationship breakdown
    rels = summary["relationship_distribution"]
    assert rels["direct"]["percentage"] == 35.0
    assert rels["relative"]["percentage"] == 25.0
    assert rels["volunteer"]["percentage"] == 20.0
    assert rels["responder"]["percentage"] == 20.0

    # Anomaly breakdown
    anomalies = summary["anomalies"]
    # 25-35% duplicate or overlapping reports
    assert 25.0 <= anomalies["duplicate_reports"]["percentage"] <= 35.0
    # 10-15% contradictory reports
    assert 10.0 <= anomalies["contradictory_reports"]["percentage"] <= 15.0
    # 20-30% ambiguous locations
    assert 20.0 <= anomalies["ambiguous_locations"]["percentage"] <= 30.0
    # 20-30% missing critical fields
    assert 20.0 <= anomalies["missing_critical_fields"]["percentage"] <= 30.0


def test_linguistic_coverage_and_code_switching(benchmark_dataset: RaahatBenchDataset) -> None:
    """Verify presence of Hindi, English, Malayalam, and Hindi-English code-switching."""
    lang_summary = benchmark_dataset.distribution_summary["language_mode_distribution"]

    assert lang_summary["code_switched"]["count"] > 350
    assert lang_summary["english"]["count"] > 150
    assert lang_summary["hindi"]["count"] > 100
    assert lang_summary["malayalam"]["count"] > 100

    # Check actual text samples for linguistic markers
    code_switched_samples = [r.raw_text for r in benchmark_dataset.reports if r.language_mode == "code_switched"]
    assert any("phanse hain" in text or "paas" in text for text in code_switched_samples)
    assert any("urgent" in text.lower() or "rescue" in text.lower() for text in code_switched_samples)

    malayalam_samples = [r.raw_text for r in benchmark_dataset.reports if r.language_mode == "malayalam"]
    assert any("vellam" in text.lower() or "rakshikkanam" in text.lower() for text in malayalam_samples)


def test_every_report_references_valid_ground_truth(benchmark_dataset: RaahatBenchDataset) -> None:
    """Critical benchmark integrity: every report must link to an existing ground-truth incident."""
    incident_map: dict[uuid.UUID, GroundTruthIncident] = {
        inc.incident_id: inc for inc in benchmark_dataset.incidents
    }
    assert len(incident_map) == 100

    for report in benchmark_dataset.reports:
        assert report.ground_truth_incident_id in incident_map
        inc = incident_map[report.ground_truth_incident_id]

        # Valid coordinates
        assert 8.0 <= inc.latitude <= 13.0  # South India / Kerala bounds
        assert 74.0 <= inc.longitude <= 78.0

        # Ground truth dictionary must contain required evaluation fields
        gt = report.ground_truth
        assert gt["incident_id"] == str(inc.incident_id)
        assert gt["true_severity"] in ("critical", "urgent", "standard", "low")
        assert gt["true_people"] >= 1
        assert gt["true_trapped"] in ("trapped_roof", "trapped_upper_floor", "ground_submerged", "none")


def test_offline_device_sequences_monotonicity(benchmark_dataset: RaahatBenchDataset) -> None:
    """Offline volunteer reports must have monotonic device sequence numbers per device."""
    volunteer_reports = [r for r in benchmark_dataset.reports if r.is_offline_sync]
    assert len(volunteer_reports) == 200

    device_sequences: dict[uuid.UUID, list[int]] = {}
    for r in volunteer_reports:
        assert r.device_id is not None
        assert r.device_sequence is not None
        device_sequences.setdefault(r.device_id, []).append(r.device_sequence)

    assert len(device_sequences) == 5
    for dev_id, seqs in device_sequences.items():
        # Sequences must be strictly increasing: 1, 2, 3, ...
        assert seqs == list(range(1, len(seqs) + 1))


def test_to_submission_contract(benchmark_dataset: RaahatBenchDataset) -> None:
    """Every benchmark report must cleanly convert into a valid domain ReportSubmission."""
    for report in benchmark_dataset.reports[:50]:
        sub = report.to_submission()
        assert isinstance(sub, ReportSubmission)
        assert sub.disaster_id == BENCHMARK_DISASTER_ID
        assert sub.source_type in (
            SourceType.IVR,
            SourceType.SMS,
            SourceType.WEB,
            SourceType.VOLUNTEER,
            SourceType.RADIO,
        )
        assert sub.idempotency_key == f"bench:{report.report_id}"
        assert "text" in sub.raw_payload


def test_save_and_load_round_trip(benchmark_dataset: RaahatBenchDataset) -> None:
    """Verify dataset serialization and deserialization preserves all fields and records."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        files = RaahatBenchGenerator.save_dataset(benchmark_dataset, tmp_dir)

        assert Path(files["dataset"]).exists()
        assert Path(files["incidents"]).exists()
        assert Path(files["metadata"]).exists()

        loaded = RaahatBenchGenerator.load_dataset(files["dataset"])

        assert loaded.benchmark_id == benchmark_dataset.benchmark_id
        assert loaded.num_reports == 1000
        assert loaded.num_incidents == 100
        assert loaded.reports[0].report_id == benchmark_dataset.reports[0].report_id
        assert loaded.incidents[0].incident_id == benchmark_dataset.incidents[0].incident_id


def test_frozen_datasets_exist_in_repository() -> None:
    """Verify that frozen dataset files in evaluation/datasets/ exist and are loadable."""
    datasets_dir = Path("evaluation/datasets")
    dataset_file = datasets_dir / "raahat_bench_1000.json"
    incidents_file = datasets_dir / "ground_truth_incidents.json"
    metadata_file = datasets_dir / "metadata.json"

    assert dataset_file.exists(), "evaluation/datasets/raahat_bench_1000.json is missing!"
    assert incidents_file.exists(), "evaluation/datasets/ground_truth_incidents.json is missing!"
    assert metadata_file.exists(), "evaluation/datasets/metadata.json is missing!"

    loaded = RaahatBenchGenerator.load_dataset(dataset_file)
    assert loaded.num_reports == 1000
    assert loaded.num_incidents == 100
