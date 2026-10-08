"""Stage 3: audited, one-time evaluation; MITM exact sign flips and fixed gates."""
from magnet8_common import *
from magnet8_design import load_design
from magnet8_audit import require_complete, audit_results, read_predictions
import argparse
import math
from collections import Counter


def signed_sums(values):
    sums = np.zeros(1)
    for value in values:
        sums = np.concatenate((sums-value, sums+value))
    return sums


def signflip(d):
    d = np.asarray(d, dtype=float)
    assert d.ndim == 1 and 0 < len(d) <= 30 and np.isfinite(d).all()
    left, right = signed_sums(d[:len(d)//2]), np.sort(signed_sums(d[len(d)//2:]))
    threshold = float(d.sum())-len(d)*1e-12
    hits = int(np.sum(len(right)-np.searchsorted(right, threshold-left, side='left'), dtype=np.int64))
    if len(d) <= 14:
        # Small-K legacy verification only: re-association of IEEE sums can move
        # exact tolerance-boundary ties by an ulp. Resolve ONLY those ambiguous
        # pairs using the legacy mean expression. The preregistered K=30 path
        # above always uses sum(d)-30e-12 and never enumerates 2**30 signs.
        error = 8*np.finfo(float).eps*(np.abs(d).sum()+len(d)*1e-12)
        if np.any(np.searchsorted(right, threshold-left+error, side='right') >
                  np.searchsorted(right, threshold-left-error, side='left')):
            nleft = len(d)//2
            raw_right = signed_sums(d[nleft:])
            order = np.argsort(raw_right)
            shifts = np.arange(len(d))
            for li, subtotal in enumerate(left):
                lo = np.searchsorted(right, threshold-subtotal-error, side='left')
                hi = np.searchsorted(right, threshold-subtotal+error, side='right')
                if hi > lo:
                    indices = li + (order[lo:hi] << nleft)
                    signs = ((indices[:, None] >> shifts) & 1)*2-1
                    legacy_hits = int(np.sum(np.mean(signs*d, axis=1) >= d.mean()-1e-12))
                    old_hits = int(np.sum(right[lo:hi] >= threshold-subtotal))
                    hits += legacy_hits-old_hits
    return dict(numerator=hits, denominator=2**len(d), p=hits/2**len(d))


def signflip_p(d):
    return signflip(d)['p']


def fixed_sequence(results):
    active, statuses = True, {}
    for h in (f'H{i}' for i in range(1, 7)):
        p = results[h]['p'] if isinstance(results[h], dict) else results[h]
        assert np.isfinite(p) and 0 <= p <= 1
        statuses[h] = ('rejected' if p < .05 else 'not_rejected') if active else 'not_tested'
        active = active and statuses[h] == 'rejected'
    return statuses


def conclusion_map(statuses, cv, v80, honest90, process_valid=True):
    passed = lambda h: process_valid and statuses[h] == 'rejected'
    result = {'M-X7': passed('H1') and cv['M'],
              'M-NI10-X7': passed('H2') and cv['M'] and cv['A']}
    for h, method, region in [('H3', 'A', 'F'), ('H4', 'M', 'F'), ('H5', 'A', 'T'), ('H6', 'M', 'T')]:
        result[f'{method}-{region}'] = passed(h) and v80[method][region] and honest90[method][region]
    return result


def aggregate(results, process_valid=True):
    assert set(results) == set(CAL)
    for exp in CAL:
        assert set(results[exp]) == set(ARMS), 'All 30 paired groups required'
        for result in results[exp].values():
            assert len(result['checkpoints']) == 7
            for checkpoint in result['checkpoints']:
                assert np.isfinite(checkpoint['q']) and checkpoint['q'] >= 0
                for name in EVAL[exp]:
                    metric = checkpoint['metrics'][name]
                    assert all(np.isfinite(v) for v in metric.values())
                    assert 0 <= metric['coverage'] <= metric['n'] and metric['width'] >= 0
            assert result['metrics'] == result['checkpoints'][-1]['metrics']
    def values(exp, method, region, metric):
        return np.array([results[exp][f'{method}{k}']['metrics'][region][metric] for k in range(1, 31)])
    a, m, r = [values('E1', x, 'X7', 'winkler') for x in 'AMR']
    differences = [r-m, 1.10*a-m]
    for region in ('XF', 'XT'):
        differences.extend(values('E2', 'R', region, 'winkler')-values('E2', x, region, 'winkler') for x in 'AM')
    hypotheses = {}
    for i, d in enumerate(differences, 1):
        hypotheses[f'H{i}'] = dict(d_k=d.tolist(), **signflip(d), mean=float(d.mean()), median=float(np.median(d)),
            IQR=float(np.percentile(d, 75)-np.percentile(d, 25)), positive_count=int((d > 0).sum()),
            zero_count=int((d == 0).sum()), negative_count=int((d < 0).sum()))
    statuses = fixed_sequence(hypotheses)
    for h, status in statuses.items():
        hypotheses[h]['status'] = status
    validity, validity_pass_counts = {'E1': {}, 'E2': {}}, {'E1': {}, 'E2': {}}
    for arm in ARMS:
        metrics = results['E1'][arm]['metrics']
        g, x = metrics['G7r'], metrics['X7']
        c1 = g['coverage'] >= math.ceil(.8*g['n'])
        c2 = x['coverage'] >= 506 and x['width'] <= 3*g['width']
        validity['E1'][arm] = dict(C1=c1, C2=c2, CV=c1 and c2)
        metrics = results['E2'][arm]['metrics']
        g = metrics['G8']
        c1 = g['coverage'] >= math.ceil(.8*g['n'])
        row = dict(C1=c1)
        for region, name, lower, nominal in [('F', 'XF', 4289, 4825), ('T', 'XT', 6676, 7511)]:
            x = metrics[name]
            row[f'V80_{region}'] = c1 and x['coverage'] >= lower and x['width'] <= 3*g['width']
            row[f'HONEST90_{region}'] = x['coverage'] >= nominal
        validity['E2'][arm] = row
    for method in 'AMR':
        for exp, fields in [('E1', ('CV', 'C1', 'C2')), ('E2', ('C1', 'V80_F', 'V80_T', 'HONEST90_F', 'HONEST90_T'))]:
            validity_pass_counts[exp][method] = {field: sum(bool(validity[exp][f'{method}{k}'][field]) for k in range(1, 31)) for field in fields}
    cv = {m: validity_pass_counts['E1'][m]['CV'] >= 26 for m in 'AMR'}
    v80 = {m: {r: validity_pass_counts['E2'][m][f'V80_{r}'] >= 26 for r in 'FT'} for m in 'AMR'}
    honest = {m: {r: validity_pass_counts['E2'][m][f'HONEST90_{r}'] >= 26 for r in 'FT'} for m in 'AMR'}
    learning, sampling_counts, coverage_summary = {}, {}, {}
    for exp in CAL:
        learning[exp], sampling_counts[exp], coverage_summary[exp] = {}, {}, {}
        for method in 'AMR':
            learning[exp][method], sampling_counts[exp][method], coverage_summary[exp][method] = {}, {}, {}
            for category in ('S0', 'additions'):
                totals = {}
                for field in ('fset', 'T', 'dBdt_bin', 'fset_T'):
                    tally = Counter()
                    for k in range(1, 31):
                        tally.update(results[exp][f'{method}{k}']['sampling_counts'][category][field])
                    totals[field] = dict(sorted(tally.items()))
                for field in ('n', 'boundary_282', 'boundary_70', 'boundary_either', 'boundary_both'):
                    totals[field] = sum(results[exp][f'{method}{k}']['sampling_counts'][category][field] for k in range(1, 31))
                sampling_counts[exp][method][category] = totals
            for name in EVAL[exp]:
                learning[exp][method][name] = {}
                for metric in ('winkler', 'coverage_fraction', 'coverage', 'width', 'relative_error', 'mae', 'bias'):
                    data = np.array([[cp['metrics'][name][metric] for cp in results[exp][f'{method}{k}']['checkpoints']] for k in range(1, 31)])
                    learning[exp][method][name][metric] = dict(mean=data.mean(axis=0).tolist(), minimum=data.min(axis=0).tolist(), maximum=data.max(axis=0).tolist())
                cover = values(exp, method, name, 'coverage_fraction')
                width = values(exp, method, name, 'width')
                coverage_summary[exp][method][name] = dict(mean=float(cover.mean()), minimum=float(cover.min()),
                    maximum=float(cover.max()), per_arm=cover.tolist(), nominal90_shortfall=np.maximum(0, .9-cover).tolist(),
                    width=dict(mean=float(width.mean()), minimum=float(width.min()), maximum=float(width.max()), per_arm=width.tolist()))
    return dict(process_valid=process_valid, hypotheses=hypotheses, validity=validity,
                validity_pass_counts=validity_pass_counts, sampling_counts=sampling_counts,
                CV=cv, V80=v80, HONEST90=honest, conclusions=conclusion_map(statuses, cv, v80, honest, process_valid),
                learning_curves=learning, coverage_summary=coverage_summary, arms=results)


def validate_calibration(calibration, splits, seals):
    assert calibration['sha256'] == digest({k: v for k, v in calibration.items() if k != 'sha256'})
    assert calibration['prereg_sha'] == PREREG_SHA and calibration['H'] == H
    assert calibration['config_sha256'] == CONFIG_SHA and calibration['code_sha256'] == code_hashes()
    assert calibration['split_sha256'] == digest(splits) and calibration['arm_seals'] == seals
    assert set(calibration['calibration']) == set(CAL)
    for exp in CAL:
        assert set(calibration['calibration'][exp]) == set(ARMS)
        for qs in calibration['calibration'][exp].values():
            assert len(qs) == 7 and np.isfinite(qs).all() and np.all(np.asarray(qs) >= 0)


def evaluate(source=OUT, out=STAGE/'first', replay_arms=('A1', 'M1')):
    source, out = Path(source), Path(out)
    for name in ('metrics.json', 'arm_table.csv', 'primary_evaluation.json', 'EVALUATED'):
        if (out/name).exists():
            raise FileExistsError(f'First evaluation artifact exists: {name}; no overwrite')
    require_complete(source)
    calibration = read_json(out/'calibration.json')
    require_box()
    df, splits = load_design()
    fd = os.open(out/'EVALUATING', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        results, seals, replayed = audit_results(source, df, splits, replay_arms)
        validate_calibration(calibration, splits, seals)
        for exp in CAL:
            item = splits[exp]
            module = adapter(int(exp[1]))
            # Evaluation-only local labels, created after the calibration seal check.
            labels = {name: read_targets(item[name], item[name], set(item['pool']) | set(item[CAL[exp]])) for name in EVAL[exp]}
            for arm in ARMS:
                result = results[exp][arm]
                for b, cp in enumerate(result['checkpoints']):
                    q = calibration['calibration'][exp][arm][b]
                    pred = read_predictions(source/'arms'/exp/arm, b, exp, item)
                    cp.update(q=q, metrics={})
                    for name in EVAL[exp]:
                        table = pred[pred['set'] == name]
                        metric = module.metrics(labels[name], table.mu.to_numpy(), table.sigma.to_numpy(), q)
                        metric['coverage_fraction'] = metric['coverage']/metric['n']
                        metric['nominal90_shortfall'] = max(0., .9-metric['coverage_fraction'])
                        cp['metrics'][name] = metric
                result['metrics'] = result['checkpoints'][-1]['metrics']
            del labels
        output = aggregate(results)
        output.update(prereg_sha=PREREG_SHA, H=H, config_sha256=CONFIG_SHA, code_sha256=code_hashes(),
                      split_sha256=digest(splits), calibration_sha256=sha(out/'calibration.json'),
                      arm_seals=seals, replayed_arms=replayed, sealed_at=now())
        # Freeze scientific evaluation before even opening iGSE predictions.
        freeze(out/'primary_evaluation.json', encoded(output))
        baseline = pd.read_csv(SOURCE, usecols=['sample_id', 'predicted_W_m3']).set_index('sample_id')
        output['igse_baseline'] = {}
        for exp in CAL:
            for name in EVAL[exp]:
                ids = splits[exp][name]
                y = read_targets(ids, ids)
                estimate = baseline.loc[ids, 'predicted_W_m3'].to_numpy()
                assert np.isfinite(estimate).all() and (estimate > 0).all()
                output['igse_baseline'][name] = float(np.median(np.abs(estimate/(10.**y)-1)))
        output['igse_note'] = 'Descriptive only: temperature-specific prefitting may have used held-out sines, including 90 C; not a fair unsupported baseline.'
        output['primary_evaluation_sha256'] = sha(out/'primary_evaluation.json')
        rows = []
        for exp in CAL:
            for arm in ARMS:
                for cp in results[exp][arm]['checkpoints']:
                    for name in EVAL[exp]:
                        rows.append(dict(exp=exp, arm=arm, checkpoint=cp['batch'], added=cp['added'], set=name, q=cp['q'],
                                         **cp['metrics'][name], **{'final_'+key: value for key, value in output['validity'][exp][arm].items()}))
        freeze(out/'arm_table.csv', pd.DataFrame(rows).to_csv(index=False, lineterminator='\n').encode('utf-8'))
        freeze(out/'metrics.json', encoded(output))
        freeze(out/'EVALUATED', encoded({name: sha(out/name) for name in ('metrics.json', 'arm_table.csv', 'primary_evaluation.json', 'calibration.json')}))
    finally:
        (out/'EVALUATING').unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=OUT)
    ap.add_argument('--out', type=Path, default=STAGE/'first')
    ap.add_argument('--replay-arms', default='A1,M1', help='Comma-separated preselected arms in BOTH experiments; all for all A/M arms')
    args = ap.parse_args()
    replay = [a for a in ARMS if a[0] in 'AM'] if args.replay_arms == 'all' else args.replay_arms.split(',')
    assert replay and all(a in ARMS and a[0] in 'AM' for a in replay), 'At least one A/M replay arm required'
    evaluate(args.source, args.out, replay)
    print('First evaluation sealed. No metrics printed.')


if __name__ == '__main__':
    main()
