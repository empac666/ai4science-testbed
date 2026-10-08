# M6：DC-link 第五轮实现与隔离冒烟报告

本阶段按预注册实现，未启动正式 2120 例扫描，未导出正式案例，未生成正式第五轮评估结果。分支保持 `feat/r5-matched-pairs`；未执行 commit、push、checkout、reset、stash。Python 为 `python3`，未安装包。

## 冻结与复用

所有第五轮脚本入口先调用 `dclink_design5.py --verify`；核对 config、设计及 config.reused_sha256 的全部文件，并断言 model 等于第三轮配置与 `dclink_surrogate2.CONFIG`。

- config SHA256：`ec1cce652758fda7e6ffbe688ea77d46d6f9264d5f8666dfa3fb83a5832c9466`。
- design SHA256：`8f1496ba6e5b4c27d50582f55fe1fa0fc8d1682a8e7f87ae1f56d589ec6ca3fb`。
- `fit_m2`、`believer`、`posterior_std`、`mixed_believer` 直接 import 第三、四轮原函数。区间校准、区间指标、Winkler、采点统计、冻结与摘要均复用已有函数。
- `dclink_surrogate5.evaluate_arm` 使用相同拟合和预测计算顺序。用真实第四轮 A、RS1 数据重拟合，第三轮 test/角落/dt3、校准 q 及补充集在内的 **90 项 M2 指标逐位一致**；结果见 `data/dclink5_smoke/regression.json`。
- 原预注册、已有轮次脚本和冻结输入未改动。运行时环境技能要求的 environment_status 工具未暴露；本任务不需要网络或凭据，使用本地环境执行。

## 实现

1. `dclink_active5.py`：12 个自适应臂各自只读 S0 与本臂已完成目标。先读 case_id/group/ideal，再以物理行 skiprows 排除其他目标；跨臂、旧轮臂及留出集被 allowlist 拒绝。候选池仅排除本臂已采点。批次保存核参数、归一化、线性系数、σ/分数分位数、输入指纹和 SHA256，首次不可覆盖。
2. `dclink_sweep5.py`：base 800 例；每一批先完成 12 臂全部选点，再提交 264 例。单独 adaptive 入口要求全部 base 已成功完成。jobs 只接受 1 或 2，所有线程环境变量为 1，NUMBA_CACHE_DIR 为 `data/numba_cache`。直接复用第四轮有界队列、参数不变重试一次、会话 start/submitted/heartbeat/end 与 interrupted_inflight 恢复协议。扫描文件加锁，阶段结束或异常时更新 lab/cases/dclink5 中可恢复摘要副本。
3. `dclink_surrogate5.py`：18 臂分别拟合 M2 及只报告的 M0/M1；第三轮 calib 60 的第 55 顺序统计量校准。主判据只用 T5/C5/D5，旧留出集与补充集只报告。记录每臂 MAE、偏差、q、覆盖、宽度、C5/D5 Winkler、角落和 dt=3 及全部 dead_time 类别采点数，M 臂 dt3≤27 的组数、R 臂 C5 覆盖分布及其均值/样本标准差。
4. 精确枚举 64 种符号；比较 `permuted_mean >= observed_mean - 1e-12`，保留平局和恒等变换。固定 H1→H2→H3→H4、p<0.05，首次未拒绝后为 not_tested，仍报告名义 p 和全部六组差值。四个结论严格对应预注册第 7 节，CV 使用至少 5/6。
5. 每臂拟合结果可断点恢复；正式评估指纹绑定全部数据、批次、主要依赖源码与仿真来源。`first.pending` 写完后原子改名至 `first/`，重复入口只核对并恢复副本。已用合成数据测试首次封存、重复跳过、输入改动拒绝与产物篡改拒绝。
6. `dclink_case5.py`：独立从逐点预测重算校准秩、区间、覆盖/宽度/误差、Winkler、C/CV、64 种 bit-mask 置换、固定顺序与结论，不调用第五轮判据函数。采点数独立复核；显式 --train/--verify-results/--export 接入 evidence。当前只在临时合成案例上验证导出与 `python -m lab.evidence check`。
7. `dclink_figures5.py`：正式绘图实现三张中文图：角落 A/M/R 配对及 H1–H3、dt3 A/M 配对及 H4、18 臂覆盖门限和采点数。使用指定 Noto Sans CJK SC 字体、unicode_minus=False、150 dpi。正式图仅用合成测试临时输出；本轮保留两张冒烟图至 `data/dclink5_smoke/figures/`，标题均注明“冒烟，不作评估”，已目视检查。
8. Makefile 仅新增 sweep5、surrogate5 两个目标及其 .PHONY 声明；未改其他目标。

## 未指定细节的处理

- 文件夹和指标使用与 group 一致的 `A1`/`M1`/`R1` 命名，对应预注册的 A_1/M_1/R_1；臂次序按组依次 A、M（评估为 A、M、R）。并列选点规则由原采集函数保留。
- 任一案例两次失败即停止推进；不替换、不缩减预算、不以部分批次训练下一批。中断在途不算一次已完成失败，恢复后仍以原参数重跑，沿用第四轮协议。
- CSV/会话摘要是可恢复文件，可以原子更新；选点记录、评估 checkpoint 与首次评估是不可覆盖文件。恢复扫描会从日志重建累计 CSV。
- 会话墙钟沿用第四轮 heartbeat：中断后只计最后一个持久 heartbeat 的时长，不臆造崩溃后的经过时间。进程 SIGSTOP/SIGCONT 内存看门狗仍按预注册由主持人外部启动；脚本先执行 free -g，available<4 GB 时等待，每次只投递最多两个仿真。
- 冒烟仅用前 2 个 base、A1/M1 各 2 点，pool 前 200、S0 前 40。4 s 与正式 6 s 的数据严格分目录；冒烟不算覆盖判据、不计算正式 p 值。
- 模型触及既有 GP 核参数边界时 sklearn 发出 ConvergenceWarning，保留冻结配置，不调参。

## 测试与冒烟实测

最终 `make test`：**110 项全部通过，14.292 秒**，含第五轮 15 项测试与全部旧测试。日志：`data/dclink5_smoke/validation/make_test.log`。覆盖冻结、全部 2120 个 index/seed、跨臂目标守卫、采集复用、不可覆盖批次、精确置换平局、顺序门控、C/CV 边界、12 臂同步提交、失败停止、计时中断恢复、18 臂合成端到端、逐点独立核对、临时 evidence 导出与绘图。

冒烟前 `free -g` 显示 available=6 GB，jobs=2。六例全部首次成功，无替换或失败重试；duration=4 s、startup=1 s。

| case_id | group | y | elapsed_s |
|---|---|---:|---:|
| dclink5_0000 | T5 | 4.90780341831652 | 14.13349068000025 |
| dclink5_0001 | T5 | -0.8457548282367139 | 13.889758041001187 |
| dclink5_0800 | A1 | -0.889305092493394 | 14.2947253070015 |
| dclink5_0801 | A1 | -6.188215938236313 | 14.108815324001625 |
| dclink5_0910 | M1 | -1.025540543002949 | 11.76269197900183 |
| dclink5_0911 | M1 | -5.989739019201215 | 11.656320324000262 |

第一次扫描会话墙钟 **40.899730293 s**；每例平均 **13.307633609 s**。第二次同命令续跑墙钟 **0.026506774 s**；成功记录仍为 6 条，总 submitted 仍为 6 条，第二会话没有 submitted，确认全部跳过。合计会话墙钟 **40.926237067 s**。真实冒烟没有中断；中断在途恢复分支由注入日志与合成重试测试验证，不冒称做过真实杀进程实验。

按仿真物理时长线性放大估计，正式两进程扫描耗时：`13.307633609 × (6/4) × 2120 / 2 / 3600 = 5.878 小时`。这是六例冒烟外推，不是正式实测；未包含后续 60 次选点拟合、评估拟合及内存看门狗暂停，实际墙钟可能更长。

## 交付状态

完成验证后创建 `data/dclink5/READY_TO_RUN`，记录冻结输入、实现与依赖的实际 SHA256。正式目录只有原设计与 READY 标记；`lab/cases/dclink5/first/` 和 `cases/dclink_surrogate5` 均未创建。正式启动留给主持人按预注册在后台加内存看门狗执行。
