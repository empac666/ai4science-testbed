"""Extract numbers from repository-local snapshots of real DC-link history."""
import json
import re
from pathlib import Path

SOURCES = Path(__file__).parent / 'dev_sources'


def extract():
    initial = (SOURCES / 'fw_initial.md').read_text()
    fixed = (SOURCES / 'fw_fixed.md').read_text()
    old = re.search(r'(\d+) 项 C 测试＋(\d+) 项 CLI 测试通过，共 (\d+) 个 C 断言', initial)
    new = re.search(r'(\d+) 项 C 测试、(\d+) 个断言、(\d+) 项 CLI 测试', fixed)
    if not old or not new:
        raise ValueError('historical summaries changed')
    metrics = {'initial_c_tests': int(old[1]), 'initial_cli_tests': int(old[2]), 'initial_assertions': int(old[3]),
               'fixed_c_tests': int(new[1]), 'fixed_assertions': int(new[2]), 'fixed_cli_tests': int(new[3])}
    for key, label in [('initial_error_pct', '指定正弦用例最大误差'), ('counterexample_pct', '另一纹波相位下存在')]:
        match = re.search(label + r'\s*\*\*(\d+\.\d+)%', initial)
        if not match:
            raise ValueError('historical error metric absent')
        metrics[key] = float(match[1])
    for key, pattern in [('fixed_ls_error_pct', r'原 0\.267084% 反例，LS \| (\d+\.\d+)%'),
                         ('fixed_logger_bytes', r'logger\s*\*\*(\d+) B')]:
        match = re.search(pattern, fixed)
        if not match:
            raise ValueError('fixed metric absent: ' + key)
        metrics[key] = float(match[1]) if 'pct' in key else int(match[1])
    table = (SOURCES / 'compare_sw_avg.md').read_text()
    for name in ('sw_film_C090_L030_base', 'sw_film_C095_L100_base', 'sw_film_C100_L050_harmonics'):
        row = next(line for line in table.splitlines() if line.startswith('| ' + name + ' '))
        cells = [c.strip() for c in row.strip('|').split('|')]
        metrics[name + '_sw_error_pct'] = float(cells[6])
        metrics[name + '_avg_error_pct'] = float(cells[9])
    ruling = (SOURCES / 'rulings.md').read_text()
    match = re.search(r'code (\d+) 就是 PLL 失锁', ruling)
    metrics['pll_unlock_gate_code'] = int(match[1])
    return metrics


if __name__ == '__main__':
    print(json.dumps(extract(), ensure_ascii=False, allow_nan=False))
