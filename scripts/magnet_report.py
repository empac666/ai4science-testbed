#!/usr/bin/env python3
"""Render Chinese data card/report from verified sources and actual outputs."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LABELS={'sine':'正弦','triangle':'三角类','trapezoid':'梯形'}
LIBRARY='https://www.princeton.edu/~minjie/magnet.html'
LICENSE='https://raw.githubusercontent.com/PrincetonUniversity/magnet/main/LICENSE'
CHALLENGE_LICENSE='https://raw.githubusercontent.com/minjiechen/magnetchallenge-1/main/LICENSE'
README='https://raw.githubusercontent.com/minjiechen/magnetchallenge-1/main/README.md'
HANDBOOK='https://raw.githubusercontent.com/minjiechen/magnetchallenge-1/main/docs/handbook.pdf'
PAPER='https://www.wcmagnetics.com/wp-content/uploads/2015/02/prediction.pdf'
CROSSREF='https://api.crossref.org/works/10.1109/CIPE.2002.1196712'

def main():
    out=ROOT/'data/magnet';staging=ROOT/'lab/cases/magnet'
    meta=json.loads((out/'igse_metadata.json').read_text());m=json.loads((out/'igse_metrics.json').read_text())
    man=json.loads((out/'MANIFEST.json').read_text());entry=man['files'][0]
    validation=json.loads((staging/'validation.json').read_text())
    fetch_record=json.loads((staging/'fetch_run.json').read_text())
    igse_record=json.loads((staging/'igse_run.json').read_text())
    initial_record=json.loads((staging/'initial_fetch_run.json').read_text())
    review=json.loads((staging/'classification_review.json').read_text())
    assert review['audit_sha256']==hashlib.sha256((out/'classification_audit.csv').read_bytes()).hexdigest(), 'Classification audit changed: inspect new panels before exporting'
    card=['# MagNet N87 数据卡','','## 来源与获取','',
      f'来源：[MagNet Library]({LIBRARY})；下载 [pre-training.zip]({man["archive"]["url"]}) 中的 `pre-training/N87.zip`。仅获取 N87 成员，不把整个预训练包当成本案例的数据。',
      f'获取时间（UTC）：`{man["retrieved_at"]}`；最近校验：`{man["verified_at"]}`。',
      f'远端 ETag：`{entry["etag"]}`；Last-Modified：`{entry["last_modified"]}`。',
      f'N87 ZIP 实际字节数：{entry["size_bytes"]}；SHA256：`{entry["sha256"]}`；外层成员 CRC32：`{entry["zip_crc32"]}`。',
      '完整外层成员长度/CRC 和内层全部 CSV CRC 均已校验。整体预训练包只下载了字节范围，整体 SHA256 未计算，MANIFEST 中明确为 null。',
      '下载中断后保留 ETag 绑定的压缩字节分片；再次运行只补齐剩余范围。旧的解压后残缺 ZIP 不作为可信续传前缀。CRC 不符会报错，不会生成成功清单。','',
      '## 许可与使用条款（亲自核实）','',
      f'[MagNet 软件仓库许可原文]({LICENSE}) 的标题为 “MIT License”。其对象摘录：',
      '> of this software and associated documentation files (the "Software")',
      f'[挑战代码仓库]({CHALLENGE_LICENSE}) 同样采用 MIT。',
      '这两份文件位于代码仓库，并把对象称为软件与相关文档；所核实页面没有明确把 Princeton 单独托管的测量数据纳入该许可。不能据此给数据标注 MIT。',
      f'[挑战 README]({README}) 的数据使用要求逐字摘录：',
      '> If you used MagNet data, please acknowledge the MagNet project',
      '同一句的后半部分要求引用页面末尾列出的论文。它是署名/引用要求，未明确授予数据再分发权。',
      f'[挑战手册]({HANDBOOK}) “Intellectual Property and Use of Prize Money” 一节逐字摘录：',
      '> There are no special licenses or rights required by the sponsors.',
      '该段谈参赛队提交的软件、模型、算法及其知识产权，并非数据授权。手册技术规则允许参赛队用数据训练、测试模型，但未找到明确的数据再分发或商用许可。',
      f'在本次打开核实的 [Library 页面]({LIBRARY})、代码仓库许可、挑战 README 和手册中，**未找到明确的数据许可**。这是检索范围内的结论，不表示全网不存在许可。原始测量 CSV/ZIP 留在 gitignore 的 data/magnet；入库的是哈希、派生预测、指标及方法文档。','',
      '## 官方规模与本次实际范围','',
      f'[Library 原文]({LIBRARY})：',
      '> Complete MagNet Raw Database (15 Materials, 29.31 GB)',
      '> Pretest Training Data (10 Materials, 3.14 GB)',
      '以上是材料数和包大小，不是样本总数；本次核实的该页面没有给出全库总样本数。未能核实全库样本总数及“N87 原始全库 142,871 条”的原论文出处，因此不将它们作为本案例事实。',
      f'本次 N87 是预训练子集，实际 {meta["n"]} 条，每条 B 和 H 波形 {meta["points"]} 点。实际统计来自 `magnet_igse.py`，不是从公开全库规模推断。',
      '', '| 字段 | 实际最小值 | 实际最大值 | 单位/说明 |','|---|---|---|---|']
    for key,unit in [('temperature_C','℃；离散组见下文'),('frequency_Hz','Hz'),('amplitude_T','T；B̂ = (max B − min B)/2'),('measured_W_m3','W/m³')]:
        lo,hi=meta['ranges'][key];card.append(f'| {key} | {lo:.12g} | {hi:.12g} | {unit} |')
    card+=['', '实际温度组：'+ '、'.join(f'{t:g} ℃' for t in meta['temperatures_C'])+'。',
      'ZIP 字段：`'+ '`, `'.join(meta['members'])+'`。无波形类型、占空比或激励类型标签，CSV 无表头；样本编号取原始行号，从零开始。',
      '单位及单周期解释与手册技术规则一致：频率 Hz、B 为 Tesla、温度 Celsius、体积损耗 W/m³；采用均匀单周期网格且不重复末端点。','',
      '## 固定波形规则与抽检','',
      '先去均值，投影到一周期正弦/余弦基，计算 RMS 残差除以原波形 RMS。残差 ≤0.05 判为正弦。其余波形计算周期差分绝对值，低于本条差分 p90 的 0.1 倍的点作为平台；平台占比 ≥0.05 判为梯形，其余判为三角类。没有读取实测损耗来分类，也没有以评估误差选择阈值。',
      '三角类包括非对称三角及无明显平台的多段斜率形状，不声称每条都是理想两段三角。初始残差阈值 0.02 的边界抽检发现失真正弦误分；按 B 形状固定为 0.05 后重新拟合。',
      '最终分类计数：'+ '；'.join(f'{LABELS[w]} {meta["waveform_counts"][w]}' for w in LABELS)+'。',
      f'固定种子分层随机抽检每类 {review["random_n"]//3} 条，总 {review["random_n"]} 条，逐图检查的一致数 {review["random_consistent"]}；另抽距两个阈值最近的边界 {review["boundary_n"]} 条，一致数 {review["boundary_consistent"]}。',
      '抽检员为本任务 researcher_a；按上述广义形状定义检查，既非盲审，也无独立真值标签。该一致率只描述这批图的可读形状，不是总体分类准确率。三角边界的多段斜率样本已逐条备注。',
      '抽样行号与逐条评审见 `classification_audit.csv`、`classification_audit_review.csv`；完整审核图保存在 data/magnet/classification_audit_*.png。','']
    (staging/'data_card.md').write_text('\n'.join(card))
    report=['# M3：MagNet N87 数据管道与 iGSE 基线','','## 数据卡摘要','',
      f'实际使用预训练 N87 子集：{meta["n"]} 条单周期波形，每条 {meta["points"]} 点。ZIP 长度与全部 CRC 校验通过，SHA256 为 `{entry["sha256"]}`。详见 [数据卡](../../lab/cases/magnet/data_card.md)。',
      f'温度为 '+ '、'.join(f'{t:g} ℃' for t in meta['temperatures_C'])+'；频率、磁通密度幅值及损耗范围均由实际 CSV 统计，见数据卡。',
      f'已亲自打开 [官网]({LIBRARY})、[软件许可]({LICENSE})、[挑战许可]({CHALLENGE_LICENSE})、[README]({README}) 和 [手册]({HANDBOOK})。未找到明确的数据许可；代码 MIT 不可直接视为测量数据 MIT。官网已核实完整原始库材料数为 15，预训练包材料数为 10；官网没有给出总样本数，不引用未经核实的全库总数。',
      '没有波形标签。B-only 固定规则得到：'+ '；'.join(f'{LABELS[w]} {meta["waveform_counts"][w]} 条' for w in LABELS)+'。规则与逐条抽检在数据卡中；三角类包含多段斜率波形。','',
      '## 拟合和积分','',
      f'按样本原始行序，用 numpy default_rng 固定种子 {meta["seed"]} 对全部正弦 ID 做随机排列，取前一半 {m["split.train_n"]} 条训练，其余正弦留出。只在训练正弦中按温度分别拟合 log P = log k + α log f + β log B̂；未对测试集重拟合、调参。',
      f'评估总数 {m["split.eval_n"]}，其中正弦 {m["sine.all.n"]}，全部非正弦 {m["triangle.all.n"]+m["trapezoid.all.n"]}；预测 CSV 同时保留 train/eval 标签，统计与散点图只读 eval。',
      'B̂ 为峰峰值的一半；f 使用 Hz，B 使用 T，P 使用 W/m³，k 的数值依赖这些单位。每个温度一组参数：','',
      '| 温度 ℃ | 训练正弦数 | k | α | β | log 空间 RMSE |','|---|---|---|---|---|---|']
    for t,p in meta['parameters'].items(): report.append(f'| {t} | {p["n"]} | {p["k"]:.10g} | {p["alpha"]:.10g} | {p["beta"]:.10g} | {p["log_rmse"]:.6f} |')
    report+=['',
      r'$k_i = k / [(2\pi)^{\alpha-1} 2^{\beta-\alpha} \int_0^{2\pi}|\cos\theta|^\alpha d\theta]$，',
      r'$P_{iGSE}=k_i(\Delta B)^{\beta-\alpha}\,T^{-1}\int_0^T|dB/dt|^\alpha dt$，$\Delta B=\max B-\min B$。',
      '余弦积分以 Beta 函数解析求值；B 的周期前向差分包含末点到首点的闭合边，dt = 1/(fN)。在每条线性段上准确积分，所以离散计算为差分斜率绝对值的 α 次幂均值。不平滑 B，不做正弦专用导数替代。','',
      '## 实际评估结果','',
      '相对误差为 `(P_iGSE − P_meas)/P_meas`。除样本数外，表中均显示百分数；有符号中位数为正代表总体偏高，为负代表偏低。p95 使用 numpy 默认线性分位数。','',
      '| 波形 | 温度 ℃ | n | 绝对误差均值 % | 中位数 % | p95 % | ≤10% 比例 % | ≤20% 比例 % | 有符号中位数 % |',
      '|---|---|---|---|---|---|---|---|---|']
    for wave in LABELS:
        for group in ('all',*[f'T{t:g}' for t in meta['temperatures_C']]):
            prefix=wave+'.'+group
            cells=[str(m[prefix+'.n'])]+[f'{100*m[prefix+"."+key]:.3f}' for key in ('abs_mean','abs_median','abs_p95','within_10','within_20','signed_median')]
            report.append('| '+LABELS[wave]+' | '+('全温度' if group=='all' else group[1:])+' | '+' | '.join(cells)+' |')
    report+=['','（图：误差热图；发布包仅保留数值表与绘图脚本。）','','（图：预测对实测；发布包仅保留数值表与绘图脚本。）','',
      '两图使用 addfont 注册 Noto Sans CJK SC。最终 PNG 均已亲自打开检查，无中文缺字、文字无重叠。','',
      '## 与公开文献的核实对比','',
      f'Venkatachalam、Sullivan、Abdallah、Tacca 的 [原论文]({PAPER}) 已打开；[Crossref 注册记录]({CROSSREF}) 核实 DOI 为 **10.1109/CIPE.2002.1196712**，题名为 Accurate prediction of ferrite core loss with nonsinusoidal waveforms using only Steinmetz parameters，会议为 IEEE Workshop on Computers in Power Electronics，论文首页标注 COMPEL 2002。',
      '本实现与原论文式 (9)/(10) 的峰峰值 iGSE 及正弦归一化相同；周期 PWL 积分对应式 (13)。原论文还递归分解主/次回线并按所占时间加权；本任务仅用全局 ΔB，未实现该分解。',
      '原文实验使用 3C85 MnZn 环形磁芯，本案例是 MagNet N87，且数据划分、参数拟合范围和误差统计不同。因此不把原论文的性能描述当作 N87 的预期误差，也不声称复现其材料实验结果。',
      f'[挑战 README]({README}) 描述相对误差和 p95 评价，但其公开比赛表使用另一个验证集及参赛者模型，不能与本任务训练/留出划分直接排榜。本报告仅给出本机实际 iGSE 结果。','',
      '## 验证、重跑与证据','',
      '`make magnet` 依次通过公共 lab.repro CLI 记录 fetch 校验与 iGSE、绘图、export-case、evidence check。已有 N87 文件在长度及外/内 CRC 全部通过时不再下载；仍会重新核实远端 ETag 和本地完整性。`igse_metrics.json` 为扁平键；录证用副本展开点分键，避免数字检查器把扁平键误当层级路径。',
      '解析正弦与 Steinmetz 的相对误差测试阈值 <1e-3、三角闭式解、分组统计、已知参数恢复及波形规则均有测试。D-02 右图仅样本外，D-05 运行数据缺失/不完整会 skipUnless；划分清单和合成 make_split 测试无需 data/dclink。',
      f'预测 CSV 实际字节数 {(out/"igse_predictions.csv").stat().st_size}，小于 5 MB，按任务要求存入 lab/cases/magnet；原始测量 B/H CSV 未入库。',
      f'实际 make test：{validation["make_test"]["tests"]} 项，全部通过；make surrogate 重跑通过且与首次入库 surrogate_metrics.json 完全相等。隔离测试在 DC-link 数据缺失及空 JSON 不完整两种状态各运行 {validation["absent"]["tests"]} 项，各跳过 {validation["absent"]["skipped"]} 项运行数据测试，其余通过。',
      f'初次成功下载录证耗时 {initial_record["duration_s"]:.3f} s，峰值 RSS {initial_record["peak_rss_mb"]:.3f} MiB；最近 fetch 校验 {fetch_record["duration_s"]:.3f} s / {fetch_record["peak_rss_mb"]:.3f} MiB；最终 iGSE（含 H 形状校验）{igse_record["duration_s"]:.3f} s / {igse_record["peak_rss_mb"]:.3f} MiB。BLAS/OMP/NumExpr 线程固定为 1；未安装新包。',
      '新增 fetch 测试模拟中断，验证从已有压缩前缀续传、已有完整 ZIP 不下载、完整但损坏的 ZIP 重新获取；测试仅用内存合成 ZIP，不依赖网络或测量数据。',
      '案例见 `cases/magnet_igse/`，中文 report 与 claims 的数字均引用真实运行指标，包含脚本、清单、图及报告的哈希快照。','',
      '## 局限性','',
      '仅一个材料的预训练子集；不覆盖 MagNet 原始全库。无官方波形标签；多段斜率合并到三角类，随机形状抽检和边界检查不构成独立分类真值。',
      '固定幂律在每个温度内跨频率/幅值拟合，忽略局部参数变化。全局峰峰值版本不处理次回线，数值微分会放大测量噪声。只有离散测量温度的参数，不对中间温度插值。',
      '正弦随机留出仍与训练来自同一测量流程，不是跨设备或跨材料泛化；非正弦完全未用于参数拟合。记录的脚本运行资源为过程树 RSS，并不能替代测量仪器不确定度分析。数据使用授权仍未明确。','']
    (ROOT/'docs/reports/M3_magnet.md').write_text('\n'.join(report))
if __name__=='__main__':main()
