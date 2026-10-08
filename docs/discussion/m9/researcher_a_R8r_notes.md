# researcher_a R8r 交付说明

- 新增 `docs/reports/M9_magnet_round8.md`：按上轮结构写中文结果报告，区分检验拒绝、覆盖条件与最终结论，落实主持人全部裁定。包含效应量、相对降幅、逐臂有效性清单、覆盖极值、采点、学习曲线、输入极值、描述性 iGSE 与 SHA256 证据。
- 新增只读 `scripts/m9_report_tables.py`：仅使用 stdlib、numpy、pandas，默认输出全部 Markdown 到标准输出；支持 `--section hypotheses` 等分节输出。读取封存评估、校准、CSV、已有复算摘要和最终日志，设计规模补读冻结的 `split_summary.json`。不拟合、不采样、不重放、不重新枚举符号翻转，不写文件。
- 修改 `scripts/magnet8_figures.py`：移除对实验 common 模块的导入，保留中文/Noto CJK/Agg 逻辑及封存哈希检查；覆盖图补齐 G7r；新增 `r8_effects.png` 与 `r8_bias.png`。效果图同时标检验状态与结论，偏差图明确只作描述。禁止输出至 first* 封存目录或输入 metrics 所在目录。

自检：使用指定 Python，设置 PYTHONUTF8=1。报告 18 个自动区块与辅助脚本标准输出逐字一致；CSV 共 3780 行（最终检查点 540 行）与封存 JSON 指标及校准 q 逐项核对通过；主假设差值、摘要统计、有效性计数及复算整数分子核对通过；EVALUATED 文件哈希检查通过。两脚本 `python -m py_compile`、AST 解析与 `git diff --check` 通过。报告包含完整的编号章节，没有遗留模板占位符。

未能验证：笔记本无 matplotlib，本次没有运行作图脚本，未生成或视觉验收 PNG，未验证 local_node 上的字体与 matplotlib 版本兼容性。主持人需运行 `python scripts/magnet8_figures.py` 并检查五图。未运行独立重计算；本次仅读取已有复算摘要与成功日志。看门狗无暂停/无失败及首次复算报错经过来自用户执行记录与裁定，没有在本机重审 sweep 日志。

范围核对：未联网、未安装、未 commit/push；封存 first* 文件和用户禁止修改的实验脚本无变更。实际分支为 `feat/r8-magnet-onesided`，HEAD 为 `adc3550`；其父提交为用户指定的 `ed79d88`，新增内容仅为 `docs/discussion/m9/prompt_researcher_a_R8r.md`。没有回退或修改该提交。

R8R_DONE
