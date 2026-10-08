#!/usr/bin/env python3
"""Run public reproducibility CLI stages and export a portable MagNet case."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STAGING=ROOT/'lab/cases/magnet'
PYTHON=sys.executable

def cli(*args):
    result=subprocess.run([PYTHON,'-m','lab.repro',*map(str,args)],cwd=ROOT,text=True,capture_output=True)
    if result.returncode: raise RuntimeError(result.stdout+'\n'+result.stderr)
    return result.stdout

def record(stage):
    inputs=['scripts/magnet_'+stage+'.py']
    if stage=='igse':inputs+=['data/magnet/MANIFEST.json']
    metric='data/magnet/'+('fetch_metrics.json' if stage=='fetch' else 'igse_evidence_metrics.json')
    rec=json.loads(cli('run','--name','magnet-'+stage,'--inputs',*inputs,
        '--metrics-from',metric,'--',PYTHON,'scripts/magnet_'+stage+'.py'))
    if rec['exit_code'] or rec.get('parse_error'):raise RuntimeError('Recorded stage failed')
    (STAGING/(stage+'_run.json')).write_text(json.dumps(rec,indent=2)+'\n')
    print(stage,rec['run_id'])

def export():
    from magnet_report import main as render_report
    render_report()
    records={stage:json.loads((STAGING/(stage+'_run.json')).read_text()) for stage in ('fetch','igse')}
    claims=[];lines=['# MagNet N87 iGSE 证据案例','','本案例按温度分别拟合正弦训练子集，评估正弦留出集和全部非正弦样本。',
        '波形名称来自固定规则；多段斜率且无平台的波形合并为三角类。完整公式、来源和局限见数据卡及里程碑报告。','','## 结果','']
    def marked(value,key,stage='igse',unit='比例'):
        cid='c'+str(len(claims));claims.append(dict(id=cid,kind='metric',text=key,value=float(value),unit=unit,
            run_id=records[stage]['run_id'],metric_key=key,tol_abs=0,tol_rel=1e-9))
        return f'{value:.12g}⟦c:{cid}⟧'
    m=json.loads((ROOT/'data/magnet/igse_metrics.json').read_text())
    lines.append('下载校验通过：'+marked(1,'fetch.verified','fetch','布尔编码')+'；N87 ZIP 字节数：'+marked(json.loads((ROOT/'data/magnet/MANIFEST.json').read_text())['files'][0]['size_bytes'],'fetch.bytes','fetch','字节')+'。')
    for key in ('data.n','data.points','split.train_n','split.eval_n'):
        lines.append('`'+key+'`：'+marked(m[key],key,unit='计数')+'。')
    lines+=['','| 波形 / 温度 | 样本数 | 绝对误差均值 | 中位数 | p95 | 十分之一以内比例 | 五分之一以内比例 | 有符号中位数 |',
            '|---|---|---|---|---|---|---|---|']
    for wave in ('sine','triangle','trapezoid'):
        for group in ('all','T25','T50','T70','T90'):
            prefix=f'{wave}.{group}'
            values=[marked(m[prefix+'.'+k],prefix+'.'+k,unit='计数' if k=='n' else '比例') for k in ('n','abs_mean','abs_median','abs_p95','within_10','within_20','signed_median')]
            lines.append('| `'+prefix+'` | '+' | '.join(values)+' |')
    lines+=['','## 方法与限制','','误差为预测减实测再除以实测；表中误差和覆盖比例以小数表示。',
        '基线使用周期分段线性积分和全局峰峰值，未实现论文的次回线分解。分类是波形形状约定，不是原始标签。',
        '不把解析恒等式测试视为对磁芯物理的独立验证。原始数据许可未明确；案例只携带脚本、哈希和汇总。']
    (STAGING/'claims.json').write_text(json.dumps(claims,ensure_ascii=False,indent=2)+'\n')
    (STAGING/'report.md').write_text('\n'.join(lines)+'\n')
    inputs=['scripts/magnet_figures.py','scripts/magnet_case.py','scripts/magnet_report.py','lab/cases/magnet/data_card.md',
       'docs/reports/M3_magnet.md','docs/figures/m3_igse_error.png','docs/figures/m3_igse_scatter.png',
       'data/magnet/igse_metadata.json','data/magnet/igse_metrics.json','data/magnet/MANIFEST.json',
       'lab/cases/magnet/classification_audit_review.csv','lab/cases/magnet/classification_review.json',
       'lab/cases/magnet/validation.json',
       'tests/test_magnet_igse.py','tests/test_magnet_fetch.py']
    artifact=json.loads(cli('run','--name','magnet-artifacts','--inputs',*inputs,'--',PYTHON,'-c','print("保留图表、方法、来源和分类抽检证据")'))
    ids=[r['run_id'] for r in records.values()]+[artifact['run_id']]
    initial=STAGING/'initial_fetch_run.json'
    if initial.exists(): ids.insert(0,json.loads(initial.read_text())['run_id'])
    new=[rid for rid in ids if not (ROOT/'cases/magnet_igse/runs'/rid).exists()]
    if new:cli('export-case','cases/magnet_igse','--runs',*new,'--claims',STAGING/'claims.json','--report',STAGING/'report.md')
    (STAGING/'run_ids.json').write_text(json.dumps(ids,indent=2)+'\n')
    print('Exported cases/magnet_igse')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fetch',action='store_true');ap.add_argument('--igse',action='store_true');args=ap.parse_args()
    STAGING.mkdir(parents=True,exist_ok=True)
    if args.fetch:record('fetch')
    elif args.igse:record('igse')
    else:export()
if __name__=='__main__':main()
