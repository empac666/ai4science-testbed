# 里程碑 3 交叉评审报告（MagNet iGSE 基线 + DC-link 代理模型第二轮）

本评审为独立只读交叉评审。评审过程中未修改任何文件，未启动任何新扫描，关键数学公式与数据统计均经由轻量 Python 脚本进行了独立重算与验证。

---

## 逐条评审意见

### 1. iGSE 实现
**评审结论：同意**

**依据与具体分析：**
1. **$k_i$ 公式实现**：
   在 [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L28-L31) 中，[`ki_from_steinmetz`](file://./scripts/magnet_igse.py#L28) 采用：
   $$k_i = \frac{k}{(2\pi)^{\alpha-1} 2^{\beta-\alpha} \int_0^{2\pi}|\cos\theta|^\alpha d\theta}$$
   代码中使用 `2 * scipy.special.beta(0.5, (alpha + 1) / 2)` 解析计算 $\int_0^{2\pi}|\cos\theta|^\alpha d\theta$。经数值积分检验（分别在 $\alpha \in \{1.2, 1.5, 1.8, 2.0\}$ 测试），该 Beta 函数闭式解与数值积分的差值小于 $10^{-11}$。公式与 Venkatachalam 等人原论文（IEEE COMPEL 2002，DOI: 10.1109/CIPE.2002.1196712）式 (10) 完全一致。
2. **$\Delta B$ 取法**：
   在 [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L36) 中，`delta = np.ptp(b, axis=-1)`，即 $\Delta B = \max(B) - \min(B)$。对于无局部回线（minor hysteresis loops）的单调半周期激励，全局峰峰值取法完全准确。代码在正弦波检验中，`igse` 与 Steinmetz 解析损耗的相对误差仅为 $2.3 \times 10^{-6}$（源自 1024 点折线离散化误差）。
3. **积分离散化**：
   在 [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L37-L38) 中：
   `slopes = np.abs(np.roll(b, -1, axis=-1) - b) * b.shape[-1] * frequency`
   因为数据为一个完整周期且不重复首末点，前向周期差分 `np.roll(b, -1) - b` 严格闭合末点到首点的区间。在分段线性插值下，每一小段导数恒定，折线积分退化为对斜率 $\alpha$ 次幂的均值计算，属于解析积分，无梯形数值近似误差。
4. **按温度分组拟合 Steinmetz 参数**：
   在 [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L126-L129) 和 [`docs/reports/M3_magnet.md`](file://./docs/reports/M3_magnet.md#L18-L21) 中，分别对 25 ℃、50 ℃、70 ℃、90 ℃ 拟合独立参数：
   - 25 ℃: $\alpha = 1.366, \beta = 2.586, k = 10.28$
   - 50 ℃: $\alpha = 1.556, \beta = 2.588, k = 0.762$
   - 70 ℃: $\alpha = 1.720, \beta = 2.610, k = 0.097$
   - 90 ℃: $\alpha = 1.976, \beta = 2.604, k = 0.0039$
   铁氧体材料（如 N87）的损耗随温度呈非线性变化（通常在 80~100 ℃ 存在损耗谷底），经典 Steinmetz 公式本身不包含温度变量。按离散测量温度分层拟合能够充分解耦温度对损耗机制的影响，比全温强行拟合单套参数在物理上更加合理。

---

### 2. 波形分类规则
**评审结论：部分同意**

**依据与具体分析：**
1. **规则分类的可靠性（同意部分）**：
   在官方未提供波形标注的前提下，利用 $B(t)$ 的频域与时域特征构建确定性规则是唯一可行的无监督方案。在 [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L40-L54) 中：
   - 正弦判据：去均值后投影到一阶正交正弦基，能量残差 $\le 0.05$ 判为正弦（1,426 条）。
   - 梯形判据：平台点（差分绝对值 $< 0.1 \times p90$ 差分）占比 $\ge 0.05$ 判为梯形（6,104 条）。
   - 三角类判据：其余波形（33,086 条）。
   该规则不依赖实测损耗标签，保证了特征提取与基线评估的无偏性。
2. **多段斜率混入三角类对误差统计的扭曲（不同意/风险部分）**：
   - 数据集中 81.5%（33,086 条）的样本被归入"三角类"。抽检记录 [`lab/cases/magnet/classification_audit_review.csv`](file://./lab/cases/magnet/classification_audit_review.csv#L14-L25) 明确指出三角类包含大量"无明显平台的多段斜率波形"（如多电平逆变器阶梯激励产生的多段折线波）。
   - 传统 iGSE 在经典理想两段斜率三角波下具有极高精度；但在多段斜率或非单调振荡波形下，如果不做主/次回线分解（minor hysteresis loops relaxation），全局峰峰值取法会导致不可忽视的模型失真。
   - 结果中三角类的 $p95$ 绝对误差高达 47.09%（[`lab/cases/magnet/igse_metrics.json`](file://./lab/cases/magnet/igse_metrics.json#L75)），直接将所有多段斜率复杂波形通称为"三角类"，严重扭曲了读者对经典三角波 iGSE 预测能力的认知。

---

### 3. MagNet 结论
**评审结论：同意**

**依据与具体分析：**
1. **数据许可**：
   在 [`docs/reports/M3_magnet_provenance.md`](file://./docs/reports/M3_magnet_provenance.md#L7-L17) 中，逐字核对了 Princeton MagNet Library 页面、代码仓库 LICENSE、比赛仓库 README 及参赛手册。明确澄清了"MIT 仅适用于代码仓库本身，官方并未对托管的测量数据授予 MIT 许可"，并建议仅作科研使用、禁止原始数据直接分发（已加入 `.gitignore`）。结论实事求是，破除了此前社区常见的"数据即代码同属 MIT"的误解。
2. **数据规模**：
   报告在 [`docs/reports/M3_magnet.md`](file://./docs/reports/M3_magnet.md#L5-L7) 中严格区分了全库材料数（15 种，29.31 GB）与预训练包材料数（10 种，3.14 GB），确认本次使用的实际 N87 预训练样本数为 40,616 条（每条 1,024 点），校验了外层 ZIP 大小（683,282,735 字节）及 SHA256。拒绝引用未获一手核实的"142,871 组"或"电力电子 ImageNet"等二手宣传口径，表述克制。
3. **误差表述**：
   指标与数值完全基于留出评估集（39,903 条），未与训练集混淆。报告诚实列出了全部温度与波形分项指标（[`docs/reports/M3_magnet.md`](file://./docs/reports/M3_magnet.md#L31-L47)），并在局限性（第 73-77 行）中坦白指出了未实现次回线分解、数值微分放大测量噪声等局限，无任何夸大。

---

### 4. 第二轮执行与预注册是否一致
**评审结论：同意**

**依据与具体分析：**
1. **Design 与划分**：
   - 预注册文件 [`docs/prereg/M3_surrogate_round2_prereg.md`](file://./docs/prereg/M3_surrogate_round2_prereg.md#L8-L24) 于 commit `ffd7c9f`（2026-10-02 23:27）提交。
   - 随后的扫描设计与划分清单在运行全量扫描前冻结并提交于 commit `c167ecc`（2026-10-03 00:10），其 SHA256 为：
     - Design: `042113d489ebdd00afab37ae3b0202665fbc45704bd175cb409786a4c5b1de7d`
     - Split: `cfeba53e86b52ee9f1ee5cc584c48e1331f8b8850a101546abec00813437d0ed`
   - 各集合样本数：train=200（第一轮分布内样本）、calib=75、test=75、ood_dt3=30、ood_corner=30、supplement_ood=40（第一轮 OOD 样本，仅留作观察不参与训练和判据），与预注册严格一致。
2. **M0–M5 定义**：
   [`scripts/dclink_surrogate2.py`](file://./scripts/dclink_surrogate2.py#L32-L37) 中，M2 的均值方程严格采用 reviewer_b 预注册特征（常数项、死区时间项 $t_{dead} f_c$、负载项 $load$、滤波带宽倒数项 $f_{grid}/bw_{iac}$、孔径延迟项 $4\pi f_{grid} t_{ap}$），残差 GP 参数与第一轮一致，M0/M1/M3/M4/M5 实现均完全吻合。
3. **C1/C2 计算**：
   在 [`scripts/dclink_surrogate2.py`](file://./scripts/dclink_surrogate2.py#L47-L61) 中，分位数取第 69 个顺序统计量（$\lceil 76 \times 0.9 \rceil = 69$），C1 门限为 62/75，C2 门限为覆盖数 $\ge 24/30$ 且宽度 $\le 3 \times test$。计算逻辑分毫不差。
4. **是否存在事后调整**：
   Git 历史清晰显示：预注册和设计冻结先于执行，第一次执行产物完整封存于 [`lab/cases/dclink2/first/`](file://./lab/cases/dclink2/first/)，哈希逐位匹配。尽管 C2-corner 仅差 4 例未过（20/30 vs 24/30），团队完全没有事后放宽 $q$ 或调整 OOD 划分，如实宣告了预注册"不通过"。

---

### 5. 第二轮判定结果
**评审结论：同意**

**依据与具体分析：**
1. **数据事实与判定结果**：
   根据 [`lab/cases/dclink2/surrogate_metrics.json`](file://./lab/cases/dclink2/surrogate_metrics.json#L70-L86)：
   - **C1**（分布内 test）：覆盖 74/75（98.7% $\ge$ 82.7%），平均宽度 0.640，**通过**。
   - **C2-dt3**（死区 OOD）：覆盖 29/30（96.7% $\ge$ 80.0%），平均宽度 0.815（为 test 的 1.27 倍 $\le$ 3.0 倍），**通过**。
   - **C2-corner**（低载低带宽角落 OOD）：覆盖 20/30（66.7% $<$ 80.0%），平均宽度 0.953（为 test 的 1.49 倍 $\le$ 3.0 倍），**未通过**。
   - **总判定：不通过**。
2. **σ 归一化保形在 OOD 上的表现与成败机理**：
   - **E-dt3 为何成功**：死区时间从 $[0, 2.5]\,\mu\mathrm{s}$ 外推到 $3.0\,\mu\mathrm{s}$ 属于平滑的 1D 外推。物理上死区效应引起的波形畸变与死区时间高度线性，M2 的解析项 $\beta_1 t_{dead} f_c$ 成功捕捉了该趋势（MAE 仅为 0.1024，与分布内的 0.0846 相当）；GP 残差不确定度 $\sigma$ 自适应增大 27%（均值从 0.1313 升至 0.1672），区间宽度自适应放宽至 0.8152，足以覆盖残差尾部。
   - **E-corner 为何失败**：轻载（$0.30 \le load \le 0.35$）与低带宽（$50 \le bw \le 75\,\mathrm{kHz}$）的耦合处在严重非线性调制区。M2 的解析模型仅包含独立的加性主效应，缺少关键的乘积交互项（如 $(f_{grid}/bw)/load$），导致点预测出现明显系统性负偏差（$\mathrm{bias} = -0.1615$，最大误差高达 0.9945，MAE 从 0.085 骤升至 0.3203）。同时，由于角落区域紧贴训练集边缘，在标准化输入空间中的欧氏距离不足以让 RBF 核的方差 $\sigma$ 充分放大（平均 $\sigma$ 仅从 0.1313 增至 0.1954，仅增 1.49 倍）。角落区域的归一化残差第 90 百分位高达 3.875，远超校准阈值 $q=2.437$，导致 10 个样本逸出区间，最终覆盖率仅 66.7%。
   - **M2 与 M1 的对比反思**：M2 因在线性项吸收了部分方差，在分布内残差更小，导致校准分位数 $q$ 较 M1 收窄（2.437 vs 2.697），在角落处的区间宽度也更窄（0.953 vs 1.063）。这使得 M2 虽然点预测 MAE 略优于 M1（0.320 vs 0.339），但在极端角落的保形覆盖数反而比 M1 少 3 例（20/30 vs 23/30）。报告中"点预测改善与区间覆盖并非同步"的解释完全成立。

---

### 6. 非理想传感器对照组的结论
**评审结论：同意**

**依据与具体分析：**
1. **实验对照的严谨性**：
   对照组在相同 210 个参数点上开启 `SensorConfig(ideal=False)`，引入真实传感器高斯噪声与增益漂移，每例采用独立确定性种子（`20261004 + i`）。配对差值 $|y_{nonideal} - y_{ideal}|$ 均值为 0.2324，中位数 0.1889，最大值 1.1789（[`docs/reports/M3_dclink_round2_researcher_a.md`](file://./docs/reports/M3_dclink_round2_researcher_a.md#L61)）。
2. **结论的理论与数据支撑**：
   - 沿用理想仿真数据拟合与校准的 M2 模型在非理想传感器数据上评估时，由于输入参数未变，模型给出的区间宽度完全相同（分布内平均半宽约 0.320）。
   - 传感器噪声带来的扰动量（$p90 = 0.4864$）直接与区间半宽处于同一数量级，导致数据违背了保形推断的核心前提——**可交换性（Exchangeability）**。
   - 结果显示，M2 在分布内 test 上的覆盖率从 98.7% 骤跌至 69.3%，calib 跌至 58.7%，角落 OOD 跌至 53.3%（[`lab/cases/dclink2/surrogate_metrics.json`](file://./lab/cases/dclink2/surrogate_metrics.json#L92-L113)）。
   - 该对照组实验严格遵循预注册中"只报告、不判定"的要求，有力证明了：**未建模传感器噪声域漂移会使纯仿真校准的保形区间迅速失效**。该结论完全站得住。

---

### 7. 图
**评审结论：部分同意**

**依据与具体分析：**
1. **中文显示（同意）**：
   所有四张图片（[`m3_igse_error.png`](file://./docs/figures/m3_igse_error.png)、[`m3_igse_scatter.png`](file://./docs/figures/m3_igse_scatter.png)、[`m3_round2_methods.png`](file://./docs/figures/m3_round2_methods.png)、[`m3_round2_nonideal.png`](file://./docs/figures/m3_round2_nonideal.png)）均通过 `fontManager.addfont` 正确载入了 `NotoSansCJK-Regular.ttc`。经直接查看图片文件，中文标题、坐标轴标签、图例均正常渲染，无任何乱码、豆腐块（口口）或文字重叠问题。
2. **潜在视觉误导（不同意/需修正部分）**：
   - **`m3_round2_nonideal.png` 右图存在严重视觉错觉**：
     在 [`scripts/dclink_figures2.py`](file://./scripts/dclink_figures2.py#L49-L53) 中，代码将理想组偏移设为 `-0.15`，非理想组偏移设为 `+0.15`，并使用虚线折线将离散组别的区间宽度相连（`width_ax.plot(pos + offset, width, 'o--')`）。
     事实上，由于非理想数据与理想数据使用完全相同的输入参数，**M2 在两组上的区间宽度在数值上 100% 恒等**（test 均为 0.640，dt3 均为 0.815，corner 均为 0.953）。
     然而，因为折线整体呈上升趋势（0.64 $\to$ 0.815 $\to$ 0.953），橙色（非理想）折线因横向右移 0.3 个单位，**在视觉上整体被压在蓝色（理想）折线的正下方**！这极易使读者产生"非理想传感器的区间宽度变窄了"的虚假错觉。
   - **`m3_round2_methods.png` 右图动态范围失调**：
     该图将解析模型 M3（宽度 7.54）和 M5（宽度 9.04）与高精度模型 M0~M2（宽度 0.64~1.06）共用线性 y 轴，导致 y 轴上限拉伸至 28。核心比较对象 M0、M1、M2 在分布内及 OOD 上的自适应宽度拉伸细节在图底被压缩成扁平薄条，严重损害了图表的可读性。

---

### 8. 其他：发现的 Bug 或可疑之处

1. **MagNet 分类器平台阈值设置存在结构性逻辑漏洞（Bug）**：
   在 [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L51-L53) 中：
   ```python
   slope = np.abs(np.roll(b, -1, axis=1) - b)
   plateau = np.mean(slope < .1 * np.quantile(slope, .9, axis=1)[:, None], axis=1)
   labels = np.where(residual <= .05, 'sine', np.where(plateau >= .05, 'trapezoid', 'triangle'))
   ```
   - 经数值验证，对于**纯理论正弦波**，波峰与波谷处的自然平缓区域满足上述导数条件的比例为 **0.0625（6.25%）**。
   - 代码所设定的梯形波门限为 `plateau >= 0.05`（5.0%），**该阈值竟然低于理想正弦波自身的波峰自然平缓比例**！
   - 目前没有发生大规模正弦误判为梯形，完全依赖于外层 `residual <= 0.05` 这一前置条件的拦截。一旦某个正弦波存在 5.1% 的畸变（`residual = 0.051`），它不会被划为三角类或失真正弦，而是会**瞬间被误判为梯形波（trapezoid）**！这也是 [`lab/cases/magnet/data_card.md`](file://./lab/cases/magnet/data_card.md#L48) 中提及此前阈值设为 0.02 时失真正弦被大面积误判的根本原因。该平台率阈值定义存在结构性脆弱缺陷。
2. **梯形波系统性负偏差的物理机理未在报告中解释**：
   在 [`docs/reports/M3_magnet.md`](file://./docs/reports/M3_magnet.md#L43-L47) 中，梯形波在所有温度下的有符号相对误差中位数均为负数（-10.6% ~ -13.5%）。物理上，梯形波在平顶区导数为零，传统 iGSE 计算出的平顶损耗为零，忽略了磁滞弛豫与粘滞损耗，导致经典 iGSE 对梯形波普遍存在系统性低估。报告忠实记录了负偏差数据，但正文中未对这一经典物理缺陷做出阐述。

---

## 分歧清单

| 编号 | 主张 | 依据 | 建议处理 |
|---|---|---|---|
| D-06 | 拒绝将所有非平台复杂波形泛称为"三角类"，当前分类会扭曲标准三角波的 iGSE 误差统计 | [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L53) 将所有非正弦且平台 $< 5\%$ 的波形（占 81.5%）全归为三角类；[`lab/cases/magnet/classification_audit_review.csv`](file://./lab/cases/magnet/classification_audit_review.csv#L14) 显示其中大量为多段斜率阶梯波；三角类 $p95$ 误差高达 47.09% | 在 [`docs/reports/M3_magnet.md`](file://./docs/reports/M3_magnet.md) 表头及正文中将"三角类"明确改称为"广义三角/多段斜率类"或"残余非平台类"，并在报告中注明该组性能不能代表经典两段斜率对称三角波 |
| D-07 | `m3_round2_nonideal.png` 右图存在视觉误导，虚线平移给人以非理想传感器宽度缩窄的错觉 | [`scripts/dclink_figures2.py`](file://./scripts/dclink_figures2.py#L49-L53)；数学上同一参数点下理想与非理想传感器输入的 M2 区间宽度 100% 恒等（test 均为 0.640，dt3 均为 0.815，corner 均为 0.953），但因施加了 $\pm 0.15$ 水平偏移并画了正斜率折线，使橙线整体落在蓝线下方 | 修改绘图脚本：移除横跨类别组的虚线连线；对宽度采用单一点标记或重合误差线，并明确标注"输入点相同，区间宽度严格相等" |
| D-08 | 波形分类器中的平台阈值（0.05）低于理想正弦波自身的峰值平缓比例（0.0625），存在分类判定倒挂风险 | [`scripts/magnet_igse.py`](file://./scripts/magnet_igse.py#L51-L53)；理想正弦波在定义下的平缓比例为 6.25%；轻微失真（残差 $> 0.05$）的平滑波形会被直接错判为梯形波 | 在平台判据中增加连续点平顶约束（要求连续 $M$ 个采样点导数接近 0），或将无量纲平缓阈值提升至 $12\% \sim 15\%$，使其舒适地高于正弦转折点的自然比例 |
| D-09 | `m3_round2_methods.png` 右图线性 y 轴范围过大（达 28），掩盖了高精度模型之间的宽度自适应差异 | [`scripts/dclink_figures2.py`](file://./scripts/dclink_figures2.py#L31-L35)；M3（7.54）和 M5（9.04）拉伸了整体坐标系，使 M0~M2 在 0.6~1.0 之间的细微扩展在图上几乎无法分辨 | 采用对数 y 轴（log scale），或使用断轴（broken axis）/双面板，将低精度解析模型与高精度代理模型分轴呈现 |
