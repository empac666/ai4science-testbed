"""Offline recomputation from published predictions, without model fitting."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def recheck(case):
    folder = ROOT / 'lab/cases' / case
    stored = json.loads((folder / 'surrogate_metrics.json').read_text())
    frame = pd.read_csv(folder / 'predictions.csv', float_precision='round_trip')
    dimensions = [x for x in ('arm', 'method', 'sensor', 'split') if x in frame]
    comparisons = 0
    for values, rows in frame.groupby(dimensions):
        labels = dict(zip(dimensions, values))
        group = labels['split']
        if labels.get('sensor') == 'nonideal':
            group = 'nonideal_' + group
        prefix = '.'.join([labels[x] for x in ('arm', 'method') if x in labels] + [group])
        y, pred, lo, hi = (rows[x].to_numpy() for x in ('y', 'prediction', 'lower', 'upper'))
        covered = int(((y >= lo) & (y <= hi)).sum())
        err = pred - y
        values = dict(n=len(y), covered=covered, coverage=covered / len(y),
                      mean_width=float(np.mean(hi-lo)), mae=float(np.mean(abs(err))),
                      max_abs_error=float(np.max(abs(err))), bias=float(np.mean(err)),
                      mean_winkler=float(np.mean(hi-lo+20*np.maximum(lo-y, 0)+20*np.maximum(y-hi, 0))))
        for metric, value in values.items():
            key = prefix + '.' + metric
            if key in stored:
                expected = stored[key]
                if metric in ('n', 'covered'):
                    assert value == expected, (case, key, value, expected)
                else:
                    assert np.isclose(value, expected, rtol=1e-10, atol=1e-10), (case, key, value, expected)
                comparisons += 1
    assert comparisons > 0
    return dict(prediction_rows=len(frame), metric_comparisons=comparisons)


def main():
    results = {case: recheck(case) for case in ('dclink', 'dclink2', 'dclink3', 'dclink4', 'dclink5')}
    # This validates existing R8 summaries; it does not rerun historical independent recomputation.
    from m9_report_tables import build_sections
    sections = build_sections()
    results['magnet8'] = dict(summary_sections_checked=len(sections))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
