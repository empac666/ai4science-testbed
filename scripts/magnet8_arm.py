"""Stage 1: arm-local acquisition and label-free checkpoint predictions."""
from magnet8_common import *
from magnet8_design import load_design, equal_bins
import argparse
from collections import Counter
import io
import time
import signal


def smoke_split(df, real, exp):
    rng = np.random.default_rng(12345)
    pool = set(real['pool'])
    ranked = df.loc[sorted(pool)].reset_index(drop=True).sort_values(['dBdt', 'sample_id'], ascending=[False, True])
    high = ranked.head(80).sample_id.tolist()
    rest = sorted(pool-set(high))
    reserved = rng.choice(rest, 350 if exp == 'E2' else 250, replace=False).tolist()
    if exp == 'E1':
        item = dict(X7=high, G7r=reserved[:150], CAL7r=reserved[150:])
    else:
        item = dict(XF=high, XT=reserved[:80], XFT=reserved[80:160], G8=reserved[160:250], CAL8=reserved[250:])
    remaining = sorted(pool-holdouts(exp, item))
    s0 = rng.choice(remaining, 30, replace=False).tolist()
    candidates = rng.choice(sorted(set(remaining)-set(s0)), 2000, replace=False).tolist()
    item['pool'] = sorted(s0+candidates)
    if exp == 'E2':
        item['S'] = real['S']
    for k in range(1, 31):
        item[f'S0_{k}'] = s0
        item[f'R_{k}'] = np.random.default_rng(12345+k).choice(sorted(candidates), 10, replace=False).tolist()
    assert set(item['pool']) | holdouts(exp, item) <= pool
    assert not set(item['pool']) & holdouts(exp, item)
    return item


def experiment_frame(df, split, exp):
    df = df.copy()
    df['dBdt_bin'], _ = equal_bins(df.dBdt, df.loc[split['pool'], 'dBdt'])
    df['cell'] = df.dBdt_bin.astype(str)
    return df


def sampling_stats(df, ids):
    rows = df.loc[ids]
    return dict(n=len(ids), fset=dict(Counter(map(str, rows.fset))),
                T=dict(Counter(map(lambda x: str(int(x)), rows.T_C))),
                dBdt_bin=dict(Counter(rows.cell)),
                fset_T=dict(Counter(f'{int(f)}|{int(t)}' for f, t in zip(rows.fset, rows.T_C))),
                boundary_282=int((rows.fset == 282).sum()), boundary_70=int((rows.T_C == 70).sum()),
                boundary_either=int(((rows.fset == 282) | (rows.T_C == 70)).sum()),
                boundary_both=int(((rows.fset == 282) & (rows.T_C == 70)).sum()))


def extrema(df, ids):
    return {name: dict(min=float(df.loc[ids, name].min()), max=float(df.loc[ids, name].max()))
            for name in ('frequency_Hz', 'fset', 'T_C', 'amplitude_T', 'dBdt')}


def fingerprint(exp, arm, batch, train, candidates, split, model, smoke):
    scaler, coef, gp = model
    return dict(exp=exp, arm=arm, batch=batch, smoke=smoke, training_ids=train,
        candidate_count=len(candidates), candidate_sha256=digest(candidates), split_sha256=digest(split),
        config_sha256=CONFIG_SHA, code_sha256=code_hashes(), gp_seed=gp_seed(int(exp[1])),
        kernel_theta=gp.kernel_.theta.tolist(), kernel=str(gp.kernel_), y_mean=float(gp._y_train_mean),
        y_std=float(gp._y_train_std), scaler_mean=scaler.mean_.tolist(), scaler_scale=scaler.scale_.tolist(),
        linear_coef=coef.tolist())


def validate_batch(record, expected, candidates, count):
    assert record['sha256'] == digest({k: v for k, v in record.items() if k != 'sha256'}), 'Batch SHA mismatch'
    assert record['fingerprint'] == expected, 'Batch fingerprint mismatch'
    selected = [p['sample_id'] for p in record['points']]
    assert len(selected) == len(set(selected)) == count and set(selected) <= set(candidates)
    return selected


def choose(module, model, df, method, candidates, selected, count, random_ids):
    if method == 'R':
        points = [dict(sample_id=i, sigma=None, score=None, a_c=None, cell=str(df.loc[i, 'cell'])) for i in random_ids]
    else:
        z = model[0].transform(df.loc[candidates, module.FEATURES].to_numpy())
        if method == 'M':
            _, points = module.mixed_believer(model, z, count, df.loc[candidates, 'cell'].to_numpy(),
                                             df.loc[selected, 'cell'].tolist(), candidates)
        else:
            _, points = module.believer(model, z, count, candidates)
            bin_counts = Counter(df.loc[selected, 'cell'])
            for p in points:
                p['cell'] = str(df.loc[p['sample_id'], 'cell'])
                p['a_c'] = bin_counts[p['cell']]
                bin_counts[p['cell']] += 1
    return points


def save_model(path, model):
    scaler, coef, gp = model
    stream = io.BytesIO()
    np.savez(stream, scaler_mean=scaler.mean_, scaler_scale=scaler.scale_, coef=coef,
             kernel_theta=gp.kernel_.theta, X_train=gp.X_train_, L=gp.L_, alpha=gp.alpha_,
             y_mean=gp._y_train_mean, y_std=gp._y_train_std)
    freeze(path, stream.getvalue())


def run(exp, arm, out, smoke=False, allow_missing_sources=False):
    assert exp in CAL and arm in ARMS
    out = Path(out)
    if smoke:
        assert out.resolve() == (ROOT/'data/magnet8_smoke').resolve(), 'Smoke must use data/magnet8_smoke'
    else:
        require_box()
        assert not allow_missing_sources
    start = time.perf_counter()
    df, designs = load_design(allow_missing_sources if smoke else False)
    real = designs[exp]
    split = smoke_split(df, real, exp) if smoke else real
    df = experiment_frame(df, split, exp)
    method, k = arm[0], int(arm[1:])
    e = int(exp[1])
    batches, size = (2, 5) if smoke else (6, 20)
    folder = out/'arms'/exp/arm
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'DONE').exists():
        raise FileExistsError('Completed arm is sealed; sweep skips it')
    fd = os.open(folder/'RUNNING', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    log = lambda message: append(folder/'log.txt', f'{now()} {message}')
    old_term = None
    if os.name == 'posix':
        def terminate(signum, frame):
            raise KeyboardInterrupt('Infrastructure SIGTERM; retain frozen checkpoints')
        old_term = signal.signal(signal.SIGTERM, terminate)
    try:
        manifest = dict(exp=exp, arm=arm, smoke=smoke, prereg_sha=PREREG_SHA, H=H,
                        config_sha256=CONFIG_SHA, code_sha256=code_hashes(), versions=versions(),
                        source_checks=verify_sources(allow_missing_sources if smoke else False),
                        split_sha256=digest(split), gp_seed=gp_seed(e),
                        seeds=dict(family=seed(e, 0, 0), S0=seed(e, 1, k), R=seed(e, 2, k)))
        freeze(folder/'manifest.json', encoded(manifest))
        log(f'Start smoke={smoke}; same-seed checkpoint recovery allowed')
        module = adapter(e)
        reader = PoolReader(exp, arm, split, real if smoke else None)
        selected, checkpoints, batch_hashes = [], [], []
        s0 = split[f'S0_{k}']
        for b in range(batches+1):
            train_ids = s0+selected
            train = df.loc[train_ids].copy()
            train['y'] = reader.read(train_ids)
            model = module.fit_m2(train)
            model_path = folder/f'model_{b}.npz'
            save_model(model_path, model)
            predictions = []
            for name in (CAL[exp], *EVAL[exp]):
                ids = split[name]
                # No calibration/evaluation target access in this process.
                mu, sigma = module.predict(model, df.loc[ids])
                assert np.isfinite(mu).all() and np.isfinite(sigma).all() and (sigma > 0).all()
                predictions.append(pd.DataFrame(dict(set=name, sample_id=ids, mu=mu, sigma=sigma)))
            prediction_path = folder/f'predictions_{b}.csv'
            freeze(prediction_path, pd.concat(predictions).to_csv(index=False, float_format='%.17g', lineterminator='\n').encode('utf-8'))
            checkpoints.append(dict(batch=b, added=len(selected), training_extrema=extrema(df, train_ids),
                model_sha256=sha(model_path), predictions_sha256=sha(prediction_path)))
            log(f'Checkpoint {b} frozen; training_count={len(train_ids)}')
            if b == batches:
                break
            candidates = sorted(set(split['pool'])-set(train_ids))
            fp = fingerprint(exp, arm, b+1, train_ids, candidates, split, model, smoke)
            path = folder/f'batch_{b+1}.json'
            if path.exists():
                record = read_json(path)
                chosen = validate_batch(record, fp, candidates, size)
                if method == 'R':
                    assert chosen == split[f'R_{k}'][b*size:(b+1)*size]
                log(f'Reused frozen batch {b+1}')
            else:
                points = choose(module, model, df, method, candidates, selected, size, split[f'R_{k}'][b*size:(b+1)*size])
                record = dict(fingerprint=fp, points=points)
                record['sha256'] = digest(record)
                chosen = validate_batch(record, fp, candidates, size)
                freeze(path, encoded(record))
                log(f'Batch {b+1} frozen before querying labels')
            reader.authorize(chosen)
            selected.extend(chosen)
            batch_hashes.append(record['sha256'])
        result = dict(**manifest, manifest_sha256=sha(folder/'manifest.json'), training_ids=s0+selected,
                      selected_ids=selected, batch_sha256=batch_hashes, checkpoints=checkpoints,
                      sampling_counts=dict(S0=sampling_stats(df, s0), additions=sampling_stats(df, selected)),
                      pool_extrema=extrema(df, split['pool']), elapsed_seconds=time.perf_counter()-start)
        if (folder/'result.json').exists():
            # A crash between result and DONE must remain resumable. Everything
            # except the original elapsed time is rederived and compared.
            result['elapsed_seconds'] = read_json(folder/'result.json')['elapsed_seconds']
        freeze(folder/'result.json', encoded(result))
        freeze(folder/'DONE', (sha(folder/'result.json')+'\n').encode('utf-8'))
        log('DONE: acquisition, models and predictions sealed; no holdout labels read')
    except BaseException as exc:
        log(f'FAILED {type(exc).__name__}: {exc}')
        raise
    finally:
        (folder/'RUNNING').unlink()
        if old_term is not None:
            signal.signal(signal.SIGTERM, old_term)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exp', required=True, choices=list(CAL))
    ap.add_argument('--arm', required=True, choices=ARMS)
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--allow-missing-sources', action='store_true')
    args = ap.parse_args()
    run(args.exp, args.arm, ROOT/'data/magnet8_smoke' if args.smoke else OUT, args.smoke, args.allow_missing_sources)
    print(f'{args.exp}/{args.arm}: acquisition and predictions sealed (smoke={args.smoke}).')


if __name__ == '__main__':
    main()
