# MagNet 数据来源与许可：主持人核实记录（2026-10-02 约 23:30，北京时间）

所有来源都由主持人在 2026-10-02 用 curl 或 WebFetch 亲自打开过。

## 许可

| 来源 | 内容 | 是否覆盖数据 |
|---|---|---|
| https://raw.githubusercontent.com/PrincetonUniversity/magnet/main/LICENSE | "MIT License / Copyright (c) 2021 Minjie Chen" | 这是**代码仓库**（MagNet 平台软件）的许可。仓库里没有任何文字说明它适用于测量数据 |
| https://raw.githubusercontent.com/minjiechen/magnetchallenge/main/LICENSE（`magnetchallenge-1` 的内容相同） | "MIT License / Copyright (c) 2023 MInjie Chen"（原文就是这样拼写的） | 同样是**代码仓库**的许可；数据并不托管在这个仓库里 |
| https://www.princeton.edu/~minjie/magnet.html（MagNet Library，标注 "updated 04-01-2025"） | 页面只列出了数据下载链接 | **页面上没有任何许可或使用条款** |
| magnetchallenge README | "If you used MagNet data, please acknowledge the MagNet project by citing the papers listed at the end of this page." | 这是**引用要求**，不是许可 |
| MagNet Handbook（2023-03-25）第 313 行附近 | "There are no special licenses or rights required by the sponsors." | 这句话出自"参赛队知识产权"一节，讲的是**参赛作品**，不是数据 |

**结论：没有找到明确的数据许可。** 之前的说法"许可为 MIT"不准确：MIT 只适用于这两个代码仓库。

**建议用法**：仅用于研究；按要求引用 Serrano 等人 2023 年的 TPEL 论文（doi:10.1109/TPEL.2023.3291084）及另外两篇论文；不再分发原始数据（本仓库已把数据设为 gitignore）。如果要商用或二次发布，应先写信给 CONTACT_REMOVED 确认。

## 规模
以下内容来自 MagNet Library 页面原文，主持人已核实：
- "Complete MagNet Raw Database (15 Materials, 29.31 GB)"
- "MagNet Challenge 1 Database (updated 03-09-2024) — Pretest Training Data (10 Materials, 3.14 GB)"
- 其中 `pre-training.zip` 实际大小为 3,141,536,646 字节（HEAD 请求返回的 content-length），Last-Modified 为 2024-03-10 01:47:20 GMT（北京时间 2024-03-10 09:47）。
- 在这个压缩包中，N87 成员 `pre-training/N87.zip` 解压后为 683,282,735 字节（ZIP 目录记录）。

**未核实的说法**：
- 搜索引擎摘要称 "Why MagNet" 论文写到 N87 有 142,871 组波形。IEEE 的 PDF 对我们的请求返回 418，**主持人没能打开原文核实**，所以不作为事实引用。N87 的实际样本数以 researcher_a 从数据中统计的结果为准。
- "数十万条""电力电子界的 ImageNet"这类说法，主持人没有在一手来源中找到原文，应视为二手描述。
