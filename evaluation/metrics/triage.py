"""Safety and triage metrics (RAAHAT_SPEC §9.2)."""
from __future__ import annotations

HIGH_SEVERITY_LEVELS = {"critical", "urgent", "critical_review"}
LOW_SEVERITY_LEVELS = {"standard", "low"}


def calculate_high_severity_recall(
    predicted_priorities: list[str],
    true_severities: list[str],
) -> float:
    """Calculate recall on high-severity incidents (critical + urgent)."""
    true_high_count = 0
    correct_high_count = 0

    for pred, true_sev in zip(predicted_priorities, true_severities):
        p_norm = pred.lower()
        t_norm = true_sev.lower()

        if t_norm in HIGH_SEVERITY_LEVELS:
            true_high_count += 1
            if p_norm in HIGH_SEVERITY_LEVELS:
                correct_high_count += 1

    return correct_high_count / true_high_count if true_high_count > 0 else 0.0


def calculate_under_triage_rate(
    predicted_priorities: list[str],
    true_severities: list[str],
) -> float:
    """Calculate under-triage rate: proportion of true high-severity incidents classified as low/standard."""
    true_high_count = 0
    under_triaged_count = 0

    for pred, true_sev in zip(predicted_priorities, true_severities):
        p_norm = pred.lower()
        t_norm = true_sev.lower()

        if t_norm in HIGH_SEVERITY_LEVELS:
            true_high_count += 1
            if p_norm in LOW_SEVERITY_LEVELS:
                under_triaged_count += 1

    return under_triaged_count / true_high_count if true_high_count > 0 else 0.0


def calculate_false_escalation_rate(
    predicted_priorities: list[str],
    true_severities: list[str],
) -> float:
    """Calculate false escalation rate: proportion of low/standard incidents escalated to critical/urgent."""
    true_low_count = 0
    escalated_count = 0

    for pred, true_sev in zip(predicted_priorities, true_severities):
        p_norm = pred.lower()
        t_norm = true_sev.lower()

        if t_norm in LOW_SEVERITY_LEVELS:
            true_low_count += 1
            if p_norm in HIGH_SEVERITY_LEVELS:
                escalated_count += 1

    return escalated_count / true_low_count if true_low_count > 0 else 0.0


def calculate_unknown_preservation_rate(
    preserved_unknown_fields_list: list[list[str]],
    true_missing_fields_list: list[list[str]],
) -> float:
    """Calculate rate at which genuinely unobserved/missing fields are preserved as unknown."""
    total_true_missing = 0
    preserved_count = 0

    for preserved, true_missing in zip(preserved_unknown_fields_list, true_missing_fields_list):
        for field in true_missing:
            total_true_missing += 1
            if field in preserved:
                preserved_count += 1

    return preserved_count / total_true_missing if total_true_missing > 0 else 1.0
