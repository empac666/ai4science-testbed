你是独立统计审稿人。请审阅下面第九轮预注册（MagNet N87 单侧外推下预测区间诚实性）及其冻结配置。不要调用任何工具，只输出文字。
请按编号列出问题（R9-C01…），每条标注 must-fix / should-fix / nit，说明理由与具体修改建议。重点：假设是否直接检验覆盖诚实、门控与宽度约束能否防"靠变宽变诚实"、伪外推划分是否泄漏真实留出区 y、种子与 H 定义、检验顺序与结论映射是否完备、配置 JSON 与文档是否逐项一致、功效是否足够。最后一行给出 VERDICT: APPROVE / APPROVE_WITH_FIXES / REJECT。

=== 预注册 ===
# 第九轮预注册：N87 单侧外推区间的经验诚实度

版本：R9p-local_node-researcher_a-1，2026-10-08；状态：**待 reviewer_b 评审、待用户批准，尚未执行**。冻结配置为 `lab/cases/magnet9/config_prerun.json`，设计核对记录为 `docs/discussion/m10/researcher_a_R9p_notes.md`。本任务只写这三个文档/配置文件，不写实验代码、不生成随机划分、不运行实验、不读 y、不联网、不安装、不提交或推送；第一至八轮文件不变。

## 1. 背景、问题与范围

第八轮预注册、报告及主持人裁定是已披露先验信息。其 H1–H6 全部拒绝，但 E2 外推覆盖门控全部失败：A/M/R 的 V80 通过数分别为 XF 22/17/2、XT 3/2/1；HONEST90 为 XF 5/2/0、XT 1/1/0，门槛均为26/30。A/M 的 XF 平均覆盖约82%，XT 的 A/M/R 约63%/62%/59%，低于名义90%。XFT 的平均 log10 偏差换算为几何比例，低估约14%（A）至26%（R），不是算术平均百分比误差。逐臂离散大；“由 S0 驱动”仍是裁定二.4 指明的未检验推测。

主问题：**固定主动采样 A 和模型预算，支撑内的方向性伪外推残差加偏差校正，能否缩小 XF/XT 的90%覆盖欠缺，并在预先限制宽度和 Winkler 代价后达到经验诚实标准？** 次问题：去掉中心偏差校正后如何；受控改变 S0 几何组成是否降低离散度。

只保留 A 采集，不再比较 M/R 采集优越性，避免同时改变采样策略与区间方法。基线 B 是第八轮 E2-A 的全局单标量 q 规则，在本轮新族划分、新 S0、新 GP 种子下完整重跑；不复用历史模型、标签缓存、q 或预测。三种区间方法共享同组同 S0 处理的训练轨迹，因此差异来自区间规则。E 为消融，只报告；D 为唯一确认性候选，不能结果后把 E 提升为主方法。

这是同一 N87 固定数据集上的新随机化研究，历史轮次看过部分标签，不是新材料/新测量的独立复现。R9p 未打开目标 CSV、波形文件或第八轮 `first*/` 中任何产物；只使用允许的文档、源代码、配置、无标签划分摘要和输入特征。

## 2. 数据、区域与族划分（冻结）

输入仅取 `data/magnet6/features.csv` 白名单：sample_id、frequency_Hz、T_C、waveform、amplitude_T、log10_f、log10_Bpk、duty、plateau、shape。忽略旧 cell/corner。执行目标为 y=log10(measured_W_m3)，仅未来获批执行阶段可按阶段权限读取。不得以 iGSE 预测、误差、历史残差或其他 y 派生量选区、定阈值或调参；本轮不新增 iGSE 对照。

族规则沿用第八轮：在全部输入的排序唯一 frequency_Hz 上，相邻自然对数差>0.01时新开频率簇；fset=`round(median(cluster)/1000)` kHz。族键为 `f"{fset}_{waveform}_{round(10*duty)}_{round(20*plateau)}"`，Python ties-to-even；族键按字符串字典序、id按整数排序。先建全局族，再限制区域。

| 集合 | 规则 | 点数 | 集合内族数 |
|---|---|---:|---:|
| 全体 | N87 | 40616 | 291 |
| S 支撑区 | fset<300 且 T_C≤70 | 25122 | 220 |
| XF | fset≥300 且 T_C≤70 | 5361 | 69 |
| XT | fset<300 且 T_C=90 | 8345 | 217 |
| XFT（只报告） | fset≥300 且 T_C=90 | 1788 | 67 |

四区互斥并覆盖全体；按原始频率≥300000 Hz与fset≥300划分差异为0。温度为25/50/70/90 °C；频率设定点为50、56、63、71、79、89、100、112、126、141、159、178、199、224、251、282、316、355、397、446 kHz。XF∪XFT=7149，XT∪XFT=10133。训练允许的最高设定点282 kHz、最高温度70 °C；实际池/训练极值另报，不能以允许上限冒充实际支撑。

**完全沿用 R8-E2 的 G/CAL 抽取规则与规模。** 对220个支撑族作一次排列，前30族的支撑样本为 G9，随后20族的支撑样本为 CAL9；余170族的支撑样本为池 P。三者在 S 内按族互斥；同族90 °C点仍在 XT。所有 k、S0 处理、区间方法共用这一划分。P 的输入侧保守下界为12892点。G/CAL/P实际点数须待提交绑定后确定，不在本稿填入旧轮计数。

## 3. K、S0 处理与主动采样

K=30，k=1,…,30。主分析只使用 **U：普通均匀 S0** 的30个匹配组。另设 **S：边界均衡 S0** 的30组作为预先设计的只报告干预，不把两处理合成K=60，也不将同一S0下的三种区间当独立重复。

每个k用一个新随机流，生成排序 P 的均匀随机排列 π_k。U取π_k前100点。S按同一个π_k在六个输入层内的相对次序取前指定个数：

| fset层 | 25 °C | 50 °C | 70 °C |
|---|---:|---:|---:|
| ≤199 kHz | 16 | 17 | 17 |
| 224/251/282 kHz | 16 | 17 | 17 |

S总计100点，频率边缘占50%；温度占32/34/34%。U/S以共同随机次序耦合，均各自无放回；同号k构成S0干预的配对块。S不是额外边缘标签预算，两个处理均为100+120=220点。各k随机流独立；不同组、处理可重叠id。各处理的 B/E/D 共用完整 S0、采集序列和最终模型，不各自重新采点。

采集保持 R8 A：b=0,…,5各从头拟合当前100+20b个已查询点，以 GP σ 的 kriging believer 选20点，选完整批才读取该批y；并列取最小整数sample_id。批内超参数及 y 标准化固定，按原模型库 Cholesky 更新；候选为 P 减去本轨迹已查询点。b=6在220点上最终拟合。共60条采集轨迹、180个区间输出臂（U/S各30×B/E/D）。主检验每项只有U的30对。

## 4. 模型与方向性伪外推（公式冻结）

主模型及两种影子模型使用同一冻结数值规则：OLS均值列[1,log10_f,log10_Bpk,T_C,T_C²,shape]，`numpy.linalg.lstsq(..., rcond=None)`；残差 GP 输入[log10_f,log10_Bpk,T_C,duty,plateau,shape]。StandardScaler仅拟合各自训练子集。核为Constant(1,[0.01,100])×ARD-RBF(六个初值1，界[0.01,100])+White(0.01,[1e-8,10])；alpha=1e-10，normalize_y=True，优化重启2。σ含WhiteKernel，底值2.220446049250313e-16。每次从头拟合；影子模型不继承主模型的系数、scaler、超参数或缓存。

以下公式逐(s,k)计算，s∈{U,S}；省略下标。最终已查询训练集记 T，主模型输出μ(x)、σ(x)。在**支撑内**固定两个方向j：

| j | 核心 C_j | 伪外推边缘 E_j | S内核心/边缘点数 | 核心/边缘族数 |
|---|---|---|---|---|
| F | fset≤199 | fset∈{224,251,282} | 20317 / 4805 | 174 / 46 |
| T | T_C≤50 | T_C=70 | 16734 / 8388 | 220 / 218 |

F使用设定点间隙，不用样本分位数；T用最高支撑温度层。两方向交叠允许，但各自模型、偏差、q分开。外推方向不以 y 决定。影子模型 M_j 只用 T∩C_j 拟合，输出μ_j、σ_j；**T∩E_j 不得参与 M_j 的拟合或标准化**。最终主模型仍用全部T，不删除边缘训练数据。M_j只用于构造伪外推残差，不直接预测真实外推区的中心。

偏差校正量在已查询的伪留出训练点上估计：

`δ_j = median_{i∈T∩E_j}(y_i − μ_j(x_i))`。

偶数样本中位数取中间两值的算术平均；不截断δ、不强制正号、不乘距离外推倍数。正δ向上平移中心。δ使用训练预算内的标签，CAL9不估计δ；CAL标签只确定q。因此不增加查询预算，也不在同一批CAL残差上同时拟合中心再取分位数。适应性采样仍可能使δ有偏，不能称其无偏估计。

令 `Q90(a_1,…,a_n)=a_(ceil(0.9(n+1)))`，升序、1起始、无插值。实现用整数秩 `ceil(9(n+1)/10)`；要求秩≤n且所有分数有限。三方法：

* **B（全局q基线）**：`q0=Q90({|y−μ|/σ : CAL9})`；各区统一 `[μ−q0σ, μ+q0σ]`。
* **E（方向性伪外推、无中心校正；只报告消融）**：`qE_j=max(q0,Q90({|y−μ_j|/σ_j : CAL9∩E_j}))`；XF用j=F、XT用j=T，中心仍为μ。
* **D（方向性伪外推+中心偏差校正；唯一确认性候选）**：`qD_j=max(q0,Q90({|y−μ_j−δ_j|/σ_j : CAL9∩E_j}))`；XF区间`[μ+δ_F−qD_Fσ, μ+δ_F+qD_Fσ]`，XT同式换T。

G9上 E/D 与 B 完全相同（中心μ、半宽q0σ），因为不需向已知边缘之外迁移。XFT只报告：E中心μ、q=`max(qE_F,qE_T)`；D中心`μ+δ_F+δ_T`、q=`max(qD_F,qD_T)`，半宽均乘最终σ。此加和是冻结的诊断规则，不假定双方向相互作用已建模，不据其结果选择方法。

使用σ归一化残差，但**不增加距离权重、局部核带宽、重要性权重或多候选调参**。q的max下限避免相较q0任意缩窄，不构成覆盖保证。影子模型误差能否迁移到最终模型的真实外推误差，正是待检验假说；伪F最大频率比282/199≈1.42，真实F最大446/282≈1.58，T的伪/真实跨越分别20/20 °C，均不保证损耗残差同分布。

**温度影子模型的秩问题预先披露。** 仅25/50 °C时，1/T/T²列相关；保留已冻结的最小范数OLS解，不改成线性T、正则化或删列。须报告各模型设计矩阵秩、条件数及温度层。此不可辨识性可能损害δ_T/q_T的迁移，失败不触发事后更换模型。

## 5. 输入可行性、标签权限与流程有效性

提交绑定后的无标签检查要求：所有冻结总数/族数吻合；P各六层足够S配额；CAL9∩E_F、CAL9∩E_T各≥20点且≥2族。不得抽到不利划分就重抽。沿用均匀CAL20时，F边缘族数<2的先验组合概率为 `[C(174,20)+46 C(174,19)]/C(220,20)≈0.049805`，不是模拟结果，也不是全部不可行概率；本稿接受这个失败风险以保留基线可比性。

每条轨迹最终还须：各T∩C_j≥30点、≥2个fset；F核心包含25/50/70三层，T核心包含25/50两层；各T∩E_j≥10点。影子点不足视为流程不完整，不改变伪边界、不补标签、不只删除失败组。温度OLS的预期秩亏本身不是数值失败；非有限预测/分数、拟合异常或子集不满足上述输入条件则无确认性结论。

权限顺序：冻结无标签清单及实现 → 完成并封存全部60条采集轨迹、主模型b=0…6、最终两影子模型及δ → 才开放CAL9标签计算所有q → 封存区间与评估输入预测 → 独立评估进程才开放G9/XF/XT/XFT标签 → 封存首次结果 → 独立复算与reviewer_b评审。

权限按(s,k,轨迹,阶段,id)校验。三方法可共享其同一轨迹的已查询标签/模型；影子模型按核心掩码另行拟合。不得跨k或U/S共享标签、拟合缓存、超参数或历史模型，即使id相同也由各自权限独立查询。G/CAL/真留出标签不参与采集、训练、δ、早停、超参数选择；CAL只求预定q。设计计数只读输入，不导入可能触发读数据的旧实验模块。

确认性流程有效要求全部60条轨迹及180区间臂完整、每假设30个有限差值、划分/预算/源文件/模型/种子哈希与采集重放通过、无标签泄漏。一个预定S0处理失败也不能隐去；整轮标“不完整”，不作确认性结论。基础设施故障可记录后同种子同配置同状态恢复；模型失败不能静默换算法/种子。禁止删组、补组、改小K。

## 6. 提交绑定与种子（不填本轮具体H）

**H=`int(预注册提交 SHA 前8位十六进制,16)`。** 预注册提交指用户批准、reviewer_b评审后首次完整包含生效三文件的提交，由主持人在本任务结束后的获授权流程完成；完整SHA/H只写后续运行清单，本稿和配置不填具体值。该提交须早于任何本轮随机集合生成、训练或校准；实现提交不能替换它，不得反复提交搜寻有利种子。本任务不提交/推送；后续远端同步如需进行由主持人获授权安排，不从旧轮推断本次已有授权。

设计种子：`seed(r,k)=2**96 + H*2**16 + r*256 + k`。族排列用(r,k)=(0,0)；每k的S0共同排列用(1,k)，k=1…30。每次独立初始化`numpy.random.default_rng(seed)`，PCG64，版本写清单；保留Python完整整数，不取模、不转uint32。无其他随机抽取，伪划分为输入规则。

GP种子：`gp_seed=2**30 + (H % 2**29)`，范围[1073741824,1610612735]。全部处理、k、批次及影子模型有意共用此种子，每次从头初始化；这是控制优化器随机性，不是额外独立重复。

与全部第六/七/八轮种子核对：R6 H6=3634890171，用H6、H6+k(k=1…8)、H6+100+k；R7 H7=1869701181，用H7、H7+k(k=1…20)、H7+100+k；R6/R7 GP=20261004。R8两个实验全部设计种子为`2**64+H8*2**16+e*4096+r*256+k`（e=1,2，H8=511081239），均小于2**65；R8 GP两值3169646126/3169646127。R9设计种子≥2**96，GP范围也与上述历史整数完全不交。冻结后显式建立历史与本轮种子集合做交集断言；本轮有意共享项按用途登记，不能算碰撞。种子整数不重合不代表样本id互斥或新独立测量。

## 7. 指标、主假设与精确固定顺序

最终b=6为唯一确认性检查点。对区域Z、方法m、处理s、组k，`c=闭区间内点数/n_Z`、`g=max(0,0.90−c)`（90%覆盖欠缺，越小越好）、`w=mean(U−L)`。Winkler为`W=mean((U−L)+20(L−y)1[y<L]+20(y−U)1[y>U])`，log10单位。点在区域内等权、30组等权，不合并XF与XT；g按臂先截断再求均值，不能改成对平均覆盖截断。

下表全部在U处理对同k的D/B配对；`d_k>0`支持备择。每条原假设为E[d_k]≤0，备择E[d_k]>0，T=mean(d_k)。

| 顺序 | 一句话假设（备择） | d_k |
|---|---|---|
| H1 | D较全局q基线B降低XF的90%覆盖欠缺。 | g_B,XF − g_D,XF |
| H2 | D较全局q基线B降低XT的90%覆盖欠缺。 | g_B,XT − g_D,XT |
| H3 | D在XF的期望Winkler满足相对B的10%非劣界。 | 1.10 W_B,XF − W_D,XF |
| H4 | D在XT的期望Winkler满足相对B的10%非劣界。 | 1.10 W_B,XT − W_D,XT |

**H1→H2→H3→H4唯一固定序列，每步α=0.05，p<0.05才拒绝。** 前一步不拒绝即停止，后续标“未检验”；p=0.05不拒绝。可以列后续名义p，但不得恢复正式链条。E消融、S处理、偏差、XFT、S0方差分析均不进入序列。

精确单侧符号翻转：`p=#{s∈{−1,+1}^30: Σs_k d_k ≥ Σd_k−30ε}/2**30`，ε为binary64常量1e-12。包含原始配置、并列、零值的全部重数；整数分子，不加伪计数，不用Monte Carlo，不在检验前十进制舍入d。C03清理同时统一数值契约：以封存binary64 d与ε的精确二进制有理数值计和/比较；转换到共同2幂分母的任意精度整数后做两半2^15有符号和的MITM排序计数。不得因浮点重新结合改变容差边界归属；不分配2^30大向量。K=30以此得到与完整2^30枚举等价的整数分子。

有效p的前提是给定固定数据/划分，独立随机流产生的配对差在零效应边界满足独立符号对称；解释均值≤0的复合原假设还要求对称位置平移模型。H3/H4的前提施加于移位差1.10W_B−W_D，不是交换D/B标签。覆盖欠缺有截断、离散和零值，未保证对称；精确枚举只保证计算精确，不能消除此推断限制。条件FWER≤0.05依赖上述各p有效，不以结果后换检验解决偏态。H3/H4是期望分数非劣，不是等效或逐组比值检验。

## 8. 覆盖门控与有限宽度约束

逐(s,m,Z)报告各项；确认性结论只用U-D。所有30组均进入统计检验，覆盖/宽度门控不删组、不改变p序列。

| 层次 | 冻结条件 |
|---|---|
| 每臂支撑底线C1 | G9覆盖数≥ceil(0.8 n_G9) |
| 每臂V80-F | C1且XF覆盖数≥4289，且w_XF≤3w_G9 |
| 每臂V80-T | C1且XT覆盖数≥6676，且w_XT≤3w_G9 |
| 方法V80(m,Z) | 对应V80通过≥26/30臂 |
| 每臂HONEST90-F/T | XF覆盖数≥4825；XT覆盖数≥7511，分别计数 |
| 方法HONEST90(m,Z) | 对应90%条件通过≥26/30臂；只含覆盖，不混入宽度 |
| 平均覆盖MEAN90(m,Z) | 30臂等权平均c≥0.90；用Σ覆盖数≥ceil(0.9×30×n_Z)判定 |
| 宽度代价WIDTH(m,Z) | mean_k w_m,Z≤1.50 mean_k w_B,Z，且**每一组**w_m,k,Z≤2.00 w_B,k,Z |

V80及HONEST90定义沿用第八轮，≥26/30是经验重复通过门槛，不是置信下界；新增MEAN90避免剩余4臂严重失败被掩盖。MEAN90计数阈值XF=144747、XT=225315。WIDTH的B必须是相同处理、相同k的新基线；两项均直接比较乘积，不除以零宽度。若基线宽度为0，候选仅0宽度可通过对应约束。B自身仍报告实际覆盖与宽度，宽度相对自身约束自然成立。

记 `A(m,Z)=V80∧HONEST90∧MEAN90`，`J(m,Z)=A(m,Z)∧WIDTH(m,Z)`。允许区间输出超过宽度上限，但判该门控失败；**不得裁窄、重新定q或降低δ以“修复”门控**。90%是经验覆盖目标而非过覆盖奖励；平均宽度1.50与逐组2.00是结果前设定的工程容忍度，不由第八轮逐样本结果反推。Winkler的10%界另由H3/H4检验，限制中心误差和宽度的综合代价。

XFT只报覆盖/宽度/Winkler/偏差和欠覆盖分布，不设V80/HONEST通过结论，不用于任何合取门控。不得把30×n点当独立二项样本形成总体90%保证。

## 9. 结论映射（穷尽处理）

先判断流程：不完整/泄漏/无效时全部确认性结论不可作出，只描述带标记的已得结果。流程有效时，正式拒绝指本固定序列中拒绝，名义p不算。

分区结论：`SUCCESS_F = J(U,D,XF) ∧ H1拒绝 ∧ H3拒绝`；`SUCCESS_T = J(U,D,XT) ∧ H2拒绝 ∧ H4拒绝`。两项都成立才能写“双方向达到预注册的、代价受限的经验诚实改进”；只一项成立只写该方向，均不成立不宣称整体成功。由于固定顺序，XT先前失败会阻断H3，届时XF也只能作相应降级描述，不能拆出另一检验家族。

以下分层规则适用于每一区域并覆盖所有组合：

1. A失败：分别列V80/HONEST90/MEAN90失败项，写“未达到完整经验覆盖标准”；即使覆盖欠缺检验拒绝，也仅为欠缺缩小。
2. A通过、WIDTH失败：写“达到覆盖标准，但区间宽度代价超限”，不得称代价受限的诚实成功。
3. J通过、该区覆盖假设未拒绝/未检验：写“达到经验门槛，但未确认相对新基线的欠覆盖改进”，区分未拒绝与未检验。
4. J通过且覆盖假设拒绝，但Winkler假设未拒绝/未检验：写“覆盖欠缺改进且达到门槛，10%综合代价非劣未确认”。
5. J通过且该区两项假设正式拒绝：相应SUCCESS成立；只可声称在本固定评估集/新随机重复上达到这些标准。

独立列B/E/D、U/S的所有经验门控，门控描述不受p序列阻断。B若已达到同样门槛，不得称B“不诚实”；D与B均零欠缺时H1/H2可为p=1，不得据此声称D无价值。E或S即使全部门槛好看也只报告，不替代U-D。未拒绝不证明等效、劣效或无效；经验门槛通过不提供总体/条件/新材料的90%分布无关保证。

## 10. S0问题与其他只报告项

S0分析预先固定主指标为各区 **D的覆盖率c**，在U/S各30组上计算样本方差 `v_s,Z=Σ(c_s,k,D,Z−mean_k c_s,k,D,Z)^2/29`。报告方差比v_S/v_U、降幅ρ=1−v_S/v_U，以及配对欠覆盖差 `Δg_Z=mean_k(g_U,k,D,Z−g_S,k,D,Z)`。

描述性支持判据：v_U>0、v_S≤0.50v_U且Δg≥0，表示“边界均衡S0在该方向至少减半覆盖离散，且平均覆盖欠缺不恶化”。两方向分别判断；两区均满足才写“双方向支持本S0处理可降低离散”。v_U=0时比值/ρ记null、判据记不可评，不加ε；否则不满足就写“未满足该预定支持判据”，不声称S0不影响。列30对原始差、各处理均值/极值，不做额外p检验、重采样或挑选指标。

另在U处理的30×3覆盖率矩阵z_km（m=B/E/D）上逐XF/XT作固定平方和分解：grand=mean z；SS_total=Σ(z−grand)²；SS_group=3Σ_k(mean_m z_km−grand)²；SS_method=30Σ_m(mean_k z_km−grand)²；SS_interaction=Σ(z_km−mean_m z_km−mean_k z_km+grand)²。报告三者/SS_total；SS_total=0则比例为null。SS_group占比≥0.50仅标“共享组分量过半”，无显著性/因果含义；无格内重复，交互与残余不可再分。

所有优化器、族划分及规则固定后，组间变化来自S0及其引起的后续A轨迹；此干预估计的是“S0选择+下游采集”的总影响，不能分离纯S0与采集的中介影响，不能追溯证明第八轮离散原因。S0分解和支持标记均不进入SUCCESS。

另只报告：逐臂c/g/w/W、覆盖计数、90%欠缺、MAE、中心偏差mean(中心−y)、中位相对误差median|10^(中心−y)−1|、q0/qE/qD/δ、影子子集点/族/温度数与矩阵秩；E对D的消融差；XFT全部指标；各假设差的均值/中位数/IQR/正零负个数与名义p；采点按fset、T、v=log10(4fBpk)的池上8等宽档计数，S0与新增分开；实际训练/池极值。validity_pass_counts、sampling_counts使用不同字段。偏差机理只能是假说，不将涡流/趋肤/饱和写成已证实成因。

## 11. 功效与局限

K=30固定，无中期查看或增样。条件于对称配对差，正态近似单侧功效为Φ(δ√30−1.644854)：标准化效应δ=0.4时约0.707、δ=0.6时约0.950。仅作规划量级；覆盖欠缺离散/截断、历史效应选择、固定序列、26/30和宽度合取会降低实际成功机会，本轮未做模拟或用y估计功效。

族相关、单一固定族划分、同一N87数据复用、主动选择导致的偏差样本分布、伪域与真域迁移、温度秩亏均限制结论。区间仍为对称log10区间，可能不能修复异方差/不对称尾部；不因失败临时增添局部权重。S0干预是50%频率边缘的特定政策，不是所有S0策略的结论。无标签可行性检查也可能失败；这是被冻结设计的风险，不提供重抽许可。

## 12. C03代码清理与未来单元测试要求

只登记新实现要求，本任务不写或运行这些测试。不得修改第八轮封存 `magnet8_evaluate.py`。新R9实现不得调用或复制其K≤14的legacy补算分支，也不得调用第六轮旧signflip；统一采用第7节的精确枚举或等价精确MITM契约，正式入口断言K=30。小K只作合成数据验证，不成为正式分析替代路径。

未来在开真实标签前必须验证：K=1…14及K=15/16的合成向量，统一MITM与独立完整2^K枚举整数分子一致；全零p=1、K=30且每个d_k=1.0时分子1、全负p=1、重复/正负并列、含零的2^z重数、负值、大/小尺度及恰在/两侧容差边界；通过二进制有理数整数量化避免平台浮点重结合；非有限、错误形状、正式K≠30拒绝。另测p=0.05不拒绝及停止后的未检验状态、整数覆盖向上取整、有限样本q秩、校正正负号、零宽度门控、S0零方差、伪边缘标签不进影子拟合、CAL不进δ、真实留出绝不进校准。独立复算须重建整数p分子及所有门控/结论，不能只比较打印p小数。

## 13. 执行约束、冻结与不得更改条款

**用户批准之前不运行任何实验；R9p交付不构成运行许可。** 未来只在box执行。最多2个重任务并行（拟合、批量预测、评估、独立重算均计入），每任务单线程，OMP_NUM_THREADS/OPENBLAS_NUM_THREADS/MKL_NUM_THREADS/NUMEXPR_NUM_THREADS均设1。计划60×(7主模型+2影子模型)=540次拟合；三种区间不重复拟合，不追加随机采样臂。

采用nohup setsid启动；看门狗在工作进程组之外，每5秒读MemAvailable。低于3.8 GiB时停止派发并暂停工作进程，高于4.3 GiB才恢复，区间内/等于阈值维持状态。暂停不释放已用内存；持续低内存或OOM记录为基础设施故障后停止，按同状态恢复，不改数据/模型/阈值。状态写 `./ai4s_r9_status.md`。第八轮曾下调阈值是已披露偏离，本轮不自动继承。

主持人未来记录批准、完整预注册SHA/H、三文件及实现哈希、软件版本、历史种子排重、源数据校验；在标签访问前封存排序id、族、S0共同排列/两个S0、伪子集规则、各集合计数及哈希。输入/文本/配置不一致时停止澄清，不能自行选择有利版本。实现缺陷保留首次结果与勘误；**结果后不得更改方法、δ/q公式、边界、假设、顺序、α、容差、门限、K、预算、区域、S0配额、种子或结论映射**。评审前的无结果修订须留记录；冻结后变更只能另立未来预注册，不能追认本轮成功。

| 冻结输入/参考 | SHA256 | 本次核对 |
|---|---|---|
| data/magnet6/features.csv | 781a7048e54bf7c517120b28efa450dbc584192d7faaa6fc4c3c7a2ccf47931c | 输入白名单计数、实算哈希 |
| scripts/magnet6_model.py | b13d4a663df242b91f18853cd0d58333ee892f9a9263ccf39b50bc4d4744109e | 只读源码、实算哈希 |
| scripts/magnet7_design.py | a2bf3774fd1e09c9405faf48107a0f374b22ea9570fe2c68567bbe053174e167 | 只读族/种子规则、实算哈希 |
| data/magnet/igse_predictions.csv | a6814e41af2c0ee3ed6d32611f9ded2a04c60425a5e642476b716acc3c7909b8 | 沿用R8配置，未打开/重算 |
| data/magnet/N87/B.npy | c3fc6db884093554a00464c689975eba0686d27e853003cf9882dcb01058ba96 | 沿用R8配置，未打开/重算 |

三交付文件的SHA256写交付消息及提交后清单，避免自哈希循环。源标签文件的未来完整性校验不授权训练进程读取留出标签。

## 14. 作者与修订记录

本版由 **local_node researcher_a** 撰写，基于 `feat/r9-honest-extrap` / `f9c985f`，日期2026-10-08。参考了用户提供的前次中断探索日志，仅将其中已披露历史材料与输入计数作为参考；本次重新核对关键输入计数，未生成第九轮随机集合或结果。

**reviewer_b评审后修订：待进行。** 本稿不声称reviewer_b已评审；后续修订须记录评审意见、处理及无标签/无结果状态，更新三文件一致性，再由用户批准并由主持人冻结提交。本次未调用子代理，也未修改第一至八轮文件。

=== config_prerun.json ===
{
  "schema_version": "R9p-local_node-researcher_a-1",
  "round": 9,
  "material": "N87",
  "status": "pending_reviewer_b_review_and_user_approval_no_experiment_run",
  "prereg_path": "docs/prereg/M10_magnet_round9_prereg.md",
  "notes_path": "docs/discussion/m10/researcher_a_R9p_notes.md",
  "authorship": {
    "author": "local_node researcher_a",
    "date": "2026-10-08",
    "branch": "feat/r9-honest-extrap",
    "base_commit": "f9c985f",
    "reviewer_b_review": "pending; revise after review, do not claim completed review"
  },
  "scope": {
    "current_task": "Documents/config only; input-only static counts and validation permitted",
    "forbidden_current_actions": [
      "read target CSV or any y-derived data except disclosed historical report summaries",
      "read lab/cases/magnet8/first*/ artifacts",
      "generate random splits, S0 lists or acquisition sequences",
      "write experiment code or run experiments",
      "network access, pip install, git commit, git push",
      "modify any round 1 through 8 files"
    ],
    "confirmatory_candidate": "D under S0 treatment U",
    "acquisition": "A only; no M or R acquisition arms",
    "baseline": "B: rerun R8 E2-A model/acquisition/global scalar q with R9 seeds and split; no historical predictions, q, labels or model cache reused",
    "inference_scope": "Randomization variability conditional on fixed N87 data and one family split; not independent measurements or new material replication"
  },
  "data": {
    "features_csv": "data/magnet6/features.csv",
    "features_sha256": "781a7048e54bf7c517120b28efa450dbc584192d7faaa6fc4c3c7a2ccf47931c",
    "design_columns": ["sample_id", "frequency_Hz", "T_C", "waveform", "amplitude_T", "log10_f", "log10_Bpk", "duty", "plateau", "shape"],
    "ignore_legacy_columns": ["cell", "corner"],
    "target_csv": "data/magnet/igse_predictions.csv",
    "target_column": "measured_W_m3",
    "target_formula": "log10(measured_W_m3)",
    "target_csv_sha256": "a6814e41af2c0ee3ed6d32611f9ded2a04c60425a5e642476b716acc3c7909b8",
    "waveform_npy": "data/magnet/N87/B.npy",
    "waveform_sha256": "c3fc6db884093554a00464c689975eba0686d27e853003cf9882dcb01058ba96",
    "hash_provenance": "features/model/family source hashes verified in R9p; target CSV and B.npy hashes inherited from R8 config without opening or rehashing those files",
    "igse_comparison": false,
    "label_access_order": [
      "after user approval and prereg commit binding: freeze input-only split, S0 and implementation",
      "training: read only local S0 and queried pool labels; complete and seal all 60 trajectories, b=0..6 main models, final shadow models and deltas",
      "calibration: reveal CAL9 only to compute predefined q values; never estimate delta, fit, select or stop",
      "seal q and all evaluation interval predictions",
      "isolated evaluation: reveal G9/XF/XT/XFT labels; no feedback to training/calibration",
      "seal first evaluation; independent recomputation and reviewer_b review"
    ],
    "permission_key": ["s0_treatment", "k", "trajectory", "stage", "sample_id"],
    "sharing": "B/E/D share their own (s,k) queried labels/trajectory/model; each shadow fit gets only its local core subset. No cross-k, cross-U/S or historical label/model/hyperparameter cache even for overlapping IDs."
  },
  "family_definition": {
    "reference": "scripts/magnet7_design.py:family_features and scripts/magnet8_design.py",
    "reference_sha256": "a2bf3774fd1e09c9405faf48107a0f374b22ea9570fe2c68567bbe053174e167",
    "construction_scope": "all input rows before restricting regions",
    "frequency_clustering": "sorted unique frequency_Hz; new cluster when natural log(f_i/f_previous)>0.01",
    "setpoint_formula": "round(median(cluster)/1000) kHz",
    "family_key": "f'{fset}_{waveform}_{round(10*duty)}_{round(20*plateau)}'",
    "rounding": "Python ties-to-even",
    "family_sort": "lexicographic string",
    "id_sort": "numeric integer"
  },
  "regions": {
    "S": {"rule": "fset<300 and T_C<=70", "n": 25122, "families": 220},
    "XF": {"rule": "fset>=300 and T_C<=70", "n": 5361, "families": 69, "confirmatory": true},
    "XT": {"rule": "fset<300 and T_C==90", "n": 8345, "families": 217, "confirmatory": true},
    "XFT": {"rule": "fset>=300 and T_C==90", "n": 1788, "families": 67, "confirmatory": false, "pass_fail_gate": false}
  },
  "expected_design_counts": {
    "total": 40616,
    "unique_ids": 40616,
    "global_families": 291,
    "temperatures_C": [25, 50, 70, 90],
    "frequency_setpoints_kHz": [50, 56, 63, 71, 79, 89, 100, 112, 126, 141, 159, 178, 199, 224, 251, 282, 316, 355, 397, 446],
    "raw_frequency_300000_vs_fset_300_mismatch": 0,
    "high_frequency_union": 7149,
    "T90_union": 10133,
    "support_six_strata": {"core_25": 6766, "core_50": 6766, "core_70": 6785, "edge_25": 1600, "edge_50": 1602, "edge_70": 1603},
    "pool_minimum_over_all_50_family_holdouts": 12892
  },
  "split": {
    "rule_unchanged_from": "R8 E2",
    "number_of_splits": 1,
    "eligible": "sorted 220 families with support rows",
    "permutation": "default_rng(seed(0,0)).permutation(sorted_support_family_keys)",
    "G9_family_slice": [0, 30],
    "CAL9_family_slice": [30, 50],
    "slice_convention": "zero-based half-open",
    "rows": "support rows only in selected families; same-family T=90 remains XT",
    "pool_formula": "P = S minus G9 minus CAL9",
    "pool_family_count": 170,
    "shared_by": "all k, U/S and B/E/D",
    "actual_G_CAL_pool_counts": "undetermined until prereg commit binding; do not substitute R8 counts",
    "redraw_on_failure": false,
    "cal_F_fewer_than_2_families_probability_formula": "(comb(174,20)+46*comb(174,19))/comb(220,20)",
    "cal_F_fewer_than_2_families_probability": 0.04980485381454628
  },
  "design": {
    "K": 30,
    "k_range_inclusive": [1, 30],
    "s0_size": 100,
    "batches": 6,
    "batch_size": 20,
    "additional_labels_per_trajectory": 120,
    "final_training_size": 220,
    "primary_checkpoint": 6,
    "s0_treatments": ["U", "S"],
    "primary_s0_treatment": "U",
    "interval_methods": ["B", "E", "D"],
    "trajectories": 60,
    "interval_arms": 180,
    "main_model_fits": 420,
    "shadow_model_fits": 120,
    "total_model_fits": 540,
    "pairing": "same k and U trajectory for every formal D-vs-B contrast; do not pool U/S or methods as independent repeats",
    "s0_common_order": "pi_k=default_rng(seed(1,k)).permutation(sorted_integer_pool_IDs)",
    "U": "first 100 IDs in pi_k",
    "S": "first quota IDs in each stratum according to relative order in the same pi_k; union has 100 IDs",
    "S_strata": [
      {"fset_rule": "<=199", "T_C": 25, "quota": 16},
      {"fset_rule": "<=199", "T_C": 50, "quota": 17},
      {"fset_rule": "<=199", "T_C": 70, "quota": 17},
      {"fset_rule": "in [224,251,282]", "T_C": 25, "quota": 16},
      {"fset_rule": "in [224,251,282]", "T_C": 50, "quota": 17},
      {"fset_rule": "in [224,251,282]", "T_C": 70, "quota": 17}
    ],
    "sampling": "within trajectory without replacement; overlap across k and U/S allowed; common order couples U/S and independent seed streams separate k"
  },
  "model": {
    "library": "scripts/magnet6_model.py",
    "library_sha256": "b13d4a663df242b91f18853cd0d58333ee892f9a9263ccf39b50bc4d4744109e",
    "reuse_rule": "future isolated R9 adapter; do not mutate old files or use old evaluation_frame/fixed_sequence/signflip; override GP seed only in copied model config",
    "linear_features": ["1", "log10_f", "log10_Bpk", "T_C", "T_C^2", "shape"],
    "ols_solver": "numpy.linalg.lstsq(...,rcond=None), minimum-norm solution",
    "gp_features": ["log10_f", "log10_Bpk", "T_C", "duty", "plateau", "shape"],
    "scaler": "StandardScaler fitted on this model's own training subset only",
    "kernel": "ConstantKernel(1,(0.01,100))*RBF([1]*6,(0.01,100))+WhiteKernel(0.01,(1e-8,10))",
    "gp_alpha": 1e-10,
    "normalize_y": true,
    "gp_optimizer_restarts": 2,
    "gp_random_state": "2**30 + (H % 2**29)",
    "sigma": "predict(return_std=True), includes WhiteKernel; max(std, sigma_floor)",
    "sigma_floor": 2.220446049250313e-16,
    "refit": "from scratch each batch, final model and each shadow model; no warm starts or shared fitted scaler/hyperparameters",
    "temperature_shadow_rank_deficiency": "expected with only 25/50 C and columns 1,T,T^2; retain minimum-norm solver, report rank/condition number; do not replace model after results"
  },
  "acquisition": {
    "strategy": "R8 A sigma kriging believer",
    "candidates": "P minus local already queried IDs",
    "score": "GP predictive sigma including WhiteKernel",
    "ties": "smallest integer sample_id",
    "within_batch": "freeze hyperparameters and y normalization; Cholesky believer updates as frozen model library",
    "label_reveal": "fit 100+20*b queried points for b=0..5; select entire next batch of 20 before revealing its labels; final fit b=6 on 220 points",
    "shared": "B/E/D use exactly the same local acquired T and final model"
  },
  "pseudo_extrapolation": {
    "construction_scope": "support S only; deterministic input masks, never true holdout labels",
    "directions": {
      "F": {"core": "S and fset<=199", "edge": "S and fset in [224,251,282]", "core_n": 20317, "edge_n": 4805, "core_families": 174, "edge_families": 46, "target_region": "XF"},
      "T": {"core": "S and T_C<=50", "edge": "S and T_C==70", "core_n": 16734, "edge_n": 8388, "core_families": 220, "edge_families": 218, "target_region": "XT"}
    },
    "shadow_fit": "M_j trained only on T intersect core_j; outputs mu_j,sigma_j; exclude T intersect edge_j from all fitting/scaling; final main model still uses all T",
    "delta_source": "T intersect edge_j; queried training labels only, no CAL or evaluation labels",
    "delta_formula": "delta_j=median(y_i-mu_j(x_i) for i in T intersect edge_j)",
    "median_even_rule": "arithmetic mean of middle two ordered values",
    "delta_sign": "positive delta shifts center upward",
    "delta_clip": false,
    "delta_distance_multiplier": false,
    "calibration_source": "CAL9 intersect edge_j",
    "transfer": "shadow standardized residual quantiles transferred to main-model sigma in real target region; empirical hypothesis without coverage guarantee",
    "additional_distance_or_importance_weights": false,
    "bandwidth_or_hyperparameter_search": false,
    "shadow_checkpoint": 6
  },
  "intervals": {
    "nominal_coverage": 0.9,
    "Q90_rank_one_based": "ceil(9*(n+1)/10)",
    "Q90_interpolation": "none; ascending order statistic",
    "Q90_validity": "rank<=n and all scores finite",
    "q0": "Q90(abs(y-mu)/sigma on all CAL9)",
    "B": {
      "role": "baseline",
      "G9": {"center": "mu", "q": "q0"},
      "XF": {"center": "mu", "q": "q0"},
      "XT": {"center": "mu", "q": "q0"},
      "XFT": {"center": "mu", "q": "q0"}
    },
    "E": {
      "role": "report-only ablation",
      "qE_j": "max(q0,Q90(abs(y-mu_j)/sigma_j on CAL9 intersect edge_j))",
      "G9": {"center": "mu", "q": "q0"},
      "XF": {"center": "mu", "q": "qE_F"},
      "XT": {"center": "mu", "q": "qE_T"},
      "XFT": {"center": "mu", "q": "max(qE_F,qE_T)"}
    },
    "D": {
      "role": "only confirmatory candidate under U",
      "qD_j": "max(q0,Q90(abs(y-mu_j-delta_j)/sigma_j on CAL9 intersect edge_j))",
      "G9": {"center": "mu", "q": "q0"},
      "XF": {"center": "mu+delta_F", "q": "qD_F"},
      "XT": {"center": "mu+delta_T", "q": "qD_T"},
      "XFT": {"center": "mu+delta_F+delta_T", "q": "max(qD_F,qD_T)"}
    },
    "interval_formula": "[center-q*main_model_sigma, center+q*main_model_sigma]",
    "endpoint_inclusion": "closed",
    "repair_after_gate_failure": false,
    "distribution_free_guarantee_claim": false
  },
  "seeds": {
    "H": "int(first 8 hexadecimal characters of the prereg commit SHA,16)",
    "H_value": null,
    "prereg_commit_SHA": null,
    "design_seed_formula": "2**96 + H*2**16 + r*256 + k",
    "roles": {"family_permutation": {"r": 0, "k": 0}, "s0_common_permutation": {"r": 1, "k": "1..30"}},
    "rng": "numpy.random.default_rng(seed), PCG64; independently initialized per role/k; pin NumPy version",
    "design_seed_integer_policy": "full Python integer; no modulus or uint32 conversion",
    "gp_seed_formula": "2**30 + (H % 2**29)",
    "gp_seed_range_inclusive": [1073741824, 1610612735],
    "intentional_sharing": "same GP seed for all treatments, k, batches and shadow fits; same S0 permutation for U/S and same trajectory for B/E/D",
    "historical": {
      "R6": {"H": 3634890171, "design_formulas": ["H", "H+k for k=1..8", "H+100+k for k=1..8"], "gp_seed": 20261004},
      "R7": {"H": 1869701181, "design_formulas": ["H", "H+k for k=1..20", "H+100+k for k=1..20"], "gp_seed": 20261004},
      "R8": {"H": 511081239, "experiments_e": [1, 2], "design_formula": "2**64 + H*2**16 + e*4096 + r*256 + k", "role_k": [[0, 0], [1, "1..30"], [2, "1..30"]], "gp_seeds": [3169646126, 3169646127]}
    },
    "nonoverlap_proof": "R9 design seeds>=2**96, all R8 E1/E2 design seeds<2**65 and R6/R7 seeds<2**32; R9 GP reserved range excludes all actual R6/R7/R8 design and GP seeds",
    "post_commit_check": "explicit historical and new integer seed sets must have empty intersection; list intentional within-R9 reuse separately",
    "no_seed_grinding": true
  },
  "metrics": {
    "coverage_count": "sum(L_i<=y_i<=U_i)",
    "c": "coverage_count/n_region",
    "g": "max(0,0.90-c), computed per arm before averaging",
    "w": "mean(U-L), log10 units",
    "W": "mean((U-L)+20*(L-y)*I(y<L)+20*(y-U)*I(y>U)), log10 units",
    "bias": "mean(center-y)",
    "MAE": "mean(abs(center-y))",
    "median_relative_error": "median(abs(10**(center-y)-1))",
    "weighting": "equal rows within region; equal 30 pairs; no pooling XF/XT/XFT"
  },
  "tests": {
    "K": 30,
    "treatment": "U",
    "candidate": "D",
    "comparator": "B",
    "order": ["H1", "H2", "H3", "H4"],
    "alpha_each": 0.05,
    "hypotheses": [
      {"id": "H1", "region": "XF", "sentence": "D较全局q基线B降低XF的90%覆盖欠缺。", "d_k": "g_B_XF-g_D_XF", "endpoint": "coverage_shortfall", "direction": "positive"},
      {"id": "H2", "region": "XT", "sentence": "D较全局q基线B降低XT的90%覆盖欠缺。", "d_k": "g_B_XT-g_D_XT", "endpoint": "coverage_shortfall", "direction": "positive"},
      {"id": "H3", "region": "XF", "sentence": "D在XF的期望Winkler满足相对B的10%非劣界。", "d_k": "1.10*W_B_XF-W_D_XF", "endpoint": "winkler_noninferiority", "direction": "positive"},
      {"id": "H4", "region": "XT", "sentence": "D在XT的期望Winkler满足相对B的10%非劣界。", "d_k": "1.10*W_B_XT-W_D_XT", "endpoint": "winkler_noninferiority", "direction": "positive"}
    ],
    "null": "E[d_k]<=0 for each hypothesis",
    "alternative": "E[d_k]>0",
    "statistic": "mean(d_k), K=30 matched pairs",
    "winkler_noninferiority_multiplier": 1.1,
    "p_formula": "count(s in {-1,+1}**30: sum(s*d)>=sum(d)-30*epsilon)/2**30",
    "mean_tolerance_binary64": 1e-12,
    "arithmetic_contract": "d and epsilon are sealed binary64 inputs interpreted as exact binary rationals; convert to common power-of-two denominator, use arbitrary-precision integer sums/comparisons; no rounding of d",
    "implementation": "exact MITM with two 2**15 signed-sum lists and inclusive integer threshold count; exact 2**K enumeration only as oracle, no 2**30 allocation",
    "denominator": 1073741824,
    "include_identity_ties_and_zero_multiplicity": true,
    "monte_carlo": false,
    "pseudocount": false,
    "reject_rule": "p<0.05 and all preceding hypotheses formally rejected; equality is non-rejection",
    "stop_rule": "first non-rejection stops formal sequence; all later statuses not_tested, nominal p report-only",
    "assumptions": "independent paired seed repetitions conditional on fixed data/split; sign symmetry at zero boundary, symmetric location-shift model for composite mean null; applies to shifted NI differences too; discrete truncated coverage differences may violate symmetry",
    "fwer_scope": "<=0.05 only conditional on each p being valid under stated assumptions; exact counting is not assumption-free randomization inference",
    "descriptive_gates_do_not_change_test_sequence": true,
    "drop_failed_gate_pairs": false
  },
  "gates": {
    "scope": "separately for every s,m and Z=XF/XT; confirmatory conclusions only U,D",
    "required_pass_count": 26,
    "K": 30,
    "C1": "coverage_count_G9>=ceil(4*n_G9/5)",
    "V80_per_arm": {
      "XF": "C1 and coverage_count_XF>=4289 and w_XF<=3*w_G9",
      "XT": "C1 and coverage_count_XT>=6676 and w_XT<=3*w_G9"
    },
    "V80_method": "at least 26/30 corresponding per-arm passes",
    "HONEST90_per_arm_min_counts": {"XF": 4825, "XT": 7511},
    "HONEST90_method": "at least 26/30 nominal90 per-arm passes, coverage only",
    "MEAN90": "equal-pair mean c>=0.9, evaluated using integer sum of counts",
    "MEAN90_sum_count_min": {"XF": 144747, "XT": 225315},
    "WIDTH": {
      "mean_width_max_multiple_of_B": 1.5,
      "each_pair_width_max_multiple_of_B": 2.0,
      "each_pair_requirement": "all 30 pairs, not 26/30",
      "comparator": "same s,k fresh B",
      "comparison": "direct <= multiplier*baseline, no division; zero baseline only passes for zero candidate width; no post-gate q/center adjustment"
    },
    "support_width_max_multiple": 3.0,
    "A": "V80 and HONEST90 and MEAN90",
    "J": "A and WIDTH",
    "interpretation": "empirical finite-panel criteria, not confidence bounds or population coverage guarantee",
    "XFT_gate": null
  },
  "validity": {
    "input_preflight": [
      "all frozen input totals, unique IDs, families, temperatures and frequency setpoints match",
      "S/XF/XT/XFT disjoint and exhaustive; G9/CAL9/P family-disjoint within support",
      "all six P strata have at least their S0 quota",
      "each CAL9 intersect pseudo-edge has at least 20 rows and 2 families"
    ],
    "shadow_min_core_rows": 30,
    "shadow_min_core_fsets": 2,
    "shadow_core_temperature_levels": {"F": [25, 50, 70], "T": [25, 50]},
    "delta_min_edge_rows": 10,
    "model_validity": "all fits complete and all predictions, sigmas, deltas, q and differences finite; expected T shadow rank deficiency alone is not failure",
    "process": "all 60 trajectories and 180 interval arms complete, all formal tests have 30 pairs, exact budgets and label permissions audited, source/model/config/seed hashes and acquisition replay pass",
    "failure_policy": "any planned U or S trajectory failure => incomplete round, no confirmatory conclusions; no drop/replacement/redraw/boundary change/budget addition; only logged infrastructure retry with identical seed/config/state"
  },
  "conclusions": {
    "require_process_valid": true,
    "SUCCESS_F": "J(U,D,XF) and formally_rejected(H1) and formally_rejected(H3)",
    "SUCCESS_T": "J(U,D,XT) and formally_rejected(H2) and formally_rejected(H4)",
    "both": "only SUCCESS_F and SUCCESS_T together support both-direction cost-constrained empirical honesty improvement",
    "one": "only name the successful direction; no extrapolation-wide success claim",
    "neither": "no overall success claim",
    "exhaustive_region_hierarchy": [
      {"when": "not process_valid", "interpretation": "incomplete/invalid; no confirmatory claim"},
      {"when": "process_valid and not A", "interpretation": "full empirical coverage standard not met; list failed V80/HONEST90/MEAN90; a rejected coverage test only means smaller shortfall"},
      {"when": "process_valid and A and not WIDTH", "interpretation": "coverage criteria met but width cost exceeded"},
      {"when": "process_valid and J and coverage hypothesis not formally rejected", "interpretation": "empirical criteria met but relative shortfall improvement unconfirmed; distinguish not_rejected/not_tested"},
      {"when": "process_valid and J and coverage hypothesis formally rejected and Winkler hypothesis not formally rejected", "interpretation": "coverage shortfall improved and criteria met; 10 percent score noninferiority unconfirmed"},
      {"when": "process_valid and J and both regional hypotheses formally rejected", "interpretation": "regional SUCCESS under fixed-panel limits"}
    ],
    "special_cases": "B may also be honest; all-zero shortfalls give p=1. E/S are descriptive only even if their gates pass. Non-rejection does not establish equivalence/inferiority. Fixed sequence can block H3 after XT H2 failure; do not split families post hoc."
  },
  "s0_report_only": {
    "method": "D",
    "regions": ["XF", "XT"],
    "primary_metric": "coverage_fraction c",
    "variance": "v_s,Z=sum((c_s,k,D,Z-mean_k(c_s,k,D,Z))**2)/29",
    "variance_ratio": "v_S/v_U if v_U>0 else null",
    "variance_reduction": "1-v_S/v_U if v_U>0 else null",
    "paired_shortfall_change": "Delta_g=mean_k(g_U,k,D,Z-g_S,k,D,Z)",
    "descriptive_support_rule": "v_U>0 and v_S<=0.50*v_U and Delta_g>=0",
    "zero_variance": "v_U==0 => ratio/reduction null, criterion not_evaluable; no epsilon substitution",
    "both_direction_support": "both region rules pass; otherwise report each region separately",
    "no_formal_p_or_bootstrap": true,
    "variance_decomposition": {
      "matrix": "U treatment coverage z_km with k=1..30 and m=B,E,D, separately XF/XT",
      "grand": "mean(z)",
      "SS_total": "sum_km((z_km-grand)**2)",
      "SS_group": "3*sum_k((mean_m(z_km)-grand)**2)",
      "SS_method": "30*sum_m((mean_k(z_km)-grand)**2)",
      "SS_interaction": "sum_km((z_km-mean_m(z_km)-mean_k(z_km)+grand)**2)",
      "fractions": "each component/SS_total, null if SS_total==0",
      "group_majority_flag": "SS_total>0 and SS_group/SS_total>=0.50; descriptive only",
      "limitation": "no within-cell repetition; interaction and residual cannot be separated"
    },
    "interpretation": "S0-policy plus downstream acquisition total effect; no isolation of pure S0 from its mediated sampling effect, no retrospective causal proof about R8"
  },
  "report_only": [
    "all s,m,k,regions final c/g/w/W, coverage counts, nominal90 shortfall, MAE, bias, median relative error and gate components; full per-arm minima/maxima",
    "all q0/qE/qD/delta, shadow/core/edge/calibration counts and families, design matrix ranks/condition numbers and temperature levels",
    "E-vs-D ablation and all S treatment outputs; never promote to confirmatory after results",
    "XFT scores and distributions only, no pass/fail or formal test",
    "each hypothesis d mean/median/IQR and positive/zero/negative counts; nominal p with fixed-sequence status",
    "sampling by fset, temperature and 8 equal-width bins of v=log10(4*f*Bpk) over entire P; clip(floor(8*(v-lo)/(hi-lo)),0,7), require hi>lo; S0 separated from additions",
    "realized pool/training extrema; validity_pass_counts separate from sampling_counts",
    "S0 variance policy contrast, decomposition and prespecified descriptive support flags; no extra formal hypotheses"
  ],
  "power_and_limits": {
    "simulation_performed": false,
    "planning_formula": "Phi(delta*sqrt(30)-1.644854)",
    "approximate_power_scenarios": [{"delta": 0.4, "power": 0.707}, {"delta": 0.6, "power": 0.95}],
    "caveat": "not exact sign-flip power or power of gated success; discrete shortfall, symmetry, multiplicity gate, validity and width constraints limit interpretation",
    "limitations": ["single reused N87 dataset and one family split", "family correlation and adaptive selection", "pseudo-to-real residual transfer unproven", "two-temperature OLS rank deficiency", "symmetric log10 intervals", "specific 50-percent frequency-edge S0 policy", "input-only feasibility can fail without redraw"]
  },
  "C03_future_implementation_requirements": {
    "do_not_modify": "scripts/magnet8_evaluate.py or any round 1 through 8 file",
    "remove": "no copied/called K<=14 legacy floating-point correction branch; no old magnet6 signflip",
    "retain": "one exact enumeration/MITM arithmetic contract for all validation K; formal entry requires K=30",
    "unit_tests_before_real_labels": [
      "K=1..14 plus 15 and 16 synthetic vectors: MITM integer numerator equals independent exhaustive 2**K oracle",
      "all zeros p=1; K=30 and every d_k=1.0 has numerator=1; all negatives p=1",
      "duplicates, mixed signs, exact ties, zeros with 2**z multiplicity, small/large scales",
      "exact and either-side epsilon threshold examples using binary-rational integer arithmetic; no float reassociation exceptions",
      "reject NaN/Inf/wrong shapes and formal K!=30",
      "p==0.05 non-rejection; fixed sequence stops and never resumes",
      "integer coverage ceilings, Q90 finite rank, bias correction sign, zero width baseline, zero S0 variance",
      "shadow edge labels excluded from shadow fit; CAL excluded from delta; true holdouts excluded from all calibration"
    ],
    "independent_recompute": "rebuild integer p numerators, metrics, validity_pass_counts, every gate and conclusions; decimal p agreement alone insufficient",
    "current_task_tests_written_or_run": false
  },
  "execution": {
    "user_approval_required_before_any_experiment": true,
    "prereg_commit_binding_required_before_random_generation": true,
    "host": "local_node only",
    "max_parallel_heavy_jobs": 2,
    "heavy_jobs_include": ["fitting", "batch prediction", "evaluation", "independent recomputation"],
    "threads_per_job": 1,
    "thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
    "launch": "nohup setsid; watchdog outside paused worker process groups",
    "watchdog": {
      "metric": "MemAvailable",
      "poll_seconds": 5,
      "pause_below_GiB": 3.8,
      "resume_above_GiB": 4.3,
      "hysteresis": "between thresholds or at equality retain state",
      "action": "stop dispatch and pause workers below low threshold; resume above high threshold; pausing does not reclaim memory; persistent low memory/OOM => logged infrastructure stop, identical seed/config/state resume; no threshold/data/model changes"
    },
    "status_path": "./ai4s_r9_status.md",
    "preserve_first_outputs_and_errata": true
  },
  "freeze": {
    "commit_rule": "first commit containing all three effective reviewed documents/config after user approval, before any R9 random generation/training/calibration; moderator commits in a separately authorized later task",
    "no_current_commit_or_push": true,
    "no_substitute_implementation_HEAD": true,
    "manifest": ["approval", "full prereg SHA and H", "three deliverable hashes", "implementation hashes and software versions", "source checks", "historical/new seed disjointness", "sorted IDs, families, common permutations, U/S S0s, pseudo masks/counts and hashes"],
    "conflict_rule": "stop before labels if prereg/config/input assertions conflict; do not choose favorable interpretation",
    "post_results_immutable": ["methods", "delta/q formulas", "pseudo boundaries", "hypotheses", "order", "alpha", "tolerance", "thresholds", "K", "budgets", "regions", "S0 quotas", "seeds", "conclusion mapping"],
    "revision_policy": "record reviewer_b comments and all pre-result revisions; frozen changes require a new future preregistration, not retroactive success",
    "self_hash_policy": "deliverable SHA256 values in handoff and later manifest, no circular self hashes"
  }
}
