# MagNet N87 数据卡

## 来源与获取

来源：[MagNet Library](https://www.princeton.edu/~minjie/magnet.html)；下载 [pre-training.zip](https://www.princeton.edu/~minjie/magnet/pre-training.zip) 中的 `pre-training/N87.zip`。仅获取 N87 成员，不把整个预训练包当成本案例的数据。
获取时间（UTC）：`2026-10-02T16:07:13.182102+00:00`；最近校验：`2026-10-02T16:18:48.057826+00:00`。
远端 ETag：`"bb400b86-613449b089a00"`；Last-Modified：`Sun, 10 Mar 2024 01:47:20 GMT`。
N87 ZIP 实际字节数：683282735；SHA256：`d7c3703295dc113527702cd2420b3334c8eb302c347ecc8ae425b666ce6915ff`；外层成员 CRC32：`442c0ebc`。
完整外层成员长度/CRC 和内层全部 CSV CRC 均已校验。整体预训练包只下载了字节范围，整体 SHA256 未计算，MANIFEST 中明确为 null。
下载中断后保留 ETag 绑定的压缩字节分片；再次运行只补齐剩余范围。旧的解压后残缺 ZIP 不作为可信续传前缀。CRC 不符会报错，不会生成成功清单。

## 许可与使用条款（亲自核实）

[MagNet 软件仓库许可原文](https://raw.githubusercontent.com/PrincetonUniversity/magnet/main/LICENSE) 的标题为 “MIT License”。其对象摘录：
> of this software and associated documentation files (the "Software")
[挑战代码仓库](https://raw.githubusercontent.com/minjiechen/magnetchallenge-1/main/LICENSE) 同样采用 MIT。
这两份文件位于代码仓库，并把对象称为软件与相关文档；所核实页面没有明确把 Princeton 单独托管的测量数据纳入该许可。不能据此给数据标注 MIT。
[挑战 README](https://raw.githubusercontent.com/minjiechen/magnetchallenge-1/main/README.md) 的数据使用要求逐字摘录：
> If you used MagNet data, please acknowledge the MagNet project
同一句的后半部分要求引用页面末尾列出的论文。它是署名/引用要求，未明确授予数据再分发权。
[挑战手册](https://raw.githubusercontent.com/minjiechen/magnetchallenge-1/main/docs/handbook.pdf) “Intellectual Property and Use of Prize Money” 一节逐字摘录：
> There are no special licenses or rights required by the sponsors.
该段谈参赛队提交的软件、模型、算法及其知识产权，并非数据授权。手册技术规则允许参赛队用数据训练、测试模型，但未找到明确的数据再分发或商用许可。
在本次打开核实的 [Library 页面](https://www.princeton.edu/~minjie/magnet.html)、代码仓库许可、挑战 README 和手册中，**未找到明确的数据许可**。这是检索范围内的结论，不表示全网不存在许可。原始测量 CSV/ZIP 留在 gitignore 的 data/magnet；入库的是哈希、派生预测、指标及方法文档。

## 官方规模与本次实际范围

[Library 原文](https://www.princeton.edu/~minjie/magnet.html)：
> Complete MagNet Raw Database (15 Materials, 29.31 GB)
> Pretest Training Data (10 Materials, 3.14 GB)
以上是材料数和包大小，不是样本总数；本次核实的该页面没有给出全库总样本数。未能核实全库样本总数及“N87 原始全库 142,871 条”的原论文出处，因此不将它们作为本案例事实。
本次 N87 是预训练子集，实际 40616 条，每条 B 和 H 波形 1024 点。实际统计来自 `magnet_igse.py`，不是从公开全库规模推断。

| 字段 | 实际最小值 | 实际最大值 | 单位/说明 |
|---|---|---|---|
| temperature_C | 25 | 90 | ℃；离散组见下文 |
| frequency_Hz | 49950 | 446690 | Hz |
| amplitude_T | 0.0105132697738 | 0.280714663396 | T；B̂ = (max B − min B)/2 |
| measured_W_m3 | 444.416175443 | 2590076.72491 | W/m³ |

实际温度组：25 ℃、50 ℃、70 ℃、90 ℃。
ZIP 字段：`B_waveform[T].csv`, `H_waveform[Am-1].csv`, `Frequency[Hz].csv`, `Temperature[C].csv`, `Volumetric_losses[Wm-3].csv`。无波形类型、占空比或激励类型标签，CSV 无表头；样本编号取原始行号，从零开始。
单位及单周期解释与手册技术规则一致：频率 Hz、B 为 Tesla、温度 Celsius、体积损耗 W/m³；采用均匀单周期网格且不重复末端点。

## 固定波形规则与抽检

先去均值，投影到一周期正弦/余弦基，计算 RMS 残差除以原波形 RMS。残差 ≤0.05 判为正弦。其余波形计算周期差分绝对值，低于本条差分 p90 的 0.1 倍的点作为平台；平台占比 ≥0.05 判为梯形，其余判为三角类。没有读取实测损耗来分类，也没有以评估误差选择阈值。
三角类包括非对称三角及无明显平台的多段斜率形状，不声称每条都是理想两段三角。初始残差阈值 0.02 的边界抽检发现失真正弦误分；按 B 形状固定为 0.05 后重新拟合。
最终分类计数：正弦 1426；三角类 33086；梯形 6104。
固定种子分层随机抽检每类 12 条，总 36 条，逐图检查的一致数 36；另抽距两个阈值最近的边界 12 条，一致数 12。
抽检员为本任务 researcher_a；按上述广义形状定义检查，既非盲审，也无独立真值标签。该一致率只描述这批图的可读形状，不是总体分类准确率。三角边界的多段斜率样本已逐条备注。
抽样行号与逐条评审见 `classification_audit.csv`、`classification_audit_review.csv`；完整审核图保存在 data/magnet/classification_audit_*.png。
