"""Statistical bootstrap confidence intervals and paired significance testing."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
from pydantic import BaseModel, ConfigDict


class BootstrapResult(BaseModel):
    """Result of paired bootstrap evaluation with 95% confidence interval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mean_a: float
    ci_a_low: float
    ci_a_high: float
    mean_b: float
    ci_b_low: float
    ci_b_high: float
    delta_mean: float  # (b - a)
    delta_ci_low: float
    delta_ci_high: float
    p_value: float
    is_significant: bool


def paired_bootstrap_ci(
    metric_fn: Callable[[list[Any], list[Any]], float],
    predictions_a: list[Any],
    predictions_b: list[Any],
    ground_truths: list[Any],
    n_bootstraps: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> BootstrapResult:
    """Compute paired bootstrap resampling for two model predictions against ground truth.

    Calculates:
      - 95% CI for Model A
      - 95% CI for Model B
      - 95% CI for delta (B - A)
      - Paired two-tailed bootstrap p-value
    """
    n = len(ground_truths)
    if n == 0:
        return BootstrapResult(
            mean_a=0.0, ci_a_low=0.0, ci_a_high=0.0,
            mean_b=0.0, ci_b_low=0.0, ci_b_high=0.0,
            delta_mean=0.0, delta_ci_low=0.0, delta_ci_high=0.0,
            p_value=1.0, is_significant=False,
        )

    rng = np.random.default_rng(seed)
    scores_a = np.zeros(n_bootstraps)
    scores_b = np.zeros(n_bootstraps)
    deltas = np.zeros(n_bootstraps)

    for i in range(n_bootstraps):
        indices = rng.integers(0, n, size=n)
        sub_a = [predictions_a[idx] for idx in indices]
        sub_b = [predictions_b[idx] for idx in indices]
        sub_gt = [ground_truths[idx] for idx in indices]

        score_a = metric_fn(sub_a, sub_gt)
        score_b = metric_fn(sub_b, sub_gt)

        scores_a[i] = score_a
        scores_b[i] = score_b
        deltas[i] = score_b - score_a

    low_pct = (alpha / 2.0) * 100
    high_pct = (1.0 - alpha / 2.0) * 100

    ci_a_low, ci_a_high = np.percentile(scores_a, [low_pct, high_pct])
    ci_b_low, ci_b_high = np.percentile(scores_b, [low_pct, high_pct])
    delta_low, delta_high = np.percentile(deltas, [low_pct, high_pct])

    # Two-sided empirical p-value for H0: delta = 0
    # Fraction of bootstrap samples that cross zero in the opposite direction
    observed_delta = float(np.mean(deltas))
    if observed_delta >= 0:
        p_val = 2.0 * float(np.mean(deltas <= 0))
    else:
        p_val = 2.0 * float(np.mean(deltas >= 0))
    p_val = min(1.0, max(0.0, p_val))

    # Significance at alpha: delta CI does not contain zero
    is_sig = (delta_low > 0 and delta_high > 0) or (delta_low < 0 and delta_high < 0)

    return BootstrapResult(
        mean_a=round(float(np.mean(scores_a)), 4),
        ci_a_low=round(float(ci_a_low), 4),
        ci_a_high=round(float(ci_a_high), 4),
        mean_b=round(float(np.mean(scores_b)), 4),
        ci_b_low=round(float(ci_b_low), 4),
        ci_b_high=round(float(ci_b_high), 4),
        delta_mean=round(observed_delta, 4),
        delta_ci_low=round(float(delta_low), 4),
        delta_ci_high=round(float(delta_high), 4),
        p_value=round(p_val, 4),
        is_significant=bool(is_sig),
    )
