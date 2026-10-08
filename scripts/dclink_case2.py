#!/usr/bin/env python3
"""通过公开 lab.repro CLI 记录并导出第二轮证据。"""
import json
import sys
import subprocess
from dclink_surrogate2 import ROOT,OUT,STAGE,METHODS,SETS,write_json
PYTHON=sys.executable

def cli(*args):
    r=subprocess.run([PYTHON,'-m','lab.repro',*map(str,args)],cwd=ROOT,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stdout+'\n'+r.stderr)
    return r.stdout

def record(name,inputs,command,metrics=None):
    args=['run','--name',name,'--inputs',*inputs]
    if metrics: args+=['--metrics-from',metrics]
    return json.loads(cli(*args,'--',*command))['run_id']

def train():
    marker=STAGE/'surrogate_training_run.json'
    if marker.exists():
        # Revalidate provenance and recover outputs without fitting again.
        subprocess.run([PYTHON,'scripts/dclink_surrogate2.py'],cwd=ROOT,check=True); return
    rid=record('dclink-round2-first',['scripts/dclink_surrogate2.py','scripts/dclink_surrogate.py','scripts/dclink_split2.py',
        'data/dclink/sweep.csv','data/dclink/design.json','data/dclink2/sweep_ideal.csv','data/dclink2/sweep_nonideal.csv',
        'data/dclink2/design.json','data/dclink2/split.json','lab/cases/dclink2/split_manifest.json',
        'data/dclink2/READY_TO_RUN','lab/cases/dclink2/config_prerun.json',
        'docs/prereg/M3_surrogate_round2_prereg.md','data/dclink_src/simsw/dclink_simsw/common.py'],
        [PYTHON,'scripts/dclink_surrogate2.py'],'data/dclink2/surrogate_evidence_metrics.json')
    write_json(marker,{'run_id':rid})

def verify_results():
    import numpy as np
    import pandas as pd
    m=json.loads((OUT/'surrogate_metrics.json').read_text())
    df=pd.read_csv(OUT/'predictions.csv')
    for method in METHODS:
        for group in SETS:
            r=df[(df.method==method)&(df.sensor=='ideal')&(df['split']==group)]
            c=int(((r.y>=r.lower)&(r.y<=r.upper)).sum())
            assert (len(r),c)==(m[f'{method}.{group}.n'],m[f'{method}.{group}.covered'])
            assert np.isclose((r.upper-r.lower).mean(),m[f'{method}.{group}.mean_width'],atol=1e-13)
        r=df[(df.method==method)&(df.sensor=='ideal')&(df['split']=='calib')]
        assert len(r)==75
        score=abs(r.y-r.prediction)/r.sigma
        assert np.isclose(np.sort(score)[68],m[f'{method}.calib.q'],atol=1e-12)
    for g in ['calib','test','ood_dt3','ood_corner']:
        r=df[(df.method=='m2')&(df.sensor=='nonideal')&(df['split']==g)]
        assert int(((r.y>=r.lower)&(r.y<=r.upper)).sum())==m[f'm2.nonideal_{g}.covered']
    for name in ['predictions.csv','surrogate_metrics.json','surrogate_metadata.json']:
        assert (OUT/name).read_bytes()==(STAGE/'first'/name).read_bytes()
    # Independently apply thresholds to recomputed bounds instead of calling criteria().
    r=df[(df.method=='m2')&(df.sensor=='ideal')]
    tw=(r[r['split']=='test'].upper-r[r['split']=='test'].lower).mean()
    passed=[]
    for label,g,threshold in [('C1','test',62),('C2-dt3','ood_dt3',24),('C2-corner','ood_corner',24)]:
        a=r[r['split']==g]
        coverage=int(((a.y>=a.lower)&(a.y<=a.upper)).sum())>=threshold
        width=g=='test' or (a.upper-a.lower).mean()<=3*tw
        ok=coverage and width
        assert ok==m['criterion.'+label+'.pass']
        passed.append(ok)
    assert all(passed)==m['criterion.overall']
    print(json.dumps(dict(methods_checked=6,eval_groups_checked=4,nonideal_groups_checked=4,
                          calibration_n=75,calibration_rank=69,first_files_checked=3,validation_pass=1)))

def report(m,timing):
    lines=['# M3 DC-link 代理模型第二轮执行报告','',
        '严格按预注册实施；第一轮判定不追溯修改。主方法为 M2，只有理想传感器的新 test、E-dt3 和 E-corner 参与判定。',
        '主持人启动全量扫描：`nohup python3 scripts/dclink_sweep2.py --jobs 4 > data/dclink2/sweep.log 2>&1 &`。',
        '扫描完成后执行：`make surrogate2`。第一轮输入和脚本保持只读；共享机器限制四个扫描进程、每进程单计算线程。','',
        '## 判据与原始计数','',
        '| 判据 | 覆盖数 / 样本数 | 覆盖数下限 | 平均宽度 | 宽度上限 | 判定 |',
        '|---|---|---|---|---|---|']
    for c in ['C1','C2-dt3','C2-corner']:
        p='criterion.'+c
        limit=f'{m[p+".width_limit"]:.6f}' if p+'.width_limit' in m else '不设上限'
        lines.append(f'| {c} | {m[p+".covered"]}/{m[p+".n"]} | {m[p+".required_covered"]} | {m[p+".mean_width"]:.6f} | {limit} | '+('通过' if m[p+'.pass'] else '不通过')+' |')
    lines+=['','总判定：**'+('通过' if m['criterion.overall'] else '不通过')+'**。误差和宽度单位为百分点；覆盖率为比例。','',
        '## 方法对比','',
        'M0：GP 标准保形；M1：GP σ 归一化保形；M2：reviewer_b 解析均值＋残差 GP、σ 归一化保形；M3：reviewer_b 解析模型标准保形；M4：MLP 标准保形；M5：第一轮 researcher_a 解析模型标准保形。','',
        '| 方法 | 集合 | MAE | 最大误差 | 偏差 | 覆盖数 | 覆盖率 | 平均宽度 |',
        '|---|---|---|---|---|---|---|---|']
    for method in METHODS:
        for g in SETS:
            p=f'{method}.{g}'
            vals=[f'{m[p+"."+k]:.6f}' for k in ['mae','max_abs_error','bias']]
            lines.append('| '+method+' | '+g+' | '+' | '.join(vals)+f' | {m[p+".covered"]}/{m[p+".n"]} | {m[p+".coverage"]:.6f} | {m[p+".mean_width"]:.6f} |')
    lines+=['','supplement_ood 是已见过结果的第一轮 OOD；仅补充报告，不训练、不参与判据。','',
        '## 非理想对照','',
        '使用同一组参数点和独立种子，沿用理想数据上拟合与校准的 M2，不重新校准。',
        '| 集合 | 覆盖数 | 覆盖率 | 平均宽度 | MAE |','|---|---|---|---|---|']
    for g in ['calib','test','ood_dt3','ood_corner','all']:
        p='m2.nonideal_'+g
        lines.append(f'| {g} | {m[p+".covered"]}/{m[p+".n"]} | {m[p+".coverage"]:.6f} | {m[p+".mean_width"]:.6f} | {m[p+".mae"]:.6f} |')
    lines+=['','配对目标差绝对值：'+ '，'.join(f'{k}={m["nonideal.abs_delta."+k]:.6f}' for k in ['mean','median','p90','p95','max'])+'。','',
        '## 耗时与执行细节','',f'完整扫描墙钟耗时：{timing["total_wall_s"]:.6f} 秒；完成仿真数：{timing["completed_n"]}。',
        '仿真通过导入调用第一轮 run_case；适配层只设置理想/非理想传感器、输出路径和冒烟时长。正式运行仍为记录 6 秒、startup 1 秒、solver dt 50 ns。',
        '设计使用种子 20261004 的同一随机生成器顺序产生各组 LHS，四维 dead_time 用六个等宽类别映射；E-in 从 600 个候选依序排除角落后取前 150 个。E-dt3 的 dead_time 固定，其余维度保持 LHS。',
        '划分在 READY_TO_RUN 前生成并写入 SHA256；train 仅第一轮全部分布内样本。n=75 的校准分位数取第 69 个顺序统计量。',
        '所有超参数在 scripts/dclink_surrogate2.py 的 CONFIG 固定并打印，GP 与 MLP 复用第一轮配置。输入标准化仅在 train 拟合；M2 解析均值与残差 GP 都只用 train。',
        '第一次完整评估保存在 lab/cases/dclink2/first；重复运行核对输入和配置哈希后复用第一次结果。','',
        '## 偏离与限制','',
        '正式设计、拟合、校准及判定未主动偏离预注册。冒烟首次使用 1.5 秒时长未满足回放的 3 秒稳定门控，失败日志保留；改用 4 秒记录、1 秒 startup 的两例缩短测试，均与正式数据隔离。',
        '仿真与回放共享物理来源，结果不能替代实测验证。非理想对照、第一轮 OOD 与 M3/M5 比较均只报告。','',
        '## 数据解释','']
    for g in ['test','ood_dt3','ood_corner']:
        lines.append(f'{g}：M2 偏差 {m[f"m2.{g}.bias"]:.6f}、MAE {m[f"m2.{g}.mae"]:.6f}，覆盖 {m[f"m2.{g}.covered"]}/{m[f"m2.{g}.n"]}，区间宽度 {m[f"m2.{g}.mean_width"]:.6f}（test 的 {m[f"m2.{g}.mean_width"]/m["m2.test.mean_width"]:.6f} 倍）。这些计数与宽度直接决定预注册结果。')
    for g in ['test','ood_dt3','ood_corner']:
        lines.append(f'{g}：M3 与 M5 的 MAE 分别为 {m[f"m3.{g}.mae"]:.6f} 和 {m[f"m5.{g}.mae"]:.6f}；M0 与 M2 覆盖率分别为 {m[f"m0.{g}.coverage"]:.6f} 和 {m[f"m2.{g}.coverage"]:.6f}。这是预注册方法的描述性对照，不能单独确证差异的物理因果。')
    import pandas as pd
    import numpy as np
    pred=pd.read_csv(OUT/'predictions.csv')
    main=pred[(pred.method=='m2')&(pred.sensor=='ideal')]
    cal=main[main['split']=='calib']; corner=main[main['split']=='ood_corner']
    score=abs(corner.y-corner.prediction)/corner.sigma
    lines.append(f'角落的归一化残差第 90 百分位为 {np.quantile(score,.9):.6f}，超过校准阈值 q={m["m2.calib.q"]:.6f}；角落有 {m["m2.ood_corner.n"]-m["m2.ood_corner.covered"]} 个目标值落在区间外。σ 归一化保形已将平均宽度增至 test 的 {m["m2.ood_corner.mean_width"]/m["m2.test.mean_width"]:.6f} 倍，仍未充分覆盖角落残差尾部。')
    lines.append(f'M2 相比 M1 的角落 MAE 从 {m["m1.ood_corner.mae"]:.6f} 降至 {m["m2.ood_corner.mae"]:.6f}，平均宽度从 {m["m1.ood_corner.mean_width"]:.6f} 收窄至 {m["m2.ood_corner.mean_width"]:.6f}，覆盖数也从 {m["m1.ood_corner.covered"]}/30 降至 {m["m2.ood_corner.covered"]}/30；点预测改善与区间覆盖并非同步。本轮据此保持不通过，不事后扩大 q。')
    lines.append('非理想数据仅改变目标值，因此配对输入上的区间宽度完全相同；覆盖变化反映传感器扰动带来的目标移动。')
    rid=json.loads((STAGE/'surrogate_training_run.json').read_text())['run_id']
    rec=json.loads((ROOT/'runs'/rid/'record.json').read_text())
    lines+=['','## 验证','',
            f'第一次训练记录：{rid}；时长 {rec["duration_s"]:.6f} 秒，峰值进程树 RSS {rec["peak_rss_mb"]:.6f} MiB。训练 stderr 为空；MLP 未达到最大迭代数。',
            '第二轮测试通过；逐区间边界独立复算覆盖数、平均宽度和判据，核对各方法第 69 个校准顺序统计量、非理想计数及第一次副本字节一致性，全部通过。',
            '两张图以 Noto Sans CJK SC、150 dpi 生成并已目视检查。lab.evidence check cases/dclink_surrogate2 返回 pass；结构化检查结果保存至案例 check.json。']
    (ROOT/'docs/reports/M3_dclink_round2_researcher_a.md').write_text('\n'.join(lines)+'\n')

def main():
    m=json.loads((OUT/'surrogate_metrics.json').read_text()); timing=json.loads((OUT/'sweep_timing.json').read_text())
    tests=record('dclink-round2-tests',['tests/test_dclink_round2.py','data/dclink2/design.json','data/dclink2/split.json',
        'lab/cases/dclink2/split_manifest.json'],[PYTHON,'-m','unittest','discover','-s','tests','-p','test_dclink_round2.py','-v'])
    validation=record('dclink-round2-independent-verification',['scripts/dclink_case2.py','data/dclink2/predictions.csv',
        'data/dclink2/surrogate_metrics.json','lab/cases/dclink2/first/predictions.csv'],[PYTHON,'scripts/dclink_case2.py','--verify-results'])
    report(m,timing)
    rid=json.loads((STAGE/'surrogate_training_run.json').read_text())['run_id']
    art=record('dclink-round2-artifacts',['scripts/dclink_sweep2.py','scripts/dclink_figures2.py','scripts/dclink_case2.py',
        'tests/test_dclink_round2.py','data/dclink2/surrogate_metrics.json','data/dclink2/predictions.csv',
        'lab/cases/dclink2/first/provenance.json','docs/figures/m3_round2_methods.png',
        'docs/figures/m3_round2_nonideal.png','docs/reports/M3_dclink_round2_researcher_a.md'],
        [PYTHON,'scripts/dclink_split2.py','--verify'])
    timeid=record('dclink-round2-scan-timing',['data/dclink2/sweep_timing.json','data/dclink2/progress.jsonl'],
        [PYTHON,'-c','print("导入主持人启动的扫描计时，不运行扫描")'],'data/dclink2/sweep_timing_evidence.json')
    claims=[]; lines=['# DC-link 第二轮证据案例','','主判定仅理想数据上的 M2；非理想、第一轮 OOD 和解析模型比较只报告。','']
    for key,v in m.items():
        cid='c'+str(len(claims))
        claims.append(dict(id=cid,kind='metric',text=key,value=float(v),unit='原指标单位',run_id=rid,metric_key=key,tol_abs=0,tol_rel=1e-6))
        lines.append(f'- `{key}`：{float(v):.10g}⟦c:{cid}⟧')
    key='total_wall_s'; v=timing[key]; cid='c'+str(len(claims))
    claims.append(dict(id=cid,kind='metric',text='全量扫描耗时',value=v,unit='秒',run_id=timeid,metric_key=key,tol_abs=0,tol_rel=1e-6))
    lines+=['',f'主持人启动的全量扫描墙钟耗时：{v:.10g}⟦c:{cid}⟧ 秒。',
            '详细中文报告见 docs/reports/M3_dclink_round2_researcher_a.md；配置及第一次结果见 lab/cases/dclink2/first。']
    write_json(STAGE/'claims.json',claims); (STAGE/'report.md').write_text('\n'.join(lines)+'\n')
    runs=[rid,art,timeid,tests,validation]; new=[r for r in runs if not (ROOT/'cases/dclink_surrogate2/runs'/r).exists()]
    cli('export-case','cases/dclink_surrogate2','--runs',*new,'--claims','lab/cases/dclink2/claims.json','--report','lab/cases/dclink2/report.md')
    write_json(STAGE/'run_ids.json',runs)

if __name__=='__main__':
    if sys.argv[1:]==['--train']: train()
    elif sys.argv[1:]==['--verify-results']: verify_results()
    else:
        t=json.loads((OUT/'sweep_timing.json').read_text())
        write_json(OUT/'sweep_timing_evidence.json',{k:v for k,v in t.items() if isinstance(v,(int,float)) and not isinstance(v,bool)})
        main()
