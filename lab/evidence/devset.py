"""Build transparent historical-evidence perturbations, not alleged original failures."""
import copy
import json
import shutil
from pathlib import Path
from lab.repro.runner import ROOT, PYTHON, run, write_json
from lab.evidence.checker import digest


def build():
    sources = Path(__file__).parent / 'dev_sources'
    rec = run('dclink-history-extraction', [PYTHON, '-m', 'lab.evidence.history_metrics'],
              inputs=sorted(sources.glob('*.md')), parser='json')
    if rec['exit_code'] or rec.get('parse_error'):
        raise ValueError('historical metric extraction failed: ' + str(rec))
    metrics = json.loads((ROOT / 'runs' / rec['run_id'] / 'metrics.json').read_text())
    base = ROOT / 'evalsets/dev'
    labels = {}
    def case(name, key, label='normal', codes=(), mutate=None, description='原始历史指标完整且一致'):
        dest = base / name
        if dest.exists():
            raise ValueError('refusing to overwrite dev case: ' + name)
        run_dest = dest / 'runs' / rec['run_id']
        run_dest.parent.mkdir(parents=True)
        shutil.copytree(ROOT / 'runs' / rec['run_id'], run_dest)
        value = metrics[key]
        unit = '%' if key.endswith('pct') else ''
        claims = [{'id': 'v', 'kind': 'metric', 'text': '历史材料中的 ' + key,
                   'value': value, 'unit': unit, 'run_id': rec['run_id'], 'metric_key': key}]
        write_json(dest / 'claims.json', claims)
        (dest / 'report.md').write_text('# DC-link 历史证据开发案例\n\n'
              '本例由真实历史材料构造，用于 EV-1.0 格式检查；不是本机重跑 DC-link 的结果。\n'
              '构造说明：' + description + '\n\n## 结果\n'
              f'`{key}`：{value}⟦c:v⟧\n', encoding='utf-8')
        write_json(dest / 'source.json', {'origin': 'dclink-edge-ai@docs-history',
                   'extraction_run': rec['run_id'], 'metric': key,
                   'mutation': description, 'historical_input_copies': [
                       {'path': 'runs/' + rec['run_id'] + '/' + item['path'], 'sha256': item['sha256']}
                       for item in rec['inputs']]})
        if mutate:
            mutate(dest, run_dest, claims)
        labels[name] = {'label': label, 'expected_codes': list(codes), 'description': description}
    def rec_change(field, value=None, delete=False):
        def change(dest, rd, claims):
            r = json.loads((rd / 'record.json').read_text())
            if delete:
                del r[field]
            else:
                r[field] = value
            write_json(rd / 'record.json', r)
        return change
    def claim_change(field, value):
        def change(dest, rd, claims):
            claims[0][field] = value
            write_json(dest / 'claims.json', claims)
        return change
    def report_change(text):
        return lambda d, rd, c: (d / 'report.md').write_text(text, encoding='utf-8')
    def models(mode):
        def change(d, rd, c):
            c[0].update(kind='validation', subject_model='estimator', reference_model='average')
            write_json(d / 'claims.json', c)
            m = {'estimator': {'source': 'dclink:ref_estimator', 'derived_from': [], 'assumptions': []},
                 'average': {'source': 'dclink:average_model', 'derived_from': [], 'assumptions': []}}
            if mode == 'source':
                m['average']['source'] = m['estimator']['source']
            elif mode == 'derived':
                m['bridge'] = {'source': 'dclink:bridge', 'derived_from': ['average'], 'assumptions': []}
                m['estimator']['derived_from'] = ['bridge']
            else:
                for model in m.values():
                    model['assumptions'] = ['core:ideal_average_topology']
            write_json(d / 'models.json', m)
        return change
    keys = ['initial_c_tests', 'initial_cli_tests', 'initial_assertions', 'fixed_c_tests', 'fixed_assertions',
            'fixed_cli_tests', 'initial_error_pct', 'counterexample_pct', 'fixed_ls_error_pct', 'fixed_logger_bytes',
            'sw_film_C090_L030_base_sw_error_pct', 'sw_film_C095_L100_base_sw_error_pct']
    for i, key in enumerate(keys, 1):
        case(f'normal_{i:02d}', key)
    case('defect_01_report_wrong', 'initial_c_tests', 'defect', ['E_REPORT_MISMATCH'],
         report_change(f"## 结果\nC 测试 {metrics['fixed_c_tests']}⟦c:v⟧"), '正文偷换为修复后的测试数量，论断仍是初版数量')
    case('defect_02_claim_wrong', 'initial_c_tests', 'defect', ['E_VALUE_MISMATCH', 'E_REPORT_MISMATCH'],
         claim_change('value', metrics['fixed_c_tests']), '把初版论断偷换为修复后数量，运行指标和正文未变')
    case('defect_03_no_run', 'fixed_c_tests', 'defect', ['E_RUN_MISSING'],
         lambda d, rd, c: shutil.rmtree(d / 'runs'), '删除历史提取运行证据')
    case('defect_04_provenance', 'fixed_c_tests', 'defect', ['E_SCHEMA', 'E_PROVENANCE'],
         rec_change('cmd', delete=True), '删除运行命令 provenance')
    case('defect_05_hash', 'fixed_c_tests', 'defect', ['E_HASH'],
         lambda d, rd, c: (rd / 'stdout.txt').write_text('tampered historical transcript'), '篡改 stdout 未更新哈希')
    case('defect_06_run_failed', 'fixed_c_tests', 'defect', ['E_RUN_FAILED'],
         rec_change('exit_code', 1), '注入失败退出码；不是声称原始 DC-link 运行失败')
    case('defect_07_metric_missing', 'fixed_c_tests', 'defect', ['E_METRIC_MISSING'],
         claim_change('metric_key', 'absent'), '论断引用不存在的指标键')
    case('defect_08_unknown_claim', 'fixed_c_tests', 'defect', ['E_CLAIM_UNKNOWN'],
         report_change(f"## 结果\n{metrics['fixed_c_tests']}⟦c:absent⟧"), '正文引用未登记论断')
    case('defect_09_unclaimed', 'initial_error_pct', 'defect', ['E_UNCLAIMED_NUMBER'],
         report_change(f"## 结果\n最大误差 {metrics['initial_error_pct']}%"), '真实误差缺失论断标记')
    case('defect_10_same_source', 'fixed_ls_error_pct', 'defect', ['E_SAME_SOURCE'], models('source'), '模拟将同一来源包装为独立验证')
    case('defect_11_derived', 'fixed_ls_error_pct', 'defect', ['E_SAME_SOURCE'], models('derived'), '模拟多层派生模型互相验证')
    case('defect_12_core', 'sw_film_C090_L030_base_avg_error_pct', 'defect', ['E_SAME_SOURCE'], models('core'),
         '基于平均值模型自证的历史评审，显式登记共享理想平均拓扑 core 假设')
    case('defect_13_scope', 'fixed_c_tests', 'defect', ['E_SCOPE'],
         lambda d, rd, c: write_json(d / 'task.json', {'allowed_paths': ['fw/'], 'changed_files': ['sim/model.py']}),
         '模拟 fw 限定任务修改 sim 文件；未实际修改 DC-link 仓库')
    case('defect_14_path', 'fixed_c_tests', 'defect', ['E_PATH', 'E_METRIC_MISSING'],
         rec_change('metrics_file', '../metrics.json'), '指标路径含父目录段')
    case('defect_15_schema', 'fixed_c_tests', 'defect', ['E_SCHEMA', 'E_RUN_MISSING'],
         lambda d, rd, c: (rd / 'record.json').write_text('{broken'), '损坏运行记录 JSON')
    case('defect_16_abs_path', 'fixed_c_tests', 'defect', ['E_PATH', 'E_METRIC_MISSING'],
         rec_change('metrics_file', '/metrics.json'), '指标路径为绝对路径')
    case('semantic_01_thd', 'pll_unlock_gate_code', 'semantic', [],
         report_change(f"## 结果\nTHD 门控代码 {metrics['pll_unlock_gate_code']}⟦c:v⟧ 拦截了谐波。"),
         '历史裁定指出 code 3 是 PLL 失锁而非 THD 门控；数字一致，但文字语义错误，确定性检查器不裁定')
    write_json(base / 'labels.json', labels)
    return labels


if __name__ == '__main__':
    print('Generated ' + str(len(build())) + ' cases')
