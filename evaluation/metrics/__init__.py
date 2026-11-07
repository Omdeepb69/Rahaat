"""Evaluation metrics package for RaahatBench."""
from __future__ import annotations

from .bootstrap import BootstrapResult, paired_bootstrap_ci
from .resolution import (
    calculate_bcubed_metrics,
    calculate_false_merge_rate,
    calculate_missed_duplicate_rate,
)
from .spatial import (
    calculate_ece,
    calculate_mae_meters,
    calculate_top_k_accuracy,
    calculate_top_k_recall,
)
from .triage import (
    calculate_false_escalation_rate,
    calculate_high_severity_recall,
    calculate_under_triage_rate,
    calculate_unknown_preservation_rate,
)

__all__ = [
    "calculate_top_k_accuracy",
    "calculate_top_k_recall",
    "calculate_mae_meters",
    "calculate_ece",
    "calculate_bcubed_metrics",
    "calculate_false_merge_rate",
    "calculate_missed_duplicate_rate",
    "calculate_high_severity_recall",
    "calculate_under_triage_rate",
    "calculate_false_escalation_rate",
    "calculate_unknown_preservation_rate",
    "BootstrapResult",
    "paired_bootstrap_ci",
]
