#!/usr/bin/env python3
"""Chinese round-seven figures from sealed results and input-only design."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from magnet7_design import ROOT, STAGE, load_design, config


def render(metrics_path, out, design=None):
    config()
    m = json.loads(Path(metrics_path).read_text())
    df, split = load_design() if design is None else design
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus'] = False
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    colors = dict(A='#2474b5', M='#df7622', R='#4b9956')
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for k in range(1, 21):
        for ax, dataset, metric in zip(axes, ('X7', 'G7', 'X7'), ('winkler', 'winkler', 'coverage')):
            ax.plot(range(3), [m['arms'][f'{x}{k}']['metrics'][dataset][metric] for x in 'AMR'], 'o-', alpha=.65)
    for ax, title in zip(axes, ('外推区 X7：平均 Winkler', '新激励族 G7：平均 Winkler', '外推区 X7：覆盖数（共 632）')):
        ax.set_xticks(range(3), ['主动 A', '混合 M', '随机 R'])
        ax.set_title(title)
    for ax in axes[:2]:
        ax.set_ylabel('平均 Winkler（log10 单位）')
    axes[2].axhline(506, color='gray', linestyle='--', label='有效性门限 506')
    axes[2].legend()
    fig.tight_layout()
    fig.savefig(out / 'r7_pairs.png', dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, dataset, title in zip(axes, ('X7', 'G7'), ('外推区 X7', '新激励族 G7')):
        for x, label in zip('AMR', ('主动 A', '混合 M', '随机 R')):
            curve = m['learning_curves'][x][dataset]['winkler']
            added = np.arange(7) * 20
            ax.plot(added, curve['mean'], label=label, color=colors[x])
            ax.fill_between(added, curve['minimum'], curve['maximum'], alpha=.15, color=colors[x])
        ax.set(title=title, xlabel='新增采样点数', ylabel='平均 Winkler（均值及最小—最大范围）')
        ax.legend()
    fig.tight_layout()
    fig.savefig(out / 'r7_learning_curves.png', dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={'width_ratios': [2, 1]})
    ax = axes[0]
    def points(ids, **kwargs):
        ax.scatter(df.loc[ids, 'log10_f'], df.loc[ids, 'log10_Bpk'], **kwargs)
    points(split['pool'], s=4, c='lightgray', label='候选池', rasterized=True)
    points(split['S0_1'], s=24, c='black', marker='x', label='初始集 S0（k=1）')
    for method, marker in zip('AMR', ('o', '^', 's')):
        points(m['arms'][f'{method}1']['selected_ids'], s=30, facecolors='none', edgecolors=colors[method], marker=marker, label=f'{method} 新增（k=1）')
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    xf, yb = np.log10(200000), np.log10(.10)
    ax.plot([xf, xf, xmax], [ymax, yb, yb], '--', color='crimson', label='X7 区域边界')
    ax.fill_between([xf, xmax], yb, ymax, color='crimson', alpha=.06)
    ax.set(xlim=(xmin, xmax), ylim=(ymin, ymax), xlabel='log10 频率 f（Hz）', ylabel='log10 磁通密度 Bpk（T）')
    ax.legend(fontsize=8)
    axes[1].boxplot([[m['arms'][f'{x}{k}']['sampling']['frontier_count'] for k in range(1, 21)] for x in 'AMR'], tick_labels=['主动 A', '混合 M', '随机 R'])
    axes[1].set_ylabel('前沿新增点数（20 组配对）')
    fig.tight_layout()
    fig.savefig(out / 'r7_sampling.png', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--metrics', type=Path, default=STAGE / 'first/metrics.json')
    ap.add_argument('--out', type=Path, default=ROOT / 'docs/figures')
    args = ap.parse_args()
    render(args.metrics, args.out)
