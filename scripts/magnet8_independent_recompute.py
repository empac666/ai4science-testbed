#!/usr/bin/env python3
"""
Independent Recompute Script for Round 8 (magnet8) Physics-Surrogate Evaluation.

Preregistered protocol:
- Recomputes calibration q, prediction intervals, Winkler scores, and all primary metrics.
- Exact one-sided sign-flip permutation tests (2^30 configurations) via Meet-In-The-Middle.
- Fixed-sequence hypothesis gating (H1 -> H6).
- 80% engineering validity (CV, V80) and nominal 90% coverage honesty (HONEST90).
- Formal conclusions mapping and sealed comparison verification.
"""

import os
import sys

# Constrain threading prior to importing numerical libraries
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


def generate_signed_sums(arr: np.ndarray) -> np.ndarray:
    """Generate all 2^len(arr) signed sums for a 1D array."""
    sums = np.array([0.0], dtype=np.float64)
    for val in arr:
        sums = np.concatenate([sums + val, sums - val])
    return sums


def compute_sign_flip_p(d: np.ndarray, K: int = 30) -> Tuple[int, float]:
    """
    Exact one-sided sign-flip permutation test p-value:
    p = #{s in {-1, +1}^K: mean(s * d) >= mean(d) - 1e-12} / 2^K
    Implemented via Meet-in-the-Middle using sum threshold sum(d) - K * 1e-12.
    """
    if len(d) != K:
        raise ValueError(f"Expected vector of length {K}, got {len(d)}")

    d = np.asarray(d, dtype=np.float64)
    if np.all(d == 0.0):
        total_perms = 1 << K
        return total_perms, 1.0

    k1 = K // 2
    d1 = d[:k1]
    d2 = d[k1:]

    s1 = generate_signed_sums(d1)
    s2 = generate_signed_sums(d2)
    s2_sorted = np.sort(s2)

    threshold = float(np.sum(d)) - K * 1e-12
    targets = threshold - s1

    # s1 + s2 >= threshold <=> s2 >= threshold - s1
    indices = np.searchsorted(s2_sorted, targets, side="left")
    numerator = int(np.sum(len(s2_sorted) - indices))
    denominator = 1 << K
    p = float(numerator / denominator)
    return numerator, p


def run_mitm_self_test():
    """Verify MITM exact enumeration against brute-force on small K synthetic vectors."""
    # Test 1: Zero vector
    k_test = 8
    d_zero = np.zeros(k_test, dtype=np.float64)
    num, p = compute_sign_flip_p(d_zero, K=k_test)
    assert num == (1 << k_test) and p == 1.0, "Self-test failed on zero vector."

    # Test 2: Randomized cases with zeros, ties, positive, and negative values
    rng = np.random.default_rng(20261005)
    candidates = [-1.4, -0.6, 0.0, 0.0, 0.5, 0.5, 1.2, 2.1]
    for _ in range(5):
        d_synth = rng.choice(candidates, size=k_test).astype(np.float64)
        num_mitm, _ = compute_sign_flip_p(d_synth, K=k_test)

        thresh = float(np.sum(d_synth)) - k_test * 1e-12
        bf_num = 0
        for signs in itertools.product([-1.0, 1.0], repeat=k_test):
            s_sum = float(np.sum(np.array(signs, dtype=np.float64) * d_synth))
            if s_sum >= thresh:
                bf_num += 1

        assert num_mitm == bf_num, (
            f"Self-test mismatch: MITM {num_mitm} != Brute-force {bf_num} on {d_synth}"
        )


def compute_set_metrics(
    y: np.ndarray,
    p_meas: np.ndarray,
    mu: np.ndarray,
    sigma: np.ndarray,
    q: float,
) -> Dict[str, Any]:
    """Compute Winkler and secondary evaluation metrics on a designated evaluation set."""
    n = int(len(y))
    l_bound = mu - q * sigma
    u_bound = mu + q * sigma

    covered = (y >= l_bound) & (y <= u_bound)
    cov_count = int(np.sum(covered))
    cov_frac = float(cov_count / n) if n > 0 else 0.0
    shortfall = float(max(0.0, 0.9 - cov_frac))

    widths = u_bound - l_bound
    mean_width = float(np.mean(widths))

    under = np.maximum(0.0, l_bound - y)
    over = np.maximum(0.0, y - u_bound)
    w_scores = widths + 20.0 * under + 20.0 * over
    mean_winkler = float(np.mean(w_scores))

    pred_power = 10.0**mu
    rel_errors = np.abs(pred_power - p_meas) / p_meas
    med_rel_error = float(np.median(rel_errors))

    mae = float(np.mean(np.abs(mu - y)))
    bias = float(np.mean(mu - y))

    return {
        "n": n,
        "coverage": cov_count,
        "width": mean_width,
        "winkler": mean_winkler,
        "relative_error": med_rel_error,
        "mae": mae,
        "bias": bias,
        "coverage_fraction": cov_frac,
        "nominal90_shortfall": shortfall,
    }


class IndependentComparator:
    """Verifies recomputed structures against sealed records with strict tolerances."""

    def __init__(self, abs_tol: float = 1e-6, rel_tol: float = 1e-9):
        self.abs_tol = abs_tol
        self.rel_tol = rel_tol
        self.total_comparisons = 0
        self.mismatches: List[str] = []
        self.max_abs_diff_by_category: Dict[str, float] = {}

    def compare(self, category: str, path: str, comp_val: Any, sealed_val: Any):
        self.total_comparisons += 1
        if category not in self.max_abs_diff_by_category:
            self.max_abs_diff_by_category[category] = 0.0

        if isinstance(sealed_val, bool) or isinstance(comp_val, bool):
            if comp_val != sealed_val:
                self.mismatches.append(f"[{category}] {path}: {comp_val} != {sealed_val}")
            return

        if isinstance(sealed_val, (int, np.integer)) and isinstance(
            comp_val, (int, np.integer)
        ):
            if comp_val != sealed_val:
                diff = float(abs(int(comp_val) - int(sealed_val)))
                self.max_abs_diff_by_category[category] = max(
                    self.max_abs_diff_by_category[category], diff
                )
                self.mismatches.append(
                    f"[{category}] {path}: {comp_val} != {sealed_val} (diff={diff})"
                )
            return

        if isinstance(sealed_val, str):
            if comp_val != sealed_val:
                self.mismatches.append(f"[{category}] {path}: '{comp_val}' != '{sealed_val}'")
            return

        # Numeric float comparison
        try:
            c = float(comp_val)
            s = float(sealed_val)
            diff = abs(c - s)
            self.max_abs_diff_by_category[category] = max(
                self.max_abs_diff_by_category[category], diff
            )
            tol = max(self.abs_tol, self.rel_tol * max(abs(c), abs(s)))
            if diff > tol:
                self.mismatches.append(
                    f"[{category}] {path}: computed={c:.8e} != sealed={s:.8e} (diff={diff:.3e})"
                )
        except (ValueError, TypeError):
            if comp_val != sealed_val:
                self.mismatches.append(f"[{category}] {path}: {comp_val} != {sealed_val}")


def main():
    parser = argparse.ArgumentParser(
        description="Independent Recomputation of magnet8 Physics-Surrogate Evaluation."
    )
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root path.")
    parser.add_argument(
        "--force", action="store_true", help="Force overwrite of existing output files."
    )
    args = parser.parse_args()

    # Self-test MITM implementation before analyzing real data
    run_mitm_self_test()

    root = Path(args.repo_root).resolve()
    labels_file = root / "data" / "magnet" / "igse_predictions.csv"
    split_file = root / "data" / "magnet8" / "split.json"
    arms_dir = root / "data" / "magnet8" / "arms"
    sealed_cal_file = root / "lab" / "cases" / "magnet8" / "first" / "calibration.json"
    sealed_eval_file = (
        root / "lab" / "cases" / "magnet8" / "first" / "primary_evaluation.json"
    )

    out_dir = root / "lab" / "cases" / "magnet8" / "first_recompute"
    out_json = out_dir / "independent_recompute.json"
    out_csv = out_dir / "independent_per_arm_final.csv"

    if not args.force:
        if out_json.exists():
            print(f"Error: {out_json} exists. Pass --force to overwrite.", file=sys.stderr)
            sys.exit(1)
        if out_csv.exists():
            print(f"Error: {out_csv} exists. Pass --force to overwrite.", file=sys.stderr)
            sys.exit(1)

    # 1. Load labels once into memory-light lookups
    labels_df = pd.read_csv(labels_file, usecols=["sample_id", "measured_W_m3"])
    label_p_map = dict(
        zip(labels_df["sample_id"].astype(int), labels_df["measured_W_m3"].astype(float))
    )
    label_y_map = {sid: math.log10(p) for sid, p in label_p_map.items()}
    del labels_df

    # 2. Load split lists
    with open(split_file, "r", encoding="utf-8") as f:
        split_raw = json.load(f)

    splits = {
        "E1": {k: [int(x) for x in v] for k, v in split_raw["E1"].items() if isinstance(v, list) and not any(isinstance(x, str) for x in v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)},
        "E2": {k: [int(x) for x in v] for k, v in split_raw["E2"].items() if isinstance(v, list) and not any(isinstance(x, str) for x in v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)},
    }

    cal_set_map = {"E1": "CAL7r", "E2": "CAL8"}
    eval_set_map = {
        "E1": ["X7", "G7r"],
        "E2": ["XF", "XT", "XFT", "G8"],
    }

    # Verify split size invariants
    assert len(splits["E1"]["CAL7r"]) == 3508
    assert len(splits["E1"]["G7r"]) == 5375
    assert len(splits["E1"]["X7"]) == 632
    assert len(splits["E2"]["CAL8"]) == 1704
    assert len(splits["E2"]["G8"]) == 3197
    assert len(splits["E2"]["XF"]) == 5361
    assert len(splits["E2"]["XT"]) == 8345
    assert len(splits["E2"]["XFT"]) == 1788

    arms_list = [f"{m}{k}" for k in range(1, 31) for m in "AMR"]

    recomputed_arms: Dict[str, Dict[str, Dict[str, Any]]] = {"E1": {}, "E2": {}}
    cal_qs_recomputed: Dict[str, Dict[str, List[float]]] = {"E1": {}, "E2": {}}

    # 3. Process each arm independently (memory-light)
    for exp in ["E1", "E2"]:
        cal_name = cal_set_map[exp]
        eval_names = eval_set_map[exp]

        cal_ids = splits[exp][cal_name]
        cal_y = np.array([label_y_map[sid] for sid in cal_ids], dtype=np.float64)
        n_cal = len(cal_ids)
        cal_rank = math.ceil((n_cal + 1) * 0.9)
        assert cal_rank <= n_cal

        eval_y = {
            s: np.array([label_y_map[sid] for sid in splits[exp][s]], dtype=np.float64)
            for s in eval_names
        }
        eval_p = {
            s: np.array([label_p_map[sid] for sid in splits[exp][s]], dtype=np.float64)
            for s in eval_names
        }

        for arm in arms_list:
            arm_dir = arms_dir / exp / arm
            q_list: List[float] = []
            ckpt_list: List[Dict[str, Any]] = []

            for b in range(7):
                pred_path = arm_dir / f"predictions_{b}.csv"
                df_pred = pd.read_csv(pred_path)

                # Split prediction records by set and verify sample integrity
                cal_sub = df_pred[df_pred["set"] == cal_name]
                assert len(cal_sub) == n_cal
                cal_pred_ids = cal_sub["sample_id"].astype(int).tolist()
                assert cal_pred_ids == cal_ids, f"ID order mismatch on {exp}/{arm}/b{b}"

                mu_cal = cal_sub["mu"].to_numpy(dtype=np.float64)
                sigma_cal = cal_sub["sigma"].to_numpy(dtype=np.float64)
                residuals = np.abs(cal_y - mu_cal) / sigma_cal
                res_sorted = np.sort(residuals)
                q = float(res_sorted[cal_rank - 1])
                assert np.isfinite(q), f"Non-finite q in {exp}/{arm}/b{b}"
                q_list.append(q)

                ckpt_metrics: Dict[str, Any] = {}
                for s in eval_names:
                    eval_sub = df_pred[df_pred["set"] == s]
                    assert len(eval_sub) == len(splits[exp][s])
                    eval_pred_ids = eval_sub["sample_id"].astype(int).tolist()
                    assert eval_pred_ids == splits[exp][s]

                    mu_s = eval_sub["mu"].to_numpy(dtype=np.float64)
                    sigma_s = eval_sub["sigma"].to_numpy(dtype=np.float64)

                    ckpt_metrics[s] = compute_set_metrics(
                        eval_y[s], eval_p[s], mu_s, sigma_s, q
                    )

                ckpt_list.append({"batch": b, "q": q, "metrics": ckpt_metrics})

            recomputed_arms[exp][arm] = {"checkpoints": ckpt_list}
            cal_qs_recomputed[exp][arm] = q_list

    # 4. Hypothesis Testing H1..H6 at batch b=6
    # Hypotheses table mappings:
    # H1: E1 X7: W_R - W_M
    # H2: E1 X7: 1.10 W_A - W_M
    # H3: E2 XF: W_R - W_A
    # H4: E2 XF: W_R - W_M
    # H5: E2 XT: W_R - W_A
    # H6: E2 XT: W_R - W_M
    hypo_defs = [
        ("H1", "E1", "X7", lambda w_a, w_m, w_r: w_r - w_m),
        ("H2", "E1", "X7", lambda w_a, w_m, w_r: 1.10 * w_a - w_m),
        ("H3", "E2", "XF", lambda w_a, w_m, w_r: w_r - w_a),
        ("H4", "E2", "XF", lambda w_a, w_m, w_r: w_r - w_m),
        ("H5", "E2", "XT", lambda w_a, w_m, w_r: w_r - w_a),
        ("H6", "E2", "XT", lambda w_a, w_m, w_r: w_r - w_m),
    ]

    recomputed_hypotheses: Dict[str, Any] = {}
    gating_active = True

    for h_name, exp, set_name, diff_fn in hypo_defs:
        d_k: List[float] = []
        for k in range(1, 31):
            w_a = recomputed_arms[exp][f"A{k}"]["checkpoints"][6]["metrics"][set_name][
                "winkler"
            ]
            w_m = recomputed_arms[exp][f"M{k}"]["checkpoints"][6]["metrics"][set_name][
                "winkler"
            ]
            w_r = recomputed_arms[exp][f"R{k}"]["checkpoints"][6]["metrics"][set_name][
                "winkler"
            ]
            d_k.append(float(diff_fn(w_a, w_m, w_r)))

        d_arr = np.array(d_k, dtype=np.float64)
        num, p_val = compute_sign_flip_p(d_arr, K=30)

        d_mean = float(np.mean(d_arr))
        d_med = float(np.median(d_arr))
        q75 = float(np.percentile(d_arr, 75, method="linear"))
        q25 = float(np.percentile(d_arr, 25, method="linear"))
        iqr = float(q75 - q25)
        pos_cnt = int(np.sum(d_arr > 0))
        zero_cnt = int(np.sum(d_arr == 0))
        neg_cnt = int(np.sum(d_arr < 0))

        if gating_active:
            if p_val < 0.05:
                status = "rejected"
            else:
                status = "not_rejected"
                gating_active = False
        else:
            status = "not_tested"

        recomputed_hypotheses[h_name] = {
            "d_k": d_k,
            "numerator": num,
            "denominator": 1 << 30,
            "p": p_val,
            "mean": d_mean,
            "median": d_med,
            "IQR": iqr,
            "positive_count": pos_cnt,
            "zero_count": zero_cnt,
            "negative_count": neg_cnt,
            "status": status,
        }

    # 5. Validity Criteria & Pass Counts (at b=6)
    # E1: C1: G7r cov >= ceil(0.8*|G7r|); C2: X7 cov >= 506 and X7 width <= 3*G7r width; CV = C1 and C2
    # E2: C1: G8 cov >= ceil(0.8*|G8|); V80_F: C1 and XF cov>=4289 and XF width<=3*G8 width;
    #     V80_T: C1 and XT cov>=6676 and XT width<=3*G8 width; HONEST90_F: XF cov>=4825; HONEST90_T: XT cov>=7511
    recomputed_validity: Dict[str, Dict[str, Dict[str, bool]]] = {"E1": {}, "E2": {}}
    recomputed_pass_counts: Dict[str, Dict[str, Dict[str, int]]] = {
        "E1": {m: {"CV": 0, "C1": 0, "C2": 0} for m in "AMR"},
        "E2": {
            m: {
                "C1": 0,
                "V80_F": 0,
                "V80_T": 0,
                "HONEST90_F": 0,
                "HONEST90_T": 0,
            }
            for m in "AMR"
        },
    }

    # E1 validity evaluation
    thresh_g7r = math.ceil(0.8 * len(splits["E1"]["G7r"]))
    for arm in arms_list:
        m = arm[0]
        m6 = recomputed_arms["E1"][arm]["checkpoints"][6]["metrics"]
        c1 = bool(m6["G7r"]["coverage"] >= thresh_g7r)
        c2 = bool((m6["X7"]["coverage"] >= 506) and (m6["X7"]["width"] <= 3.0 * m6["G7r"]["width"]))
        cv = bool(c1 and c2)

        recomputed_validity["E1"][arm] = {"C1": c1, "C2": c2, "CV": cv}
        if c1:
            recomputed_pass_counts["E1"][m]["C1"] += 1
        if c2:
            recomputed_pass_counts["E1"][m]["C2"] += 1
        if cv:
            recomputed_pass_counts["E1"][m]["CV"] += 1

    # E2 validity evaluation
    thresh_g8 = math.ceil(0.8 * len(splits["E2"]["G8"]))
    for arm in arms_list:
        m = arm[0]
        m6 = recomputed_arms["E2"][arm]["checkpoints"][6]["metrics"]
        c1 = bool(m6["G8"]["coverage"] >= thresh_g8)
        v80_f = bool(c1 and (m6["XF"]["coverage"] >= 4289) and (m6["XF"]["width"] <= 3.0 * m6["G8"]["width"]))
        v80_t = bool(c1 and (m6["XT"]["coverage"] >= 6676) and (m6["XT"]["width"] <= 3.0 * m6["G8"]["width"]))
        honest_f = bool(m6["XF"]["coverage"] >= 4825)
        honest_t = bool(m6["XT"]["coverage"] >= 7511)

        recomputed_validity["E2"][arm] = {
            "C1": c1,
            "V80_F": v80_f,
            "HONEST90_F": honest_f,
            "V80_T": v80_t,
            "HONEST90_T": honest_t,
        }
        if c1:
            recomputed_pass_counts["E2"][m]["C1"] += 1
        if v80_f:
            recomputed_pass_counts["E2"][m]["V80_F"] += 1
        if v80_t:
            recomputed_pass_counts["E2"][m]["V80_T"] += 1
        if honest_f:
            recomputed_pass_counts["E2"][m]["HONEST90_F"] += 1
        if honest_t:
            recomputed_pass_counts["E2"][m]["HONEST90_T"] += 1

    # Aggregate gates (pass threshold >= 26/30)
    recomputed_cv = {m: bool(recomputed_pass_counts["E1"][m]["CV"] >= 26) for m in "AMR"}
    recomputed_v80 = {
        m: {
            "F": bool(recomputed_pass_counts["E2"][m]["V80_F"] >= 26),
            "T": bool(recomputed_pass_counts["E2"][m]["V80_T"] >= 26),
        }
        for m in "AMR"
    }
    recomputed_honest90 = {
        m: {
            "F": bool(recomputed_pass_counts["E2"][m]["HONEST90_F"] >= 26),
            "T": bool(recomputed_pass_counts["E2"][m]["HONEST90_T"] >= 26),
        }
        for m in "AMR"
    }

    # Conclusions mapping (§9)
    recomputed_conclusions = {
        "M-X7": bool(
            (recomputed_hypotheses["H1"]["status"] == "rejected")
            and recomputed_cv["M"]
        ),
        "M-NI10-X7": bool(
            (recomputed_hypotheses["H2"]["status"] == "rejected")
            and recomputed_cv["M"]
            and recomputed_cv["A"]
        ),
        "A-F": bool(
            (recomputed_hypotheses["H3"]["status"] == "rejected")
            and recomputed_v80["A"]["F"]
            and recomputed_honest90["A"]["F"]
        ),
        "M-F": bool(
            (recomputed_hypotheses["H4"]["status"] == "rejected")
            and recomputed_v80["M"]["F"]
            and recomputed_honest90["M"]["F"]
        ),
        "A-T": bool(
            (recomputed_hypotheses["H5"]["status"] == "rejected")
            and recomputed_v80["A"]["T"]
            and recomputed_honest90["A"]["T"]
        ),
        "M-T": bool(
            (recomputed_hypotheses["H6"]["status"] == "rejected")
            and recomputed_v80["M"]["T"]
            and recomputed_honest90["M"]["T"]
        ),
    }

    # 6. Coverage Summary per Method/Set
    # Inspect sealed reference to determine whether coverage_summary uses count or fraction
    use_fraction = True
    if sealed_eval_file.exists():
        with open(sealed_eval_file, "r", encoding="utf-8") as f:
            sealed_eval_preview = json.load(f)
        try:
            sample_val = sealed_eval_preview["coverage_summary"]["E1"]["A"]["X7"]["mean"]
            if sample_val > 1.0:
                use_fraction = False
        except Exception:
            pass

    recomputed_coverage_summary: Dict[str, Any] = {"E1": {}, "E2": {}}
    for exp in ["E1", "E2"]:
        for m in "AMR":
            recomputed_coverage_summary[exp][m] = {}
            method_arms = [f"{m}{k}" for k in range(1, 31)]
            for s in eval_set_map[exp]:
                cov_vals = [
                    (
                        recomputed_arms[exp][arm]["checkpoints"][6]["metrics"][s][
                            "coverage_fraction"
                        ]
                        if use_fraction
                        else recomputed_arms[exp][arm]["checkpoints"][6]["metrics"][s][
                            "coverage"
                        ]
                    )
                    for arm in method_arms
                ]
                width_vals = [
                    recomputed_arms[exp][arm]["checkpoints"][6]["metrics"][s]["width"]
                    for arm in method_arms
                ]
                recomputed_coverage_summary[exp][m][s] = {
                    "mean": float(np.mean(cov_vals)),
                    "minimum": (
                        float(np.min(cov_vals)) if use_fraction else int(np.min(cov_vals))
                    ),
                    "maximum": (
                        float(np.max(cov_vals)) if use_fraction else int(np.max(cov_vals))
                    ),
                    "per_arm": [
                        (float(v) if use_fraction else int(v)) for v in cov_vals
                    ],
                    "width": {
                        "mean": float(np.mean(width_vals)),
                        "minimum": float(np.min(width_vals)),
                        "maximum": float(np.max(width_vals)),
                    },
                }

    # 7. Comparison with sealed official files
    comparator = IndependentComparator(abs_tol=1e-6, rel_tol=1e-9)

    # 7a. Calibration comparison
    with open(sealed_cal_file, "r", encoding="utf-8") as f:
        sealed_cal = json.load(f)

    for exp in ["E1", "E2"]:
        for arm in arms_list:
            s_qs = sealed_cal["calibration"][exp][arm]
            c_qs = cal_qs_recomputed[exp][arm]
            for b in range(7):
                comparator.compare(
                    "calibration_q", f"{exp}/{arm}/b{b}", c_qs[b], s_qs[b]
                )

    # 7b. Primary evaluation comparison
    with open(sealed_eval_file, "r", encoding="utf-8") as f:
        sealed_eval = json.load(f)

    for exp in ["E1", "E2"]:
        for arm in arms_list:
            for b in range(7):
                s_ckpt = sealed_eval["arms"][exp][arm]["checkpoints"][b]
                c_ckpt = recomputed_arms[exp][arm]["checkpoints"][b]
                comparator.compare(
                    "checkpoint_q", f"{exp}/{arm}/b{b}/q", c_ckpt["q"], s_ckpt["q"]
                )
                for s in eval_set_map[exp]:
                    for m_key, c_mval in c_ckpt["metrics"][s].items():
                        s_mval = s_ckpt["metrics"][s][m_key]
                        comparator.compare(
                            "checkpoint_metrics",
                            f"{exp}/{arm}/b{b}/{s}/{m_key}",
                            c_mval,
                            s_mval,
                        )

    # Hypotheses comparison
    for h_name in ["H1", "H2", "H3", "H4", "H5", "H6"]:
        s_h = sealed_eval["hypotheses"][h_name]
        c_h = recomputed_hypotheses[h_name]
        for k_idx in range(30):
            comparator.compare(
                "hypotheses_d_k",
                f"{h_name}/d_{k_idx+1}",
                c_h["d_k"][k_idx],
                s_h["d_k"][k_idx],
            )
        comparator.compare("hypotheses_test", f"{h_name}/numerator", c_h["numerator"], s_h["numerator"])
        comparator.compare("hypotheses_test", f"{h_name}/denominator", c_h["denominator"], s_h["denominator"])
        comparator.compare("hypotheses_test", f"{h_name}/p", c_h["p"], s_h["p"])
        comparator.compare("hypotheses_test", f"{h_name}/status", c_h["status"], s_h["status"])
        for stat_key in ["mean", "median", "IQR", "positive_count", "zero_count", "negative_count"]:
            comparator.compare(
                "hypotheses_stats", f"{h_name}/{stat_key}", c_h[stat_key], s_h[stat_key]
            )

    # Validity comparison
    for exp in ["E1", "E2"]:
        for arm in arms_list:
            s_v = sealed_eval["validity"][exp][arm]
            c_v = recomputed_validity[exp][arm]
            for v_key in s_v:
                comparator.compare("validity", f"{exp}/{arm}/{v_key}", c_v[v_key], s_v[v_key])

    # Pass counts comparison
    for exp in ["E1", "E2"]:
        for m in "AMR":
            s_vpc = sealed_eval["validity_pass_counts"][exp][m]
            c_vpc = recomputed_pass_counts[exp][m]
            for vpc_key in s_vpc:
                comparator.compare(
                    "validity_pass_counts", f"{exp}/{m}/{vpc_key}", c_vpc[vpc_key], s_vpc[vpc_key]
                )

    # Gate booleans comparison
    for m in "AMR":
        comparator.compare("validity_gates", f"CV/{m}", recomputed_cv[m], sealed_eval["CV"][m])
        for sub in ["F", "T"]:
            comparator.compare(
                "validity_gates", f"V80/{m}/{sub}", recomputed_v80[m][sub], sealed_eval["V80"][m][sub]
            )
            comparator.compare(
                "validity_gates",
                f"HONEST90/{m}/{sub}",
                recomputed_honest90[m][sub],
                sealed_eval["HONEST90"][m][sub],
            )

    # Conclusions comparison
    for c_key in ["M-X7", "M-NI10-X7", "A-F", "M-F", "A-T", "M-T"]:
        comparator.compare(
            "conclusions", f"conclusions/{c_key}", recomputed_conclusions[c_key], sealed_eval["conclusions"][c_key]
        )

    # Coverage summary comparison
    for exp in ["E1", "E2"]:
        for m in "AMR":
            for s in eval_set_map[exp]:
                s_cs = sealed_eval["coverage_summary"][exp][m][s]
                c_cs = recomputed_coverage_summary[exp][m][s]
                for cs_k in ["mean", "minimum", "maximum"]:
                    comparator.compare(
                        "coverage_summary", f"{exp}/{m}/{s}/{cs_k}", c_cs[cs_k], s_cs[cs_k]
                    )
                if "per_arm" in s_cs:
                    for k_idx in range(30):
                        comparator.compare(
                            "coverage_summary",
                            f"{exp}/{m}/{s}/per_arm/{k_idx}",
                            c_cs["per_arm"][k_idx],
                            s_cs["per_arm"][k_idx],
                        )
                if "width" in s_cs:
                    for w_k in ["mean", "minimum", "maximum"]:
                        comparator.compare(
                            "coverage_summary",
                            f"{exp}/{m}/{s}/width/{w_k}",
                            c_cs["width"][w_k],
                            s_cs["width"][w_k],
                        )

    # 8. Compute per-arm final metrics and per-method means
    per_arm_final_metrics: Dict[str, Dict[str, Dict[str, Any]]] = {"E1": {}, "E2": {}}
    coverage_counts_per_arm: Dict[str, Dict[str, Dict[str, int]]] = {"E1": {}, "E2": {}}
    csv_rows: List[Dict[str, Any]] = []

    for exp in ["E1", "E2"]:
        for arm in arms_list:
            m = arm[0]
            k = int(arm[1:])
            q_final = recomputed_arms[exp][arm]["checkpoints"][6]["q"]
            per_arm_final_metrics[exp][arm] = {}
            coverage_counts_per_arm[exp][arm] = {}

            for s in eval_set_map[exp]:
                met = recomputed_arms[exp][arm]["checkpoints"][6]["metrics"][s]
                per_arm_final_metrics[exp][arm][s] = met
                coverage_counts_per_arm[exp][arm][s] = met["coverage"]

                csv_rows.append(
                    {
                        "exp": exp,
                        "arm": arm,
                        "method": m,
                        "k": k,
                        "set": s,
                        "q": q_final,
                        "n": met["n"],
                        "coverage": met["coverage"],
                        "coverage_fraction": met["coverage_fraction"],
                        "width": met["width"],
                        "winkler": met["winkler"],
                        "relative_error": met["relative_error"],
                        "mae": met["mae"],
                        "bias": met["bias"],
                    }
                )

    per_method_means_final: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {
        "E1": {},
        "E2": {},
    }
    for exp in ["E1", "E2"]:
        for m in "AMR":
            per_method_means_final[exp][m] = {}
            method_arms = [f"{m}{k}" for k in range(1, 31)]
            for s in eval_set_map[exp]:
                per_method_means_final[exp][m][s] = {}
                metric_keys = [
                    "coverage",
                    "coverage_fraction",
                    "width",
                    "winkler",
                    "relative_error",
                    "mae",
                    "bias",
                    "nominal90_shortfall",
                ]
                for m_k in metric_keys:
                    vals = [
                        per_arm_final_metrics[exp][arm][s][m_k] for arm in method_arms
                    ]
                    per_method_means_final[exp][m][s][m_k] = float(np.mean(vals))

    # 9. Write outputs
    out_dir.mkdir(parents=True, exist_ok=True)

    recompute_report = {
        "hypotheses": recomputed_hypotheses,
        "validity": recomputed_validity,
        "validity_pass_counts": recomputed_pass_counts,
        "CV": recomputed_cv,
        "V80": recomputed_v80,
        "HONEST90": recomputed_honest90,
        "conclusions": recomputed_conclusions,
        "per_arm_final_metrics": per_arm_final_metrics,
        "per_method_means_final_metrics": per_method_means_final,
        "coverage_counts_per_arm": coverage_counts_per_arm,
        "coverage_summary": recomputed_coverage_summary,
        "arms": recomputed_arms,
        "comparison_summary": {
            "total_comparisons": comparator.total_comparisons,
            "mismatch_count": len(comparator.mismatches),
            "max_abs_diff_by_category": comparator.max_abs_diff_by_category,
            "first_20_mismatches": comparator.mismatches[:20],
            "verified": len(comparator.mismatches) == 0,
        },
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(recompute_report, f, indent=2)

    pd.DataFrame(csv_rows).to_csv(out_csv, index=False)

    # 10. Console reporting and exit code
    print("=" * 60)
    print("INDEPENDENT RECOMPUTATION AUDIT COMPLETE")
    print(f"Total comparisons executed: {comparator.total_comparisons}")
    print(f"Total mismatches: {len(comparator.mismatches)}")
    print("Max absolute difference by category:")
    for cat, diff in comparator.max_abs_diff_by_category.items():
        print(f"  - {cat:<24}: {diff:.3e}")

    if comparator.mismatches:
        print("\nFirst mismatches encountered:")
        for mm in comparator.mismatches[:20]:
            print(f"  * {mm}")
        print("=" * 60)
        sys.exit(1)
    else:
        print("\nSUCCESS: All recomputed values match sealed evaluation within tolerance.")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
