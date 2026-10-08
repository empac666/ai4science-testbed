# AI4Science：可核查的研究实验 / Auditable research experiments

用预注册、封存评估、独立复算与交叉评审，检验小样本代理模型的预测与区间是否可信。

A research workbench testing small-data surrogate predictions and uncertainty intervals through preregistration, sealed evaluation, independent recomputation, and cross-review.

电力电子变换器直流母线偏置案例（DC-link，第 1–5 轮）及 MagNet 磁损耗案例（第 6–9 轮）。结论限定于各轮数据、划分与假设；仿真不替代硬件实验，同一数据集的新划分不等于独立实测复现。

The DC-link simulation case covers rounds 1–5; MagNet core loss covers rounds 6–9. Simulation is not hardware validation; new splits of one dataset are not independent measurement replication.

## 方法 / Method

预注册 → 封存三阶段评估 → 独立复算 → 多 AI 交叉评审与逐条裁定。

1. **预注册 / Preregister:** 先冻结主假设、数据权限、随机种子、指标、检验顺序与失败条件，再看结果。Freeze hypotheses, access rules, seeds, metrics, test order, and failure gates.
2. **三阶段封存 / Three sealed stages:** 采集与训练完成后封存模型；随后开放校准标签、封存区间规则；最后开放评估标签并封存首次结果。Acquire/train → calibrate → evaluate. 第八轮显式实现这三阶段；早期轮次机制见各轮报告，不倒写历史。
3. **独立复算 / Independent recomputation:** 从预测和逐臂记录重算覆盖、宽度、Winkler、检验和门控，披露共享实现与数据的限制。Recompute from predictions and arm records; disclose shared-code/data limitations.
4. **交叉评审 / Cross-review:** 对意见逐条接受、部分接受或驳回，并保留依据。Document adjudication; multiple reviewers are not proof of statistical independence.

Winkler 越低越好，同时惩罚过宽与漏覆盖；分数改善不能替代覆盖门控。A/M/R 为主动、混合、随机采样；名义覆盖目标为 90%。Lower Winkler scores are better, but do not establish adequate coverage. A/M/R denote active/mixed/random sampling; nominal coverage is 90%.

## 第 1–8 轮结论 / Results, rounds 1–8

数字来自链接报告；不同案例的分数单位不同，不直接跨轮比较绝对值。Values are from linked reports; units differ across cases.

| 轮 / Round | 真实数字 / Reported evidence | 结论与范围 / Conclusion and scope |
| --- | --- | --- |
| [1](docs/reports/M2_researcher_a.md) | GP test MAE 0.181757 百分点；OOD MAE 0.339906；OOD 覆盖 0.400000 | 不通过 / Failed: OOD coverage outside [0.85, 0.95]. |
| [2](docs/reports/M3_dclink_round2_researcher_a.md) | M2 覆盖：test 74/75，死区留出 29/30，角落 20/30（要求 ≥24/30） | 不通过 / Failed on the corner gate. |
| [3](docs/reports/M4_dclink_round3.md) | 角落覆盖 A 38/40、R 25/40；Winkler 1.559 vs 3.339；p=0.00168 | 总判定通过；单次主动实现 / Passed for this comparison. |
| [4](docs/reports/M5_dclink_round4.md) | 固定 A 的 Winkler 1.559，五个新随机臂 2.201–3.636；M 覆盖 37/40、Winkler 1.472 | H-A、H-M 通过；A/M 各仅一次实现 / Passed with limited method-level replication. |
| [5](docs/reports/M6_dclink_round5.md) | 6 组配对；H1–H3 p=0.015625；H4 p=0.421875；CV-A/M/R=6/6、6/6、1/6 | A、M、M 对 A 的 10% 非劣成立；dt3 优越不成立 / Distinguish superiority from non-inferiority. |
| [6](docs/reports/M7_magnet_round6.md) | 8 组；H1 p=0.0391，H2 p=0.6055；Winkler R 0.0647 → A 0.0558；97.5% 角落点有跨温度孪生点 | A 成立但脆弱；H3–H6 未检验；不是严格外推 / Fragile support; nearby related samples remain in the pool. |
| [7](docs/reports/M8_magnet_round7.md) | 20 组；H1 p=0.0209，H2 p=3.62e-5，H3 p=0.0769；CV-A 20/20 | 两类留出上的 Winkler 优势成立；点预测优势未成立，H4/H5 未检验 / Supported-corner extrapolation only. |
| [8](docs/reports/M9_magnet_round8.md) | 每实验 30 组；H1–H6 全拒绝；E2 主动 XF/XT Winkler 降 64.25%/29.91%；HONEST90-A 仅 5/30、1/30（要求 ≥26/30） | E1 混合采样结论成立；E2 的 A/M/R 在 XF/XT 的 V80 与 HONEST90 均失败 / E2 effective-superiority claims fail despite significant score gains. |

## 第九轮 / Round 9

**XF/XT 覆盖显著改善，但均未达完整 SUCCESS；XF 宽度非劣未证。** 严格区分：覆盖的正式检验对象是相对基线的 90% 覆盖欠缺；XF 的 WIDTH 硬性宽度预算失败，H3 检验的 Winkler 综合代价非劣也未获确认，不能将二者混称为一个宽度检验。

固定主动采样，主分析为 U 处理的 30 个配对组，比较全局 q 基线 B 与方向性伪外推加中心校正 D：

| 区域 | B → D 平均覆盖 | 覆盖欠缺检验 | Winkler 非劣检验 | 经验门控与结论 |
| --- | --- | --- | --- | --- |
| XF | 0.76848847 → 0.83639868 | H1 p=0.018968277，拒绝 | H3 p=0.27077449，未拒绝 | A、WIDTH、J 失败；未达到完整经验覆盖标准 |
| XT | 0.68721789 → 0.78348712 | H2 p=7.8665093e-05，拒绝 | H4 p=4.8531219e-06，拒绝 | WIDTH 通过，A、J 失败；未达到完整经验覆盖标准 |

两区域各自固定序列、α=0.025，无 α 回收。显著性以固定数据与族划分下的符号对称等假设为前提；经验覆盖门控不提供总体覆盖保证。XF 相同宽度诊断未观察到平均中心改善，不能排除 D/B 改善仅由加宽解释。S0 干预未满足预定支持判据，不代表无影响。

Coverage improved significantly in XF and XT in the prespecified shortfall tests, but neither region achieved full SUCCESS. XF failed the hard WIDTH budget and did not establish Winkler non-inferiority; XT passed those cost criteria but failed empirical coverage gates. Inference remains conditional on the stated symmetry assumptions and fixed dataset/split.

见[预注册](docs/prereg/M10_magnet_round9_prereg.md)、[配置](lab/cases/magnet9/config_prerun.json)、[修订报告及四张图](docs/reports/M10_magnet_round9.md)、[结果复审](docs/discussion/m10/reviewer_b_review_R9results.md)和[逐条裁定](docs/discussion/m10/moderator_rulings.md)。复审为 ACCEPT WITH MINOR REVISIONS，五条采纳、一条部分采纳。

预注册中的“待批准、尚未执行”保留历史时点状态；本次发布已封存的第九轮结果及文字小修，不倒写历史批准。日志不随公开包分发；原始封存引用与当前公开文件校验的区别见[发布说明](RELEASE_NOTES.md)。

## 离线复现 / Offline reproduction

Python ≥3.12。数值测试需要预先安装 numpy、pandas、scipy、scikit-learn、matplotlib；本次使用已有环境，不联网、不安装包。在仓库根目录执行，解释器可指定为已有环境。

Use an existing Python environment with these scientific packages. These commands do not download data or install packages:

```bash
python3 scripts/public_release.py
python3 scripts/prepare_public_data.py
make test PYTHON=python3
python3 scripts/m9_report_tables.py > data/round8_tables.md
python3 scripts/recheck_published.py
python3 scripts/recheck_published_r9.py
```

准备脚本只恢复包内小型输入元数据，拒绝覆盖不一致文件。缺少外部仿真器、波形特征或划分的测试明确跳过；合成测试、证据检查和封存表核查仍运行。复算脚本从发布预测重算第 1–5 轮区间指标，并核查第八轮表格；第九轮只读核查封存指标、精确检验及门控，不重新拟合模型或读取原始标签。

Preparation restores bundled metadata only. Tests requiring unavailable external inputs report skips. The recheck uses published predictions and round-8 summaries; the round-9 check verifies published metrics, exact tests, and gates without model fitting or original labels.

第 1–5 轮完整仿真还需单独提供通用仿真器到 `external/dclink-simulator`（含 `dclink_simsw` 和回放程序）。该依赖不在授权快照内，本包不能独立生成原始波形。旧报告中的成功记录是历史记录，当前范围以本节为准。详见[发布说明](RELEASE_NOTES.md)。

Full DC-link simulation needs the external simulator, absent from this snapshot. Historical success records are not current verification claims. Historical commit identifiers remain as provenance/seed constants; no old Git objects or history are included.

## 数据获取与许可 / Data access and licenses

大于 20 MB 的数据文件不入库。原始 ZIP、波形、运行缓存存于被忽略的 `data/`；当前导出快照无超过此门限的文件。Raw data stays outside version control.

| 数据 / Dataset | 官方获取 / Official access | 许可说明 / License notes |
| --- | --- | --- |
| MagNet（第 6–9 轮） | [官方数据目录](https://www.princeton.edu/~minjie/magnet.html) → Challenge 1 Pretest Training Data → N87。需联网时另行运行 `python3 scripts/magnet_fetch.py`，下载后 `python3 scripts/magnet_igse.py` 生成缓存。 | [上游软件 MIT](https://github.com/PrincetonUniversity/magnet/blob/main/LICENSE)不能自动套用于测量数据；所核查官方目录未明确独立数据许可。遵循下载包条款与引用要求，本仓库不另授再分发权。Software MIT does not automatically license measurements. |
| NASA PCoE（仅后续候选，未用于本轮） | [官方数据仓库](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/)提供电池等数据及引用方式。 | [电池数据条目](https://data.nasa.gov/dataset/li-ion-battery-aging-datasets)标为 “License not specified”；核对具体包条款，不把公开下载解释为 MIT。Not used in the reported experiments. |

官方页面于 2026-10-08 核对；未下载数据。第 6–9 轮全流程还需原始波形、`data/magnet6/features.csv` 与各轮划分，严格保留种子和阶段访问边界。Official pages checked on 2026-10-08; full reruns require those original inputs and frozen procedures.

## 许可证 / License

项目代码使用 [MIT](LICENSE)。数据、上游材料及派生数据遵循原始许可和适用条款，不自动重新许可为 MIT。

Project code is MIT. Data and upstream materials retain their original licenses and applicable terms.
