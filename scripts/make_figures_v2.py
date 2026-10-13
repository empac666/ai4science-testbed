#!/usr/bin/env python3
"""Redraw the four R9 figures from the sealed metrics file.

Does not rewrite seals or figure_manifest.json.
"""
import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "lab" / "cases" / "magnet9" / "first" / "metrics.json"
SOURCE = "lab/cases/magnet9/first/metrics.json"
OUT = ROOT / "docs" / "figures"
NAVY, ORANGE, GREEN, RED, GRAY = "#1f4e79", "#e07b39", "#3a9a5b", "#b23a48", "#6b7280"
COLORS = {"B": NAVY, "E": ORANGE, "D": GREEN}
METHODS = ("B", "E", "D")
TICKS = ["B\n全局 global", "E\n方向 directional", "D\n平移 shift"]


def use_cjk():
    from matplotlib import font_manager

    listed = subprocess.check_output(["fc-list", "Noto Sans CJK SC", "file"], text=True)
    paths = [line.split(":")[0].strip() for line in listed.splitlines() if line.strip()]
    if not paths:
        raise SystemExit("Noto Sans CJK SC is not installed")
    for path in paths:
        font_manager.fontManager.addfont(path)
    plt.rcParams.update({
        "font.family": "Noto Sans CJK SC",
        "font.weight": "regular",
        "axes.titleweight": "regular",
        "axes.labelweight": "regular",
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#333333",
        "text.color": "#222222",
        "axes.labelcolor": "#222222",
        "xtick.color": "#222222",
        "ytick.color": "#222222",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 8,
    })


def strip_png_text(path):
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"not a png: {path.name}")
    out = bytearray(data[:8])
    i = 8
    while i + 8 <= len(data):
        length = int.from_bytes(data[i:i + 4], "big")
        ctype = data[i + 4:i + 8]
        end = i + 12 + length
        if ctype not in (b"tEXt", b"iTXt", b"zTXt"):
            out += data[i:end]
        i = end
        if ctype == b"IEND":
            break
    Path(path).write_bytes(out)
    width = int.from_bytes(out[16:20], "big")
    if width != 1600:
        raise SystemExit(f"{path.name} width {width} != 1600")


def save_png(fig, name):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    strip_png_text(path)


def require_arms(metrics):
    for prefix in ("U", "S"):
        for k in range(1, 31):
            key = f"{prefix}{k:02d}"
            if key not in metrics["arms"]:
                raise SystemExit(f"missing arm {key}")


def fig_metric(metrics, metric, filename, ylabel, title, log=False):
    fig, axes = plt.subplots(2, 2, figsize=(8.0, 7.0))
    for i, split in enumerate(("U", "S")):
        for j, zone in enumerate(("XF", "XT")):
            ax = axes[i, j]
            for k in range(1, 31):
                values = [metrics["arms"][f"{split}{k:02d}"][method][zone][metric] for method in METHODS]
                ax.plot(range(3), values, color=GRAY, alpha=0.28, lw=0.6, zorder=1)
            for x, method in enumerate(METHODS):
                values = np.array([metrics["arms"][f"{split}{k:02d}"][method][zone][metric] for k in range(1, 31)])
                ax.scatter(np.full(30, x), values, color=COLORS[method], alpha=0.75, s=12, zorder=2)
                ax.scatter([x], [values.mean()], marker="D", color="#222222", s=28, zorder=3)
            ax.set_xticks(range(3), TICKS, fontsize=7)
            ax.set_title(f"{split} / {zone}（30 条配对轨迹 30 paired）", fontsize=8)
            ax.set_ylabel(ylabel, fontsize=7)
            ax.grid(axis="y", color="#e5e7eb")
            ax.set_axisbelow(True)
            if metric == "c":
                ax.axhline(0.9, color=RED, ls="--", lw=0.9)
                ax.axhline(0.8, color=GRAY, ls=":", lw=0.8)
                ax.set_ylim(0, 1.03)
            else:
                ax.set_yscale("log")
    fig.suptitle(title, fontsize=11)
    fig.text(0.01, 0.008, "点为各臂，黑菱形为均值。 Dots are arms; black diamonds are means。  "
             f"数据来源 Source: {SOURCE}", fontsize=7, color=GRAY)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.88, bottom=0.08, hspace=0.38, wspace=0.28)
    save_png(fig, filename)


def fig_pairs(metrics):
    fig, axes = plt.subplots(2, 2, figsize=(8.0, 6.4))
    status_en = {"rejected": "拒绝 rejected", "not_rejected": "未拒绝 not rejected"}
    for ax, name in zip(axes.flat, ("H1", "H2", "H3", "H4")):
        test = metrics["hypotheses"][name]
        values = np.array(test["differences"]["values"], dtype=float)
        if len(values) != 30:
            raise SystemExit(f"{name} has {len(values)} differences")
        ax.axhline(0, color=GRAY, lw=0.8)
        ax.scatter(np.arange(1, 31), values, c=np.where(values >= 0, GREEN, RED), s=16)
        ax.axhline(values.mean(), color="#222222", ls="--", lw=0.9)
        shown = status_en.get(test["status"], test["status"])
        ax.set_title(f"{name} / {test['region']}   p={test['p']:.4g}  {shown}", fontsize=8)
        ax.set_xlabel("配对组 Matched group k", fontsize=7)
        ylabel = "配对差 g_B − g_D" if name in ("H1", "H2") else "配对差 1.10 W_B − W_D"
        ax.set_ylabel(ylabel, fontsize=7)
        ax.grid(axis="y", color="#e5e7eb")
        ax.set_axisbelow(True)
        ax.text(0.98, 0.95, f"均值 mean {values.mean():.4g}", transform=ax.transAxes,
                ha="right", va="top", fontsize=7)
    fig.suptitle("预注册配对差（仅 U；正值偏向 D）\nPrespecified paired differences (U only; positive favors D)", fontsize=11)
    fig.text(0.01, 0.006, f"数据来源 Source: {SOURCE}", fontsize=7, color=GRAY)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.08, hspace=0.42, wspace=0.32)
    save_png(fig, "r9_pairs.png")


def fig_s0(metrics):
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 4.4))
    for ax, zone in zip(axes, ("XF", "XT")):
        for k in range(1, 31):
            ys = [metrics["arms"][f"{split}{k:02d}"]["D"][zone]["c"] for split in ("U", "S")]
            ax.plot([0, 1], ys, color=GREEN, alpha=0.35, marker="o", ms=3)
        block = metrics["S0"][zone]
        ax.set_xticks([0, 1], ["U 均匀\nuniform", "S 均衡\nbalanced"], fontsize=8)
        ax.set_ylim(0, 1.02)
        ax.axhline(0.9, color=RED, ls="--", lw=0.9)
        ax.set_title(f"{zone}：方差比 S/U = {block['ratio']:.3g}\nVariance ratio S/U = {block['ratio']:.3g}", fontsize=8)
        ax.set_ylabel("D 的经验覆盖率\nD empirical coverage", fontsize=7)
        ax.grid(axis="y", color="#e5e7eb")
        ax.set_axisbelow(True)
    fig.suptitle("S0 策略对照（仅描述） S0 policy contrast (descriptive only)", fontsize=11)
    fig.text(0.01, 0.01, f"数据来源 Source: {SOURCE}", fontsize=7, color=GRAY)
    fig.subplots_adjust(left=0.10, right=0.94, top=0.82, bottom=0.20, wspace=0.32)
    save_png(fig, "r9_s0.png")


def main():
    use_cjk()
    if not METRICS.is_file():
        raise SystemExit(f"missing {SOURCE}")
    stage = METRICS.parent
    for name in ("EVALUATED.json", "RECOMPUTED.json"):
        if not (stage / name).is_file():
            raise SystemExit(f"missing seal {name}")
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    require_arms(metrics)
    fig_metric(metrics, "c", "r9_coverage.png", "经验覆盖率\nEmpirical coverage",
               "R9 覆盖率 Coverage")
    fig_metric(metrics, "W", "r9_winkler.png", "平均 Winkler（对数轴）\nMean Winkler (log axis)",
               "R9 Winkler 分数（越小越好） Winkler score (smaller is better)", log=True)
    fig_pairs(metrics)
    fig_s0(metrics)
    for name in ("r9_coverage.png", "r9_winkler.png", "r9_pairs.png", "r9_s0.png"):
        print(f"wrote docs/figures/{name}")


if __name__ == "__main__":
    main()
