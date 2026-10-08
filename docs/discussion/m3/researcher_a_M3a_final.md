已完成，未执行 commit/push/checkout。

- D-02/D-05 已修复；`make test` 75 项全部通过。
- `make surrogate` 重跑通过，指标与首次入库快照完全一致。
- N87 下载完整，外层及全部内层 CRC 校验通过：40,616 条，每条 1,024 点。
- `make magnet` 全流程通过；证据检查 `pass`，无错误或警告。中文图片已逐张检查。
- 全温度绝对误差中位数／p95：正弦 12.09%／33.25%，三角类 12.84%／47.09%，梯形 14.42%／54.75%。

详见[中文报告](./docs/reports/M3_magnet.md)、[数据卡](./lab/cases/magnet/data_card.md)和[证据案例](./cases/magnet_igse/report.md)。

许可核实结论：未找到明确的数据许可；[代码仓库 MIT](https://raw.githubusercontent.com/PrincetonUniversity/magnet/main/LICENSE)不能直接视为数据许可。