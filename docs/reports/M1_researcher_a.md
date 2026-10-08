# 里程碑 1 researcher_a 交付报告

分支 `feat/w1-w2`，以未修改的 `docs/spec/evidence_spec.md`（EV-1.0）为准。P1 检查器、P2 运行记录器、P4 开发集已可用，P5 本报告完成。P3 自动入口和案例生成已实现，但本机缺少 GNU make，指定命令尚未成功，所以 **P3 的“cases/dclink_recheck 必须通过”未满足**。失败证据未隐藏；另交付真实成功的直接编译补充诊断案例。

未执行 git commit、push 或 checkout，未修改 `scripts/`、`data/magnet/`、`data/dclink/`，未写入 `external/dclink-simulator`。没有调用 LLM 进行检查。

## 文件清单

实现与历史来源快照：

- `lab/__init__.py`
- `lab/evidence/__init__.py`
- `lab/evidence/__main__.py`
- `lab/evidence/checker.py`
- `lab/evidence/cli.py`
- `lab/evidence/dev_sources/compare_sw_avg.md`
- `lab/evidence/dev_sources/fw_fixed.md`
- `lab/evidence/dev_sources/fw_initial.md`
- `lab/evidence/dev_sources/rulings.md`
- `lab/evidence/devset.py`
- `lab/evidence/history_metrics.py`
- `lab/repro/__init__.py`
- `lab/repro/__main__.py`
- `lab/repro/fw_diagnostic.py`
- `lab/repro/runner.py`
- `lab/repro/dclink.py`

其他交付：

- `tests/test_evidence.py`、`tests/test_repro.py`：单元及 CLI 集成测试。
- `pyproject.toml`：包元数据与 `evcheck`、`evcheck-batch` 控制台别名；Python ≥3.12，运行时只依赖标准库。未向仓库外的虚拟环境安装包。
- `Makefile`：`test`、`dclink-check`、`evaluate`；禁止 Make 目标并行。
- `evalsets/dev/`：29 个案例目录，含 report、claims、来源说明和打包的实际历史提取运行；外加 `labels.json`、`eval.json`、`results.json`、`README.md`。
- `cases/dclink_recheck/`：指定 make 命令失败的真实记录、Python 成功运行、数字标记报告、检查结果及 `timing.json`。
- `cases/dclink_diagnostic/`：直接 GCC 编译测试和 Python 测试，检查为 pass；明确标注不等于 GNU make 运行。
- `docs/reports/M1_researcher_a.md`、`M1_unittest.log`、`M1_evaluate.log`、`M1_batch.log`：交付说明及验证日志。

运行产生但被既有 `.gitignore` 排除的文件：`runs/<run_id>/`（原始运行）、`data/dclink_src/`（固定归档源码与编译产物）、`data/dclink_src_manifest.json`、`data/dclink_numba_cache/`。案例已复制必要的 record、metrics、输入、stdout/stderr，可在不保留这些全局生成目录的情况下检查。export-case 跳过没有被 record 引用的临时目录；被声明的临时产物仍打包。

## 命令与行为

本机没有 make，以下直接 Python 命令可执行：

```sh
python3 -m unittest discover -s tests -v
python3 -m lab.evidence check cases/dclink_diagnostic --json
python3 -m lab.evidence batch evalsets/dev --out evalsets/dev/results.json
python3 -m lab.evidence evaluate evalsets/dev --labels evalsets/dev/labels.json --out evalsets/dev/eval.json
python3 -m lab.repro run --name experiment --inputs input.csv --metrics-from measured.json -- <cmd ...>
python3 -m lab.repro run --name json-metrics --parse json -- <cmd ...>
python3 -m lab.repro export-case cases/example --runs <run_id ...> --claims claims.json --report report.md
python3 -m lab.repro dclink-check
```

后两条通用记录示例需要调用者提供真实文件及命令。`--parse` 支持 `fw`、`pytest`、`json`，可与 `--metrics-from` 合用。命令退出码保留在 record 中，解析失败单独写 `parse_error`，不把成功命令改写成失败退出码。解析失败时记录器 CLI 返回 1。缺少可执行文件也生成完整记录，退出码记为 127。

`metrics.json` 的 `repro` 命名空间保留给退出码、耗时、RSS；调用者若使用同名指标，记录解析错误，避免无声覆盖。`--metrics-from` 原始文件复制为 `metrics-source.json` 并列入 outputs。stdout/stderr 都存为文件并核对哈希。输入采用仓库内副本，避免用绝对 external 路径绕过 EV-1.0。record 附加 dirty、hostname、peak_rss_mb、cwd 和测量方式。

check 输出严格包含 verdict/errors/warnings，各诊断有 code/where/detail；pass 退出 0，fail 退出 1，工具自身错误退出 2。batch 输出案例名到检查结果的映射，有失败返回 1。evaluate 完成统计返回 0，输入或工具错误返回 2；输出 tp/fn/fp/tn、precision/recall、semantic 的单独计数、每例 expected_codes/actual_codes 和是否相符。

安装 GNU make 后可用 `make test`、`make evaluate`、`make dclink-check`。没有 make 时，本次执行的补充入口为：

```sh
python3 -m lab.repro dclink-check --diagnose-missing-make
```

它首先尝试规范要求的原始 make 命令，保留失败记录，再串行执行显式标注的 GCC 诊断以准备固件回放程序，最后运行 Python 测试。主案例仍引用失败 make，仍返回 1；补充成功结果另存 `cases/dclink_diagnostic/`，不会冒充 P3 达标。直接编译命令可单独运行 `python -m lab.repro.fw_diagnostic`，完整实际命令在 stdout 日志中。

## 测试与开发集评估

本次 **58 项 unittest 全部通过**，详见 `M1_unittest.log`。每个 EV-1.0 错误代码均有独立触发测试；有效案例以逐代码 subTest 覆盖全部不触发条件。另覆盖负号（含 Unicode 负号）、小数与科学计数法、百分号、千分位、行内代码、标识符、Sprint 编号、日期、结果段范围、多段结果、同源双向多层闭包与循环、仅共享非 core 假设、仅共享祖先、external 缺失与存在仍核对哈希、路径越界与 symlink、缺文件、坏 JSON/null/类型、非有限值与超大整数、容差、重复 ID、CLI 退出码及 evaluate 语义类排除。记录器测试覆盖真实子进程、输入复制、指标来源、stdout/stderr、导出、解析失败、缺命令和声明在临时目录的产物。

开发集为 **16 defect + 12 normal + 1 semantic**。真实历史指标由一次实际运行的 `history_metrics` 提取，输入副本和哈希随每个案例打包；故意注入的错误在 labels/source/report 中说明。数字没有补造，坏元数据也没有冒充历史事实。指定的 `dclink-edge-ai/replay/out/` 本机不存在，因此取材于允许的 docs 历史文件。

| 实际标签 | 检查 fail | 检查 pass |
|---|---:|---:|
| defect | 16（TP） | 0（FN） |
| normal | 0（FP） | 12（TN） |

precision = 1.0，recall = 1.0。29 例的期望代码和实际代码全部相符。semantic 例为 THD 门控误述：代码值正确但把 PLL 失锁误说成 THD 门控，检查 pass；只统计，不计分。这个满分是开发集机制验证结果，不能外推为真实研究报告的错误检出率或语义识别能力。

## DC-link 实测结果与资源

归档源为 `be9a0f40ce52d4add2e9ac86767937162ed03981`，通过 `git -C external/dclink-simulator archive be9a0f4` 流式解包。每次重跑重新解包有生成标记的目录；无匹配标记或为 symlink 时拒绝覆盖。归档文件的 SHA-256 清单在执行任何构建前生成，并作为各运行的 inputs 副本。

| 运行 | 实际结果 | 耗时（秒） | 峰值 RSS（MiB） |
|---|---|---:|---:|
| 指定 `make -C data/dclink_src/fw clean test replay check` | 找不到 make，exit 127，固件摘要无法解析 | 见主案例 record | 0.00（没有启动作业） |
| 补充直接编译与 C/CLI 测试 | 47 项 C、412988 个断言、15 项 CLI；warning 行数 0，exit 0 | 9.392962 | 71.195312 |
| `pytest sim/tests simsw/tests -q` | 77 passed，0 failed，exit 0 | 102.440069 | 260.703125 |

指定主案例 verdict=fail，代码仅 E_RUN_FAILED；补充诊断案例 verdict=pass，errors/warnings 都为空。主流程（含补充诊断）的实测总耗时为 112.079138 秒，补充案例落盘后的总计为 112.199955 秒，记录作业峰值为 260.703125 MiB，均来自 timing.json。运行 ID：

- 固件直接诊断：`20261002T135705-dclink-fw-direct-diagnostic-4462c271`。
- Python 测试：`20261002T135714-dclink-python-2e731ede`。
- 缺少 make 的指定运行：`20261002T135705-dclink-fw-e3ff7c21`。

所有重型作业串行，MAKEFLAGS=-j1，BLAS/OpenMP/NumExpr 线程数为 1；子进程继承 2500 MiB 地址空间上限。RSS 以 20 ms 间隔采样进程及后代总和，同时取 Linux wait4 的内核 ru_maxrss 较大值。它能捕获短命进程的单进程高水位，但仍可能漏掉短暂的多进程合计峰值；不包含共用机器上其他任务的内存，也不把记录器控制进程混入作业指标。这是有测量定义的峰值观测，不是对整个共用机器的硬保证。

最初 Python 预检因缺少固件 CLI 得到 70 passed / 7 failed；完成直接编译后正式复核全部通过。没有将历史的测试数量混入本次复核结果。GNU make 下载尝试因网络/DNS 不可用失败，未修改系统安装目录。

## EV-1.0 歧义及当前处理

未改规范原文，以下实现选择供主持人审阅：

1. E_SCHEMA 与 E_PROVENANCE 对 cmd/git_sha/started_at/inputs 的缺失及类型错误重叠，因此两者都输出；输入条目的坏结构也同时报告 provenance。一个失败 run 被多条 claim 引用时，每条 claim 都产生诊断，不强行只留一个。
2. 规范给出 batch 命令但没有 batch JSON 容器与 evaluate/labels 格式、退出码。采用前述案例名映射和 label 对象映射；evaluate 即使检出缺陷也退出 0，因为统计成功并不等于被评案例通过。
3. `allowed_paths` 的“前缀之下”按路径组件处理，并归一化相对路径中的 `.`：lab 允许 lab/a，不允许 laboratory/a；允许路径自身和 `.` 根目录。`..` 按路径段禁止，绝对 POSIX/Windows 路径与逃出根目录的 symlink 同样拒绝。没有把所有字符串都猜成路径，模型 source 仍是来源标识。规范未要求 id 非空，字符串空 ID 也按原规则解析，不额外设限制。
4. 数字和布尔值在 Python 中存在继承关系，但 JSON bool 不作为数字接受；NaN/Infinity/溢出整数不作为合法指标。嵌套 metrics 的非数字叶子报告 E_SCHEMA，选中该叶子的 claim 另报 E_METRIC_MISSING。
5. 标记必须紧邻数字；没有紧邻数字的已知 ID 标记报告 E_SCHEMA，数字自身另报 E_UNCLAIMED_NUMBER。ID 存在性与已标记数值一致性检查适用于整篇报告；只有未标记数字检查限定在精确的二级“结果”标题范围。这是第 6 节两条规则的分工。
6. 百分号与 unit="%" 时按字面数值比较，不除以 100。规范没有定义 unit 不是 % 时的百分号换算，也没有规定缩放；实现统一按字面数值比较，不做隐式单位转换。容差默认值照规范执行；负容差按非法字段处理。
7. 同源严格采用列出的三项 OR 条件，未把“有共同祖先但双方互不派生”扩张成同源；共享非 core 假设也不报告。未知派生模型名按模型登记格式错误 E_SCHEMA 报告，闭包有环时仍确定性终止。
8. W_ 警告未给具体代码或大文件阈值。当前仅输出 W_UNREFERENCED_CLAIM；没有凭空制定超大文件阈值。
9. 输入/输出内部文件缺失报 E_SCHEMA；仅 `external: true` 可豁免缺失，存在时仍核对哈希。metrics 没有 external 豁免。源清单能证明输入登记内容，EV-1.0 本身不要求检查器重新证明这些输入真是进程实际使用的每一个文件，或鉴定命令与文字语义。

## 工作区访问纠正

初始约束文件查找曾误用父目录范围，只返回一个仓库外 AGENTS.md 路径，未读取其内容；之后文件内容搜索限于本仓库及授权只读源。首次 Python 预检没有指定 TMPDIR，pytest 的默认临时文件落到 /tmp；发现后，记录器统一将 TMPDIR、Matplotlib 和 XDG 缓存设置到仓库内运行临时目录，正式复核使用了这一设置。没有读取或搜索 ~。

交付保留未提交状态；主持人可先审阅 P1/P2/P4，再为环境提供 GNU make，按原始命令完成最后的 P3 验收。
