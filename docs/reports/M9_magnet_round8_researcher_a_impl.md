# 第八轮实现交付：R8a

已完成设计、采集、校准、评估、作图、扫描驱动和 unittest。未运行正式臂、全规模计时或正式扫描。未读取真实留出/校准集标签，未计算或打印其指标。未联网、安装软件、提交或推送。

绑定的生效预注册提交为 `1e767b17c6195e01bceb5bf20dcd4189df3b9571`，H=511081239。运行时用 `git cat-file -e` 检查提交，并逐字节核对当前预注册与该提交内容。配置 SHA256 为 `58916038c50fdde7993079630bf0bf2f03a6df5d7f8d734e8c8598cce699fa8b`。第六轮模型和第一至七轮文件均未修改。Makefile 仅追加七个目标。

## 实现与封存

`magnet8_common.py` 管理哈希、完整整数种子、UTF-8/LF 输出和标签权限。模型适配每次创建独立模块，深复制第六轮配置，仅覆盖 GP 种子。合成数据证明：种子恢复为 20261004 时，两种实现的 μ、σ 逐位相同；原模块配置不变。E1/E2 的 GP 种子分别为 3169646126、3169646127。

设计只用 features.csv 的显式输入列白名单。集合、族、预算、种子与等宽档均有断言。`design.csv`、`split.json` 和 `split_summary.json` 可逐字节重新生成核验。源文件哈希按字节流计算；本机标量 CSV 的哈希已通过，B.npy 缺失。只有设计和冒烟显式使用 `--allow-missing-sources`。正式臂、校准和评估不接受缺源许可，且阻止在 Windows 上执行。

1. **采集封存**：每个实验/组/臂各建独立 PoolReader 和模型实例。读取标签前检查本实验池、全部留出与校准集合；E2 还检查 S。初始仅授权 S0。整批选点冻结后才授权该批标签。每个检查点保存模型数值状态 `.npz`、CAL/评估集的 μ/σ，以及哈希；此阶段不读 CAL 或评估标签。输出有 RUNNING 排他锁、冻结批次、fingerprint、DONE、Asia/Shanghai 日志、S0 与新增点分列统计、池和训练输入极值。断点恢复重新拟合并核对已冻结状态，不换种子。
2. **校准封存**：先要求 180 臂全部 DONE，再核对全部模型、预测、批次、种子与权限。仅开放各实验自己的 CAL 标签，计算全部 b=0…6 的有限样本顺序统计量 q，封存 `first/calibration.json`。已存在即拒绝覆盖。
3. **评估封存**：重新审计全部臂和校准封存，之后才读取评估标签。先封存 `primary_evaluation.json`，再开放 iGSE 预测作只报告比较。最终写 `metrics.json`、全部检查点的 `arm_table.csv` 和 `EVALUATED` 哈希清单。已有首次评估产物即拒绝覆盖。CSV 中 `final_` 前缀表示最终检查点的有效性标志。

`magnet8_audit.py` 对全部臂检查批次链、模型/预测哈希、S0/R 种子、R 完整顺序和采点统计。默认在两个实验各重放 A1、M1 的全部六批；可在运行前用 `--replay-arms A1,M1,A2,M2` 指定更多臂，或用 `all` 重放全部 A/M。重放只用冻结协方差状态和输入，不读标签。

K=30 的精确符号翻转只分配两半各 32768 个符号和，排序后以 searchsorted 计整数分子；阈值严格为 `sum(d)-30e-12`。零向量 p=1，全正等值向量 p=2^-30。小 K≤14 的浮点容差边界可能因加法重排与旧库出现末位差异；仅这些小 K 边界对按旧库均值表达式复核，以保持测试逐值一致。正式 K=30 不进入该兼容分支。

固定顺序使用 p<0.05。CV、V80、HONEST90 独立于 p 门控，并严格按预注册映射结论。输出保留全部 30 个差值、整数分子、名义 p、门控状态、各检查点指标、覆盖欠缺、学习曲线、iGSE 限制说明。`validity_pass_counts` 与 `sampling_counts` 分开构建和测试；XFT 不设确认性通过/失败判定。

作图脚本只在 render 内导入 matplotlib，从已封存指标生成三张中文图。扫描驱动按 k 交错排列 E1/E2、A/M/R，最多两个独立子进程组。每五秒读取 MemAvailable，按 3.8/4.3 GiB 滞回暂停/恢复；看门狗留在驱动进程。低内存持续 900 秒默认记基础设施停止，可事先调整超时。臂失败后继续其余臂，最终非零退出。驱动记录完成、失败、状态变化和总耗时；Windows 只允许 dry-run。

## 输入设计核对

以下均为输入信息，不含标签或评估结果。

| 实验 | 集合 | 样本数 | 族数 |
|---|---|---:|---:|
| E1 | X7 | 632 | 39 |
| E1 | G7r | 5375 | 40 |
| E1 | CAL7r | 3508 | 20 |
| E1 | 池 | 31101 | 231 |
| E2 | S | 25122 | 220 |
| E2 | G8 | 3197 | 30 |
| E2 | CAL8 | 1704 | 20 |
| E2 | 池 | 20221 | 170 |
| E2 | XF | 5361 | 69 |
| E2 | XT | 8345 | 217 |
| E2 | XFT | 1788 | 67 |

全体为 40616 点、291 族；E1 合格族为 252。全部区域互斥关系、抽样预算和确定性断言通过。设计 GP 种子、族种子以及 30 组 S0/R 种子和集合哈希见 `lab/cases/magnet8/split_summary.json`。

v=log10(4fBpk) 的九个档边界如下。显示值不用于重新计算，完整精度存于 JSON。

| 边界序号 | E1 池 | E2 池 |
|---:|---:|---:|
| 0 | 3.557401159414773 | 3.555472461398943 |
| 1 | 3.767791259076286 | 3.766245455872777 |
| 2 | 3.978181358737798 | 3.977018450346611 |
| 3 | 4.188571458399311 | 4.187791444820444 |
| 4 | 4.398961558060824 | 4.398564439294278 |
| 5 | 4.609351657722336 | 4.609337433768112 |
| 6 | 4.819741757383850 | 4.820110428241946 |
| 7 | 5.030131857045362 | 5.030883422715780 |
| 8 | 5.240521956706875 | 5.241656417189613 |

## 本机验证与限制

使用指定 `LOCAL_PATH`：Python 3.12.10、NumPy 2.5.3、SciPy 1.18.1、scikit-learn 1.9.1、pandas 3.0.6。四个数值线程环境变量均设为 1。

- design 与 `--verify --allow-missing-sources` 均通过，未读取标签。
- E1/E2 各 A1、M1、R1，共六个冒烟均完成。输出只在 `data/magnet8_smoke`。伪外推集合为本实验真实池中 v 最高的 80 点；其余伪集合也仅来自同一真实池。每臂 S0=30，候选=2000，两批各 5，最终训练=40。伪集合仅作预测，连其标签也未读取。
- `python -m unittest tests.test_magnet8 -v`：30 项，29 项通过，1 项因缺少 matplotlib 跳过。含 MITM/暴力/旧库一致性、K=30、种子、设计、泄漏断言、模型逐位一致、批次篡改、门控全组合、26/30 门槛、计数隔离、预测顺序、三阶段合成封存和 dry-run。合成封存测试使用模拟审计返回值和合成标签；不代替 local_node 上的正式完整性核验。
- 第七轮原始命令确实执行：17 项中 14 项通过，3 项因环境缺失报错。原因是 B.npy、已冻结的第七轮 data 设计产物和 matplotlib 在本机缺失。随后只在测试进程内把这三项标为环境 skip：17 项，14 通过、3 跳过。未改第七轮源码或测试；不能把这一结果写成原始全套无条件通过。日志为 `data/magnet8_smoke/legacy_tests.log`。
- 另做输入侧回归：用已校验 features.csv 的显式白名单，在内存中按原第七轮函数重建设计，仅替换测试进程的 `load_design` 文件读取入口，不落盘、不读 y。原来的设计确定性与冒烟隔离两项也通过。因此该输入回归模式为 17 项、16 通过、仅作图 1 项跳过，见 `legacy_tests_input_harness.log`；它不声称核验了本机缺失的第七轮冻结产物。
- 核对六个 DONE、批次、模型与预测哈希；所有冒烟训练 id 都在各自真实池内。核对没有正式 `data/magnet8/arms` 和 `lab/cases/magnet8/first` 输出。新增文本与追加后的 Makefile 均为 UTF-8/LF，无 CRLF。

GP 在极小合成/冒烟数据上有核参数触及既定边界的 ConvergenceWarning，未修改边界、重启数或模型。没有运行正式规模以估时或量测峰值内存。正式进程内存上限及 Linux 信号看门狗需由主持人在 local_node 验证；本机只测试其调度和滞回逻辑。三张图也需在 local_node 实际渲染检查。本机未生成任何真实结果图。

首次封存遇到中断时不得删除已有科学结果后静默重算。采集可在确认工作进程已退出后处理遗留 RUNNING 锁，以原种子/代码/版本恢复。校准和评估的排他锁同理；若已有首次评估文件，则保留并走透明复算/勘误流程。普通 SIGTERM 会记录失败并清理采集锁，SIGKILL/OOM 可能留下锁。

## 主持人在 local_node 的执行顺序

先审查并冻结本次实现，保留上述预注册 SHA。不要用实现提交替换 H。将输入设计产物带到 local_node 或在 local_node 重新生成后比较；data 下的文件被仓库忽略，需明确安排传输或生成。补齐源文件后执行：

```bash
cd .
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONUTF8=1
PY=python3
$PY scripts/magnet8_design.py
$PY scripts/magnet8_design.py --verify
$PY -m unittest tests.test_magnet8 -v
$PY -m unittest tests.test_magnet7 -v
$PY scripts/magnet8_sweep.py --dry-run
mkdir -p ./r6_logs
nohup setsid "$PY" scripts/magnet8_sweep.py --jobs 2 > ./r6_logs/sweep8_console.log 2>&1 &
```

驱动本身另写 `./r6_logs/sweep8.log`，状态追加到 `./ai4s_r8_status.md`。待 180 臂全部完成并检查失败日志后，按序执行：

```bash
$PY scripts/magnet8_calibrate.py
$PY scripts/magnet8_evaluate.py --replay-arms A1,M1
$PY scripts/magnet8_figures.py
```

如需全部 A/M 重放，应在首次评估前将上面的参数改为 `--replay-arms all`。首次评估后，由主持人另行独立复算和安排 reviewer_b 交叉评审。本任务没有调用 reviewer_b，也没有启动任何 local_node 工作。

交付字节哈希见 `M9_magnet_round8_researcher_a_impl.sha256`，涵盖新增实现、测试、报告、输入设计、全部冒烟产物和验证日志；清单自身哈希单独在交付消息给出，避免自哈希循环。
