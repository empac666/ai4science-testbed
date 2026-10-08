# 交叉评审报告：里程碑 2（DC-link 代理模型与保形区间）

**评审人**：独立交叉评审员（reviewer_b）<br>
**评审对象**：researcher_a 实现代码、技术报告及主持人预注册设计<br>
**基准数据依据**：入库持久化归档目录 `lab/cases/dclink/`<br>
**约束遵守**：本评审全过程只读，未修改任何仓库文件，未运行大规模扫描。

---

## 逐条评审意见

### 1. split conformal 实现与主判据计算
- **结论**：**同意**
- **依据与分析**：
  1. **分位数与有限样本修正**：
     在 [`scripts/dclink_surrogate.py` 第 67-74 行](file://./scripts/dclink_surrogate.py#L67-L74) 的 [`conformal_quantile`](file://./scripts/dclink_surrogate.py#L67-L74) 中，秩次计算采用：
     $$\text{rank} = \lceil (n+1)(1-\alpha) \rceil$$
     当校准集 $n=40, \alpha=0.1$ 时，$\lceil 41 \times 0.9 \rceil = \lceil 36.9 \rceil = 37$。代码排序后取索引 `rank - 1 = 36`（即第 37 个顺序统计量），并在 `rank > len(scores)` 时正确返回 `inf`。这与保形预测经典文献（Vovk / Lei et al. / Angelopoulos & Bates）及预注册 [`docs/prereg/M2_prereg.md` 第 17 行](file://./docs/prereg/M2_prereg.md#L17) 的数学定义完全一致。
     [`tests/test_dclink_surrogate.py` 第 25-30 行](file://./tests/test_dclink_surrogate.py#L25-L30) 对 $n=9$ 取 9、$n=40$ 取 37 以及越界返回无穷大均给出了针对性单元测试。
  2. **主判据计算**：
     在 [`scripts/dclink_surrogate.py` 第 166 行](file://./scripts/dclink_surrogate.py#L166)，主判据为：
     `metrics['criterion.gp_ood_coverage_in_85_95'] = bool(0.85 <= metrics['gp_conformal.ood.coverage'] <= 0.95)`。
     实测 `gp_conformal.ood.coverage` 为 `0.400000`（16/40 覆盖），入库指标 [`lab/cases/dclink/surrogate_metrics.json` 第 151 行](file://./lab/cases/dclink/surrogate_metrics.json#L151) 记录为 `false`，判定计算完全正确，且严格遵守了“主判据仅指 GP 标准绝对残差保形，不使用归一化保形”的预注册约束。

---

### 2. 数据泄漏检查
- **结论**：**同意**
- **依据与分析**：
  1. **特征标准化**：[`scripts/dclink_surrogate.py` 第 134 行](file://./scripts/dclink_surrogate.py#L134) 严格使用 `StandardScaler().fit(x[train])`，测试集和校准集仅执行 `transform`。
  2. **超参数与模型拟合**：
     - GP 模型在 [`scripts/dclink_surrogate.py` 第 137 行](file://./scripts/dclink_surrogate.py#L137) 仅拟合 `(z[train], y[train])`；初始核超参数与边界全部在 `CONFIG` 常量中预先硬编码，未在看到测试结果后调优。
     - MLP 模型在 [`scripts/dclink_surrogate.py` 第 140-144 行](file://./scripts/dclink_surrogate.py#L140-L144) 显式设定 `early_stopping=False`，防止内部自动从训练集划分验证集引发泄漏。
     - `load_interp` 的分箱中心与均值仅在 `train` 上统计（第 123-130 行）；`analytic` 最小二乘求解仅输入 `(a[train], y[train])`（第 132 行）。
  3. **校准集完全隔离**：`calib` 索引仅出现在 [`scripts/dclink_surrogate.py` 第 149-155 行](file://./scripts/dclink_surrogate.py#L149-L155) 的残差评估与保形分位数提取阶段，未参与任何参数拟合。
  4. **划分本身无标签泄漏**：[`scripts/dclink_split.py` 第 11-24 行](file://./scripts/dclink_split.py#L11-L24) 仅基于输入网格特征划分，不读取目标值 $y$；各子集完全不相交且并集等于完整设计（240 例）。

---

### 3. 解析模型与物理特征合理性
- **结论**：**部分同意**
- **依据与分析**：
  - **同意的部分**：
    researcher_a 选取的三个特征在小扰动物理机理上均有根据，抓住了 CHB 电容估计的主要非理想源，严格遵从了任务提示词 [`docs/discussion/m2/prompt_researcher_a_M2.md` 第 22 行](file://./docs/discussion/m2/prompt_researcher_a_M2.md#L22) 的指导，且未偷看 $y$：
    1. 死区效应引起每个开关周期的伏秒缺失比例 $\propto t_{\text{dead}} f_c$；
    2. 前端交流采样一阶低通滤波在基波处的群延迟与相移 $\Delta\theta \propto f_{\text{grid}} / bw_{\text{iac}}$；
    3. 孔径延迟时间对应采样点偏移 $\Delta\theta \propto t_{\text{aperture}} f_c$。
  - **不同意与存在缺陷的部分**：
    1. **死区特征除以负载导致低载外推发散**：researcher_a 将死区特征构造成 $t_{\text{dead}} f_c / \text{load}$（[`scripts/dclink_surrogate.py` 第 79 行](file://./scripts/dclink_surrogate.py#L79)），却**没有包含独立的 load 线性项**。当外推到死区 3.0 µs 且处于低负载（0.3~0.35）时，该项呈现 $1/\text{load}$ 的双曲线非物理爆炸。这导致解析模型在 OOD 上的 $R^2$ 崩塌至 $-0.185$，OOD MAE 高达 2.923（[`lab/cases/dclink/surrogate_metrics.json` 第 38 行](file://./lab/cases/dclink/surrogate_metrics.json#L38)）。
    2. **孔径延迟与二倍工频的物理对应性不够严谨**：固件算法（[`data/dclink_src/fw/src/dclink_cap_est.c` 第 160-164 行](file://./data/dclink_src/fw/src/dclink_cap_est.c#L160-L164)）计算电容是提取直流母线电容上的**二倍工频（100 Hz）阻抗**。因此孔径时间延迟引起的电角度误差本质是 $\Delta\theta = 4\pi f_{\text{grid}} t_{\text{aperture}}$，将其归一化到载波频率 $f_c$（10 kHz）虽然是线性变换，但物理概念不够清晰。
  - **更优且同样“不看 y”的物理形式**：
    在电容阻抗估计中，死区伏秒误差、模拟滤波相移、孔径采样相移均作为独立叠加的扰动源，且负载本身直接影响调制比与电流信噪比。若将其解耦为纯主效应模型：
    $$\hat{y} = \beta_0 + \beta_1 (t_{\text{dead}} f_c) + \beta_2 \text{load} + \beta_3 \frac{f_{\text{grid}}}{bw_{\text{iac}}} + \beta_4 (4\pi f_{\text{grid}} t_{\text{aperture}})$$
    经实测验证：**在完全不触碰测试集/OOD 标签的情况下，该模型的 Test MAE 为 1.525，而 OOD MAE 从 2.923 骤降至 1.606（降幅达 45%）**。将 $t_{\text{dead}}$ 与 $1/\text{load}$ 强行耦合是导致解析模型外推变差的主因。

---

### 4. 对主判据未通过（OOD 覆盖率 40%）的解释
- **结论**：**部分同意**
- **依据与数据核验**：
  researcher_a 在报告 [`docs/reports/M2_researcher_a.md` 第 86 行](file://./docs/reports/M2_researcher_a.md#L86) 声称：*“分布内 test 也有失覆盖（75%），说明校准集的尾部残差对本次测试集偏乐观，不能将全部失覆盖归因于 OOD。”*
  - **同意的部分（确认校准集有限样本方差造成了分布内偏差）**：
    1. **二项置信区间**：在测试集（$n=40$）上实测覆盖 30 例（75.0%）。以 $p=0.90$ 为原假设，二项双侧检验 $p = 0.0051$；95% Wilson 置信区间为 $[59.8\%, 85.8\%]$，95% Clopper-Pearson 严格置信区间为 $[58.8\%, 87.3\%]$。
    2. **残差分布一致性检验**：对 calib 与 test 的绝对残差做非参数检验：Mann-Whitney $U = 774.0, p = 0.806$；Kolmogorov-Smirnov 检验 $D = 0.225, p = 0.266$；两集合残差中位数均为 $0.0823$。统计检验表明 calib 与 test 的总体分布高度一致。
    3. **复合条件覆盖率方差**：在 $n_{\text{cal}}=40$ 下，条件覆盖率本身服从 $\text{Beta}(37, 4)$，其标准差为 $4.58\%$；加上 $n_{\text{test}}=40$ 的离散抽样方差，在严格可交换的总体下，观测测试覆盖率 $\le 75\%$ 的发生概率约为 $3.3\%$。因此，从 90% 名义线下滑到 75% 的这 15 个百分点，确实是有限样本校准分位数抽样偏小（$q=0.1879$）带来的统计波动。
  - **不同意的部分（驳斥“不能将全部失覆盖归因于 OOD”的归因淡化）**：
    researcher_a 试图将 OOD 失败部分归咎于分布内校准噪声，这是**不成立**的：
    1. **残差膨胀压垮固定半宽**：OOD 的 MAE 达到 0.3399（为 test 的近 2 倍、calib 的 3 倍）；OOD 绝对残差中位数在死区子组为 $0.2345$、角落子组为 $0.2592$，**两者均已显著大于校准半宽 $q = 0.1879$**。即超过一半的 OOD 样本即使在中位数处都已出界，导致 24/40 例失覆盖（覆盖率 40%，二项 $p = 1.25 \times 10^{-14}$）。
    2. **反事实检验（Counterfactual Analysis）**：即使假设校准集抽样完美无噪，将区间半宽直接放大至测试集实测的第 90 分位数（$q_{\text{oracle}} = 0.3928$，使得测试集覆盖率强制达到完美的 90%），在 OOD 集合上仍有 11 个点绝对残差大于 0.3928，**OOD 覆盖率依然仅为 72.5%**，同样稳稳跌破 $[85\%, 95\%]$ 的判据下限。
    3. **外推偏差的方向性**：死区子组呈现 +0.221 的正向系统偏差，低载低带宽角落呈现 -0.415 的负向系统偏差。这种空间结构化外推偏差是标准固定宽度保形预测失效的**根本因果**，校准集波动只是次要背景噪声。

---

### 5. 预注册设计本身的缺陷分析
- **结论**：**同意**（预注册设计在统计学与实验设置上存在明显缺陷）
- **具体缺陷辨识**：
  1. **统计理论前提违背（要求 OOD 覆盖率维持 90% 在统计学上无保证）**：
     标准 Split Conformal 的覆盖保证 $\mathbb{P}(Y \in \hat{C}(X)) \ge 1-\alpha$ 严格建立在**样本可交换性（Exchangeability）**假设之上。一旦进入 OOD 区域，可交换性被打破，数学上没有任何定理能够保证固定半宽保形区间能维持 90% 覆盖率。将此作为主判据，属于理论工具与考核目标的错配。
  2. **判据窗口 $[85\%, 95\%]$ 过于严苛，假阴性率（Type I Error）极高**：
     在 $n_{\text{cal}}=40, n_{\text{test}}=40$ 时，经复合 Beta-Binomial 分布积分可知，**即使在没有任何分布偏移的完全独立同分布数据上，观测覆盖率能落在 $[85\%, 95\%]$ 内的概率也仅有 $66.3\%$**。换言之，该判据在理论上对真模型有高达 $33.7\%$ 的误杀率。同时双侧限制也惩罚了保守安全区间（如覆盖率达到 96% 也会被判不通过）。
  3. **角落子集样本量过小（$n=5$）**：
     $load \le 0.35$ 且 $bw_{\text{iac}} \le 75\text{ kHz}$ 在 4 维拉丁超立方体中的体积占比仅约 $1.4\%$，导致 240 例抽样仅命中 5 例。单例翻转就会带来 20 个百分点的覆盖率跳变，完全丧失统计可信度。
  4. **传感器模型未启用实际噪声（`ideal=True`）**：
     [`scripts/dclink_sweep.py` 第 45 行](file://./scripts/dclink_sweep.py#L45) 默认采用 `SensorConfig`，其 [`ideal=True`](file://./data/dclink_src/simsw/dclink_simsw/common.py#L116) 屏蔽了 ADC 高斯噪声与增益漂移，生成的波形过于纯净，未能完全复现硬件工况。
  5. **次要收敛判据标准表述模糊**：
     预注册中“小于方法 MAE 的 1/5”未界定参考集合（train/calib/test/ood）和具体方法，留下了自由裁量空间。
- **对里程碑 3 及后续设计的建议（不追溯判定本轮）**：
  1. **扩大样本量**：Calib 与 Test 提升至 $n \ge 100 \sim 200$，控制分位数抽样标准误 $\le 3\%$；OOD 区域采样需设立下限（各子集 $n \ge 30$）。
  2. **重构覆盖率判据**：
     - 分布内考核保形区间的有效性（建议采用单侧检验，如 Test 覆盖率二项置信下界 $\ge 85\%$）；
     - 分布外引入**协变量偏移加权保形预测（Weighted Conformal Prediction）**，或考核不确定性感知区间的效率（Width-Coverage 帕累托前沿），而非强求标准固定宽度在外推时保持名义覆盖率。
  3. **开启非理想传感器模拟**：设置 `ideal=False`，评估代理模型在真实噪声下的容忍度。

---

### 6. 图表与可视化审查
- **结论**：**不同意原图的处理方式 / 存在显著误导**
- **依据与审查发现**：
  1. **偏差图右图混入了 120 个训练集点的样本内微小残差（严重误导）**：
     审查 [`scripts/dclink_figures.py` 第 33-38 行](file://./scripts/dclink_figures.py#L33-L38)：
     `df = pd.read_csv(ROOT/'data/dclink/predictions.csv'); df = df[df.method=='gp_conformal']`
     随后直接对这 240 个点绘制 `bias = df.prediction - df.y`。
     这 240 点中包含了 **120 个训练点**。由于 GP 的白噪声核水平极小（方差仅 $0.000754$），训练集残差绝对均值仅 $0.0317$、最大仅 $0.1311$。这导致右图（“GP 预测偏差”）在非 OOD 区域密集呈现浅白色（近 0 偏差），**视觉上给读者制造了“GP 在分布内全域预测偏差几乎为 0”的假象**，掩盖了未见测试集样本真实存在的泛化误差（测试集最大误差达 1.092）。
  2. **图例与点集类别缺失**：
     [`scripts/dclink_figures.py` 第 39 行](file://./scripts/dclink_figures.py#L39) 仅用黑色圆圈标出 `OOD 点`，图例未对实心散点做出任何说明，读者无法得知其中 60% 是训练点，20% 是校准点，仅 20% 是测试点。
  3. **字体与颜色映射**：
     - 字体正常加载 Noto Sans CJK SC，负号正常显示，无缺字或豆腐块；
     - 偏差图采用双极性 `coolwarm` 色表且以 0 对称截断（`vmin=-vmax, vmax=vmax`），色表本身选取合理。

---

### 7. 其他代码缺陷与疑点
- **结论**：发现 3 处实现与测试设计问题
- **依据与代码位置**：
  1. **单元测试与运行时临时状态强耦合（测试脆弱性）**：
     [`tests/test_dclink_surrogate.py` 第 14 行](file://./tests/test_dclink_surrogate.py#L14) 调用 [`verify_split`](file://./scripts/dclink_surrogate.py#L42)，强行读取运行时临时路径 `data/dclink/split.json`。然而宿主重建脚本 [`scripts/dclink_rebuild.sh` 第 5 行](file://./scripts/dclink_rebuild.sh#L5) 包含破坏性清理 `rm -rf data/dclink`。一旦后台重建正在运行或该目录未就绪，运行 `make test` 会直接触发 `FileNotFoundError` 导致构建崩溃。测试应当解耦并读取持久化的 `lab/cases/dclink/split_manifest.json` 或进行路径 mock。
  2. **researcher_a 技术报告对 GP 预测标准差机理解释错误**：
     在 [`docs/reports/M2_researcher_a.md` 第 131 行](file://./docs/reports/M2_researcher_a.md#L131)，researcher_a 写道：*“GP 标准差还包括 WhiteKernel 的噪声项”*。
     这在技术上是**错误**的。在 `scikit-learn` 中，[`GaussianProcessRegressor.predict(..., return_std=True)`](file://./scripts/dclink_surrogate.py#L138) 计算的是潜在无噪函数 $f_*$ 的认知不确定性标准差 $\sqrt{\text{diag}(\text{cov}(f_*))}$，它通过核矩阵求逆考虑了训练点的白噪声滤波，但**在测试点预测标准差中并未累加 WhiteKernel 的观测噪声 $\sigma_{\epsilon}$**。
  3. **`load_interp` 边界截断逻辑存在微小瑕疵**：
     在 [`scripts/dclink_surrogate.py` 第 125-130 行](file://./scripts/dclink_surrogate.py#L125-L130)，插值坐标使用的是各分箱中心 `centers`。第 1 箱中心约为 0.344，导致所有落在 $[0.30, 0.344]$ 范围内的样本被 `np.interp` 强行平截为常数 `means[0]`，而不是向边界端点平滑延伸。

---

## 分歧清单

| 编号 | 你的主张 | 依据 | 建议的处理 |
|---|---|---|---|
| **D-01** | OOD 覆盖率仅 40% 的主因是外推域移（外推方差增大与系统性偏差），而非校准集抽样噪声；researcher_a 称“不能全部归因于 OOD”存在误导 | 反事实分析：将半宽放大至测试集经验第 90 分位数（$q=0.3928$）时，OOD 覆盖率仍仅 72.5%；OOD 残差中位数（0.235~0.259）直接压过校准半宽（0.188）；死区子组偏置高达 +0.221 | 在报告中更正因果定性：承认有限样本带来了 90% 到 75% 的校准波动，但明确确认主判据不通过的根本原因在于模型在外推区域的系统性偏差与误差膨胀 |
| **D-02** | `m2_bias_map.png` 右图将 120 个训练点的样本内残差画入偏差图属于严重误导 | [`scripts/dclink_figures.py` 第 33-38 行](file://./scripts/dclink_figures.py#L33-L38) 未过滤 `train`，训练点残差均值仅 0.032，大面积浅白圆点掩盖了分布内的真实测试泛化误差 | 下一轮重构绘图脚本，右图仅绘制测试集与 OOD 点（或留一法交叉验证残差），并按数据集类型（Train/Calib/Test/OOD）在图例中清晰标识点集符号 |
| **D-03** | 解析模型将死区时间除以负载（$t_{\text{dead}}/\text{load}$）且缺乏 load 独立主效应，属于劣质参数化 | 复合特征在低载高死区下双曲线发散，导致 OOD $R^2 = -0.185$，MAE 恶化至 2.923；若按物理延迟解耦主效应，OOD MAE 可大幅下降 45% 至 1.606 | 在后续里程碑的基准解析模型中，采用物理相移解耦形式，将 $t_{\text{dead}}\cdot f_c$、$\text{load}$、$f_{\text{grid}}/bw$ 作为独立线性项处理 |
| **D-04** | 预注册将标准 Split Conformal 在 OOD 上达到 90% 作为主判据属于统计学设计缺陷 | 标准保形预测严格要求可交换性，OOD 下定理失效；双侧 $[85\%, 95\%]$ 在 $n=40$ 下即使对完全理想的 IID 数据也存在 33.7% 的假阴性率 | M3 中对分布内与分布外分别考核：分布内采用单侧名义检验（$\ge 85\%$）；分布外采用加权保形或考核区间宽度-覆盖率综合效率 |
| **D-05** | 单元测试强依赖可变目录 `data/dclink/split.json` 导致测试极其脆弱 | [`tests/test_dclink_surrogate.py` 第 14 行](file://./tests/test_dclink_surrogate.py#L14) 与 [`scripts/dclink_rebuild.sh` 第 5 行](file://./scripts/dclink_rebuild.sh#L5) 冲突，后台清理时 `make test` 抛出 `FileNotFoundError` | 单元测试应读取入库的 `lab/cases/dclink/split_manifest.json`，或在隔离临时目录中执行校验，不与生成中的流水线竞争文件锁 |
