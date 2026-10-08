"""Read-only checks of published R9 metrics; no labels, fitting, or seal rewriting."""
import json
from pathlib import Path

from magnet9_independent_recompute import exact_count, independent_gate
from public_release import verify_file

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = 'lab/cases/magnet9/first/metrics.json'


def main():
    verify_file(RELATIVE)
    metrics = json.loads((ROOT / RELATIVE).read_text())
    checked = 0
    for arm, methods in metrics['arms'].items():
        relative = f'lab/cases/magnet9/first/arms/{arm}.json'
        verify_file(relative)
        record = json.loads((ROOT / relative).read_text())
        assert record['scores'] == methods, arm
        for regions in methods.values():
            for row in regions.values():
                assert row['c'] == row['coverage'] / row['n']
                assert row['g'] == max(0., .9 - row['c'])
                checked += 1

    numerators = {}
    for h, z, key in [('H1', 'XF', 'g'), ('H2', 'XT', 'g'),
                      ('H3', 'XF', 'W'), ('H4', 'XT', 'W')]:
        values = [(1.10 if key == 'W' else 1.) * metrics['arms'][f'U{k:02d}']['B'][z][key]
                  - metrics['arms'][f'U{k:02d}']['D'][z][key] for k in range(1, 31)]
        test = metrics['hypotheses'][h]
        assert values == test['differences']['values']
        numerator = exact_count(values)
        assert numerator == test['numerator'] and test['denominator'] == 2**30
        assert test['p'] == numerator / 2**30
        numerators[h] = numerator

    status = {}
    for first, second in [('H1', 'H3'), ('H2', 'H4')]:
        status[first] = 'rejected' if numerators[first] / 2**30 < .025 else 'not_rejected'
        status[second] = ('rejected' if numerators[second] / 2**30 < .025 else 'not_rejected') if status[first] == 'rejected' else 'not_tested'
    assert status == {h: row['status'] for h, row in metrics['hypotheses'].items()}

    gate_checks = 0
    for treatment in ('U', 'S'):
        for method in ('B', 'E', 'D'):
            for z in ('XF', 'XT'):
                rows = [metrics['arms'][f'{treatment}{k:02d}'][method] for k in range(1, 31)]
                base = [metrics['arms'][f'{treatment}{k:02d}']['B'] for k in range(1, 31)]
                for key, value in independent_gate(rows, base, z).items():
                    assert value == metrics['gates'][treatment][method][z][key]
                gate_checks += 1

    for z, h1, h2 in [('XF', 'H1', 'H3'), ('XT', 'H2', 'H4')]:
        gate = metrics['gates']['U']['D'][z]
        conclusion = metrics['conclusions'][z]
        for key in ('A', 'WIDTH', 'J'):
            assert conclusion[key] == gate[key]
        assert conclusion['coverage_status'] == status[h1]
        assert conclusion['Winkler_status'] == status[h2]
        assert conclusion['SUCCESS'] == (gate['J'] and status[h1] == status[h2] == 'rejected')
        differences = [metrics['arms'][f'U{k:02d}']['D'][z]['g']
                       - metrics['arms'][f'S{k:02d}']['D'][z]['g'] for k in range(1, 31)]
        assert differences == metrics['S0'][z]['Delta_g']['values']
    assert metrics['both_success'] == all(c['SUCCESS'] for c in metrics['conclusions'].values())
    print(json.dumps(dict(arm_region_metrics=checked, exact_numerators=numerators,
                          gate_checks=gate_checks, conclusions_equal=True,
                          scope='Published-metric consistency, without original labels')))


if __name__ == '__main__':
    main()
