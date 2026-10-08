# DC-link 第四轮：实现与隔离冒烟报告

本阶段完成实现、冻结核对、测试和隔离冒烟。没有启动正式 660 例扫描，没有产生第四轮正式评估或导出 `cases/dclink_surrogate4`；H-A、H-M 均未判定。分支保持 `feat/r4-seeds-mixed`，未执行 commit/push/checkout/reset/stash，未安装包。

## 冻结与复用

所有命令入口首先调用 `scripts/dclink_design4.py --verify`。另核对预注册的三个固定 SHA256、实际第三轮 split 及分组摘要；design4 验证器重新计算 manifest 中的候选池、第三轮设计/扫描、主动批次、第二轮非理想数据与首次指标哈希。模型字典严格断言等于第四轮冻结配置、第三轮冻结配置及 `dclink_surrogate2.CONFIG`。

- design：`7cfdc9423eb84d9436c1966335e3938fe98a003557587eb264f9f9dbed5be437`
- manifest：`dfc7553465d048d82db99b4c1c4972434a8abf30781b376029c83e3ff0175ad3`
- config：`da1cdf3cc9696ba7f870446d63cd21a1b2f28e8d27187dfa0480d7f5219efbd5`

最终核对日志：`data/dclink4/final_design_verify.json`。冻结三文件没有重写。

第四轮评估按四对臂直接调用第三轮 `evaluate`，保持相同训练/留出行顺序、M2/M0/M1 拟合和校准。每对完成后冻结检查点，可续跑。用第三轮真实数据重拟合 A/R 的实现检查已通过：86 个 M2 指标（含校准 q、各评估集及合并补充集）与第三轮首次封存 Python 数值严格相等，无容差；耗时 5.782081 秒。这里只做复用实现检查，不是第四轮评估。记录在 `data/dclink4/reused_implementation_check.json`。

## 实现要点

- `dclink_active4.py`：复用 `fit_m2`、`posterior_std`、原 Cholesky 增秩公式。每步计算含 WhiteKernel 的 σ，按 M 已选类别计数除以 √(1+a_c)，并列使用候选池原顺序。排除范围仅为 M 自己的 pool_id。计数含已选但最终仿真失败的点；训练仅纳入已完成点的目标。批次记录每步类别计数、σ/s 分位数、核与归一化常数、训练/候选/历史/代码指纹及整体 SHA256；只认首次选点，正式时另冻结到 lab 目录。
- 目标守卫先仅读标识、group、ideal，再用 skiprows 跳过禁止行才解析 y；仅允许第二轮非理想 S0 与 M 完成点，显式禁止留出、补充集、第三轮 R/A 和 RS1–5。冒烟只用 S0 前 40、池前 200、一次选 2 点。
- `dclink_sweep4.py`：复用原 `run_case` 和回放构建，在独立 runtime 保存源码/二进制哈希。文件锁覆盖扫描会话；最多两个工作进程、每个单线程，队列中也最多两个在途任务。失败原参数重跑一次，未返回结果的中断不消耗 attempt。正式入口核对 READY_TO_RUN 中哈希；`--phase all` 先 random 后 mixed。
- start/submitted/result/heartbeat/end 均 fsync。续跑先清理半截尾行，再立即写 start，恢复旧会话及中断在途事件；恢复本身中断也不会重复计数。汇总包含各会话、墙钟、完成数和重试耗尽失败列表。恢复 CSV 时从完整结果日志重建，不因 CSV 尚未落盘而重复计算。
- `dclink_surrogate4.py`：A-1/A-2/A-3 与 M-0/M-1/M-2 按冻结规则，H-A/H-M 分别判定；R 不进入任一假设。五个随机臂的 C 判定、覆盖均值/标准差、补充集指标、M 对 A 的双侧 Wilcoxon、类别/角落/低负载采点数均输出。正式完整评估断言 A/R M2 逐位复现后才原子发布 `first/`；重复运行只检查 provenance、产物哈希与冻结副本。
- `dclink_figures4.py`：正式两图实现角落覆盖/Winkler（32/40、36/40 门限，R 空心且标已看过）和各 dead_time/角落采点数（dt=3 的 27 上限）。本阶段实际只输出隔离冒烟图，中文 Noto Sans CJK SC、150 dpi，标题注明“冒烟，不作评估”；目视检查中文与标记正常。
- `dclink_case4.py`：接通 lab.repro 首次评估、独立核对、测试、产物记录、claims/中文报告及 export/check。独立核对不调用第四轮判据函数，重算逐点区间、校准第 55 秩、C 判据、Winkler/Wilcoxon、两个假设，并从采样 CSV 复数类别。只有显式 `--export` 才导出。合成测试实际经 lab.repro 生成临时证据、导出，并执行 `python -m lab.evidence check`；临时目录清理，未生成正式案例。
- Makefile 仅新增 sweep4/surrogate4 目标及其 PHONY 声明；未更改其他目标。

## 未指定细节的处理

随机臂覆盖标准差使用样本标准差（ddof=1），写入 metadata。低负载边定义为 load≤0.35，角落为 load≤0.35 且 bw≤75 kHz，沿用第三轮。全零配对差返回 p=1，沿用第三轮退化处理。缓存按臂对保存，provenance 同时绑定模型/采集/扫描实现、原始输入、模拟源码及回放 provenance。

中断墙钟严格按最后心跳作为已知下界；尚无完成心跳的会话记 0 秒，不能据此宣称中断无成本。启动前内存等待属于会话墙钟，若之后正常结束则计入。冒烟未构造虚假的角落覆盖或检验结果，第一张实际图采用四例 y 与 S0 模型的未校准 ±1σ 诊断，第二张展示实际采点。

## 测试

`make test`：**95 项全部通过，unittest 用时 4.499 秒**，含已有测试；完整日志 `data/dclink4/make_test.log`。第四轮新增测试覆盖冻结设计、直接矩阵求逆与 believer 的 1e-8 一致性、并列及批内计数、目标访问守卫、严格不等式与门限边界、批次冻结/候选排除、截断与中断恢复、失败重试、合成八臂端到端及证据检查。

合成端到端包含全部八臂、三种方法和校准/留出/补充集；验证检查点恢复不重新拟合、逐点独立复算以及篡改判定会失败。计时单元测试注入 3 秒旧心跳与 4 秒新会话，核对总计 7 秒、一次中断在途和不重复计数；这些数值是明确的测试输入，不是实测扫描耗时。

## 隔离冒烟实测

命令使用指定 Python，先 `--smoke --phase random --jobs 2`，再启动 mixed 在提交后终止本任务进程组，最后 `--smoke --phase all --jobs 2` 续跑。每例时长 4 s、startup 1 s、solver dt 50 ns。`free -g` 曾显示可用 3 GB，程序等待；各次真正启动仿真前检查达到 4 GB。日志见 `data/dclink4_smoke/{random_run,interrupted_run,resume_run}.log`。

| case_id | 臂 | y | 单例 elapsed_s |
|---|---|---:|---:|
| dclink4_000 | RS1 | -3.80683157807545 | 16.790967186 |
| dclink4_001 | RS1 | 0.49584505964636 | 17.073840962 |
| dclink4_550 | M | -1.35488419056107 | 14.047984377 |
| dclink4_551 | M | -6.27783548357487 | 14.148761145 |

四例成功，失败 0；最终结果的 attempt 均为 1，平均单例 15.515388418 秒。回放哈希见 `data/dclink4_smoke/runtime/replay_provenance.json`；仿真、批次与日志均在 `data/dclink4_smoke/`，没有复制到正式训练或评估输入。

中断实验对已提交的 `dclink4_550`、`dclink4_551` 发出整个自有进程组 SIGKILL，退出码 -9；驱动观察耗时 3.262181127 秒。此会话尚无完成心跳，按预注册计入 0 秒。续跑记录 **2 个 interrupted_inflight**，沿用完全相同参数哈希和首次批次，两个点重算仍为 attempt 1。没有对其他任务进程发信号。

| phase | 会话状态 | 计入 wall_s |
|---|---|---:|
| random | end | 78.357785963 |
| mixed | interrupted | 0.000000000 |
| all | end | 14.469153734 |

汇总墙钟 **92.826939697 秒**，完成 4 例，失败列表为空；已核对汇总等于全部会话计入墙钟之和。这包含首次等待内存，且不包含最后心跳之后无法恢复的墙钟。证据：`progress.jsonl`、`sweep_timing.json`、`interruption_experiment.json`。

冒烟图：`data/dclink4_smoke/figures/r4_smoke_diagnostic.png`、`r4_sampling.png`。拟合出现 WhiteKernel 下界 ConvergenceWarning，保留冻结配置和原始 warning，未调整核边界。

## 时长外推与交付状态

按四例实测均值直接外推，660 例、2 进程为 15.515388418×660÷2÷60 = **85.335 分钟**，这是 4 秒冒烟工作量的估计。正式仿真为 6 秒，若计算量按仿真时长线性增长，乘 6/4 后约 **128.002 分钟**。这两项是基于实测的外推，不是正式扫描实测；未计入共享机器负载变化、内存等待、重试和完整池采集/拟合开销。

完成最终核对后创建 `data/dclink4/READY_TO_RUN`，保存冻结输入、复用输入与实现/测试文件哈希。停在此处，正式扫描留待主持人启动。正式扫描及评估产物尚不存在。
