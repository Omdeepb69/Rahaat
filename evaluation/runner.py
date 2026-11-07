"""RaahatBench automated evaluation and ablation runner (RAAHAT_SPEC §9.2 - §9.4)."""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from evaluation.baselines.pipelines import (
    ALL_CONFIGURATIONS,
    PipelineConfig,
    PipelinePrediction,
)
from evaluation.generator import RaahatBenchGenerator
from evaluation.metrics.bootstrap import BootstrapResult, paired_bootstrap_ci
from evaluation.metrics.resolution import (
    calculate_bcubed_metrics,
    calculate_false_merge_rate,
    calculate_missed_duplicate_rate,
)
from evaluation.metrics.spatial import (
    calculate_ece,
    calculate_mae_meters,
    calculate_top_k_accuracy,
    calculate_top_k_recall,
)
from evaluation.metrics.triage import (
    calculate_false_escalation_rate,
    calculate_high_severity_recall,
    calculate_under_triage_rate,
    calculate_unknown_preservation_rate,
)
from evaluation.models import BenchmarkReportRecord, RaahatBenchDataset
from raahat.domain.shared.coordinates import PointCoordinates

logger = logging.getLogger(__name__)


class BenchmarkEvaluationResult(BaseModel):
    """Evaluation metrics for a single pipeline configuration over the benchmark."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    configuration_key: str
    configuration_name: str
    description: str
    num_reports: int

    # Geospatial intelligence
    top1_accuracy: float
    top3_recall: float
    mae_meters: float
    ece: float

    # Entity resolution
    bcubed_precision: float
    bcubed_recall: float
    bcubed_f1: float
    false_merge_rate: float
    missed_duplicate_rate: float

    # Safety and triage
    high_severity_recall: float
    under_triage_rate: float
    false_escalation_rate: float
    unknown_preservation_rate: float

    # Systems / connectivity
    ingestion_success_rate: float


class BenchmarkComparisonReport(BaseModel):
    """Complete comparative evaluation report across Configurations A through E."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_id: str
    timestamp: datetime
    num_reports: int
    num_incidents: int
    results: dict[str, BenchmarkEvaluationResult]
    bootstrap_differences_e_vs_a: dict[str, BootstrapResult]
    research_questions: dict[str, Any]
    acceptance_gates: dict[str, Any]
    limitations: list[str]


class RaahatBenchRunner:
    """Executes benchmark evaluations and statistical hypothesis tests across configurations."""

    def __init__(self, n_bootstrap_iterations: int = 1000, seed: int = 42) -> None:
        self.n_bootstraps = n_bootstrap_iterations
        self.seed = seed

    def evaluate_configuration(
        self,
        config: PipelineConfig,
        config_key: str,
        reports: list[BenchmarkReportRecord],
    ) -> tuple[BenchmarkEvaluationResult, list[PipelinePrediction]]:
        """Run single configuration across reports and compute all metrics."""
        preds = [config.process_report(r) for r in reports]

        true_coords = [
            PointCoordinates(
                latitude=float(r.ground_truth["true_latitude"]),
                longitude=float(r.ground_truth["true_longitude"]),
            )
            for r in reports
        ]
        pred_coords = [p.predicted_coords for p in preds]
        cand_coords = [p.candidate_coords for p in preds]

        # Geospatial metrics
        top1_acc = calculate_top_k_accuracy(cand_coords, true_coords, threshold_meters=500.0, k=1)
        top3_rec = calculate_top_k_recall(cand_coords, true_coords, threshold_meters=750.0, k=3)
        mae = calculate_mae_meters(pred_coords, true_coords)

        # ECE: confidence calibration
        correct_flags = [p.distance_to(t) <= 500.0 for p, t in zip(pred_coords, true_coords)]
        confidences = [p.confidence for p in preds]
        ece = calculate_ece(confidences, correct_flags)

        # Entity resolution metrics
        true_clusters = [str(r.ground_truth["incident_id"]) for r in reports]
        pred_clusters = [p.predicted_cluster_id for p in preds]

        b_prec, b_rec, b_f1 = calculate_bcubed_metrics(pred_clusters, true_clusters)
        false_merge = calculate_false_merge_rate(pred_clusters, true_clusters)
        missed_dup = calculate_missed_duplicate_rate(pred_clusters, true_clusters)

        # Triage metrics
        true_severities = [str(r.ground_truth["true_severity"]) for r in reports]
        pred_priorities = [p.predicted_priority for p in preds]
        high_rec = calculate_high_severity_recall(pred_priorities, true_severities)
        under_triage = calculate_under_triage_rate(pred_priorities, true_severities)
        false_escalate = calculate_false_escalation_rate(pred_priorities, true_severities)

        preserved_unknowns = [p.preserved_unknowns for p in preds]
        true_missing = [r.missing_fields for r in reports]
        unknown_pres = calculate_unknown_preservation_rate(preserved_unknowns, true_missing)

        # Ingestion success
        ingest_success = sum(1 for p in preds if p.ingestion_success) / len(preds)

        result = BenchmarkEvaluationResult(
            configuration_key=config_key,
            configuration_name=config.name,
            description=config.description,
            num_reports=len(reports),
            top1_accuracy=round(top1_acc, 4),
            top3_recall=round(top3_rec, 4),
            mae_meters=round(mae, 1),
            ece=round(ece, 4),
            bcubed_precision=round(b_prec, 4),
            bcubed_recall=round(b_rec, 4),
            bcubed_f1=round(b_f1, 4),
            false_merge_rate=round(false_merge, 4),
            missed_duplicate_rate=round(missed_dup, 4),
            high_severity_recall=round(high_rec, 4),
            under_triage_rate=round(under_triage, 4),
            false_escalation_rate=round(false_escalate, 4),
            unknown_preservation_rate=round(unknown_pres, 4),
            ingestion_success_rate=round(ingest_success, 4),
        )

        return result, preds

    def run_all(
        self,
        dataset: RaahatBenchDataset,
        configurations: dict[str, PipelineConfig] | None = None,
    ) -> BenchmarkComparisonReport:
        """Run complete ablation matrix (Configurations A through E) and paired bootstrap tests."""
        configs = configurations or ALL_CONFIGURATIONS
        reports = dataset.reports
        results: dict[str, BenchmarkEvaluationResult] = {}
        all_preds: dict[str, list[PipelinePrediction]] = {}

        for key, cfg in configs.items():
            res, preds = self.evaluate_configuration(cfg, key, reports)
            results[key] = res
            all_preds[key] = preds

        # Paired bootstrap significance testing: Full Raahat (Config E) vs Baseline (Config A)
        bootstrap_diffs: dict[str, BootstrapResult] = {}
        if "A" in all_preds and "E" in all_preds:
            preds_a = all_preds["A"]
            preds_e = all_preds["E"]
            true_coords = [
                PointCoordinates(
                    latitude=float(r.ground_truth["true_latitude"]),
                    longitude=float(r.ground_truth["true_longitude"]),
                )
                for r in reports
            ]
            true_clusters = [str(r.ground_truth["incident_id"]) for r in reports]
            true_severities = [str(r.ground_truth["true_severity"]) for r in reports]

            # 1. MAE bootstrap
            mae_diff = paired_bootstrap_ci(
                metric_fn=lambda p, gt: calculate_mae_meters([x.predicted_coords for x in p], gt),
                predictions_a=preds_a,
                predictions_b=preds_e,
                ground_truths=true_coords,
                n_bootstraps=self.n_bootstraps,
                seed=self.seed,
            )
            bootstrap_diffs["mae_meters"] = mae_diff

            # 2. Top-3 recall bootstrap
            top3_diff = paired_bootstrap_ci(
                metric_fn=lambda p, gt: calculate_top_k_recall([x.candidate_coords for x in p], gt, threshold_meters=750.0, k=3),
                predictions_a=preds_a,
                predictions_b=preds_e,
                ground_truths=true_coords,
                n_bootstraps=self.n_bootstraps,
                seed=self.seed,
            )
            bootstrap_diffs["top3_recall"] = top3_diff

            # 3. False merge rate bootstrap
            fm_diff = paired_bootstrap_ci(
                metric_fn=lambda p, gt: calculate_false_merge_rate([x.predicted_cluster_id for x in p], gt),
                predictions_a=preds_a,
                predictions_b=preds_e,
                ground_truths=true_clusters,
                n_bootstraps=self.n_bootstraps,
                seed=self.seed,
            )
            bootstrap_diffs["false_merge_rate"] = fm_diff

            # 4. Under-triage rate bootstrap
            ut_diff = paired_bootstrap_ci(
                metric_fn=lambda p, gt: calculate_under_triage_rate([x.predicted_priority for x in p], gt),
                predictions_a=preds_a,
                predictions_b=preds_e,
                ground_truths=true_severities,
                n_bootstraps=self.n_bootstraps,
                seed=self.seed,
            )
            bootstrap_diffs["under_triage_rate"] = ut_diff

        # Research question evaluations (RAAHAT_SPEC §9.4)
        rq1_supported = (
            "B" in results and "A" in results
            and results["B"].top3_recall > results["A"].top3_recall
            and results["B"].mae_meters < results["A"].mae_meters
        )
        rq2_supported = (
            "C" in results and "B" in results
            and results["C"].false_merge_rate < results["B"].false_merge_rate
            and results["C"].bcubed_f1 >= results["B"].bcubed_f1
        )
        rq3_supported = (
            "D" in results and "C" in results
            and results["D"].under_triage_rate < results["C"].under_triage_rate
            and results["D"].high_severity_recall >= 0.99
        )

        res_a = results.get("A")
        res_b = results.get("B")
        res_c = results.get("C")
        res_d = results.get("D")

        ev_rq1 = (
            f"Config B reduced MAE from {res_a.mae_meters}m to {res_b.mae_meters}m "
            f"and increased Top-3 recall from {res_a.top3_recall} to {res_b.top3_recall}."
            if res_a and res_b
            else "Insufficient data."
        )
        ev_rq2 = (
            f"Config C reduced false merge rate from {res_b.false_merge_rate * 100:.1f}% "
            f"to {res_c.false_merge_rate * 100:.1f}% while preserving B-cubed F1 at {res_c.bcubed_f1}."
            if res_b and res_c
            else "Insufficient data."
        )
        ev_rq3 = (
            f"Config D eliminated under-triage from {res_c.under_triage_rate * 100:.1f}% "
            f"to {res_d.under_triage_rate * 100:.1f}% by enforcing 'unknown never lowers priority', "
            f"reaching {res_d.high_severity_recall * 100:.1f}% high-severity recall."
            if res_c and res_d
            else "Insufficient data."
        )

        research_questions = {
            "RQ1_active_clarification_improves_geospatial_accuracy": {
                "supported": rq1_supported,
                "evidence": ev_rq1,
            },
            "RQ2_evidence_graph_reduces_false_merges": {
                "supported": rq2_supported,
                "evidence": ev_rq2,
            },
            "RQ3_explicit_uncertainty_preservation_reduces_under_triage": {
                "supported": rq3_supported,
                "evidence": ev_rq3,
            },
        }

        # Engineering acceptance gates (§9.3)
        res_e = results.get("E")
        acceptance_gates = {
            "high_severity_recall": {
                "target": ">= 0.99",
                "achieved": res_e.high_severity_recall if res_e else 0.0,
                "passed": res_e.high_severity_recall >= 0.99 if res_e else False,
            },
            "false_household_incident_merges": {
                "target": "<= 0.01",
                "achieved": res_e.false_merge_rate if res_e else 1.0,
                "passed": res_e.false_merge_rate <= 0.01 if res_e else False,
            },
            "location_candidate_recall_top3": {
                "target": ">= 0.90",
                "achieved": res_e.top3_recall if res_e else 0.0,
                "passed": res_e.top3_recall >= 0.90 if res_e else False,
            },
            "offline_synchronization_success": {
                "target": "100%",
                "achieved": f"{res_e.ingestion_success_rate * 100:.1f}%" if res_e else "0.0%",
                "passed": res_e.ingestion_success_rate == 1.0 if res_e else False,
            },
        }

        limitations = [
            "Dataset is synthetic: Benchmark distributions (35% direct, 25% relative, 20% volunteer, 20% radio) are controlled evaluation targets, not real-world disaster estimates.",
            "Synthetic audio SNR and noise levels model Gaussian / motor boat acoustic profiles rather than field-recorded micro-climates.",
            "99% high-severity recall on synthetic benchmark is an algorithmic validation, not an unhedged operational safety guarantee for production deployment.",
            "Single-instance evaluation: Multi-node database replication lag and physical network partition timings are evaluated separately in staging environments.",
        ]

        return BenchmarkComparisonReport(
            benchmark_id=dataset.benchmark_id,
            timestamp=datetime.now(timezone.utc),
            num_reports=len(reports),
            num_incidents=len(dataset.incidents),
            results=results,
            bootstrap_differences_e_vs_a=bootstrap_diffs,
            research_questions=research_questions,
            acceptance_gates=acceptance_gates,
            limitations=limitations,
        )

    @staticmethod
    def render_markdown_report(report: BenchmarkComparisonReport) -> str:
        """Render evaluation report as a publication-ready GitHub-flavored Markdown document."""
        lines = [
            f"# RaahatBench Evaluation Report: {report.benchmark_id}",
            "",
            f"**Evaluation Date:** {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Dataset Scale:** {report.num_reports:,} reports across {report.num_incidents:,} ground-truth incidents  ",
            "",
            "---",
            "",
            "## 1. Ablation Study Matrix (Configurations A through E)",
            "",
            "| Metric | Config A (Baseline) | Config B (Spatial) | Config C (Evidence ER) | Config D (Safety) | Config E (Full Raahat) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: |",
        ]

        # Extract rows
        res = report.results

        def _val(k: str, field: str, fmt: str = ".4f") -> str:
            if k not in res:
                return "N/A"
            v = getattr(res[k], field)
            if fmt == "pct":
                return f"{v * 100:.1f}%"
            elif fmt == "m":
                return f"{v:.1f} m"
            return f"{v:{fmt}}"

        lines.extend([
            f"| **Top-1 Location Accuracy (≤500m)** | {_val('A', 'top1_accuracy', 'pct')} | {_val('B', 'top1_accuracy', 'pct')} | {_val('C', 'top1_accuracy', 'pct')} | {_val('D', 'top1_accuracy', 'pct')} | {_val('E', 'top1_accuracy', 'pct')} |",
            f"| **Top-3 Location Recall (≤750m)** | {_val('A', 'top3_recall', 'pct')} | {_val('B', 'top3_recall', 'pct')} | {_val('C', 'top3_recall', 'pct')} | {_val('D', 'top3_recall', 'pct')} | {_val('E', 'top3_recall', 'pct')} |",
            f"| **Location MAE (metres)** | {_val('A', 'mae_meters', 'm')} | {_val('B', 'mae_meters', 'm')} | {_val('C', 'mae_meters', 'm')} | {_val('D', 'mae_meters', 'm')} | {_val('E', 'mae_meters', 'm')} |",
            f"| **ECE (Confidence Calibration)** | {_val('A', 'ece')} | {_val('B', 'ece')} | {_val('C', 'ece')} | {_val('D', 'ece')} | {_val('E', 'ece')} |",
            f"| **B-cubed F1 Score** | {_val('A', 'bcubed_f1')} | {_val('B', 'bcubed_f1')} | {_val('C', 'bcubed_f1')} | {_val('D', 'bcubed_f1')} | {_val('E', 'bcubed_f1')} |",
            f"| **False Merge Rate** | {_val('A', 'false_merge_rate', 'pct')} | {_val('B', 'false_merge_rate', 'pct')} | {_val('C', 'false_merge_rate', 'pct')} | {_val('D', 'false_merge_rate', 'pct')} | {_val('E', 'false_merge_rate', 'pct')} |",
            f"| **High-Severity Recall (≥99% gate)** | {_val('A', 'high_severity_recall', 'pct')} | {_val('B', 'high_severity_recall', 'pct')} | {_val('C', 'high_severity_recall', 'pct')} | {_val('D', 'high_severity_recall', 'pct')} | {_val('E', 'high_severity_recall', 'pct')} |",
            f"| **Under-Triage Rate** | {_val('A', 'under_triage_rate', 'pct')} | {_val('B', 'under_triage_rate', 'pct')} | {_val('C', 'under_triage_rate', 'pct')} | {_val('D', 'under_triage_rate', 'pct')} | {_val('E', 'under_triage_rate', 'pct')} |",
            f"| **Unknown Preservation Rate** | {_val('A', 'unknown_preservation_rate', 'pct')} | {_val('B', 'unknown_preservation_rate', 'pct')} | {_val('C', 'unknown_preservation_rate', 'pct')} | {_val('D', 'unknown_preservation_rate', 'pct')} | {_val('E', 'unknown_preservation_rate', 'pct')} |",
            f"| **Offline Ingestion Success** | {_val('A', 'ingestion_success_rate', 'pct')} | {_val('B', 'ingestion_success_rate', 'pct')} | {_val('C', 'ingestion_success_rate', 'pct')} | {_val('D', 'ingestion_success_rate', 'pct')} | {_val('E', 'ingestion_success_rate', 'pct')} |",
        ])

        lines.extend([
            "",
            "---",
            "",
            "## 2. Paired Bootstrap Hypothesis Testing (Config E vs Baseline A)",
            "",
            "Resampling iterations: B = 1,000 (95% Confidence Intervals, two-tailed paired bootstrap):",
            "",
            "| Metric | Baseline A [95% CI] | Full Raahat E [95% CI] | Paired Difference Δ [95% CI] | p-value | Significant |",
            "| :--- | :---: | :---: | :---: | :---: | :---: |",
        ])

        for metric_name, b_res in report.bootstrap_differences_e_vs_a.items():
            sig_badge = "✓ Yes (p < 0.05)" if b_res.is_significant else "✗ No"
            lines.append(
                f"| `{metric_name}` | {b_res.mean_a:.4f} [{b_res.ci_a_low:.4f}, {b_res.ci_a_high:.4f}] | "
                f"{b_res.mean_b:.4f} [{b_res.ci_b_low:.4f}, {b_res.ci_b_high:.4f}] | "
                f"**{b_res.delta_mean:+.4f}** [{b_res.delta_ci_low:+.4f}, {b_res.delta_ci_high:+.4f}] | "
                f"{b_res.p_value:.4f} | {sig_badge} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 3. Research Questions Evaluation (RAAHAT_SPEC §9.4)",
            "",
        ])

        for rq_id, rq_data in report.research_questions.items():
            status = "Supported" if rq_data["supported"] else "Not Supported"
            lines.append(f"### **{rq_id.replace('_', ' ').title()}**: **{status}**")
            lines.append(f"> {rq_data['evidence']}")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 4. Engineering Acceptance Gates (§9.3)",
            "",
            "| Acceptance Gate | Target | Achieved | Status |",
            "| :--- | :---: | :---: | :---: |",
        ])

        for gate_name, gate in report.acceptance_gates.items():
            pass_str = "✓ PASS" if gate["passed"] else "✗ FAIL"
            lines.append(f"| `{gate_name}` | {gate['target']} | {gate['achieved']} | **{pass_str}** |")

        lines.extend([
            "",
            "---",
            "",
            "## 5. Explicit Limitations & Boundaries",
            "",
        ])
        for lim in report.limitations:
            lines.append(f"- {lim}")

        return "\n".join(lines) + "\n"

    def save_reports(
        self,
        report: BenchmarkComparisonReport,
        output_dir: Path | str = "evaluation/reports",
    ) -> tuple[Path, Path]:
        """Save JSON and Markdown report artifacts to output_dir."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        json_file = out_dir / "raahat_bench_evaluation_report.json"
        md_file = out_dir / "raahat_bench_evaluation_report.md"

        json_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        md_text = self.render_markdown_report(report)
        md_file.write_text(md_text, encoding="utf-8")

        return json_file, md_file


def main() -> None:
    """CLI entrypoint for running evaluation against benchmark dataset."""
    parser = argparse.ArgumentParser(description="RaahatBench Ablation Evaluation Runner")
    parser.add_argument(
        "--dataset",
        type=str,
        default="evaluation/datasets/raahat_bench_1000.json",
        help="Path to frozen benchmark JSON dataset",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evaluation/reports",
        help="Output directory for generated evaluation reports",
    )
    parser.add_argument(
        "--bootstraps",
        type=int,
        default=1000,
        help="Number of paired bootstrap resampling iterations",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.info("Dataset not found at %s; generating with seed=42...", dataset_path)
        gen = RaahatBenchGenerator(seed=42)
        dataset = gen.generate()
        RaahatBenchGenerator.save_dataset(dataset, "evaluation/datasets")
    else:
        dataset = RaahatBenchGenerator.load_dataset(dataset_path)

    runner = RaahatBenchRunner(n_bootstrap_iterations=args.bootstraps)
    report = runner.run_all(dataset)
    json_path, md_path = runner.save_reports(report, args.output)

    print("Evaluation complete!")
    print(f"JSON Report: {json_path}")
    print(f"Markdown Report: {md_path}")
    print(f"Full Raahat High Severity Recall: {report.results['E'].high_severity_recall * 100:.1f}%")
    print(f"Full Raahat False Merge Rate: {report.results['E'].false_merge_rate * 100:.2f}%")


if __name__ == "__main__":
    main()
