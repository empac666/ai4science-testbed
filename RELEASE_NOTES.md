# 公开副本说明 / Public-copy provenance

本仓库是一次独立初始化的发布快照，仅有公开发布提交，不携带早期 Git 历史或远程配置。历史报告中的提交号保留为实验记录及随机种子来源，不表示可在本仓库执行 `git show` 找到旧对象。

This is a newly initialized publication snapshot with no prior Git history or remote. Historical commit identifiers are provenance/seed records, not objects available in this repository.

案例名称、标识符、研究与评审角色、机器路径已泛化。实验预测及指标数值保持原样；元数据哈希因公开文本和路径改变而相应更新。`release_manifest.json`、当前 `SHA256SUMS`、配置守卫和 `EVALUATED` 校验的是公开副本字节，不能证明历史封存时间。报告内的历史短哈希、外部数据哈希和种子不作为当前发布副本的完整性证据。第八轮 `AUTO:evidence` 是历史表，当前文件哈希以发布清单和表格脚本输出为准。

Identifiers and environment details were generalized. Predictions and scientific metrics retain their numerical values. Rebased metadata checksums verify public-copy bytes, not historical seal timing. The release manifest is the authority for current file integrity.

删除了含环境上下文的任务提示与终端日志、私人方向规划、缓存上游网页及联系人信息，以及可能嵌入旧标识的图片、HTML、PDF。历史报告中提及这些路径的文字保留为历史上下文；图片标签已改为说明文字。数值表、评审正文、裁定、绘图脚本仍保留。完整删除与替换清单在发布工作区的 `scrub_report.md`，不随代码仓库分发。

Raw task transcripts, private planning, cached source pages, and rendered assets were omitted. Numerical tables, reviews, rulings, and plotting code remain. Historical mentions of omitted paths are not promises that those artifacts are bundled.

公开环境修复包括：使用当前 Python 解释器；新仓库未提交时以全零 revision 明示其状态；不记录真实主机名；用发布清单核对预注册文件；修正标识符重命名后的编号解析。测试只在缺少真实外部依赖时跳过相关项。第八轮的访问权限测试使用微型合成编号，仍验证禁止越界及跨臂访问。

Portability changes use the current interpreter, an explicit zero revision before the first commit, a generic hostname, and published-file integrity checks. Missing optional inputs cause explicit test skips. Synthetic permission tests still check forbidden-label and cross-arm access.

第九轮已加入封存结果、预注册、配置、实现、测试、四张核查过文字与元数据的图、结果复审和逐条裁定。科学方案、样本数、阈值、分析顺序和结果数字未更改；预注册“待批准、未执行”是历史时点状态，不倒写批准记录。运行日志、标签访问日志和任务提示不分发，超过 20 MB 的文件不入库。

Round 9 now includes results and minor editorial revisions. Historical preregistration status is retained. Execution/access logs and private task prompts are excluded; no file exceeds 20 MB.

第九轮的阶段封存、代码哈希及 `report_manifest.json` / `DELIVERED` 保留历史引用，不重新制造历史封存。部分引用指向已省略的日志或脱敏前字节，报告哈希指向首次文稿，因此不能用这些历史清单验证当前公开文件。第九轮当前公开文件统一由根目录 `release_manifest.json` 校验；`magnet9_common.config()` 使用同一公开清单核对生效文件，历史提交 SHA 仍仅作种子与来源记录。早期轮次沿用原公开版的校验方式。

R9 seal and implementation hashes are historical references, including references to omitted logs or bytes before sanitization. The initial report digest predates editorial revisions. Use the root release manifest to verify current public files; it does not attest historical sealing times.

`magnet9_report.py` 保留首次报告的生成逻辑，本次小修直接维护报告 Markdown；不要用首次生成脚本覆盖修订稿。`recheck_published_r9.py` 只读复核已发布逐臂指标之间的一致性、精确整数分子、固定序列及门控；它不声称重新从原始测量复算，也不替代历史独立复算。

The initial report generator is retained for provenance. The read-only R9 checker validates published metric consistency, exact counts, sequences, and gates without original labels or model fitting.

部分数值容器及图像的压缩字节偶然匹配隐私扫描短词；公开副本仅改用无损压缩编码，逐项核对解压后的数组字节与图像像素不变。解压内容与研究数值不受影响。

本次公开副本测试：188 项，175 通过、13 因既有外部依赖缺失跳过，无失败。移植对照的 1,132,792 个 JSON 数字/布尔叶节点、187 个 CSV、620 个数值容器和四张图均无数值或像素差异。只读复核覆盖 720 项逐臂区域指标、四个精确检验整数分子及 12 组门控，结论一致；未重跑模型。
