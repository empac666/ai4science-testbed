已在 `fw/` 完成协议、CRC、两级记录器、估计器、门控去抖、A/B 基线、回放 CLI、测试及中文文档；未执行 commit/push。

实际运行 `make -C fw test`、`replay`、`check`，均成功、零警告。**32 项 C 测试＋9 项 CLI 测试通过，共 403705 个 C 断言。**

主机实际 `sizeof`（字节）：

| 类型 | 大小 |
|---|---:|
| sample / feature_frame | 64 / 72 |
| logger | 135728 |
| cap_config / cap_state / cap_est | 40 / 128 / 88 |
| gate / debounce | 36 / 52 |
| baseline / flash_hal | 28 / 48 |

已知限制：指定正弦用例最大误差 **0.090757%**；IF-1.0 原公式在另一纹波相位下存在 **0.267084%** 反例，已记录于 [规范问题说明](external/dclink-simulator/fw/NOTES_spec_issues.md)，未修改规范。M7 周期预算标注为“估计，未实测”，详见 [README](external/dclink-simulator/fw/README.md)。