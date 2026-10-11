# MATH-NS-A1 对照表：OpenAI NS 自然语言证明 vs Lean（pin f9e8bc5）

**状态：** 核心 D1/D2 已填（锁定后填写）  
**填写时间：** 2026-10-11 20:50 Asia/Shanghai  
**预注册：** [`ns_prereg_locked.md`](./ns_prereg_locked.md) · 封印 [`ns_lock_seal.json`](./ns_lock_seal.json)  
**Lean pin：** [`openai/NavierStokesAndEuler@f9e8bc5`](https://github.com/openai/NavierStokesAndEuler/tree/f9e8bc5b38b6e212696e8a30e3e91517af887bbd)

## 免责声明

我们**不**声称 OpenAI 的自然语言纳维–斯托克斯论证是错误的，也**不**声称 Clay 千禧年问题已被解决或推翻。本表只对照：在 commit `f9e8bc5` 上，选定 Lean 声明与所引 NL 估计是否语义一致。Lean 编译（若执行）只说明**形式语句**被接受，不能单独为 **NL** 证明背书。

---

## 结果摘要（核心对）

| ID | 分类（§4.2） | 一句话 |
|----|--------------|--------|
| **D1** | **WEAKER** | NL (8.19) 要 \(m+4\)；Lean 最近声明要 \(m+5\)（多丢一阶环面导数）。 |
| **D2** | **DIFFERENT** | NL (10.19) RHS 只含 \(B_R\)；Lean 还依赖 `dissipationRoot`（≈\(A_R\)），指数与时间量词也不同。 |

**预注册结局（对照 §4.3）：** **Confirmed**（D1=WEAKER 且 D2=DIFFERENT）。  
**说明：** 填写前已有 2026-10-11 spot-check；下表按锁定定位符重新抄录，属锁定后正式填表。

---

## D1 — 逆估计导数损失（Lemma 8.6 / (8.19)）

| 项 | 内容 |
|----|------|
| **分类** | **WEAKER** |
| **NL 来源** | OpenAI *Finite time blowup for Navier–Stokes*，Lemma **8.6**，公式 **(8.19)**，印刷页 **p.95** |
| **NL PDF** | https://cdn.openai.com/pdf/32d9f210-8b73-45e0-91bc-82a30aef8a9a/navier-stokes.pdf · SHA256 `0e779481…ae228f` |
| **NL 声称** | \(\displaystyle \|N^{-1}F\|_{C_y^{m}} \le C_m \|F\|_{C_y^{m+4}}\) |
| **NL 证明要点（原文）** | “The divisor bound (6.7) gives \(\lvert v_t\cdot k\rvert^{-1}\le C(1+\lvert k\rvert)\). **Four more derivatives** of \(F\) … leave a summable \((1+\lvert k\rvert)^{-3}\) bound …” |
| **差距论文** | Bastounis–Circelli–Hansen, arXiv:2610.08144, **Example 3.1**（约 p.4–5） |
| **Lean 声明** | `NavierStokes.SmoothFamilyTorusInverse.norm_derivativeWord_inverse_le` |
| **Lean 文件** | `NavierStokes/SmoothFamilyTorusInverse.lean` **L1059–1080** |
| **Permalink** | https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/SmoothFamilyTorusInverse.lean#L1059-L1080 |
| **Lean 实际假设（要点）** | 假设含 `SmoothFourierData.xJet (w.length + **5**) … ≤ C`（两处）；结论用 `ParametricTorusInverse.mixedLossConstant`；证明中出现 `∑' k, (weight k ^ **4**)⁻¹` |
| **为何 WEAKER** | 在相同输出阶 \(m=\lvert w\rvert\) 下，Lean 对输入多要求一阶环面导数（\(m+5\) vs \(m+4\)），故形式结论相对 NL (8.19) 更弱。 |
| **策略笔记（不计分）** | NL 走 \(\sum(1+\lvert k\rvert)^{-3}\)；Lean 走 weight\(^4\) / `coefficient_seminorm_bound`（Bastounis Ex. 3.1）。 |

### D1 支持行（不计 Confirmed 分）

| ID | Lean | Permalink | 备注 |
|----|------|-----------|------|
| S1 | `inverse_finiteJets` L863–875 | https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/SmoothFamilyTorusInverse.lean#L863-L875 | 文档串：“five torus derivatives lost”；`JetBound … (n+5) → … n` |
| S2a | `ParametricTorusInverse.mixedJet_inverse_bound` L654+ | https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/ParametricTorusInverse.lean#L654-L680 | 同为 `w.length + 5` |
| S2b | `SmoothFamilyTorusInverse.mixedJet_inverse_bound` L1082+ | https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/SmoothFamilyTorusInverse.lean#L1082 | 另一同名声明 |

---

## D2 — 压力通量界（Lemma 10.5 / (10.19)）

| 项 | 内容 |
|----|------|
| **分类** | **DIFFERENT** |
| **NL 来源** | 同上 OpenAI PDF，Lemma **10.5** 证明内公式 **(10.19)**，印刷页 **p.123** |
| **NL 声称（示意）** | \(\displaystyle \Bigl\lvert\int \pi\, w\cdot\nabla\chi_R\Bigr\rvert \le \frac{C_T}{R}\Bigl[(B_R+1)B_R^{1/2} + R^{-3/4}B_R^{3/4}\Bigr]\)，**几乎处处** \(t\in(0,T)\) |
| **NL RHS 依赖** | 仅 \(B_R\)（及 \(C_T,R\)）；**不显式含** \(A_R\) |
| **NL 记号** | \(A_R=(\int\chi_R\lvert\nabla w\rvert^2)^{1/2}\)，\(B_R=\lVert\varphi_R^4 w\rVert_{L^6}\)（Lemma 10.5 附近，约 p.121–123） |
| **差距论文** | Bastounis et al., **Example 3.3**（约 p.8–9） |
| **Lean 声明** | `NavierStokesR3.PressureFlux.exists_uniform_actual_pressure_flux_bound` |
| **Lean 文件** | `NavierStokes/R3/PressureFlux.lean` **L576–598** |
| **Permalink** | https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/R3/PressureFlux.lean#L576-L598 |
| **Lean 实际界（要点）** | \(\lvert\mathrm{flux}\rvert \le CP\cdot\bigl[(\mathrm{cutoffL6}^{1/2}+1)\,(\mathrm{dissipationRoot}/R + 1/R^2) + R^{-7/4}\,\mathrm{cutoffL6}^{3/4}\bigr]\)，**对所有** \(t\in(0,T)\) |
| **Lean 定义对齐** | `cutoffL6` ≈ \(B_R\)：`ComparisonSetup.lean` L50–51（\(\varphi^4\cdot w\) 的 \(L^6\)）；`dissipationRoot` ≈ \(A_R\)：L47–48（\(\varphi^8\) 加权耗散的平方根）· https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/R3/ComparisonSetup.lean#L47-L51 |
| **为何 DIFFERENT** | （1）Lean RHS **依赖** `dissipationRoot`（≈\(A_R\)），NL (10.19) 只写 \(B_R\)；（2）径向衰减结构不同（Lean 出现 \(1/R^2\)、\(R^{-7/4}\) vs NL 的 \(R^{-1}\times R^{-3/4}\)）；（3）时间量词 a.e. vs \(\forall t\)。不满足「同假设下纯变弱」的 WEAKER 定义。 |
| **策略笔记（不计分）** | Bastounis：Lean 用 Sobolev→\(L^2\) Riesz，而非 NL 引用的 \(L^{3/2}\) Riesz；Hölder 指数不同；Lean 把 a.e. 升到 \(\forall t\)。 |

### D2 支持行

| ID | Lean | Permalink | 备注 |
|----|------|-----------|------|
| S3 | `exists_uniform_canonicalCutoffFlux_bound` L546–572 | https://github.com/openai/NavierStokesAndEuler/blob/f9e8bc5b38b6e212696e8a30e3e91517af887bbd/NavierStokes/R3/PressureFlux.lean#L546-L572 | D2 所调用的规范通量界 |

---

## `lake build` 状态

**跳过。** 本机无 `elan`/`lake`/`lean`；内存紧张（约 15 GiB，可用约 2.9 GiB）。预注册已写明：全量编译**不是** Confirmed 的硬条件；本表只声称声明**文本**与 NL 的对照。

---

## 探索性（未扫完，不影响 Confirmed）

| ID | 计划 | 状态 |
|----|------|------|
| D3* | 关键字扫其他 `+ 5` / `weight k ^ 4` | 未做 |
| D4* | pressure-flux 调用链引理名列表 | 未做 |

---

## 变更记录

| 时间 | 内容 |
|------|------|
| 2026-10-11 20:50 CST | 首填 D1/D2 + 支持行；结局 Confirmed；lake build 跳过 |
