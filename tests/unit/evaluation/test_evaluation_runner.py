"""Unit tests for RaahatBench evaluation runner, ablation configurations, and metrics."""
from __future__ import annotations

import tempfile

import pytest

from evaluation.baselines.pipelines import (
    ConfigurationA,
    ConfigurationB,
    ConfigurationC,
    ConfigurationD,
    ConfigurationE,
)
from evaluation.generator import RaahatBenchGenerator
from evaluation.metrics import (
    calculate_bcubed_metrics,
    calculate_ece,
    calculate_false_escalation_rate,
    calculate_false_merge_rate,
    calculate_high_severity_recall,
    calculate_mae_meters,
    calculate_missed_duplicate_rate,
    calculate_top_k_accuracy,
    calculate_top_k_recall,
    calculate_under_triage_rate,
    calculate_unknown_preservation_rate,
    paired_bootstrap_ci,
)
from evaluation.models import RaahatBenchDataset
from evaluation.runner import RaahatBenchRunner
from raahat.domain.shared.coordinates import PointCoordinates


@pytest.fixture
def sample_dataset() -> RaahatBenchDataset:
    gen = RaahatBenchGenerator(seed=42)
    full_ds = gen.generate()
    # Use first 50 reports for fast, deterministic unit test evaluation
    return RaahatBenchDataset(
        benchmark_id="test-bench-subset",
        version="1.0.0",
        created_at=full_ds.created_at,
        seed=42,
        disaster_id=full_ds.disaster_id,
        num_reports=50,
        num_incidents=len(full_ds.incidents),
        distribution_summary=full_ds.distribution_summary,
        incidents=full_ds.incidents,
        reports=full_ds.reports[:50],
    )


def test_spatial_metrics_calculations() -> None:
    p1 = PointCoordinates(latitude=10.0, longitude=76.0)
    p2 = PointCoordinates(latitude=10.001, longitude=76.0)  # ~111m away
    p3 = PointCoordinates(latitude=10.05, longitude=76.0)   # ~5.5km away

    # MAE
    mae = calculate_mae_meters([p2], [p1])
    assert 100.0 < mae < 120.0

    # Top-k accuracy
    acc = calculate_top_k_accuracy([[p2]], [p1], threshold_meters=500.0, k=1)
    assert acc == 1.0

    acc_fail = calculate_top_k_accuracy([[p3]], [p1], threshold_meters=500.0, k=1)
    assert acc_fail == 0.0

    # Top-k recall
    rec = calculate_top_k_recall([[p3, p2]], [p1], threshold_meters=500.0, k=2)
    assert rec == 1.0

    # ECE
    ece = calculate_ece([0.9, 0.2], [True, False])
    assert 0.0 <= ece <= 1.0


def test_entity_resolution_metrics_calculations() -> None:
    # 3 reports: report 0 and 1 belong to incA, report 2 belongs to incB
    true_clusters = ["incA", "incA", "incB"]

    # Perfect clustering
    pred_perfect = ["incA", "incA", "incB"]
    p, r, f1 = calculate_bcubed_metrics(pred_perfect, true_clusters)
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0
    assert calculate_false_merge_rate(pred_perfect, true_clusters) == 0.0
    assert calculate_missed_duplicate_rate(pred_perfect, true_clusters) == 0.0

    # False merge: all merged into single cluster
    pred_all_merged = ["cluster1", "cluster1", "cluster1"]
    fm_rate = calculate_false_merge_rate(pred_all_merged, true_clusters)
    # Total merged pairs: 3. Correct: (0,1). False: (0,2) and (1,2) -> 2/3 = 0.6667
    assert 0.66 <= fm_rate <= 0.67

    # Missed duplicate: all separated into singleton clusters
    pred_singletons = ["c0", "c1", "c2"]
    md_rate = calculate_missed_duplicate_rate(pred_singletons, true_clusters)
    # True duplicate pair: (0,1). Separated -> missed rate = 1.0
    assert md_rate == 1.0


def test_safety_triage_metrics_calculations() -> None:
    true_sevs = ["critical", "urgent", "standard", "low"]
    preds = ["critical", "standard", "standard", "urgent"]

    # High severity recall: true high = [0, 1] (critical, urgent)
    # Preds for them = [critical, standard] -> 1/2 = 0.5
    high_rec = calculate_high_severity_recall(preds, true_sevs)
    assert high_rec == 0.5

    # Under-triage: true high predicted as standard/low -> report 1 = standard -> 1/2 = 0.5
    under_rate = calculate_under_triage_rate(preds, true_sevs)
    assert under_rate == 0.5

    # False escalation: true low = [2, 3] (standard, low)
    # Pred for report 3 = urgent -> 1/2 = 0.5
    false_esc = calculate_false_escalation_rate(preds, true_sevs)
    assert false_esc == 0.5

    # Unknown preservation
    preserved = [["trapped_status"], ["medical_need"]]
    missing = [["trapped_status", "people_count"], ["medical_need"]]
    rate = calculate_unknown_preservation_rate(preserved, missing)
    # 2 preserved out of 3 missing -> 2/3 = 0.6667
    assert 0.66 <= rate <= 0.67


def test_paired_bootstrap_ci() -> None:
    # Identical predictions should have delta = 0 and not be significant
    preds_a = [1.0, 2.0, 3.0, 4.0, 5.0]
    preds_b = [1.0, 2.0, 3.0, 4.0, 5.0]
    gt = [1.0, 2.0, 3.0, 4.0, 5.0]

    res = paired_bootstrap_ci(
        metric_fn=lambda p, y: sum(abs(a - b) for a, b in zip(p, y)) / len(y),
        predictions_a=preds_a,
        predictions_b=preds_b,
        ground_truths=gt,
        n_bootstraps=100,
        seed=42,
    )
    assert res.delta_mean == 0.0
    assert res.is_significant is False

    # Substantially different predictions should be significant
    preds_bad = [10.0, 20.0, 30.0, 40.0, 50.0]
    res_diff = paired_bootstrap_ci(
        metric_fn=lambda p, y: sum(abs(a - b) for a, b in zip(p, y)) / len(y),
        predictions_a=preds_bad,
        predictions_b=preds_a,
        ground_truths=gt,
        n_bootstraps=100,
        seed=42,
    )
    assert res_diff.delta_mean < -20.0
    assert res_diff.is_significant is True


def test_ablation_pipeline_progression(sample_dataset: RaahatBenchDataset) -> None:
    """Verify that moving from Config A to E systematically addresses each failure mode."""
    cfg_a = ConfigurationA()
    cfg_b = ConfigurationB()
    cfg_c = ConfigurationC()
    cfg_d = ConfigurationD()
    cfg_e = ConfigurationE()

    reports = sample_dataset.reports

    res_a, _ = RaahatBenchRunner().evaluate_configuration(cfg_a, "A", reports)
    res_b, _ = RaahatBenchRunner().evaluate_configuration(cfg_b, "B", reports)
    res_c, _ = RaahatBenchRunner().evaluate_configuration(cfg_c, "C", reports)
    res_d, _ = RaahatBenchRunner().evaluate_configuration(cfg_d, "D", reports)
    res_e, _ = RaahatBenchRunner().evaluate_configuration(cfg_e, "E", reports)

    # 1. Geospatial upgrade: Config B reduces MAE compared to Config A
    assert res_b.mae_meters < res_a.mae_meters
    assert res_b.top3_recall >= res_a.top3_recall

    # 2. Evidence graph upgrade: Config C eliminates false merges
    assert res_c.false_merge_rate < res_b.false_merge_rate
    assert res_c.bcubed_f1 > res_b.bcubed_f1

    # 3. Safety policy upgrade: Config D eliminates under-triage
    assert res_d.under_triage_rate < res_c.under_triage_rate
    assert res_d.high_severity_recall >= 0.99

    # 4. Full Raahat: Config E achieves 100% offline ingestion
    assert res_e.ingestion_success_rate == 1.0


def test_runner_report_generation_and_saving(sample_dataset: RaahatBenchDataset) -> None:
    runner = RaahatBenchRunner(n_bootstrap_iterations=50)
    report = runner.run_all(sample_dataset)

    assert report.benchmark_id == sample_dataset.benchmark_id
    assert len(report.results) == 5
    assert "mae_meters" in report.bootstrap_differences_e_vs_a
    assert "RQ1_active_clarification_improves_geospatial_accuracy" in report.research_questions

    # Render markdown
    md_text = runner.render_markdown_report(report)
    assert "# RaahatBench Evaluation Report" in md_text
    assert "Top-1 Location Accuracy" in md_text
    assert "Engineering Acceptance Gates" in md_text

    # Save to disk
    with tempfile.TemporaryDirectory() as tmp_dir:
        json_path, md_path = runner.save_reports(report, tmp_dir)
        assert json_path.exists()
        assert md_path.exists()
        assert json_path.stat().st_size > 0
        assert md_path.stat().st_size > 0
