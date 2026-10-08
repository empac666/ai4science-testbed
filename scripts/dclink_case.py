#!/usr/bin/env python3
"""Record local evidence via the public CLI; export a portable numeric case."""
import json
import subprocess
import sys
from dclink_surrogate import ROOT, FEATURES, METHODS, SETS, write_json
PYTHON=sys.executable

def cli(*args):
    result=subprocess.run([PYTHON,'-m','lab.repro',*map(str,args)],cwd=ROOT,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout+'\n'+result.stderr)
    return result.stdout

def nest(metrics):
    result={}
    for key,value in metrics.items():
        current=result
        parts=key.split('.')
        for part in parts[:-1]: current=current.setdefault(part,{})
        current[parts[-1]]=int(value) if isinstance(value,bool) else value
    return result

def record(name,inputs,cmd,metrics=None):
    args=['run','--name',name,'--inputs',*inputs]
    if metrics: args+=['--metrics-from',metrics]
    return json.loads(cli(*args,'--',*cmd))['run_id']

def train():
    surrogate=record('dclink-surrogate', ['scripts/dclink_surrogate.py','data/dclink/sweep.csv','data/dclink/split.json',
        'data/dclink/design.json','lab/cases/dclink/split_manifest.json','docs/prereg/M2_prereg.md',
        'data/dclink_src/simsw/dclink_simsw/common.py'], [PYTHON,'scripts/dclink_surrogate.py'],
        'data/dclink/surrogate_evidence_metrics.json')
    write_json(ROOT/'lab/cases/dclink/surrogate_training_run.json', {'run_id':surrogate})

def main():
    out=ROOT/'data/dclink'; claims=[]
    metricrun=json.loads((ROOT/'lab/cases/dclink/surrogate_training_run.json').read_text())['run_id']
    runids=[metricrun]
    artifactrun=record('dclink-surrogate-artifacts', ['data/dclink/surrogate_metrics.json',
        'data/dclink/predictions.csv','data/dclink/surrogate_metadata.json',
        'data/dclink/surrogate_first/provenance.json','scripts/dclink_figures.py','scripts/dclink_case.py',
        'docs/figures/m2_methods.png','docs/figures/m2_bias_map.png'],
        [PYTHON,'-c','print("保留训练产物与中文图的哈希证据")'])
    runids.append(artifactrun)
    metrics=json.loads((out/'surrogate_metrics.json').read_text())
    splitrun=record('dclink-split-verify',['scripts/dclink_split.py','scripts/dclink_verify_split.py','data/dclink/split.json',
        'lab/cases/dclink/split_manifest.json','data/dclink/design.json'],[PYTHON,'scripts/dclink_verify_split.py'])
    runids.append(splitrun)
    timing=out/'rebuild_timing.json'
    if not timing.exists(): raise FileNotFoundError('Host rebuild_timing.json is required')
    timingrun=record('dclink-rebuild-external',['data/dclink/rebuild_timing.json'],
        [PYTHON,'-c','print("主持人外部扫描耗时；此步骤仅导入，不运行扫描")'],'data/dclink/rebuild_timing.json')
    runids.append(timingrun)
    convrun=None; conv={}
    if (out/'convergence.csv').exists():
        convrun=record('dclink-convergence-parse',['scripts/dclink_convergence_metrics.py','data/dclink/convergence.csv'],
            [PYTHON,'scripts/dclink_convergence_metrics.py'])
        runids.append(convrun)
        conv=json.loads((out/'convergence_metrics.json').read_text())
        write_json(out/'convergence_evidence_metrics.json',nest(conv))
        convrun=record('dclink-convergence-metrics',['data/dclink/convergence.csv','data/dclink/convergence_metrics.json'],
            [PYTHON,'-c','print("导入收敛差值")'],'data/dclink/convergence_evidence_metrics.json')
        runids.append(convrun)
    def marked(value,key,run=metricrun,unit='百分点'):
        cid='c'+str(len(claims))
        claims.append(dict(id=cid,kind='metric',text=key,value=float(value),unit=unit,run_id=run,
                           metric_key=key,tol_abs=0,tol_rel=1e-6))
        return f'{float(value):.10g}⟦c:{cid}⟧'
    lines=['# DC-link 代理模型证据案例','', '本案例来自冻结划分及完整扫描；训练只使用训练集，校准只使用校准集。',
           '扫描计时是主持人生成的外部指标；导入步骤的运行时长不是扫描时长。','', '## 结果','',
           '| 方法 | 集合 | MAE（百分点） | 最大误差（百分点） | 偏差（百分点） | 覆盖率（比例） | 平均宽度（百分点） |',
           '|---|---|---|---|---|---|---|']
    for method in METHODS:
        for group in SETS:
            cells=[marked(metrics[f'{method}.{group}.{k}'],f'{method}.{group}.{k}',unit='比例' if k=='coverage' else '百分点')
                   for k in ('mae','max_abs_error','bias','coverage','mean_width')]
            lines.append('| '+method+' | '+group+' | '+' | '.join(cells)+' |')
    ok=metrics['criterion.gp_ood_coverage_in_85_95']
    lines+=['', '预注册主判据：'+('通过' if ok else '不通过')+'；GP 标准保形 OOD 覆盖率为 '+marked(metrics['gp_conformal.ood.coverage'],'gp_conformal.ood.coverage',unit='比例')+'。']
    timingmetrics=json.loads(timing.read_text())
    for key,value in timingmetrics.items():
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            lines.append('外部扫描指标 `'+key+'`：'+marked(value,key,timingrun,unit='原文件单位')+'。')
    if convrun:
        for key,value in conv.items():
            lines.append('收敛指标 `'+key+'`：'+marked(value,key,convrun)+'。')
    else: lines.append('收敛检查：待主持人补充。')
    lines+=['','## 方法与限制','', 'GP 标准保形使用绝对校准残差；原生区间及归一化保形仅为附加结果。',
            '模拟器与代理模型共享物理来源，本案例只声明测量指标，不声明独立物理验证。',
            '配置与第一次完整运行快照保存在 data/dclink/surrogate_first；详细推导与讨论见 docs/reports/M2_researcher_a.md。']
    staging=ROOT/'lab/cases/dclink'
    write_json(staging/'surrogate_claims.json',claims)
    (staging/'surrogate_report.md').write_text('\n'.join(lines)+'\n')
    new_runs=[rid for rid in runids if not (ROOT/'cases/dclink_surrogate/runs'/rid).exists()]
    cli('export-case','cases/dclink_surrogate','--runs',*new_runs,'--claims','lab/cases/dclink/surrogate_claims.json',
        '--report','lab/cases/dclink/surrogate_report.md')
    write_json(staging/'surrogate_run_ids.json',runids)
    write_report(metrics,timingmetrics,conv)

def write_report(m,timing,conv):
    meta=json.loads((ROOT/'data/dclink/surrogate_metadata.json').read_text())
    pred=__import__('pandas').read_csv(ROOT/'data/dclink/predictions.csv')
    gp=pred[pred.method=='gp_conformal']
    rows=['# 里程碑二：代理模型、区间与证据流程','',
          '新增训练评估、只读划分校验、中文绘图、收敛解析与证据导出脚本及测试；Makefile 提供 sweep、surrogate、m2。',
          '运行：`make surrogate`；完整重建由主持人执行 `make m2`。本次未运行 sweep 或 m2。',
          'sweep 入口包装器调用原重建脚本，跨目录清理保留冻结划分的原始字节并校验设计哈希。',
          '现有 dclink_split.py 的 --verify 会写文件，因此使用只读包装器执行原脚本并拒绝任何非一致写入。',
          '证据适配副本将扁平键展开、布尔转为数值；原始指标保留任务规定格式。','',
          '## 固定方法与物理依据','',
          '所有配置见 scripts/dclink_surrogate.py 的 CONFIG，训练开始即打印；仅训练集拟合标准化与模型，校准集仅计算区间。未根据测试或 OOD 结果调整配置。第一次完整运行保存在 lab/cases/dclink/surrogate_first，并复制至 data/dclink/surrogate_first；前者跨重建保留。重复训练核对预测输入的哈希，忽略扫描耗时列的变化。',
          '解析模型为 ŷ = β₀ + β₁ t_dead f_c/load + β₂ f_grid/(2π bw_iac) + β₃ t_aperture f_c。',
          '每周期死区占比为 t_dead f_c，平均桥臂电压扰动与该占比成正比；以负载相关电流幅值归一化后取 1/load。单极点低通低频群延迟约为 1/(2π bw_iac)，其相位扰动随 f_grid 缩放。孔径偏移相对载波周期的比例为 t_aperture f_c。线性回归系数吸收符号、比例与估计器敏感度。',
          '物理常量运行时读取快照 common.py 的 SimulationConfig；这是小扰动一阶启发式，不是电容误差的精确解析解。特征在读取完整 y 之前确定。',
          '负载插值使用训练负载范围内等宽箱中心与箱内 y 均值，空箱跳过，范围外取端点。GP 为标准化输入上的 Constant×ARD RBF+White，normalize_y=True；MLP 为固定配置的小网络。',
          '标准保形取校准绝对残差的第 ceil((n+1)(1−α)) 个顺序统计量；超出 n 时返回无穷大。GP 原生区间为 ±1.645σ，归一化保形取 |r|/σ 的相同分位数。主判据只用标准保形。',
          '', '实际执行配置：','```json',json.dumps(meta['config'],ensure_ascii=False,indent=2),'```',
          '解析拟合系数：`'+json.dumps(meta['analytic_coefficients'])+'`。',
          'GP 拟合核：`'+meta['fitted_gp_kernel']+'`；MLP 迭代数：'+str(meta['mlp_iterations'])+'。','',
          '## 实测结果','', '| 方法（标准保形） | test MAE | test 覆盖率 | OOD MAE | OOD 最大误差 | OOD 偏差 | OOD 覆盖率 | OOD 平均宽度 |',
          '|---|---|---|---|---|---|---|---|']
    for method in METHODS[:4]:
        keys=['test.mae','test.coverage','ood.mae','ood.max_abs_error','ood.bias','ood.coverage','ood.mean_width']
        rows.append('| '+method+' | '+' | '.join(f'{m[method+"."+k]:.6f}' for k in keys)+' |')
    rows+=['','误差及宽度单位为百分点，覆盖率为比例。全部方法、全部集合及附加区间的明细见 surrogate_metrics.json 与证据案例。',
           '主判据：'+('通过' if m['criterion.gp_ood_coverage_in_85_95'] else '不通过')+'。GP 标准保形 OOD 覆盖率 '+f"{m['gp_conformal.ood.coverage']:.6f}"+'，预注册允许范围为 [0.85, 0.95]。']
    q=m['gp_conformal.calib.q']
    rows.append(f'GP 校准半宽 q={q:.6f}，故所有标准保形区间宽度为 {2*q:.6f}。')
    for group in ['calib','test','ood_deadtime3','ood_lowload_lowbw']:
        g=gp[gp['split']==group]; err=(g.prediction-g.y).abs()
        rows.append(f'{group}：样本数 {len(g)}，绝对残差均值 {err.mean():.6f}，中位数 {err.median():.6f}，超过校准半宽的样本数 {int((err>q).sum())}。')
    ood=gp[gp['split'].str.startswith('ood')]
    missed=int(((ood.prediction-ood.y).abs()>q).sum())
    rows.append(f'本次 OOD 的 {missed}/{len(ood)} 个残差超过校准半宽，导致覆盖率偏低；死区子组整体偏差为 {m["gp_conformal.ood_deadtime3.bias"]:.6f}，角落子组整体偏差为 {m["gp_conformal.ood_lowload_lowbw.bias"]:.6f}，方向相反。分布内 test 也有失覆盖，说明校准集的尾部残差对本次测试集偏乐观，不能将全部失覆盖归因于 OOD。')
    rows.append('OOD 覆盖率直接由上述超半宽残差的比例决定；固定宽度并不随外推难度变化。若残差相对校准集变大则覆盖偏低，若变小则偏高；两个 OOD 子组的实测残差和失覆盖计数给出了具体来源。这是数据描述，不能单独确证物理因果。')
    if 'rebuild_wall_s' in timing:
        rows.append(f'从零重建墙钟时间 {timing["rebuild_wall_s"]:.6f} 秒；预注册的二十五分钟次要判据：'+('通过' if timing['rebuild_wall_s']<=1500 else '不通过')+'。')
    rows+=['','主持人外部扫描计时文件的原始指标：','```json',json.dumps(timing,ensure_ascii=False,indent=2),'```']
    if conv:
        rows+=['','收敛实测指标（差值单位为百分点）：','```json',json.dumps(conv,indent=2),'```']
        rows.append('逐点可接受规则：差值 <0.1 或差值 <方法 MAE/5；不同方法 MAE 会给出不同阈值，因此不将它合并为一个未定义的统一判决。')
        for method in METHODS[:4]:
            threshold=m[method+'.test.mae']/5
            deltas=[v for k,v in conv.items() if k.endswith('.abs_delta_y')]
            rows.append(f'{method}，以分布内 test MAE 为参照，MAE/5={threshold:.6f}，满足上述或条件 {sum(d<.1 or d<threshold for d in deltas)}/{len(deltas)} 点。')
    else: rows.append('收敛检查：待主持人补充。')
    rows+=['','## 不确定性与设计问题','',
           'OOD 破坏 split conformal 所需的交换性，因此没有 OOD 覆盖保证。主判据样本少、允许带窄，计数的离散性和抽样噪声可能改变通过与否；覆盖偏高也会判失败，不能直接理解为更不安全。',
           '低负载低带宽子组更小，覆盖率只作描述；死区子组与角落子组按冻结规则互斥，角落不含已经归入死区的点。',
           '当前扫描的 SensorConfig 默认 ideal=True；孔径偏移仍参与采样时点，但是否代表实际带噪传感器需主持人审查。高维非线性误差的一阶物理特征可能欠拟合，GP 标准差还包括 WhiteKernel 的噪声项。',
           '收敛五个点不能验证整个参数域；以哪个集合、哪种方法的 MAE 定义收敛阈值在预注册中不明确，本报告明确使用 test MAE。',
           '源代码快照、划分、预注册、完整 sweep 与训练脚本均作为证据输入保留。模型自身误差与仿真真实性是不同问题；本案例没有独立实验校验。']
    training_id=json.loads((ROOT/'lab/cases/dclink/surrogate_training_run.json').read_text())['run_id']
    recorded=json.loads((ROOT/'runs'/training_id/'record.json').read_text())
    rows+=['','## 验证','', 'make surrogate 与案例证据检查通过；make test 的实际输出保存在 data/m2_tests.log。训练无优化器警告。',
           f'记录的训练评估时长 {recorded["duration_s"]:.6f} 秒，峰值进程树 RSS {recorded["peak_rss_mb"]:.6f} MiB。所有计算线程限制为单线程，地址空间上限在脚本中设定。']
    (ROOT/'docs/reports/M2_researcher_a.md').write_text('\n'.join(rows)+'\n')

if __name__=='__main__':
    if sys.argv[1:] == ['--train']: train()
    else: main()
