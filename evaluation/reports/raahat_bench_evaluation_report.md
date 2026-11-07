# RaahatBench Evaluation Report: raahat-bench-v1

**Evaluation Date:** 2026-11-07 18:36:18 UTC  
**Dataset Scale:** 1,000 reports across 100 ground-truth incidents  

---

## 1. Ablation Study Matrix (Configurations A through E)

| Metric | Config A (Baseline) | Config B (Spatial) | Config C (Evidence ER) | Config D (Safety) | Config E (Full Raahat) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Top-1 Location Accuracy (≤500m)** | 75.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **Top-3 Location Recall (≤750m)** | 75.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| **Location MAE (metres)** | 967.5 m | 99.8 m | 99.8 m | 99.8 m | 80.7 m |
| **ECE (Confidence Calibration)** | 0.3625 | 0.1375 | 0.1250 | 0.1150 | 0.0925 |
| **B-cubed F1 Score** | 0.4287 | 0.4287 | 1.0000 | 1.0000 | 1.0000 |
| **False Merge Rate** | 88.8% | 88.8% | 0.0% | 0.0% | 0.0% |
| **High-Severity Recall (≥99% gate)** | 83.0% | 83.0% | 83.0% | 100.0% | 100.0% |
| **Under-Triage Rate** | 17.0% | 17.0% | 17.0% | 0.0% | 0.0% |
| **Unknown Preservation Rate** | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% |
| **Offline Ingestion Success** | 80.0% | 80.0% | 80.0% | 80.0% | 100.0% |

---

## 2. Paired Bootstrap Hypothesis Testing (Config E vs Baseline A)

Resampling iterations: B = 1,000 (95% Confidence Intervals, two-tailed paired bootstrap):

| Metric | Baseline A [95% CI] | Full Raahat E [95% CI] | Paired Difference Δ [95% CI] | p-value | Significant |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `mae_meters` | 967.4475 [903.4419, 1033.6652] | 80.7125 [79.0285, 82.4537] | **-886.7350** [-951.2115, -824.4134] | 0.0000 | ✓ Yes (p < 0.05) |
| `top3_recall` | 0.7500 [0.7230, 0.7760] | 1.0000 [1.0000, 1.0000] | **+0.2500** [+0.2240, +0.2770] | 0.0000 | ✓ Yes (p < 0.05) |
| `false_merge_rate` | 0.8739 [0.8504, 0.8958] | 0.0000 [0.0000, 0.0000] | **-0.8739** [-0.8958, -0.8504] | 0.0000 | ✓ Yes (p < 0.05) |
| `under_triage_rate` | 0.1710 [0.1457, 0.1956] | 0.0000 [0.0000, 0.0000] | **-0.1710** [-0.1956, -0.1457] | 0.0000 | ✓ Yes (p < 0.05) |

---

## 3. Research Questions Evaluation (RAAHAT_SPEC §9.4)

### **Rq1 Active Clarification Improves Geospatial Accuracy**: **Supported**
> Config B reduced MAE from 967.5m to 99.8m and increased Top-3 recall from 0.75 to 1.0.

### **Rq2 Evidence Graph Reduces False Merges**: **Supported**
> Config C reduced false merge rate from 88.8% to 0.0% while preserving B-cubed F1 at 1.0.

### **Rq3 Explicit Uncertainty Preservation Reduces Under Triage**: **Supported**
> Config D eliminated under-triage from 17.0% to 0.0% by enforcing 'unknown never lowers priority', reaching 100.0% high-severity recall.

---

## 4. Engineering Acceptance Gates (§9.3)

| Acceptance Gate | Target | Achieved | Status |
| :--- | :---: | :---: | :---: |
| `high_severity_recall` | >= 0.99 | 1.0 | **✓ PASS** |
| `false_household_incident_merges` | <= 0.01 | 0.0 | **✓ PASS** |
| `location_candidate_recall_top3` | >= 0.90 | 1.0 | **✓ PASS** |
| `offline_synchronization_success` | 100% | 100.0% | **✓ PASS** |

---

## 5. Explicit Limitations & Boundaries

- Dataset is synthetic: Benchmark distributions (35% direct, 25% relative, 20% volunteer, 20% radio) are controlled evaluation targets, not real-world disaster estimates.
- Synthetic audio SNR and noise levels model Gaussian / motor boat acoustic profiles rather than field-recorded micro-climates.
- 99% high-severity recall on synthetic benchmark is an algorithmic validation, not an unhedged operational safety guarantee for production deployment.
- Single-instance evaluation: Multi-node database replication lag and physical network partition timings are evaluated separately in staging environments.
