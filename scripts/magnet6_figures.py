#!/usr/bin/env python3
"""Chinese figures from the sealed summary; no raw target access."""
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
from magnet6_design import ROOT, STAGE


def render(metrics_path, out):
    m = json.loads(Path(metrics_path).read_text())
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus'] = False
    out.mkdir(parents=True, exist_ok=True)
    colors = dict(A='#2474b5', M='#df7622', R='#4b9956')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for k in range(1, 9):
        values = [m['arms'][f'{x}{k}']['metrics']['C6'] for x in 'AMR']
        axes[0].plot(range(3), [v['winkler'] for v in values], 'o-', label=f'配对 {k}', alpha=.8)
        axes[1].plot(range(3), [v['coverage'] for v in values], 'o-', alpha=.8)
    for ax in axes:
        ax.set_xticks(range(3), ['主动 A', '混合 M', '随机 R'])
    axes[0].set_ylabel('角落平均 Winkler（log10 单位）')
    axes[1].set_ylabel('角落覆盖数（共 200）')
    axes[1].axhline(160, color='gray', linestyle='--', label='有效性门限')
    axes[0].legend(ncol=2)
    fig.tight_layout(); fig.savefig(out / 'r6_corner_pairs.png', dpi=180); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, dataset, title in zip(axes, ('C6', 'T6'), ('角落 C6', '分布内 T6')):
        for x, label in zip('AMR', ('主动 A', '混合 M', '随机 R')):
            curve = m['learning_curves'][x][dataset]['winkler']
            added = np.arange(7) * 20
            ax.plot(added, curve['mean'], label=label, color=colors[x])
            ax.fill_between(added, curve['minimum'], curve['maximum'], alpha=.15, color=colors[x])
        ax.set(title=title, xlabel='新增采样点数', ylabel='平均 Winkler（均值及最小—最大范围）')
        ax.legend()
    fig.tight_layout(); fig.savefig(out / 'r6_learning_curves.png', dpi=180); plt.close(fig)
    names = [f'{x}{k}' for k in range(1, 9) for x in 'AMR']
    cells = sorted(set().union(*(set(m['arms'][a]['sampling']['cells']) for a in names)))
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    axes[0].bar(names, [m['arms'][a]['sampling']['corner_count'] for a in names], color=[colors[a[0]] for a in names])
    axes[0].set_ylabel('角落新增采样点数')
    bottom = np.zeros(len(names))
    for cell in cells:
        v = np.array([m['arms'][a]['sampling']['cells'].get(cell, 0) for a in names])
        axes[1].bar(names, v, bottom=bottom, label=cell, color=plt.get_cmap('tab20')(cells.index(cell)))
        bottom += v
    axes[1].set_ylabel('单元采样点数（不含初始集）')
    axes[1].legend(ncol=6, fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.08))
    fig.tight_layout(); fig.savefig(out / 'r6_sampling.png', dpi=180); plt.close(fig)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--metrics', type=Path, default=STAGE / 'first/metrics.json')
    ap.add_argument('--out', type=Path, default=ROOT / 'docs/figures')
    args = ap.parse_args()
    render(args.metrics, args.out)
