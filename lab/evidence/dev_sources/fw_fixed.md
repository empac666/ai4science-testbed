已按 IF-1.1 完成固件修改，本次只修改 `fw/`，未执行 commit/push。

实际运行 `make -C fw clean test replay check` 全部通过：**40 项 C 测试、404589 个断言、12 项 CLI 测试**；包括严格检查在内，`-Werror` 零警告。

关键容值误差：

| 测试 | 最大误差 |
|---|---:|
| 原 0.267084% 反例，LS | 0.000214% |
| 同反例，LS＋LUT | 0.000298% |
| 49.5 / 50.5 / 60 Hz | 0.000244% / 0.000198% / 0.000221% |
| 异步 fs=4997 Hz | 0.000186% |
| 40 种频率／相位／LUT 组合 | 0.000368% |

均低于 **0.01%**。使用平移后的 float 累加器，无 double 信号累加。

实测主机 `sizeof`：原始样本 **16 B**，`dclink_sample_t` **56 B**，logger **37424 B**，满足 ≤48 KB。

[README](external/dclink-simulator/fw/README.md)、[规范问题记录](external/dclink-simulator/fw/NOTES_spec_issues.md)和[逐条评审回应](external/dclink-simulator/fw/REVIEW_RESPONSE.md)已更新。M7 周期预算均注明“估计，未实测”。