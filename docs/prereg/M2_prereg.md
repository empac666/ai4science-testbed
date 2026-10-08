# 里程碑 2 预注册（2026-10-02 北京时间；在任何代理模型训练之前提交，时间以 git 提交记录为准）

- 扫描设计：`scripts/dclink_sweep.py`，种子 20261002，拉丁超立方抽样 240 例（film 电容，C_ratio=1，6 s，startup 1 s，solver dt 50 ns）。源码使用 dclink-edge-ai@be9a0f4 的 git archive 快照 `data/dclink_src`。
  - design.json SHA256 = `fa900b0a2757c6e274438f978fd88b375008cab5c3e7d19fd61fa77908da46b5`
- 划分：`scripts/dclink_split.py`，只读取输入参数，不读 y。
  - split SHA256 = `e4bac5895347942354a6dc7513c9989174888169c5c070ec9f3147900f5df4aa`
  - 各集合例数：train 120，calib 40，test 40；OOD 包括 dead_time=3 µs 的 35 例，以及低负载低带宽角落的 5 例。
- 目标 y：VALID 窗口（跳过首窗）的 C_comp 相对 c_ref 的平均误差（%）。
- 四种方法：负载插值、解析死区/前端线性模型、GP（ARD RBF+White）、MLP。全部用 calib 集做 split conformal，名义覆盖率 90%。
- **主判据**：GP+conformal 在 OOD（40 例）上的 90% 区间覆盖率落在 [85%, 95%] 内即为通过。
  - 已知风险：n=40 时二项标准误约 4.7 个百分点，判据窗口只有 ±5 个百分点，所以结果本身有较大的抽样噪声。
- 次要判据（只报告）：
  - 从零重建扫描 ≤ 25 min；
  - 5 个点上 50 ns 与 25 ns 的 |Δy| 报告实测值；预先设定"可接受"标准为 |Δy| < 0.1 个百分点，或小于方法 MAE 的 1/5。
- 承诺：方法超参数在看到 OOD 结果之前就固定；看到结果后如果有任何改动，都必须如实记录并另行报告，主判据只使用第一次运行的结果。
- 补充说明（同样在训练前提交）：
  - 主判据中的"GP+conformal"指**标准 split conformal**：以 calib 集上的绝对残差求分位数，分位数位置为 ceil((n+1)·0.9)/n。
  - GP 原生 ±1.645σ 区间和 σ 归一化 conformal 只作为附加结果报告。
  - 开发任务交给 researcher_a，提示词见 `docs/discussion/m2/prompt_researcher_a_M2.md`。
