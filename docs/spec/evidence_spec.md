# 证据格式规范 EV-1.0（主持人制定，2026-10-02；检查器与所有评估集都以此为准）

## 1. 案例目录（一个"研究报告 + 证据"单元）
```
<case>/
  report.md            # 报告正文（中文）
  claims.json          # 论断列表
  models.json          # 可选：模型登记（验证类论断需要）
  task.json            # 可选：任务范围 {"allowed_paths": [...], "changed_files": [...]}
  runs/<run_id>/record.json
  runs/<run_id>/metrics.json
  runs/<run_id>/<其他输入/输出文件>
```
所有路径相对于案例根目录，不允许 `..` 或绝对路径（出现即 E_PATH）。

## 2. 运行记录 `runs/<run_id>/record.json`
必需字段：
- `run_id`（字符串，必须与目录名一致）
- `cmd`（非空字符串）
- `git_sha`（7–40 位十六进制）
- `exit_code`（整数）
- `started_at`（ISO 8601，带时区）
- `duration_s`（数字，≥0）
- `inputs`：数组，每项 `{"path": ..., "sha256": ...}`（可以为空数组，但字段必须存在）
- `outputs`：同上
- `metrics_file`（相对 run 目录的路径，通常是 `metrics.json`）
- `metrics_sha256`
`inputs`/`outputs` 中的 path 相对于 run 目录。文件存在时必须核对哈希；文件不存在时，只有在该项写了 `"external": true` 的情况下才允许（这种情况只记录，不核对）。

## 3. 指标 `metrics.json`
扁平或嵌套 JSON。指标键用点号路径访问，例如 `ood.coverage`。值必须是数字。

## 4. 论断 `claims.json`
一个数组，每项：
- `id`（在本案例内唯一）
- `kind`：`"metric"` | `"validation"`
- `text`：中文描述
- `value`（数字）、`unit`（字符串，可以为空）
- `run_id`、`metric_key`
- 容差：`tol_abs`（默认 0）与 `tol_rel`（默认 1e-6），满足 |value − metric| ≤ max(tol_abs, tol_rel·|metric|) 即算一致
- `kind = "validation"` 时还需要：`subject_model`、`reference_model`（都必须是 models.json 里的名字）

## 5. 模型登记 `models.json`
`{ "<name>": {"source": "<来源标识，例如代码库@文件或数据集>", "derived_from": ["<name>", ...], "assumptions": ["..."]} }`
同源判定：subject 与 reference 的 `source` 相同；或者其中一方出现在另一方 `derived_from` 的传递闭包里；或者两者 `assumptions` 的交集包含以 `core:` 开头的条目（例如 `core:ideal_average_topology`）。

## 6. 报告中的数字标记
- 报告里的每个定量结果都写成 `数值⟦c:ID⟧`，例如 `覆盖率 0.912⟦c:cov⟧`。标记前紧邻的数字（允许负号、小数、科学计数法、千分位逗号、后跟 % 号）就是报告值。
- 报告值必须与 claim.value 一致（同样的容差；若带 % 号且 claim.unit 为 "%"，按数值本身比较）。
- 在 `## 结果` 二级标题（直到下一个二级标题）内，每一行出现的数字都必须带标记；以下情况豁免：表头分隔行、数字属于标识符（例如 W1、Sprint 2、IF-1.3、C99、k00 这类字母和数字混写的词）、日期 YYYY-MM-DD、行内代码 `...` 内的数字。
- 标记引用的 ID 必须在 claims.json 中存在。

## 7. 错误代码（任何一条 error 都会使 verdict = fail）
| 代码 | 含义 |
|---|---|
| E_SCHEMA | 文件缺失、JSON 解析失败、必需字段缺失或类型错误 |
| E_PATH | 路径越界（含 `..` 或绝对路径） |
| E_RUN_MISSING | claim 引用的 run 不存在 |
| E_PROVENANCE | record 缺少 cmd / git_sha / started_at / inputs 字段，或者格式非法 |
| E_HASH | 文件哈希与记录不符（metrics_sha256、inputs、outputs） |
| E_RUN_FAILED | 被引用 run 的 exit_code ≠ 0 |
| E_METRIC_MISSING | metric_key 在 metrics.json 中不存在或不是数字 |
| E_VALUE_MISMATCH | claim.value 与指标不一致 |
| E_REPORT_MISMATCH | 报告中带标记的数字与 claim.value 不一致 |
| E_CLAIM_UNKNOWN | 报告标记引用的 claim 不存在 |
| E_UNCLAIMED_NUMBER | `## 结果` 段内有未加标记的数字 |
| E_SAME_SOURCE | validation 论断的 subject 与 reference 同源 |
| E_SCOPE | task.json 中 changed_files 存在不在 allowed_paths 前缀之下的文件 |
警告（W_，不影响 verdict）：未被报告引用的 claim、超大文件等。

## 8. 检查器输出
`python -m lab.evidence check <case_dir> --json` 输出 `{"verdict": "pass"|"fail", "errors": [{"code","where","detail"}], "warnings": [...]}`；退出码：pass 为 0，fail 为 1，检查器自身出错为 2。
批量：`evcheck-batch <dir_of_cases> --out results.json`。

## EV-1.1 澄清（2026-10-02，里程碑 1 裁定后）
- `allowed_paths` 中每一项都是目录或文件路径，按路径分段做前缀匹配（`lab` 匹配 `lab/x`，不匹配 `laboratory/x`）；不支持字符串前缀（如 `scripts/dclink_`）。
- E_SCHEMA 与 E_PROVENANCE 可以同时报告；JSON 布尔值、NaN、Inf 不视为数字；百分号按字面数值比较。
- 同源只按第 5 节的三项条件判定（"有共同祖先但互不派生"暂不算同源，列入 v2 讨论）。
- batch/evaluate 的输出格式与退出码以 `lab/evidence/cli.py` 的实现为准（见 docs/reports/M1_researcher_a.md）。
