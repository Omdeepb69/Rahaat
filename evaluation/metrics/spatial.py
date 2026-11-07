"""Geospatial accuracy and calibration metrics (RAAHAT_SPEC §9.2)."""
from __future__ import annotations

import numpy as np

from raahat.domain.shared.coordinates import PointCoordinates


def calculate_top_k_accuracy(
    candidates_list: list[list[PointCoordinates]],
    true_coords: list[PointCoordinates],
    threshold_meters: float = 500.0,
    k: int = 1,
) -> float:
    """Calculate accuracy at rank 1 (or k): true point is within threshold_meters of top-k candidate."""
    if not candidates_list or not true_coords:
        return 0.0

    hits = 0
    for candidates, true_pt in zip(candidates_list, true_coords):
        top_candidates = candidates[:k]
        if any(c.distance_to(true_pt) <= threshold_meters for c in top_candidates):
            hits += 1

    return hits / len(true_coords)


def calculate_top_k_recall(
    candidates_list: list[list[PointCoordinates]],
    true_coords: list[PointCoordinates],
    threshold_meters: float = 750.0,
    k: int = 3,
) -> float:
    """Calculate candidate recall at top-k: true point is within threshold_meters of any top-k candidate."""
    return calculate_top_k_accuracy(
        candidates_list=candidates_list,
        true_coords=true_coords,
        threshold_meters=threshold_meters,
        k=k,
    )


def calculate_mae_meters(
    predicted_coords: list[PointCoordinates],
    true_coords: list[PointCoordinates],
) -> float:
    """Calculate Mean Absolute Error (MAE) in metres between top-1 predicted and true coordinates."""
    if not predicted_coords or not true_coords:
        return 0.0

    distances = [
        pred.distance_to(true_pt)
        for pred, true_pt in zip(predicted_coords, true_coords)
    ]
    return float(np.mean(distances))


def calculate_ece(
    confidences: list[float],
    correct_flags: list[bool],
    num_bins: int = 10,
) -> float:
    """Calculate Expected Calibration Error (ECE) measuring confidence calibration."""
    if not confidences or not correct_flags:
        return 0.0

    confs = np.asarray(confidences)
    accs = np.asarray(correct_flags, dtype=float)
    bin_boundaries = np.linspace(0, 1, num_bins + 1)

    ece = 0.0
    total_samples = len(confs)

    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        in_bin = (confs > bin_lower) & (confs <= bin_upper) if i > 0 else (confs >= bin_lower) & (confs <= bin_upper)
        bin_count = int(np.sum(in_bin))

        if bin_count > 0:
            bin_acc = float(np.mean(accs[in_bin]))
            bin_conf = float(np.mean(confs[in_bin]))
            ece += (bin_count / total_samples) * abs(bin_acc - bin_conf)

    return float(ece)
