# 公开副本说明 / Public-copy provenance

本仓库是一次独立初始化的发布快照，仅有公开发布提交，不携带早期 Git 历史或远程配置。历史报告中的提交号保留为实验记录及随机种子来源，不表示可在本仓库执行 `git show` 找到旧对象。

This is a newly initialized publication snapshot with no prior Git history or remote. Historical commit identifiers are provenance/seed records, not objects available in this repository.

案例名称、标识符、研究与评审角色、机器路径已泛化。实验预测及指标数值保持原样；元数据哈希因公开文本和路径改变而相应更新。`release_manifest.json`、当前 `SHA256SUMS`、配置守卫和 `EVALUATED` 校验的是公开副本字节，不能证明历史封存时间。报告内的历史短哈希、外部数据哈希和种子不作为当前发布副本的完整性证据。第八轮 `AUTO:evidence` 是历史表，当前文件哈希以发布清单和表格脚本输出为准。

Identifiers and environment details were generalized. Predictions and scientific metrics retain their numerical values. Rebased metadata checksums verify public-copy bytes, not historical seal timing. The release manifest is the authority for current file integrity.

删除了含环境上下文的任务提示与终端日志、私人方向规划、缓存上游网页及联系人信息，以及可能嵌入旧标识的图片、HTML、PDF。历史报告中提及这些路径的文字保留为历史上下文；图片标签已改为说明文字。数值表、评审正文、裁定、绘图脚本仍保留。完整删除与替换清单在发布工作区的 `scrub_report.md`，不随代码仓库分发。

Raw task transcripts, private planning, cached source pages, and rendered assets were omitted. Numerical tables, reviews, rulings, and plotting code remain. Historical mentions of omitted paths are not promises that those artifacts are bundled.

公开环境修复包括：使用当前 Python 解释器；新仓库未提交时以全零 revision 明示其状态；不记录真实主机名；用发布清单核对预注册文件；修正标识符重命名后的编号解析。测试只在缺少真实外部依赖时跳过相关项。第八轮的访问权限测试使用微型合成编号，仍验证禁止越界及跨臂访问。

Portability changes use the current interpreter, an explicit zero revision before the first commit, a generic hostname, and published-file integrity checks. Missing optional inputs cause explicit test skips. Synthetic permission tests still check forbidden-label and cross-arm access.

第九轮的科学方案、样本数、阈值及分析顺序未更改。本次指令锁定公开版本，保留原“待批准、未执行”文字及配置状态副本；不把这次发布状态倒写为历史批准。

Round 9 is locked for this release with results pending. Its original pending-approval status is disclosed; scientific rules are unchanged.
