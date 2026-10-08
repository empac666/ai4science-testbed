# R9f：第九轮预注册审稿回复

日期：2026-10-08。修订作者：local_node researcher_a（R9f）。分支：`feat/r9-honest-extrap`。生效版本：`R9f-local-researcher_a-1`。状态：按已收到意见修订完成，待用户批准，未执行实验。

本次修订文件为[预注册](../../prereg/M10_magnet_round9_prereg.md)与[配置](../../../lab/cases/magnet9/config_prerun.json)，本回复为第三交付文件。原`researcher_a_R9p_notes.md`保留为设计历史，不改写为本次回复。下文“§”均指修订后预注册节号，JSON位置用完整字段路径表示。

## 1. 审稿来源与可处理范围

已完整读取当前磁盘上的两份指定审稿文件。reviewer_b文件包含R9-C01—C08及综合核对；reviewer_c文件包含开头摘要、完整R9-C01及不完整R9-C02，**在“δ 与 q 在 CAL 上有”处结束**（2600字节）。已请求补充缺失文字；截至本版封存，未取得后续文字。本回复处理所有已收到的must-fix，并将reviewer_c开头的逐臂崩溃及检验顺序批评一并落实；不编造缺失意见编号、建议或批准结论。READY_FOR_APPROVAL表示本版供用户审阅，不表示缺失审稿已补齐或允许执行。

| 来源 | 文件 | 读取版本SHA256 |
|---|---|---|
| reviewer_b | `docs/discussion/m10/reviewer_b_review_R9p.md` | `d4ad082c3abcc635ffa7e0a90a38c84c565814736002845cf1ed4412ec47f16b` |
| reviewer_c | `docs/discussion/m10/reviewer_c_review_R9p.md` | `ed078ce855b2cc3f85cce00b5be48a3b9b749231554d03967c664ee82d095ff6` |

reviewer_b/reviewer_c的R9-C01等编号各自独立，以下始终附来源区分。审稿人不是修订稿共同作者；本版不声称再次获得审稿人批准。

## 2. 逐条处理

### reviewer_b / R9-C01 / must-fix / 采纳

- **改动位置**：§7、§9、§11、§12；JSON `tests.families`、`tests.alpha_each`、`tests.familywise_alpha`、`tests.alpha_recycling`、`tests.cross_region_blocking`、`tests.reject_rule`、`tests.stop_rule`、`conclusions`及未来验收要求。
- **改动**：使用双族方案：XF为H1→H3、XT为H2→H4，两族各α=0.025，严格p<0.025。保留原H编号，但删除原跨区四步总顺序；两族均在流程有效时启动，互不阻断，不因描述性门控失败跳过检验。无α回收/转移。SUCCESS_F和SUCCESS_T各只依赖本区J及本族两项正式拒绝。
- **理由**：两方向地位对等，单纯改为XF优先的方案A仍会让XF阻断XT；本方案允许任意单方向独立成功。每族固定序列的条件强FWER≤0.025，总体由并集界≤0.05，不要求区域独立。选择不回收α是为了固定清楚的拒绝规则，避免新增转移图和状态歧义，代价是更保守的功效。

### reviewer_b / R9-C02 / must-fix / 采纳

- **改动位置**：标题、§1、§7—§9；JSON `scope.claim_scope`、`tests.hypotheses`、`tests.coverage_interpretation`、`gates.interpretation`、`conclusions.dual_honesty_exit`及`conclusions.required_result_fields`。
- **改动**：H1/H2明确为90%覆盖欠缺配对差的相对优效性，不再把拒绝解释为绝对诚实。A/J只表示固定面板经验标准，无第一类错误控制或总体覆盖保证；确认性结果必须同时列A、WIDTH、J及两假设状态。新增双诚实描述性退出：两方法均通过A而相对改进未确认时，报告“两者均达到经验覆盖标准”，不写D方法失败。
- **理由及边界**：双A通过并不等于30臂都达到90%，也不等于所有g为0。仅在全部g_B、g_D均为0时，才写“无额外相对欠覆盖需要缩减”，并报告d全零、p=1；若d全零但共同欠缺非零，只报告欠缺相同。退出条款不重定义SUCCESS，不跳过覆盖假设去检验Winkler；WIDTH失败仍须同时报告代价超限。这保留了相对检验的科学含义，避免将基线已达标误判为候选无价值。

### reviewer_b / R9-C03 / should-fix / 部分采纳

- **改动位置**：§7、§10—§12；JSON `tests.assumptions`、`tests.fwer_scope`、`winkler_sensitivity_report_only`及`power_and_limits.limitations`。
- **采纳部分**：明确1.10乘数不能由交换D/B推出对称，20倍漏覆盖惩罚可产生重右尾，均值为零也不保证对称。新增U处理、XF/XT各30个W_D/W_B及均值之比；W_B为0时记null，不加ε。逐一删去一对，仅描述其余29对移位差均值的全部30个值、范围及非正个数，不计算新正式p或选择删对。
- **未采纳部分与理由**：不新增90%配对Bootstrap置信区间。几何比值/平均逐臂比值与主假设的期望分数差并非同一估计对象，普通Bootstrap也不能验证独立符号对称或修复原p的FWER。保留无额外随机流的确定性敏感性描述，并明确它也不构成稳健性证明。正式推断仍以原假设前提为条件，不以本次修订声称解决了未知分布的有效性。

### reviewer_b / R9-C04 / should-fix / 部分采纳

- **改动位置**：§8、§11；JSON `gates.WIDTH`、`power_and_limits`。
- **采纳部分**：按新α=0.025将单假设正态近似功效改为δ=0.4时0.591314、δ=0.6时0.907642；明确这不是端到端功效。逐一列出区域内两项检验、26/30门槛、MEAN90、FLOOR80、宽度均值及30/30上限和流程有效性等联合约束，双区成功还需两族全通。联合成功率未知且可能远低于单假设值。
- **算术与逻辑修正**：0.75^4=0.31640625仅在四事件独立时成立，不是普遍上界；一般交集上界是各边际概率的最小值。假设独立且单臂过90%门槛概率0.70时，Binomial(30,0.70)至少26次的解析尾概率约0.0302，而非约0.04；不能把“过门槛概率”当真实覆盖率，更不能据此推出本实验必须达到93%覆盖。这些只作解析例子，未模拟或读取y。
- **未采纳部分与理由**：不把WIDTH的30/30放宽为29/30。逐臂2倍是已选定的硬性工程代价上限，保留一票否决；单臂2.01倍即可失败，正式标为极端高风险。reviewer_c同时指出逐臂覆盖失败可被平均数掩盖，因此本版增加FLOOR80而不为提高功效继续放松极端臂约束。接受由此降低成功机会，不声称联合功效充足。

### reviewer_b / R9-C05 / should-fix / 采纳

- **改动位置**：§4、§5、§9、§11、§12；JSON `model.shadow_linear_feature_rule`、`model.temperature_shadow_rank_deficiency`、`model.reuse_rule`、`validity.model_validity`及未来验收要求。
- **改动**：影子模型当且仅当本地训练子集温度唯一值少于3时删除OLS的T_C²。M_T固定要求25/50两层，实际用五列；M_F要求25/50/70三层，保留六列。主模型全部检查点、GP输入与其他超参数不变。先检查必需温度层再应用特征规则，不能借删列绕过子集不足。报告实际特征列、秩、条件数和温度层。
- **理由**：在无y、无结果阶段消除已知二次温度曲率不可辨识性；不再把任意尺度下的最小范数二次外推当作稳健设计。但删一列不保证所有列满秩，其他共线性仍沿用lstsq并披露。线性外推和伪域迁移也可能误设，XT失败不能归因为“物理外推不可行”。本次只改设计契约，不写适配代码、不修改旧模型源码。

### reviewer_b / R9-C06 / nit / 采纳

- **改动位置**：§4、§8、§12；JSON `intervals.Q90_rank_one_based`、`gates.C1`、`gates.integer_ceiling_contract`、`gates.coverage_threshold_formulas`。
- **改动**：统一`ceil_div(a,b)=(a+b−1)//b`，C1为`(4*n_G9+4)//5`；80%、90%、MEAN90及Q90秩都用整数公式。
- **理由**：以相同的整数契约消除浮点ceil表述差异，无需依赖某个具体n是否会触发浮点边界问题。XF/XT覆盖计数阈值不变。

### reviewer_b / R9-C07 / nit / 采纳

- **改动位置**：§4、§8；JSON `intervals.width_monotonicity`、`gates.WIDTH.interpretation`。
- **改动**：写明D相对B逐点/逐臂弱宽，G9相等，XFT亦弱扩张；单方向q0>0时宽度比为qD_j/q0，零分母不取比。WIDTH因此只设上限。
- **理由**：覆盖变化包含中心平移与保守尺度扩张，不能暗示D通过收窄得益；中心平移本身也不保证覆盖改善。与reviewer_c C02一并澄清，弱扩张性质不证明经验诚实，更不排除仅加宽的解释。

### reviewer_b / R9-C08 / nit / 采纳

- **改动位置**：§5、§11、§13；JSON `split`、`power_and_limits.preflight_risk`、`validity.input_preflight_before_labels_and_fits`、`execution.infeasible_design_abort`、`data.label_access_order`。
- **改动**：将CAL20的F边缘不足2族约0.049805的组合风险列为首要执行风险；它只是总不可行风险的一部分。无标签预检提前到任何标签访问和拟合之前；失败状态固定为`infeasible_design_abort`，整轮不完整，无确认性结论。
- **归档与理由**：研究者立即停止；主持人保留批准、SHA/H、配置/输入清单哈希、唯一划分种子/掩码/计数、失败断言实际值、时间及无标签/无拟合阶段记录、首次失败清单和日志。不得重抽、改SHA或改称基础设施故障；重设计须另立未来预注册并保留本次失败。这样既如实统计设计风险，也不为静态已知不可行的设计启动540次拟合。

### reviewer_c / R9-C01 / must-fix / 采纳

- **改动位置**：标题、§1、§7—§10；JSON `scope.claim_scope`、`tests.hypotheses`、`tests.coverage_interpretation`、`conclusions.required_result_fields`、`conclusions.prohibited_claims`、`ablation_report_only`。
- **改动**：H1/H2写成90%覆盖欠缺的配对差，明确82%→85%仍未达标、90%→99%不产生欠缺改善；绝对标准只由描述性A/J承载，不能由拒绝证明。确认性语句必须同时报告J及其组成。预先指定D/E配对覆盖、欠缺、Winkler、宽度、MAE、偏差及参数差报告，E始终只报告。
- **理由**：D/B同时改变中心和q，检验支持的是完整策略的相对效应，不是中心校正的归因。D/E的q也可能不同，因此其总差也不能称纯中心效应；额外固定两个相同宽度锚点的描述性评分，见下一条。

### reviewer_c / R9-C02 / must-fix / 采纳（已收到文字及开头摘要）

- **改动位置**：§1、§4、§8—§13；JSON `gates.FLOOR80`、`gates.A`、`gates.interpretation`、`scope.claim_scope`、`conclusions`、`ablation_report_only`及对应未来验收要求。
- **覆盖崩溃的落实**：保留V80/HONEST90的26/30定义，但新增FLOOR80：30/30臂的G9及相应外推区覆盖均至少80%，任何一臂失败即A失败。MEAN90无法再用其他臂的高覆盖补偿低于80%的臂；仍允许最多4臂处于80%至90%，不声称所有臂达到90%。
- **仅加宽解释的落实**：承认1.50均值/2.00逐臂宽度及10% Winkler界不能排除仅靠加宽获得覆盖；特别是欠覆盖基线的惩罚减少可抵销宽度成本。不无依据地另定一个更小倍数并声称能解决归因，而将主结论严格收窄到“完整D策略在预算内的相对欠覆盖改进与经验门控通过”。禁止“WIDTH已防止靠变宽变诚实”或“D/B成功证明偏差校正有效”的结论。范围澄清不改写为新的中心贡献确认性假设。
- **固定的D/E描述性归因**：在U/S、XF/XT逐组报告D/E总差，同时分别固定qE_j和qD_j两个宽度锚点，比较有/无δ_j的中心，报告Δc、Δg、ΔW的30值、均值、中位数、极值及正零负数。两个锚点都报告，不按结果选择；没有相同宽度改善时如实说明。只用已封存预测在隔离评估阶段评分，不反馈CAL、不新增采集/拟合/正式方法臂，不进门控或SUCCESS，也不作为总体因果证明。
- **CAL权限澄清**：δ仍仅由已查询训练伪边缘估计，CAL只计算q；不把截断句臆补成审稿人的完整断言。由于qE与qD均依赖既定CAL残差，D/E全差包含重新校准的影响，故补充上述相同宽度描述且保留推断限制。
- **理由与缺文边界**：本条通过实质新增逐臂底线、收窄不能被设计支持的声称和预定归因报告，处理可见的must-fix。后半条原始建议缺失，不能承诺与未收到的建议逐字一致；若后续补齐，应在任何执行前另记审阅处理。

### reviewer_c / 开头未编号摘要 / 采纳

- **改动位置**：§7—§9；JSON `tests.families`、`gates.FLOOR80`、`conclusions`。
- **处理**：截断欠缺的推断语义并入reviewer_c C01；个别臂覆盖崩溃与加宽归因并入reviewer_c C02；固定顺序和单方向成功冲突按reviewer_b C01的双族方案处理。未替reviewer_c生成不存在的后续R9-C03等编号。

## 3. 文档与JSON一致性及静态核对

| 预注册位置 | 对应JSON字段 | 本版一致口径 |
|---|---|---|
| 文首、§14 | `schema_version`、`status`、`authorship`、`review_inputs`、各文档路径 | R9f版本、修订作者、两来源及reviewer_c缺文事实、待用户批准 |
| §1—§2 | `scope`、`data`、`family_definition`、`regions`、`expected_design_counts`、`split` | 原数据/区域/族定义与无标签计数保留；主声称收窄 |
| §3 | `design`、`acquisition` | K=30，U/S各30轨迹，三正式方法共180臂，100+120=220标签，540拟合 |
| §4—§5 | `model`、`pseudo_extrapolation`、`intervals`、`validity` | 影子温度删项、主模型保持、δ/q权限、整数Q90秩、输入预检提前 |
| §6 | `seeds`、`freeze` | SHA/H未赋值；种子公式及不重抽规则保留 |
| §7 | `metrics`、`tests` | H编号及d公式、精确MITM契约不变；F:H1→H3，T:H2→H4，各α=0.025，无回收 |
| §8 | `gates` | 整数覆盖门槛、FLOOR80全30臂、A/J公式、宽度1.50/2.00硬上限 |
| §9 | `conclusions` | 区域独立SUCCESS、完整结果句、双诚实及零欠缺条件、禁止过度归因 |
| §10 | `s0_report_only`、`report_only`、`ablation_report_only`、`winkler_sensitivity_report_only` | S0描述规则不变；D/E双宽度锚点；W比值/删对仅描述，无Bootstrap |
| §11 | `power_and_limits` | 新α单项功效、联合功效未知、解析二项例子及预检风险 |
| §12 | `C03_future_implementation_requirements` | 新双族/FLOOR80/删项/诊断验收条件仅登记，未写或运行实验测试 |
| §13 | `execution`、`freeze` | 并行/内存约束保留，新增不可行中断归档；三生效交付文件明确 |

静态核对包括JSON解析且无重复键、假设句逐字匹配、区域族及α、各整数覆盖阈值、A/J与SUCCESS对应、影子特征规则、诊断只报告范围、解析功效和组合概率、版本/路径/作者记录，以及所有未修订设计块与原配置的相等检查。原始输入计数与源文件哈希沿用R9p，未读取原始数据重算。检查中只使用预注册、配置、审稿文本和公开数学公式，没有生成随机样本、合成实验数据或运行MITM/模型/实验测试。

工作区检查确认已跟踪文件无变更（本轮交付原为未跟踪文件）；仅编辑指定预注册/配置并新增本回复，未改第一至八轮文件、审稿原文或R9p记录。未联网、未pip、未git commit/push，未读取任何y或第八轮逐样本预测，未写实验代码、未运行实验、未调用子代理。预注册与配置的最终SHA256在交付消息中给出，三文件哈希由后续获授权冻结清单记录，避免自哈希循环。

## 4. 最终假设与审批状态

以下四项均为U处理30个D/B配对上的备择，原假设均为对应E[d]≤0；g=max(0,0.90−c)，W为90% Winkler分数。

H1：XF的90%覆盖欠缺配对差期望E[g_B,XF−g_D,XF]>0。

H2：XT的90%覆盖欠缺配对差期望E[g_B,XT−g_D,XT]>0。

H3：XF的10%期望Winkler非劣，E[1.10W_B,XF−W_D,XF]>0。

H4：XT的10%期望Winkler非劣，E[1.10W_B,XT−W_D,XT]>0。

XF族H1→H3、XT族H2→H4，各α=0.025；正式p及FWER的有效性条件与经验门控限制见预注册§7—§9。两个方向互不阻断；没有新增正式假设。

READY_FOR_APPROVAL
