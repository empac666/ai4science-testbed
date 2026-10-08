"""Input-only completeness, sealed artifact and acquisition replay audits."""
from magnet8_common import *
from magnet8_arm import experiment_frame, sampling_stats, extrema, validate_batch
from collections import Counter
from types import SimpleNamespace


def require_complete(source):
    for exp in CAL:
        for arm in ARMS:
            folder = Path(source)/'arms'/exp/arm
            if not (folder/'DONE').is_file():
                raise FileNotFoundError(f'Incomplete acquisition: {exp}/{arm}')
            assert not (folder/'RUNNING').exists(), f'Arm still running: {exp}/{arm}'


def read_predictions(folder, b, exp, split):
    table = pd.read_csv(folder/f'predictions_{b}.csv', float_precision='round_trip')
    assert list(table.columns) == ['set', 'sample_id', 'mu', 'sigma']
    assert set(table['set']) == {CAL[exp], *EVAL[exp]}
    assert len(table) == sum(len(split[n]) for n in (CAL[exp], *EVAL[exp]))
    assert np.isfinite(table[['mu', 'sigma']]).all().all() and (table.sigma > 0).all()
    for name in (CAL[exp], *EVAL[exp]):
        assert table.loc[table['set'] == name, 'sample_id'].tolist() == split[name]
    return table


def audit_results(source, df, splits, replay_arms=('A1', 'M1')):
    require_complete(source)
    assert set(replay_arms) <= set(ARMS)
    hashes = code_hashes()
    results, seals, replayed = {}, {}, []
    for exp in CAL:
        item = splits[exp]
        frame = experiment_frame(df, item, exp)
        module = adapter(int(exp[1]))
        results[exp], seals[exp] = {}, {}
        for arm in ARMS:
            folder = Path(source)/'arms'/exp/arm
            result = read_json(folder/'result.json')
            assert (folder/'DONE').read_text(encoding='utf-8').strip() == sha(folder/'result.json')
            assert result['manifest_sha256'] == sha(folder/'manifest.json')
            manifest = read_json(folder/'manifest.json')
            assert all(result[key] == value for key, value in manifest.items())
            k, e = int(arm[1:]), int(exp[1])
            assert result['exp'] == exp and result['arm'] == arm and result['smoke'] is False
            assert result['prereg_sha'] == PREREG_SHA and result['H'] == H
            assert result['config_sha256'] == CONFIG_SHA and result['code_sha256'] == hashes
            assert result['split_sha256'] == digest(item) and result['gp_seed'] == gp_seed(e)
            assert result['seeds'] == dict(family=seed(e, 0, 0), S0=seed(e, 1, k), R=seed(e, 2, k))
            assert result['versions'] == versions(), 'Software environment changed'
            c = config()
            assert result['source_checks'] == {
                'data/magnet6/features.csv': c['reuse']['features_csv_sha256'],
                'data/magnet/igse_predictions.csv': c['data']['scalars_csv_sha256'],
                'data/magnet/N87/B.npy': c['data']['b_waveform_npy_sha256']}
            selected, batch_hashes = [], []
            assert len(result['checkpoints']) == 7
            for b, cp in enumerate(result['checkpoints']):
                train = item[f'S0_{k}']+selected
                assert len(train) == len(set(train)) == 100+20*b
                assert set(train) <= set(item['pool']) and not set(train) & holdouts(exp, item)
                if exp == 'E2':
                    assert set(train) <= set(item['S'])
                assert cp['batch'] == b and cp['added'] == 20*b
                assert cp['training_extrema'] == extrema(frame, train)
                assert cp['model_sha256'] == sha(folder/f'model_{b}.npz')
                assert cp['predictions_sha256'] == sha(folder/f'predictions_{b}.csv')
                read_predictions(folder, b, exp, item)
                with np.load(folder/f'model_{b}.npz', allow_pickle=False) as state:
                    assert all(np.isfinite(state[key]).all() for key in state.files)
                    assert state['X_train'].shape == (len(train), 6)
                    assert state['L'].shape == (len(train), len(train))
                    assert state['alpha'].shape == (len(train),)
                    if b == 6:
                        continue
                    record = read_json(folder/f'batch_{b+1}.json')
                    fp = record['fingerprint']
                    candidates = sorted(set(item['pool'])-set(train))
                    expected_fields = dict(exp=exp, arm=arm, batch=b+1, smoke=False, training_ids=train,
                        candidate_count=len(candidates), candidate_sha256=digest(candidates),
                        split_sha256=digest(item), config_sha256=CONFIG_SHA, code_sha256=hashes, gp_seed=gp_seed(e))
                    assert all(fp[key] == value for key, value in expected_fields.items())
                    for key, state_key in [('kernel_theta', 'kernel_theta'), ('scaler_mean', 'scaler_mean'),
                                           ('scaler_scale', 'scaler_scale'), ('linear_coef', 'coef'),
                                           ('y_mean', 'y_mean'), ('y_std', 'y_std')]:
                        np.testing.assert_array_equal(fp[key], state[state_key])
                    chosen = validate_batch(record, fp, candidates, 20)
                    if arm[0] == 'R':
                        assert chosen == item[f'R_{k}'][20*b:20*(b+1)]
                    elif arm in replay_arms:
                        mean, scale = np.asarray(fp['scaler_mean']), np.asarray(fp['scaler_scale'])
                        x = (frame.loc[train, module.FEATURES].to_numpy()-mean)/scale
                        z = (frame.loc[candidates, module.FEATURES].to_numpy()-mean)/scale
                        kernel = module.make_kernel().clone_with_theta(np.asarray(fp['kernel_theta']))
                        gp = SimpleNamespace(X_train_=x, kernel_=kernel, alpha=1e-10,
                            L_=np.linalg.cholesky(kernel(x)+1e-10*np.eye(len(x))), _y_train_std=fp['y_std'])
                        if arm[0] == 'M':
                            _, replay = module.mixed_believer(gp, z, 20, frame.loc[candidates, 'cell'].to_numpy(),
                                                            frame.loc[selected, 'cell'].tolist(), candidates)
                        else:
                            _, replay = module.believer(gp, z, 20, candidates)
                        assert chosen == [p['sample_id'] for p in replay], 'Acquisition replay mismatch'
                        np.testing.assert_allclose([[p['sigma'], p['score']] for p in record['points']],
                                                   [[p['sigma'], p['score']] for p in replay], rtol=1e-8, atol=0)
                    bin_counts = Counter(frame.loc[selected, 'cell'])
                    for point in record['points']:
                        assert point['cell'] == frame.loc[point['sample_id'], 'cell']
                        if arm[0] in 'AM':
                            assert point['a_c'] == bin_counts[point['cell']]
                            bin_counts[point['cell']] += 1
                selected.extend(chosen)
                batch_hashes.append(record['sha256'])
            assert result['selected_ids'] == selected and result['training_ids'] == item[f'S0_{k}']+selected
            assert result['batch_sha256'] == batch_hashes
            assert result['sampling_counts'] == dict(S0=sampling_stats(frame, item[f'S0_{k}']), additions=sampling_stats(frame, selected))
            assert result['pool_extrema'] == extrema(frame, item['pool'])
            results[exp][arm] = result
            seals[exp][arm] = sha(folder/'result.json')
            if arm in replay_arms and arm[0] in 'AM':
                replayed.append(f'{exp}/{arm}')
    return results, seals, replayed
