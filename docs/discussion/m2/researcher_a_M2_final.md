已完成，详见[中文报告](./docs/reports/M2_researcher_a.md)和[证据案例](./cases/dclink_surrogate/report.md)。

- `make surrogate` 跑通，证据检查通过，无错误或警告。
- `make test`：64 项测试全部通过。
- **主判据不通过**：GP 标准保形 OOD 覆盖率为 **40%**，MAE 为 **0.339906 个百分点**。
- 五点收敛检查已纳入，最大差值为 **0.042859 个百分点**。
- 首次结果已保留；重复运行的指标和预测完全一致，未调整配置。

未执行扫描或 `make m2`，未 commit、push 或 checkout。