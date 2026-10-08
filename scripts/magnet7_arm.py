#!/usr/bin/env python3
"""One deterministic arm. Only --smoke is authorized during implementation."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from magnet7_design import ROOT, OUT, CONFIG_SHA, atomic, digest, sha, write_json, load_design, config

CONFIG = config()
from magnet6_model import FEATURES, load_y, linear, fit_m2, predict, conformal_q, metrics, believer, mixed_believer


def holdouts(split):
    return set().union(*(set(split[k]) for k in ('X7', 'G7', 'CAL7')))


def evaluation_frame(df, ids, split, forbidden=()):
    """Evaluation-only reader; smoke always supplies real holdouts as forbidden."""
    assert set(ids) <= holdouts(split), 'Undeclared evaluation ids'
    assert not set(ids) & set(forbidden), 'Real holdout targets forbidden'
    result = df.loc[ids].copy()
    result['y'] = load_y(ids, forbidden)
    return result


def smoke_split(df, real):
    rng = np.random.default_rng(12345)
    pool = set(real['pool'])
    x = df.loc[sorted(pool)].reset_index(drop=True).sort_values(['dBdt', 'sample_id'], ascending=[False, True]).head(80).sample_id.tolist()
    # Reserve whole families, including any points beyond the G7 cap.
    families = sorted(set(df.loc[sorted(pool - set(x)), 'family']) - set(df.loc[x, 'family']))
    perm = rng.permutation(families).tolist()
    g_all = sorted(i for i in pool if df.loc[i, 'family'] in perm[:3])
    g = rng.permutation(g_all).tolist()[:150]
    cal = sorted(i for i in pool if df.loc[i, 'family'] in perm[3:5])
    remaining = sorted(pool - set(x) - set(g_all) - set(cal))
    s0 = rng.choice(remaining, 30, replace=False).tolist()
    candidates = rng.choice(sorted(set(remaining) - set(s0)), 2000, replace=False).tolist()
    result = dict(X7=x, G7=g, CAL7=cal, pool=sorted(s0 + candidates))
    for k in range(1, 21):
        result[f'S0_{k}'] = s0
        result[f'R_{k}'] = np.random.default_rng(12345 + k).choice(sorted(candidates), 10, replace=False).tolist()
    assert not set().union(*(set(v) for v in result.values())) & holdouts(real)
    assert not holdouts(result) & set(result['pool'])
    assert len(holdouts(result)) == len(x) + len(g) + len(cal)
    return result


def code_hashes():
    return {name: sha(ROOT / 'scripts' / name) for name in
            ('magnet7_design.py', 'magnet6_model.py', 'magnet7_arm.py', 'magnet6_design.py')}


def fingerprint(arm, batch, train_ids, candidates, split, model, smoke):
    scaler, coef, gp = model
    return dict(arm=arm, batch=batch, smoke=smoke, training_ids=train_ids,
                candidate_count=len(candidates), candidate_sha256=digest(candidates),
                split_sha256=digest(split), config_sha256=CONFIG_SHA, code_sha256=code_hashes(),
                kernel=str(gp.kernel_), kernel_theta=gp.kernel_.theta.tolist(),
                y_mean=float(gp._y_train_mean), y_std=float(gp._y_train_std),
                scaler_mean=scaler.mean_.tolist(), scaler_scale=scaler.scale_.tolist(), linear_coef=coef.tolist())


def validate_batch(record, expected, candidates, count):
    assert record['sha256'] == digest({k: v for k, v in record.items() if k != 'sha256'}), 'Batch SHA mismatch'
    assert record['fingerprint'] == expected, 'Batch fingerprint mismatch'
    selected = [p['sample_id'] for p in record['points']]
    assert len(selected) == len(set(selected)) == count and set(selected) <= set(candidates)
    return selected


def sampling_stats(df, selected):
    return dict(frontier_count=int(df.loc[selected, 'frontier'].sum()),
                dBdt_bin=dict(Counter(df.loc[selected, 'cell'])),
                fset=dict(Counter(map(str, df.loc[selected, 'fset']))))


def run(arm, out, smoke=False):
    start = time.perf_counter()
    df, real = load_design()
    split = smoke_split(df, real) if smoke else real
    hard_forbidden = holdouts(real) if smoke else set()
    forbidden = holdouts(split) | hard_forbidden
    method, k = arm[0], int(arm[1:])
    assert method in 'AMR' and 1 <= k <= 20
    batches, size = (2, 5) if smoke else (6, 20)
    folder = out / 'arms' / arm
    folder.mkdir(parents=True, exist_ok=True)
    # A per-arm lock prevents two runners from replacing frozen batches.
    lock = folder / 'RUNNING'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    def log(message):
        stamp = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        with (folder / 'log.txt').open('a') as stream:
            stream.write(f'{stamp} {message}\n')
    try:
        log('Started smoke=' + str(smoke))
        selected, checkpoints, records = [], [], []
        s0 = split[f'S0_{k}']
        for b in range(batches + 1):
            train_ids = s0 + selected
            assert not set(train_ids) & forbidden
            train = df.loc[train_ids].copy()
            train['y'] = load_y(train_ids, forbidden)
            model = fit_m2(train)
            cal = evaluation_frame(df, split['CAL7'], split, hard_forbidden)
            q = conformal_q(model, cal)
            checkpoint = dict(batch=b, added=len(selected), q=q, metrics={})
            predictions = []
            for name in ('X7', 'G7'):
                evaluation = evaluation_frame(df, split[name], split, hard_forbidden)
                mu, sigma = predict(model, evaluation)
                checkpoint['metrics'][name] = metrics(evaluation.y.to_numpy(), mu, sigma, q)
                predictions.append(pd.DataFrame(dict(set=name, sample_id=split[name], mu=mu, sigma=sigma,
                                                     lo=mu-q*sigma, hi=mu+q*sigma, y=evaluation.y.to_numpy())))
            checkpoints.append(checkpoint)
            log(f'Checkpoint {b} completed; training_count={len(train_ids)}')
            if b == batches:
                atomic(folder / 'predictions.csv', pd.concat(predictions).to_csv(index=False, float_format='%.17g').encode())
                break
            candidates = sorted(set(split['pool']) - set(train_ids))
            assert not set(candidates) & forbidden
            fp = fingerprint(arm, b + 1, train_ids, candidates, split, model, smoke)
            path = folder / f'batch_{b+1}.json'
            if path.exists():
                record = json.loads(path.read_text())
                chosen = validate_batch(record, fp, candidates, size)
                if method == 'R':
                    assert chosen == split[f'R_{k}'][b*size:(b+1)*size]
                log(f'Reused verified batch {b+1}')
            else:
                if method == 'R':
                    chosen = split[f'R_{k}'][b*size:(b+1)*size]
                    points = [dict(sample_id=i, sigma=None, score=None, a_c=None, cell=str(df.loc[i, 'cell'])) for i in chosen]
                else:
                    z = model[0].transform(df.loc[candidates, FEATURES].to_numpy())
                    if method == 'M':
                        _, points = mixed_believer(model, z, size, df.loc[candidates, 'cell'].to_numpy(),
                                                   df.loc[selected, 'cell'].tolist(), candidates)
                    else:
                        _, points = believer(model, z, size, candidates)
                        counts = Counter(df.loc[selected, 'cell'])
                        for p in points:
                            p['cell'] = str(df.loc[p['sample_id'], 'cell'])
                            p['a_c'] = counts[p['cell']]
                            counts[p['cell']] += 1
                    chosen = [p['sample_id'] for p in points]
                record = dict(fingerprint=fp, points=points)
                record['sha256'] = digest(record)
                validate_batch(record, fp, candidates, size)
                write_json(path, record)
                log(f'Frozen batch {b+1}')
            selected.extend(chosen)
            records.append(record['sha256'])
        result = dict(arm=arm, smoke=smoke, config_sha256=CONFIG_SHA, code_sha256=code_hashes(),
                      split_sha256=digest(split), training_ids=s0+selected, selected_ids=selected,
                      predictions_sha256=sha(folder / 'predictions.csv'), batch_sha256=records, checkpoints=checkpoints, q=q, metrics=checkpoints[-1]['metrics'],
                      sampling=sampling_stats(df, selected), elapsed_seconds=time.perf_counter()-start)
        write_json(folder / 'result.json', result)
        atomic(folder / 'DONE', (sha(folder / 'result.json') + '\n').encode())
        log('Completed')
    finally:
        lock.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', required=True, choices=[f'{a}{k}' for a in 'AMR' for k in range(1, 21)])
    ap.add_argument('--out', type=Path)
    ap.add_argument('--smoke', action='store_true')
    args = ap.parse_args()
    out = args.out or (ROOT / 'data/magnet7_smoke' if args.smoke else OUT)
    if args.smoke and (out.resolve() == OUT.resolve() or OUT.resolve() in out.resolve().parents):
        ap.error('Smoke output must not overwrite the real design directory')
    run(args.arm, out, args.smoke)
    print(f'{args.arm}: completed (smoke={args.smoke}); metrics saved to files.')


if __name__ == '__main__':
    main()
