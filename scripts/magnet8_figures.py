"""Five Chinese figures from sealed summaries; no model imports or recomputation."""
import argparse
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT/'lab/cases/magnet8'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render(metrics_path, out, require_seal=True):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    metrics_path, out = Path(metrics_path), Path(out)
    # Refuse output inside any sealed first* tree, even with a custom --out.
    resolved = out.resolve()
    sealed_roots = [p.resolve() for p in STAGE.glob('first*') if p.is_dir()]
    sealed_roots.append(metrics_path.parent.resolve())
    if any(resolved == p or p in resolved.parents for p in sealed_roots):
        raise ValueError('图像输出不能写入封存 first* 目录')
    if require_seal:
        seals = read_json(metrics_path.parent/'EVALUATED')
        assert seals['metrics.json'] == sha(metrics_path)
    m = read_json(metrics_path)
    font_path = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font_path)).get_name()
    else:
        plt.rcParams['font.family'] = ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    out.mkdir(parents=True, exist_ok=True)
    colors = dict(A='#2677b5', M='#df7622', R='#37946e')
    panels = [('E1', 'X7'), ('E2', 'XF'), ('E2', 'XT')]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.7))
    for ax, (exp, region) in zip(axes, panels):
        for k in range(1, 31):
            ax.plot(range(3), [m['arms'][exp][f'{x}{k}']['metrics'][region]['winkler'] for x in 'AMR'], 'o-', lw=.7, ms=3, alpha=.5)
        ax.set_xticks(range(3), ['主动 A', '混合 M', '随机 R'])
        ax.set(title=f'{exp} {region}：30 组配对', ylabel='平均 Winkler（log10 单位）')
    fig.tight_layout()
    fig.savefig(out/'r8_pairs.png', dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for ax, (exp, region) in zip(axes.flat, [('E1', 'X7'), ('E1', 'G7r'), ('E2', 'G8'), ('E2', 'XF'), ('E2', 'XT'), ('E2', 'XFT')]):
        for j, method in enumerate('AMR'):
            y = [m['arms'][exp][f'{method}{k}']['metrics'][region]['coverage_fraction'] for k in range(1, 31)]
            ax.scatter(np.arange(1, 31)+j*32, y, s=16, color=colors[method], label=method)
        ax.axhline(.8, ls='--', color='gray', label='80% 工程底线')
        ax.axhline(.9, ls=':', color='crimson', label='90% 名义覆盖')
        ax.set_xticks([15, 47, 79], ['主动 A', '混合 M', '随机 R'])
        ax.set(title=f'{exp} {region}'+('（只报告）' if region == 'XFT' else ''), ylabel='逐臂覆盖率', ylim=(0, 1.02))
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out/'r8_coverage.png', dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    for ax, (exp, region) in zip(axes[0], panels):
        for method in 'AMR':
            curve = m['learning_curves'][exp][method][region]['winkler']
            ax.plot(np.arange(7)*20, curve['mean'], color=colors[method], label=method)
            ax.fill_between(np.arange(7)*20, curve['minimum'], curve['maximum'], color=colors[method], alpha=.15)
        ax.set(title=f'{exp} {region}', xlabel='新增点数', ylabel='平均 Winkler：均值与最小–最大')
        ax.legend()
    frequencies = [50, 56, 63, 71, 79, 89, 100, 112, 126, 141, 159, 178, 199, 224, 251, 282]
    temperatures = [25, 50, 70]
    arrays = []
    for method in 'AMR':
        counts = m['sampling_counts']['E2'][method]['additions']['fset_T']
        arrays.append(np.array([[counts.get(f'{f}|{t}', 0) for f in frequencies] for t in temperatures]))
    maximum = max(float(a.max()) for a in arrays)
    for ax, method, data in zip(axes[1], 'AMR', arrays):
        im = ax.imshow(data, aspect='auto', vmin=0, vmax=max(1, maximum), cmap='YlGnBu')
        ax.set_xticks(range(len(frequencies)), frequencies, rotation=70)
        ax.set_yticks(range(3), temperatures)
        ax.set(title=f'E2 {method}：30 臂新增采点合计（S0 另列于数据）', xlabel='频率设定点（kHz）', ylabel='温度（°C）')
        fig.colorbar(im, ax=ax, label='新增点数')
    fig.tight_layout()
    fig.savefig(out/'r8_learning_sampling.png', dpi=180)
    plt.close(fig)

    # Each panel retains its own scale; H2 is the shifted noninferiority contrast.
    specs = [('H1', 'E1 X7：W_R−W_M'), ('H2', 'E1 X7：1.10W_A−W_M'),
             ('H3', 'E2 XF：W_R−W_A'), ('H4', 'E2 XF：W_R−W_M'),
             ('H5', 'E2 XT：W_R−W_A'), ('H6', 'E2 XT：W_R−W_M')]
    statuses = {'rejected': '正式拒绝', 'not_rejected': '未拒绝', 'not_tested': '未检验'}
    conclusion_keys = dict(zip([x[0] for x in specs],
                               ['M-X7', 'M-NI10-X7', 'A-F', 'M-F', 'A-T', 'M-T']))
    fig, axes = plt.subplots(2, 3, figsize=(17, 9))
    for ax, (hyp, label) in zip(axes.flat, specs):
        test = m['hypotheses'][hyp]
        d = np.asarray(test['d_k'], dtype=float)
        # Deterministic offsets: no new experimental randomness.
        offsets = np.linspace(-.19, .19, len(d))
        ax.boxplot([d], positions=[0], widths=.55, showfliers=False,
                   medianprops={'color': '#222222', 'linewidth': 1.8})
        ax.scatter(offsets, d, c=np.where(d > 0, '#2677b5', '#c54444'),
                   edgecolors='white', linewidths=.4, s=32, zorder=3)
        ax.scatter([.4], [d.mean()], marker='D', color='#df7622', label='差值均值')
        ax.axhline(0, color='gray', ls='--', lw=1)
        ax.set_xticks([])
        ax.set(xlim=(-.6, .65), ylabel='配对差 d_k（log10 单位）',
               title=f'{hyp} {label}\np={test["numerator"]}/2^{len(d)}={test["p"]:.3g}；'
                     f'{statuses.get(test["status"], test["status"])}')
        key = conclusion_keys[hyp]
        ax.text(.02, .97, f'最终结论：{key} '+('成立' if m['conclusions'][key] else '不成立'),
                transform=ax.transAxes, va='top', fontsize=9)
        ax.margins(y=.2)
        ax.legend(loc='lower right', fontsize=8)
    fig.suptitle('固定顺序检验：每图全部配对组；箱体为四分位区间（H2 仅检验非劣）', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(out/'r8_effects.png', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(13, 10), sharex=True, sharey=True)
    for ax, region in zip(axes.flat, ['XF', 'XT', 'XFT', 'G8']):
        for method, marker in zip('AMR', ['o', 's', '^']):
            records = [m['arms']['E2'][f'{method}{k}']['metrics'][region] for k in range(1, 31)]
            ax.scatter([v['bias'] for v in records], [v['coverage_fraction'] for v in records],
                       color=colors[method], marker=marker, s=30, alpha=.7, label=method)
        ax.axvline(0, color='gray', lw=1)
        ax.axhline(.9, color='crimson', ls=':', label='90% 名义覆盖')
        ax.axhline(.8, color='gray', ls='--', label='80% 参考线')
        ax.set(title=f'E2 {region}'+('（只报告）' if region=='XFT' else ''),
               xlabel='逐臂偏差 mean(预测 log10 − 实测 log10)', ylabel='逐臂覆盖率', ylim=(0,1.02))
        ax.legend(fontsize=8, loc='lower right')
        ax.grid(alpha=.15)
    fig.suptitle('负偏差与欠覆盖的描述性关系：每点一臂，不作相关性或机理检验', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(out/'r8_bias.png', dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--metrics', type=Path, default=STAGE/'first/metrics.json')
    ap.add_argument('--out', type=Path, default=ROOT/'docs/figures')
    args = ap.parse_args()
    render(args.metrics, args.out)
