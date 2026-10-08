#!/usr/bin/env python3
"""Seal a complete, audited 24-arm analysis. Never invoked for implementation."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from magnet6_design import OUT, STAGE, SOURCE, CONFIG_SHA, digest, sha, write_json, atomic, load_design
from magnet6_model import (CONFIG, FEATURES, evaluation_frame, signflip_p, fixed_sequence,
                           make_kernel, believer, mixed_believer)
from magnet6_arm import holdouts, code_hashes, validate_batch


def aggregate(results):
    """Pure summary function, also exercised on synthetic results."""
    def values(method, dataset, metric):
        return np.array([results[f'{method}{k}']['metrics'][dataset][metric] for k in range(1, 9)])
    a, m, r = [values(x, 'C6', 'winkler') for x in 'AMR']
    ti = {x: values(x, 'T6', 'winkler') for x in 'AMR'}
    differences = [r-a, r-m, 1.10*a-m, values('R', 'C6', 'relative_error')-values('M', 'C6', 'relative_error'),
                   1.10*ti['R']-ti['M'], 1.10*ti['R']-ti['A']]
    hypotheses = {f'H{i+1}': dict(d_k=d.tolist(), p=signflip_p(d)) for i, d in enumerate(differences)}
    statuses = fixed_sequence(hypotheses)
    for h, status in statuses.items():
        hypotheses[h]['status'] = status
    validity = {}
    for arm, result in results.items():
        c, t = result['metrics']['C6'], result['metrics']['T6']
        validity[arm] = dict(C1=t['coverage'] >= 240, C2=c['coverage'] >= 160 and c['width'] <= 3*t['width'])
    cv = {x: sum(all(validity[f'{x}{k}'].values()) for k in range(1, 9)) >= 7 for x in 'AMR'}
    passed = lambda h: statuses[h] == 'rejected'
    conclusions = {'A': passed('H1') and cv['A'], 'M': passed('H2') and cv['M'], 'M≈A': passed('H3'),
                   'M-RE': passed('H4'), 'M-ID': passed('H5') and cv['M'], 'A-ID': passed('H6') and cv['A']}
    curves = {}
    for x in 'AMR':
        curves[x] = {}
        for dataset in ('C6', 'T6'):
            curves[x][dataset] = {}
            for metric in ('winkler', 'coverage', 'width', 'relative_error', 'mae', 'bias'):
                data = np.array([[p['metrics'][dataset][metric] for p in results[f'{x}{k}']['checkpoints']] for k in range(1, 9)])
                curves[x][dataset][metric] = dict(mean=data.mean(axis=0).tolist(), minimum=data.min(axis=0).tolist(), maximum=data.max(axis=0).tolist())
    return dict(hypotheses=hypotheses, validity=validity, CV=cv, conclusions=conclusions,
                learning_curves=curves, arms=results)


def audit_results(source, df, split):
    results = {}
    for method in 'AMR':
        for k in range(1, 9):
            arm = f'{method}{k}'
            folder = source / 'arms' / arm
            result = json.loads((folder / 'result.json').read_text())
            assert (folder / 'DONE').read_text().strip() == sha(folder / 'result.json')
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
                selected.extend(chosen)
                hashes.append(record['sha256'])
            assert result['selected_ids'] == selected and result['training_ids'] == split[f'S0_{k}'] + selected
            assert result['batch_sha256'] == hashes
            assert [p['batch'] for p in result['checkpoints']] == list(range(7))
            assert [p['added'] for p in result['checkpoints']] == list(range(0, 121, 20))
            assert result['metrics'] == result['checkpoints'][-1]['metrics']
            assert result['q'] == result['checkpoints'][-1]['q']
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
        for k in range(1, 9):
            if not (args.source / 'arms' / f'{a}{k}' / 'result.json').is_file():
                raise FileNotFoundError(f'Missing result: {a}{k}')
    df, split = load_design()
    results = audit_results(args.source, df, split)
    output = aggregate(results)
    output['config_sha256'] = CONFIG_SHA
    output['split_sha256'] = digest(split)
    baseline = pd.read_csv(SOURCE, usecols=['sample_id', 'predicted_W_m3']).set_index('sample_id')
    output['igse_baseline'] = {}
    for dataset in ('C6', 'T6'):
        evaluation = evaluation_frame(df, split[dataset], split)
        p = 10. ** evaluation.y.to_numpy()
        output['igse_baseline'][dataset] = float(np.median(np.abs(baseline.loc[split[dataset], 'predicted_W_m3'].to_numpy()-p)/p))
    rows = []
    for arm, result in results.items():
        for dataset in ('C6', 'T6'):
            rows.append(dict(arm=arm, set=dataset, q=result['q'], **result['metrics'][dataset],
                             **output['validity'][arm], corner_count=result['sampling']['corner_count']))
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'metrics.json', output)
    atomic(args.out / 'arm_table.csv', pd.DataFrame(rows).to_csv(index=False).encode())
    print('Complete evaluation sealed; results saved to files.')


if __name__ == '__main__':
    main()
