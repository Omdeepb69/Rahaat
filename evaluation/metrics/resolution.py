"""Entity resolution and incident clustering metrics (RAAHAT_SPEC §9.2)."""
from __future__ import annotations

from collections import Counter


def calculate_bcubed_metrics(
    predicted_clusters: list[str],
    true_clusters: list[str],
) -> tuple[float, float, float]:
    """Calculate B-cubed Precision, Recall, and F1 over incident cluster assignments.

    Args:
        predicted_clusters: Cluster ID assigned by the system for each report.
        true_clusters: Ground truth incident/cluster ID for each report.

    Returns:
        tuple of (precision, recall, f1)
    """
    n = len(predicted_clusters)
    if n == 0 or len(true_clusters) != n:
        return 0.0, 0.0, 0.0

    # Build report ID sets per predicted and true cluster
    pred_map: dict[str, set[int]] = {}
    true_map: dict[str, set[int]] = {}

    for idx, (p_c, t_c) in enumerate(zip(predicted_clusters, true_clusters)):
        pred_map.setdefault(p_c, set()).add(idx)
        true_map.setdefault(t_c, set()).add(idx)

    precisions: list[float] = []
    recalls: list[float] = []

    for idx in range(n):
        p_c = predicted_clusters[idx]
        t_c = true_clusters[idx]

        pred_set = pred_map[p_c]
        true_set = true_map[t_c]

        intersection_len = len(pred_set & true_set)
        precisions.append(intersection_len / len(pred_set))
        recalls.append(intersection_len / len(true_set))

    p = sum(precisions) / n
    r = sum(recalls) / n
    f1 = (2.0 * p * r) / (p + r) if (p + r) > 0.0 else 0.0

    return round(p, 4), round(r, 4), round(f1, 4)


def calculate_false_merge_rate(
    predicted_clusters: list[str],
    true_clusters: list[str],
) -> float:
    """Calculate false merge rate: proportion of pairwise merges grouping distinct true incidents.

    Uses O(N) contingency counting rather than O(N^2) pairwise comparisons.
    """
    n = len(predicted_clusters)
    if n < 2:
        return 0.0

    # Counts per predicted cluster: pred_cluster -> total count
    pred_counts: Counter[str] = Counter(predicted_clusters)

    # Contingency counts: pred_cluster -> {true_cluster: count}
    pred_to_true: dict[str, Counter[str]] = {}
    for p_c, t_c in zip(predicted_clusters, true_clusters):
        if p_c not in pred_to_true:
            pred_to_true[p_c] = Counter()
        pred_to_true[p_c][t_c] += 1

    total_predicted_merges = 0
    correct_merges = 0

    for p_c, total_in_pred in pred_counts.items():
        if total_in_pred > 1:
            total_predicted_merges += total_in_pred * (total_in_pred - 1) // 2

            for t_count in pred_to_true[p_c].values():
                if t_count > 1:
                    correct_merges += t_count * (t_count - 1) // 2

    false_merges = total_predicted_merges - correct_merges
    return false_merges / total_predicted_merges if total_predicted_merges > 0 else 0.0


def calculate_missed_duplicate_rate(
    predicted_clusters: list[str],
    true_clusters: list[str],
) -> float:
    """Calculate missed duplicate rate: proportion of true duplicate pairs left unmerged.

    Uses O(N) contingency counting rather than O(N^2) pairwise comparisons.
    """
    n = len(predicted_clusters)
    if n < 2:
        return 0.0

    # Counts per true cluster: true_cluster -> total count
    true_counts: Counter[str] = Counter(true_clusters)

    # Contingency counts: true_cluster -> {pred_cluster: count}
    true_to_pred: dict[str, Counter[str]] = {}
    for p_c, t_c in zip(predicted_clusters, true_clusters):
        if t_c not in true_to_pred:
            true_to_pred[t_c] = Counter()
        true_to_pred[t_c][p_c] += 1

    total_true_pairs = 0
    found_pairs = 0

    for t_c, total_in_true in true_counts.items():
        if total_in_true > 1:
            total_true_pairs += total_in_true * (total_in_true - 1) // 2

            for p_count in true_to_pred[t_c].values():
                if p_count > 1:
                    found_pairs += p_count * (p_count - 1) // 2

    missed_pairs = total_true_pairs - found_pairs
    return missed_pairs / total_true_pairs if total_true_pairs > 0 else 0.0
