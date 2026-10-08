# DC-link 历史证据开发集

本集含 16 个 defect、12 个 normal、1 个 semantic 案例。全部指标由真实 DC-link 历史 Markdown 快照提取；注入缺陷只用于测试检查器，不声称原始项目曾出现对应坏 JSON、越界路径或失败退出码。

`labels.json` 格式为案例目录名到 `{label, expected_codes, description}` 的映射。semantic 案例只统计 pass/fail，不进入混淆矩阵。逐例结果在 `eval.json`，完整诊断在 `results.json`。

来源快照在 `lab/evidence/dev_sources/`，每个案例的提取运行还打包了这些输入的副本和 SHA-256；`source.json` 给出案例内相对路径、原始指标键及扰动说明。原始来源：

- `dclink-edge-ai/docs/discussion/round1_researcher_a_fw_summary.md`：初版 C/CLI 测试数、断言数、误差与反例。
- `dclink-edge-ai/docs/discussion/fix_round_researcher_a_fw.md`：修复后的测试、断言、LS 误差、logger 大小。
- `dclink-edge-ai/docs/results/sprint2/compare_sw_avg.md`：开关模型与平均值模型的真实比较表。
- `dclink-edge-ai/docs/discussion/sprint2/rulings_sprint2.md`：明确裁定门控 code 3 是 PLL 失锁，不是 THD 门控。

`defect_10` 至 `defect_12` 分别测试同 source、多层 derived_from 和共享 core 假设。`defect_13` 的越界修改是 task.json 注入，不会实际修改 DC-link 代码。`semantic_01_thd` 保留错误语义但数字与证据完全一致，所以检查器 pass；这符合本版确定性检查器的能力边界。

运行：

```sh
python3 -m lab.evidence evaluate evalsets/dev --labels evalsets/dev/labels.json --out evalsets/dev/eval.json
python3 -m lab.evidence batch evalsets/dev --out evalsets/dev/results.json
```

在没有既有案例的新工作区，可以运行 `python -m lab.evidence.devset` 从快照构造开发集。生成器拒绝覆盖已有案例，避免把人工修改抹掉。本集与实现一同开发，满分只能说明这些机制测试通过，不能代表独立盲测或真实科研结论的识别率。
