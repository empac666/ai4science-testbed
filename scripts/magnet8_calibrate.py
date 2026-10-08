"""Stage 2: open CAL labels only after all 180 arms pass seal audits."""
from magnet8_common import *
from magnet8_design import load_design
from magnet8_audit import require_complete, audit_results, read_predictions
import argparse
import math


def quantile(y, mu, sigma):
    y, mu, sigma = map(np.asarray, (y, mu, sigma))
    assert y.shape == mu.shape == sigma.shape and y.ndim == 1
    assert np.isfinite(y).all() and np.isfinite(mu).all() and np.isfinite(sigma).all() and (sigma > 0).all()
    scores = np.abs(y-mu)/sigma
    rank = math.ceil((len(scores)+1)*.9)
    assert rank <= len(scores) and np.isfinite(scores).all()
    q = float(np.partition(scores, rank-1)[rank-1])
    assert np.isfinite(q) and q >= 0
    return q


def calibrate(source=OUT, out=STAGE/'first'):
    source, out = Path(source), Path(out)
    target = out/'calibration.json'
    if target.exists():
        raise FileExistsError('Calibration already sealed; refusing overwrite')
    require_complete(source)  # before design, model or label access
    require_box()
    df, splits = load_design()
    out.mkdir(parents=True, exist_ok=True)
    lock = out/'CALIBRATING'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        _, seals, _ = audit_results(source, df, splits, replay_arms=())
        output = dict(prereg_sha=PREREG_SHA, H=H, config_sha256=CONFIG_SHA, split_sha256=digest(splits),
                      code_sha256=code_hashes(), arm_seals=seals, calibration={}, sealed_at=now())
        for exp in CAL:
            item, name = splits[exp], CAL[exp]
            # No shared cross-experiment target cache; CAL cannot train or select.
            y = read_targets(item[name], item[name], set(item['pool']) | set().union(*(set(item[n]) for n in EVAL[exp])))
            output['calibration'][exp] = {}
            for arm in ARMS:
                values = []
                for b in range(7):
                    pred = read_predictions(source/'arms'/exp/arm, b, exp, item)
                    cal = pred[pred['set'] == name]
                    values.append(quantile(y, cal.mu.to_numpy(), cal.sigma.to_numpy()))
                output['calibration'][exp][arm] = values
            del y
        # Recheck immutable references before committing the seal.
        require_complete(source)
        for exp in CAL:
            for arm in ARMS:
                assert sha(source/'arms'/exp/arm/'result.json') == seals[exp][arm]
        output['sha256'] = digest(output)
        freeze(target, encoded(output))
    finally:
        lock.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=OUT)
    ap.add_argument('--out', type=Path, default=STAGE/'first')
    args = ap.parse_args()
    calibrate(args.source, args.out)
    print('All checkpoint calibration quantiles sealed; evaluation labels remain unread.')


if __name__ == '__main__':
    main()
