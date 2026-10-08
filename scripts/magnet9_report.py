"""Deterministic Chinese report from sealed first results; no real-label access."""
from magnet9_common import *
from collections import Counter


def fmt(x):
    if x is None:return '不可评/null'
    if isinstance(x,bool):return '通过' if x else '失败'
    if isinstance(x,(int,np.integer)):return str(x)
    if isinstance(x,(float,np.floating)):return f'{x:.8g}'
    return str(x)


def main():
    root=STAGE/'first'
    for name in ('ACQUIRED','CALIBRATED','EVALUATED','RECOMPUTED'):verify_seal(root,name)
    m=read_json(root/'metrics.json');des=read_json(STAGE/'design/summary.json')
    audit=read_json(root/'acquisition_audit.json');ind=read_json(root/'independent_recompute.json')
    results={a:read_json(root/'trajectories'/a/'result.json') for a in trajectories()}
    lines=['# 第九轮：方向性伪外推区间与中心偏差校正','',
        '作者：local_node researcher_a（R9c）；2026-10-08。预注册版本 R9f-local_node-researcher_a-1。','',
        '## 结论先行','']
    def para(s):lines.extend([s,''])
    def table(headers,rows):
        lines.append('| '+' | '.join(headers)+' |');lines.append('| '+' | '.join(['---']*len(headers))+' |')
        for row in rows:lines.append('| '+' | '.join(fmt(x) for x in row)+' |')
        lines.append('')
    def section(s):para('## '+s)
    success=[z for z,c in m['conclusions'].items() if c['SUCCESS']]
    if len(success)==2:para('**双方向 SUCCESS 成立：完整 D 策略在本固定面板通过经验覆盖与宽度门控，并获得相对欠覆盖改进及 10% Winkler 非劣的条件性检验支持。**')
    elif success:para(f'**仅 {success[0]} 方向 SUCCESS 成立；不能宣称双方向或整体外推成功。**')
    else:para('**XF、XT 均未达到预注册 SUCCESS；不宣称整体外推成功。**')
    table(['区域','A','WIDTH','J','覆盖检验','Winkler 检验','SUCCESS','结论'],[
        [z,c['A'],c['WIDTH'],c['J'],c['coverage_status'],c['Winkler_status'],c['SUCCESS'],c['text']] for z,c in m['conclusions'].items()])
    para('流程有效：60/60 条轨迹、180/180 个区间臂、540 次正式拟合均完整，360/360 批采集逐点重放通过。独立复算核对了全部 720 个“区间臂×区域”指标、δ/q、诊断、精确 p 整数分子、门控与结论。合成冒烟使用额外一对 U/S 轨迹；不计入正式 K，也未读取真实留出标签。')
    para('以上检验支持均条件于固定 N87 数据及族划分上的配对差符号对称；对复合均值原假设还需对称位置平移模型。这些假设未经保证，截断欠缺和移位 Winkler 差可能偏斜。精确计算不验证推断前提；A/J 是经验标准，不是总体 90% 覆盖保证。完整 D 同时改变中心和尺度，不能据 D/B 拒绝归因于中心校正，也不能排除仅加宽解释。')
    section('H1–H4：精确检验与区域序列')
    table(['假设','区域/差值','整数分子 / 2^30','名义单侧 p','正式状态','平均差','中位差','IQR','正/零/负'],[
        [h,t['region']+('：g_B−g_D' if h in ('H1','H2') else '：1.10W_B−W_D'),
         f"{t['numerator']} / {t['denominator']}",t['p'],t['status'],t['differences']['mean'],t['differences']['median'],t['differences']['IQR'],
         '/'.join(str(t['differences'][k]) for k in ('positive','zero','negative'))] for h,t in m['hypotheses'].items()])
    para('XF 固定序列 H1→H3，XT 固定序列 H2→H4；各 α=0.025，严格 p<0.025 才拒绝。一族首项不拒绝仅令本族次项未检验；无 α 回收。所有 30 对均保留，无门控筛选、删对或十进制预舍入。以封存 binary64 差值和 ε=1e−12 的精确二进制有理值计算两半各 2^15 的整数 MITM；独立复算改写为翻转子集和计数。')
    table(['k','H1 d','H2 d','H3 d','H4 d'],[[k]+[m['hypotheses'][h]['differences']['values'][k-1] for h in ('H1','H2','H3','H4')] for k in range(1,31)])
    section('经验门控：全部处理与方法')
    table(['处理','方法','区','C1','V80','HONEST90','FLOOR80','MEAN90 总计/门槛','WIDTH 逐对','均宽比','A','WIDTH','J'],[
        [s,method,z,g['validity_pass_counts']['C1'],g['validity_pass_counts']['V80'],g['validity_pass_counts']['HONEST90'],
         g['validity_pass_counts']['FLOOR80'],f"{g['coverage_total']}/{g['mean90_required']}",
         g['validity_pass_counts']['WIDTH_pairs'],g['width_ratio_of_means'],g['A'],g['WIDTH'],g['J']]
        for s in ('U','S') for method in ('B','E','D') for z,g in m['gates'][s][method].items()])
    para('通过数的分母均为 30。V80 和 HONEST90 各需 ≥26；FLOOR80 和 WIDTH 逐对各需 30/30。C1 要求 G9≥3685/4606；XF 的 80%/90% 下限为 4289/4825，XT 为 6676/7511。V80 另要求本区均宽≤3×G9 均宽。WIDTH 同时要求均宽≤1.50×配对 B，且每对≤2.00×B。MEAN90 使用整数总覆盖数，不合并 XF/XT。')
    for z in ('XF','XT'):
        g=m['gates']['U']['D'][z];c=m['conclusions'][z]
        para(f"U-D {z} 覆盖失败项：{'、'.join(c['failed_coverage_components']) or '无'}；宽度单对否决 k={g['width_pair_veto_k']}；均宽上限：{fmt(g['width_mean_pass'])}。B/D 非零 g 臂数为 {c['baseline_nonzero_g']}/{c['candidate_nonzero_g']}，平均 g 为 {fmt(c['baseline_mean_g'])}/{fmt(c['candidate_mean_g'])}。")
    section('覆盖、宽度与 Winkler 关键数字')
    table(['处理','方法','区域','平均覆盖','覆盖最小–最大','平均 g','平均宽度','平均 Winkler','W 最小–最大','MAE','中心偏差','中位相对误差的臂均值'],[
        [s,method,z,v['c']['mean'],f"{fmt(v['c']['min'])}–{fmt(v['c']['max'])}",v['g']['mean'],v['w']['mean'],v['W']['mean'],
         f"{fmt(v['W']['min'])}–{fmt(v['W']['max'])}",v['MAE']['mean'],v['bias']['mean'],v['median_relative_error']['mean']]
        for s in ('U','S') for method in ('B','E','D') for z,v in m['summaries'][s][method].items()])
    para('区间在 log10 损耗尺度上对称，端点闭合；宽度、Winkler、MAE 和偏差均为 log10 单位。g 在每臂先截断再平均；区域内点等权、组间等权。XFT 使用冻结的 δ_F+δ_T 和 max(q_F,q_T) 规则，只报告，无门控或正式检验。所有指标的逐臂值及最小/最大值保留在 metrics.json。')
    para('![覆盖对比](../figures/r9_coverage.png)\n\n![Winkler 对比](../figures/r9_winkler.png)\n\n![配对差分布](../figures/r9_pairs.png)')
    section('D/E 消融与两种相同宽度诊断（只报告）')
    table(['处理','区','D/E 差值','均值','中位数','最小','最大','正/零/负'],[
        [s,z,name,v['mean'],v['median'],v['min'],v['max'],'/'.join(str(v[k]) for k in ('positive','zero','negative'))]
        for s in ('U','S') for z,contrasts in m['ablation'][s].items() for name,v in contrasts.items()])
    table(['处理','区','q 锚点','诊断差','均值','中位数','最小','最大','正/零/负'],[
        [s,z,anchor,name,v['mean'],v['median'],v['min'],v['max'],'/'.join(str(v[k]) for k in ('positive','zero','negative'))]
        for s in ('U','S') for z,anchors in m['equal_width'][s].items() for anchor,values in anchors.items() for name,v in values.items()])
    for s in ('U','S'):
        for z in ('XF','XT'):
            for anchor,v in m['equal_width'][s][z].items():
                positive=[name for name,x in v.items() if x['mean']>0]
                nonpositive=[name for name,x in v.items() if x['mean']<=0]
                para(f"{s}/{z}/{anchor}：均值改善指标 {positive}；未改善指标 {nonpositive}。"+
                     ('对这些未改善指标，未观察到相同宽度下的中心改善。' if nonpositive else '三项在该面板上平均改善。'))
    para('δc=c(平移)−c(未平移)、δg=g(未平移)−g(平移)、δW=W(未平移)−W(平移)，正值支持改善。D/E 是中心与重新校准 q 的总改变；两锚点均报告，无择优，也不进入 SUCCESS。这些诊断不证明总体因果贡献。每项 30 个原始值均在 metrics.json。')
    section('校准与影子模型')
    table(['轨迹','q0','δF','δT','qE_F','qD_F','qE_T','qD_T','qD_F/qE_F','qD_T/qE_T'],[
        [a,q['q0'],q['delta']['F'],q['delta']['T'],q['qE']['F'],q['qD']['F'],q['qE']['T'],q['qD']['T'],
         m['qD_qE_ratios'][a]['F'],m['qD_qE_ratios'][a]['T']] for a,q in m['parameters'].items()])
    table(['处理','方向','参数','均值','中位数','最小','最大'],[
        [s,j,name,v['mean'],v['median'],v['min'],v['max']] for s in ('U','S') for j,items in m['parameter_summaries'][s].items() for name,v in items.items()])
    table(['模型','实际均值列','训练温度层','秩范围','条件数最小–最大','秩亏模型数'],[
        [name,', '.join(metas[0]['columns']),str(sorted(set(tuple(x['temperatures']) for x in metas))),
         f"{min(x['rank'] for x in metas)}–{max(x['rank'] for x in metas)}",
         f"{fmt(min(x['condition_number'] for x in metas if x['condition_number'] is not None))}–{fmt(max(x['condition_number'] for x in metas if x['condition_number'] is not None))}",
         sum(x['rank']<len(x['columns']) for x in metas)]
        for name,metas in [('主模型全部420次',[cp['metadata'] for r in results.values() for cp in r['checkpoints']]),
                           ('M_F',[r['shadows']['F']['metadata'] for r in results.values()]),
                           ('M_T',[r['shadows']['T']['metadata'] for r in results.values()])]])
    table(['处理','方向','训练核心点数范围','训练边缘点数范围','核心族数范围','边缘族数范围','CAL边缘点/族'],[
        [s,j,*[f"{min(r['shadows'][j][part][field] for a,r in results.items() if a.startswith(s))}–{max(r['shadows'][j][part][field] for a,r in results.items() if a.startswith(s))}"
               for part,field in [('core','n'),('edge','n'),('core','families'),('edge','families')]],
         f"{des['cal_edges'][j]['n']}/{des['cal_edges'][j]['families']}"] for s in ('U','S') for j in ('F','T')])
    para('M_T 仅用 25/50°C，按预注册删除 T_C²；M_F 保留六列。主模型所有检查点均保留六列。每个模型从头拟合自己的 OLS、scaler 和残差 GP，优化重启 2 次，σ 含 WhiteKernel。核心外的已查询训练点仅估 δ，CAL 仅估 q，不混用。优化器达到边界的警告保存在日志，未更改参数界或模型。实际逐模型秩、条件数、列与训练 ID 见各轨迹 result.json 及 model_*.json/shadow_*.json。')
    section('S0 干预、覆盖方差与分解（只报告）')
    table(['区','v_U','v_S','S/U','方差降幅','Δg均值','预定支持'],[
        [z,v['v_U'],v['v_S'],v['ratio'],v['reduction'],v['Delta_g']['mean'],v['support']] for z,v in m['S0'].items()])
    table(['区','SS_total','SS_group','SS_method','SS_interaction','组占比','方法占比','交互占比','共享组分量过半'],[
        [z,v['total'],v['SS']['group'],v['SS']['method'],v['SS']['interaction'],v['fractions']['group'],v['fractions']['method'],v['fractions']['interaction'],v['group_majority']]
        for z,v in m['variance_decomposition'].items()])
    para('双方向支持标记：'+fmt(m['S0_both_support'])+'。支持规则为 v_U>0、v_S≤0.50v_U 且 mean(g_U−g_S)≥0。v_U=0 时比值与支持不可评，不加 ε。U 的 30×3 矩阵无格内重复，交互与残余不可分。干预是“S0政策+后续采集”的总影响，不能隔离纯 S0，也不能追溯证明第八轮离散成因。')
    para('![S0配对覆盖](../figures/r9_s0.png)')
    section('Winkler 非劣敏感性（U；只报告）')
    table(['区','mean(W_D)/mean(W_B)','逐一删对均值最小','最大','非正个数'],[
        [z,v['ratio_of_means'],v['leave_one_pair_out']['min'],v['leave_one_pair_out']['max'],v['nonpositive_count']] for z,v in m['winkler_sensitivity'].items()])
    table(['k','XF W_D/W_B','XT W_D/W_B','XF去掉k的均差','XT去掉k的均差'],[
        [k]+[m['winkler_sensitivity'][z]['pair_ratios'][k-1] for z in ('XF','XT')]+
        [m['winkler_sensitivity'][z]['leave_one_pair_out']['values'][k-1] for z in ('XF','XT')] for k in range(1,31)])
    para('分母为零时记 null；原检验保留所有配对。上述 30 个删对描述量不产生新 p，不用于择对，不改变 K=30。未做 Bootstrap、替代检验或额外重采样；描述性敏感性不能验证符号对称或修复 FWER。')
    section('设计、采样与阶段封存')
    para(f'预注册提交 `{PREREG_SHA}`；H={H}；GP seed={GP_SEED}。设计种子为 2^96+H×2^16+r×256+k，PCG64 完整整数。R6/R7/R8 历史种子与本轮种子集合交集为空；这不表示样本 ID 互斥或独立新测量。')
    table(['集合','点数','族数'],[[z,v['n'],v['families']] for z,v in des['sets'].items()])
    table(['P层','实际点数','S0配额'],[[z,v['n'],v['quota']] for z,v in des['pool_strata'].items()])
    table(['处理','阶段','计数','fset计数','温度计数','v八档计数'],[
        [s,stage,sum(r['sampling_counts'][stage]['n'] for a,r in results.items() if a.startswith(s)),
         *[str(dict(sorted(sum((Counter(r['sampling_counts'][stage][key]) for a,r in results.items() if a.startswith(s)),Counter()).items(),key=lambda x:int(x[0])))) for key in ('fset','T_C','v_bin')]]
        for s in ('U','S') for stage in ('S0','additions')])
    para('上述采样计数对 30 条轨迹求和，包含跨轨迹重复 ID；每条轨迹内无放回。v=log10(4fBpk) 八个等宽档在整个 P 上定义，边界为 '+str(des['v_edges'])+'。validity_pass_counts 为门控通过臂数，与 sampling_counts 分开。')
    table(['范围','变量','实际最小','实际最大'],[
        ['P',key,v['min'],v['max']] for key,v in results['U01']['pool_extrema'].items()]+[
        [s+'全部最终训练并集',key,min(r['training_extrema'][key]['min'] for a,r in results.items() if a.startswith(s)),
         max(r['training_extrema'][key]['max'] for a,r in results.items() if a.startswith(s))]
        for s in ('U','S') for key in results['U01']['training_extrema']])
    para('每条轨迹 100 个 S0+6×20 个新增标签，共 220 点；B/E/D 共用本轨迹全部主模型与采集。训练、CAL 和评估读标签权限按处理/k/阶段/ID 留痕。影子拟合排除伪边缘，δ 排除 CAL，校准排除真留出。全部 60 条采集和 δ 封存后开放 CAL；全部 q/区间封存后独立评估进程开放 G9/XF/XT/XFT。')
    para('单线程环境：OMP/OPENBLAS/MKL/NUMEXPR 均为 1；nohup setsid 后台运行，工作进程各自独立会话，看门狗位于其外。每 5 秒检查 MemAvailable，<3.8 GiB 暂停/停止派发，>4.3 GiB 恢复，等于门限保持状态，持续低内存 900 秒作为基础设施停止。未修改预注册阈值。')
    resources=[]
    for p in sorted((STAGE/'run_logs').glob('*resources.json')):
        v=read_json(p);resources.append([p.stem,v['min_MemAvailable_bytes']/2**30,max(v['peak_rss_bytes'].values(),default=0)/2**20])
    table(['阶段','最低观测 MemAvailable/GiB','5秒采样峰值 RSS/MiB'],resources)
    para('短于一个轮询周期的进程可能没有 RSS 样本；表中 0 仅表示未采到，不表示真实峰值为 0。软件版本：'+str(des['versions'])+'。')
    table(['封存','SHA256'],[['设计 EVALUATED',sha(STAGE/'design/EVALUATED.json')]]+[[name,sha(root/(name+'.json'))] for name in ('ACQUIRED','CALIBRATED','EVALUATED','RECOMPUTED')]+[['metrics.json',sha(root/'metrics.json')]])
    para('C03：真实训练标签开放前12个单元测试全部通过；审计修复后13个测试通过；其中 K=1…16 逐一对独立 2^K 枚举核对整数分子，并覆盖 K=30 全正/全负/全零、重复/零值重数、混合尺度、容差边界两侧、非法输入、两族顺序、覆盖整数门槛、影子列规则、权限、双A、零分母及诊断。第一次测试的删对均值十进制字面值比较过严，已在真实标签访问前修正测试断言；同时显式处理完全相同覆盖率向量的零方差。未改变预注册规则。')
    para('采集后、CAL开放前，首次审计因 S05/6 的浮点诊断记录逐位比较停止；选点及顺序完全相同，σ最大差3.06e−15。按预测重建已有数值精度修复审计比较，仍要求选点精确一致，并保留前后实现哈希与首失败日志。未重新拟合或采集，精确p契约未变。详见 [实现勘误](../discussion/m10/researcher_a_R9c_implementation_errata.md)。')
    para('首次结果与全部日志保留，未删组/补组/重抽/调门槛；未联网、未安装依赖、未改第一至八轮文件、未 push 或 force。reviewer_b 后续人工评审尚未在本任务中执行，不将独立复算冒充外部评审。')
    para('完整产物：[metrics.json](../../lab/cases/magnet9/first/metrics.json)、[逐臂结果](../../lab/cases/magnet9/first/arms/)、[模型/采集/影子明细](../../lab/cases/magnet9/first/trajectories/)、[独立复算](../../lab/cases/magnet9/first/independent_recompute.json)、[运行日志](../../lab/cases/magnet9/run_logs/)。')
    section('适用范围与限制')
    para('这是同一 N87 固定数据上的新随机化研究，不是新材料/新测量的独立复现。只有一个族划分，存在族相关、适应性采样及伪域→真域残差迁移风险；δ 不称无偏。两温度线性外推和剩余共线性仍是模型假设，XT 失败不能解释为物理外推不可行。E、S、XFT、两种中心诊断、方差分解与敏感性结果全部只报告，不提升为确认性候选。未拒绝不证明等效、劣效或无效。')
    path=ROOT/'docs/reports/M10_magnet_round9.md';freeze(path,('\n'.join(lines)+'\n').encode())
    freeze(root/'report_manifest.json',encoded(dict(metrics_sha256=sha(root/'metrics.json'),report_sha256=sha(path),script_sha256=sha(ROOT/'scripts/magnet9_report.py'))))
    print(path)


if __name__=='__main__':main()
