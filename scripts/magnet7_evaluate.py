#!/usr/bin/env python3
"""Seal a complete, audited 60-arm analysis. Never invoked for implementation."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from magnet7_design import OUT, STAGE, SOURCE, CONFIG_SHA, digest, sha, write_json, atomic, load_design, config

CONFIG = config()
from magnet6_model import (FEATURES,
                           make_kernel, believer, mixed_believer)
from magnet7_arm import CONFIG, evaluation_frame, holdouts, code_hashes, validate_batch, sampling_stats


def signflip_p(d, chunk_size=32768):
    """Exact enumeration with vectorized chunks; numpy row sums match legacy means."""
    d = np.asarray(d, dtype=float)
    assert d.ndim == 1 and 0 < len(d) <= 20 and np.isfinite(d).all()
    assert chunk_size > 0
    shifts = np.arange(len(d)-1, -1, -1, dtype=np.uint32)
    hits = 0
    for start in range(0, 2 ** len(d), chunk_size):
        bits = (np.arange(start, min(start+chunk_size, 2 ** len(d)), dtype=np.uint32)[:, None] >> shifts) & 1
        signs = bits.astype(np.int8)*2 - 1
        hits += int(np.count_nonzero(np.mean(signs*d, axis=1) >= d.mean()-1e-12))
    return hits / 2 ** len(d)


def fixed_sequence(results):
    active, output = True, {}
    for h in CONFIG['tests']['order']:
        p = results[h]['p'] if isinstance(results[h], dict) else results[h]
        assert 0 <= p <= 1
        status = ('rejected' if p < .05 else 'not_rejected') if active else 'not_tested'
        output[h] = status
        active = active and status == 'rejected'
    return output


def aggregate(results):
    """Pure summary function, also exercised on synthetic results."""
    def values(method, dataset, metric):
        return np.array([results[f'{method}{k}']['metrics'][dataset][metric] for k in range(1, 21)])
    a, m, r = [values(x, 'X7', 'winkler') for x in 'AMR']
    ti = {x: values(x, 'G7', 'winkler') for x in 'AMR'}
    differences = [r-a, ti['R']-ti['A'], values('R', 'X7', 'relative_error')-values('A', 'X7', 'relative_error'),
                   r-m, 1.10*a-m]
    hypotheses = {f'H{i+1}': dict(d_k=d.tolist(), p=signflip_p(d), mean=float(d.mean()),
                                 median=float(np.median(d)), IQR=float(np.percentile(d, 75)-np.percentile(d, 25)),
                                 positive_count=int(np.sum(d > 0))) for i, d in enumerate(differences)}
    statuses = fixed_sequence(hypotheses)
    for h, status in statuses.items():
        hypotheses[h]['status'] = status
    validity = {}
    for arm, result in results.items():
        x, g = result['metrics']['X7'], result['metrics']['G7']
        validity[arm] = dict(C1=g['coverage'] >= int(np.ceil(.8*g['n'])),
                             C2=x['coverage'] >= 506 and x['width'] <= 3*g['width'])
    counts = {x: sum(all(validity[f'{x}{k}'].values()) for k in range(1, 21)) for x in 'AMR'}
    cv = {x: counts[x] >= 17 for x in 'AMR'}
    passed = lambda h: statuses[h] == 'rejected'
    conclusions = {'A-X': passed('H1') and cv['A'], 'A-G': passed('H2') and cv['A'],
                   'A-RE': passed('H3'), 'M-X': passed('H4') and cv['M'], 'M≈A': passed('H5')}
    curves = {}
    for x in 'AMR':
        curves[x] = {}
        for dataset in ('X7', 'G7'):
            curves[x][dataset] = {}
            for metric in ('winkler', 'coverage', 'width', 'relative_error', 'mae', 'bias'):
                data = np.array([[p['metrics'][dataset][metric] for p in results[f'{x}{k}']['checkpoints']] for k in range(1, 21)])
                curves[x][dataset][metric] = dict(mean=data.mean(axis=0).tolist(), minimum=data.min(axis=0).tolist(), maximum=data.max(axis=0).tolist())
    sampling = {}
    for method in 'AMR':
        samples = [results[f'{method}{k}']['sampling'] for k in range(1, 21)]
        front = np.array([v['frontier_count'] for v in samples])
        sampling[method] = dict(frontier_counts=front.tolist(), frontier_mean=float(front.mean()),
                                frontier_median=float(np.median(front)),
                                frontier_IQR=float(np.percentile(front, 75)-np.percentile(front, 25)))
        for field in ('dBdt_bin', 'fset'):
            totals = Counter()  # 勘误：原用变量名 counts，覆盖了 CV 通过计数（只影响输出字段 CV_counts）
            for sample in samples:
                totals.update(sample[field])
            sampling[method][field + '_total'] = dict(sorted(totals.items()))
    return dict(sampling=sampling, hypotheses=hypotheses, validity=validity, CV=cv, CV_counts=counts, conclusions=conclusions,
                learning_curves=curves, arms=results)


def audit_results(source, df, split):
    results = {}
    for method in 'AMR':
        for k in range(1, 21):
            arm = f'{method}{k}'
            folder = source / 'arms' / arm
            result = json.loads((folder / 'result.json').read_text())
            assert not (folder / 'RUNNING').exists(), 'Arm still running'
            assert (folder / 'DONE').read_text().strip() == sha(folder / 'result.json')
            assert result['predictions_sha256'] == sha(folder / 'predictions.csv')
            assert result['arm'] == arm and result['smoke'] is False
            assert result['config_sha256'] == CONFIG_SHA and result['code_sha256'] == code_hashes()
            assert result['split_sha256'] == digest(split)
            selected, hashes = [], []
            for b in range(1, 7):
                record = json.loads((folder / f'batch_{b}.json').read_text())
                train = split[f'S0_{k}'] + selected
                candidates = sorted(set(split['pool']) - set(train))
                fp = record['fingerprint']
                assert fp['training_ids'] == train and not set(train) & holdouts(split)
                assert fp['candidate_count'] == len(candidates) and fp['candidate_sha256'] == digest(candidates)
                assert fp['config_sha256'] == CONFIG_SHA and fp['code_sha256'] == code_hashes()
                assert fp['arm'] == arm and fp['batch'] == b and fp['smoke'] is False
                assert fp['split_sha256'] == digest(split)
                chosen = validate_batch(record, fp, candidates, 20)
                if method == 'R':
                    assert chosen == split[f'R_{k}'][20*(b-1):20*b]
                else:
                    # Replay acquisition from frozen covariance parameters, without labels.
                    mean, scale = np.asarray(fp['scaler_mean']), np.asarray(fp['scaler_scale'])
                    x = (df.loc[train, FEATURES].to_numpy()-mean)/scale
                    z = (df.loc[candidates, FEATURES].to_numpy()-mean)/scale
                    kernel = make_kernel().clone_with_theta(np.asarray(fp['kernel_theta']))
                    alpha = CONFIG['model']['gp_alpha']
                    gp = SimpleNamespace(X_train_=x, kernel_=kernel, alpha=alpha,
                                         L_=np.linalg.cholesky(kernel(x)+alpha*np.eye(len(x))),
                                         _y_train_std=fp['y_std'])
                    if method == 'M':
                        _, replay = mixed_believer(gp, z, 20, df.loc[candidates, 'cell'].to_numpy(),
                                                    df.loc[selected, 'cell'].tolist(), candidates)
                    else:
                        _, replay = believer(gp, z, 20, candidates)
                    assert [p['sample_id'] for p in replay] == chosen, 'Acquisition replay mismatch'
                    np.testing.assert_allclose([[p['sigma'], p['score']] for p in record['points']],
                                               [[p['sigma'], p['score']] for p in replay], rtol=1e-8, atol=0)
                assert all(p['cell'] == df.loc[p['sample_id'], 'cell'] for p in record['points'])
                if method in 'AM':
                    counts = Counter(df.loc[selected, 'cell'])
                    for point in record['points']:
                        assert point['a_c'] == counts[point['cell']]
                        counts[point['cell']] += 1
                selected.extend(chosen)
                hashes.append(record['sha256'])
            assert result['selected_ids'] == selected and result['training_ids'] == split[f'S0_{k}'] + selected
            assert result['batch_sha256'] == hashes
            assert [p['batch'] for p in result['checkpoints']] == list(range(7))
            assert [p['added'] for p in result['checkpoints']] == list(range(0, 121, 20))
            assert result['metrics'] == result['checkpoints'][-1]['metrics']
            assert result['q'] == result['checkpoints'][-1]['q']
            assert result['sampling'] == sampling_stats(df, selected)
            for cp in result['checkpoints']:
                assert cp['q'] >= 0 and np.isfinite(cp['q'])
                for dataset in ('X7', 'G7'):
                    v = cp['metrics'][dataset]
                    assert v['n'] == len(split[dataset]) and 0 <= v['coverage'] <= v['n']
                    assert all(np.isfinite(value) for value in v.values())
            results[arm] = result
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=OUT)
    ap.add_argument('--out', type=Path, default=STAGE / 'first')
    args = ap.parse_args()
    if args.out.exists():
        raise FileExistsError('Refusing to overwrite an existing evaluation directory')
    # Check completeness before any evaluation label access.
    for a in 'AMR':
        for k in range(1, 21):
            if not (args.source / 'arms' / f'{a}{k}' / 'result.json').is_file():
                raise FileNotFoundError(f'Missing result: {a}{k}')
    df, split = load_design()
    results = audit_results(args.source, df, split)
    output = aggregate(results)
    output['config_sha256'] = CONFIG_SHA
    output['split_sha256'] = digest(split)
    baseline = pd.read_csv(SOURCE, usecols=['sample_id', 'predicted_W_m3']).set_index('sample_id')
    output['igse_baseline'] = {}
    for dataset in ('X7', 'G7'):
        evaluation = evaluation_frame(df, split[dataset], split)
        p = 10. ** evaluation.y.to_numpy()
        output['igse_baseline'][dataset] = float(np.median(np.abs(baseline.loc[split[dataset], 'predicted_W_m3'].to_numpy()-p)/p))
    rows = []
    for arm, result in results.items():
        for dataset in ('X7', 'G7'):
            rows.append(dict(arm=arm, set=dataset, q=result['q'], **result['metrics'][dataset],
                             **output['validity'][arm], frontier_count=result['sampling']['frontier_count'],
                             dBdt_bin=json.dumps(result['sampling']['dBdt_bin'], sort_keys=True),
                             fset=json.dumps(result['sampling']['fset'], sort_keys=True)))
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'metrics.json', output)
    atomic(args.out / 'arm_table.csv', pd.DataFrame(rows).to_csv(index=False).encode())
    print('Complete evaluation sealed; results saved to files.')


if __name__ == '__main__':
    main()
