# M2-C2 隔离实施方案（待审核提案）

状态：待审核提案（回应 `origin/codex/m2c2-plan-review-5` 的 R5-control、R5-manifest；历轮处置历史见 pi-report.md），不是冻结合同。基线 `origin/main = 51d497cae7f20872e5a5f9c8825fd0f83323a92f`（M2-C1 冻结发布之后）。本提案只规划，不包含宿主探测、不实现隔离、不运行真实 Hermes。

## 0. 关键状态事实（以 fetch 后 Git 状态为准）

- `origin/main = 51d497cae7f20872e5a5f9c8825fd0f83323a92f`（"Publish frozen reviewed M2-C1 boundary preflight and platform handoff"）。
- M2-C1 候选 `436e3b0e026580a6b39ece891e8ffe47ac1bb698`（`origin/hermes/m2c1`）按有限范围接受；Codex 终审 `cd92189`（`origin/codex/m2c1-review-3`）。
- 差异如实记录：main 上并不包含 C1 实现代码（`src/supervisor/workers/boundary.py`、`tests/unit/test_boundary.py` 均不在 `origin/main`），main 上只有 C1 的源规格（`tasks/M2C1/`）与冻结交接（`handoffs/M2C1/v1/`，bundle `595511a6...`）。C1 候选不是 main 的祖先（main 只前进了 3 个规格提交 `2805b1f..51d497c`）。因此 M2-C2 若需要 `validate_evidence` API，必须先解决 C1 代码的合入或复制问题（见 §1、§6）。
- M2-B 离线候选 `77920b99f279956cbe88bc2b3b2364b5ae078ce7`（`origin/hermes/m2b`）已接受但同样未合 main；`src/supervisor/agents/hermes.py` 不在 `origin/main`。
- M2-C1 交付的是纯证据校验器与平台盘点；所有 7 项边界的 observed/enforced 均为 `unknown`。C1 不证明任何 OS 隔离有效。
- 历史宿主捕获（`/tmp/m2c1-*` 探针输出 sha256）未被独立核实，不得升级为可信 attestation（Codex R3 明确保留该限制）。
- 真实执行入口：C1 的 `require_live_execution` 恒 raise `RuntimeError("live_execution_disabled")`；M2-B 的 `build_request` 恒拒绝。本提案不解锁任何真实执行。
- macOS 平台既有 55 个 pytest 失败（APFS 大小写不敏感 + 测试 regex 后果）在 C1 中单列记录；不得写成全套通过。Linux 全套（301 基线 + 新增）在 Codex R3 独立检出中通过。

## 1. 已实现能力 / 未合并候选 / 未验证能力 / 依赖关系

### 1.1 已在 main 的能力（`origin/main`，可信起点）

- M0：ProcessRunner（argv 数组、wall timeout、输出上限、取消、`tree_cleanup_confirmed` 诚实报告）、统一 AgentResult、Mock Adapter、最小事件。Linux 与模拟 Windows 有证据；原生 macOS 未实测。
- M0R/M1：干净 Git 基线检查、TaskBundle 冻结与 manifest 摘要、工作区快照、策略校验（allowed/forbidden、行/文件预算）、SQLite 操作意图（reserve/complete/unknown，不自动重放）。
- 6 个 JSON Schema、`scripts/check_specs.py`、CI 定义（Linux/macOS/Windows 基础检查，不调用真实 Agent）。
- 基线 301 项项目测试在 Linux 通过。

### 1.2 已接受但未合入 main 的候选

| 候选 | 分支 | 内容 | 状态 |
| --- | --- | --- | --- |
| `77920b99f279956cbe88bc2b3b2364b5ae078ce7` | `origin/hermes/m2b` | `src/supervisor/agents/hermes.py`（离线 HermesAdapter：`build_request` 恒拒绝、NDJSON 子集解析、身份绑定）、`tests/fixtures/hermes_cli.py`（白名单场景模拟进程）、70 新增 + 29 保护测试 | 已独立接受；未获 main 合并授权；不得以其不可用 API 为依赖（C1 合同同样如此声明） |
| `436e3b0e026580a6b39ece891e8ffe47ac1bb698` | `origin/hermes/m2c1` | `src/supervisor/workers/boundary.py`（`validate_evidence` 纯证据校验、`require_live_execution` 恒拒绝）、83 单元测试 + 23 保护测试、`deliveries/M2C1/boundary-evidence.json` | 按有限范围接受（证据格式 + 预检交付，不是 OS 隔离证明）；未合 main |

依赖关系：

- C1 代码与 M2-B 代码相互独立（C1 不 import `agents/hermes.py`；M2-B 不 import `workers/boundary.py`）。
- 两者都基于 `85fde60`/`2805b1f` 时代的 main，与当前 `51d497c` 的差异仅是 main 上新增的 C1 规格/交接文件（无生产代码冲突预期，但必须实测合并验证，不能假定）。
- **能力事实（已读 M2-B 候选代码确认，P1）**：已接受的 M2-B 候选 `77920b99f279956cbe88bc2b3b2364b5ae078ce7` 只包含离线 NDJSON 协议解析（`parse_result`）、`build_request` 恒拒绝（`RuntimeError` 含 `live_execution_disabled`）与模拟 CLI fixture（`tests/fixtures/hermes_cli.py` 不调用 Hermes/网络/模型/shell/凭证）。**M2-B 代码中不存在任何 MCP 配置加载、工具启用/禁用或执行能力**（`src/supervisor/agents/hermes.py` 全文无 MCP 引用）。合并 M2-B 不会补足这项能力，也不能用 mock/fixture 冒充软件能力。真正 MCP 工具禁用验证只能放在后续真实 Agent 独立合同；C2A 范围内 MCP 项一律 not_run/unknown。
- M2-C2 的实施前置（§6 收敛为唯一路径）：**C1 校验器 API 必须以绑定不可变 ref（`436e3b0e026580a6b39ece891e8ffe47ac1bb698`）的只读依赖方式引入**，不依赖 M2-B 合并；C2A 不运行真实 Hermes，因此 M2-B 合并不是 C2A 前置。

### 1.3 未验证 / 未实现能力（M2-C2 需要处理的）

- 任何 OS 级强制边界（文件、网络、MCP、凭证、进程树）：declared/observed/enforced 全部为 unknown。
- 本机可用隔离原语（C1 只读盘点，`enforced` 均为 unknown）：
  - `sandbox-exec`（`/usr/bin/sandbox-exec`，macOS 原生 Seatbelt）：存在。
  - `docker` CLI 29.8.0：存在但 daemon 未运行（无 socket），隔离原语实际不可用。
  - `screen`：PTY 隔离，不是进程隔离（不能当 sandbox 用，C1 报告 §9.2-4 已指出这是类别错误）。
  - 无 podman/orbstack/colima/lima/lxc；无完整 OS VM；存在第二用户账户 `emlszhou`（declared，未 exercise）。
  - 本地模型端点：`cc-switch` 127.0.0.1:15721、Python 服务 127.0.0.1:18080（仅端口盘点，不是网络隔离证据）。
- 真实 Hermes 非交互调用、fresh 会话启动方式、工具禁用能力：M2-A 调查有 declared/observed 证据，enforced 未验证；且已接受的 M2-B 候选不含任何真实工具/MCP 执行能力（§1.2 能力事实）。
- macOS 进程树回收：无 `/proc`，`_process_table()` 回退到 `ps -axo pid=,ppid=,pgid=,stat=,lstart=` 身份表（已读 `src/supervisor/workers/process.py` 确认）；`require_tree_cleanup=True` 时若身份表不可用直接返回 `environment_failure("unsupported: process tree cleanup")`，清理窗口内身份不可确认时返回 `None`。M2-A 曾间接观察到 `tree_cleanup_confirmed=None`，但**无 /proc 不等于必然 None**：按当前 Worker 实际能力实测判定。注意现有实现用 `ps` 的 `lstart` 字符串作身份，不能抵抗 PID 重用/重父化/脱离进程组，这是待验证弱点（§4.1 T6）。
- Linux CI 环境：`.github/workflows/ci.yml` 存在但未在本项目实际触发验证过（C1 的 Linux 全套通过来自 Codex 独立检出，不是本仓库 CI）。

## 2. macOS sandbox-exec 与 Linux 隔离后端可行性比较（收敛为唯一可执行推荐）

**唯一推荐：M2-C2（C2A 合同）在 Mac mini 上用 `sandbox-exec` + Seatbelt profile 实施全部拒绝测试；Linux 容器后端不属于 C2A，是后续独立合同的候选，本提案不同时保留两套可执行方案。**

先声明证据分级：**[E]** 已有本机/审核证据；**[D]** 文档/公开资料推断（本提案未在本机实测，列出依据来源）；**[H]** 待验证假设（C2A 实施阶段必须实测后才能从 H 升级为 E，不成立则诚实降级）。

### 2.1 Seatbelt 技术依据（列出来源，不直接把模糊推断当冻结规则）

- 二进制与机制：`/usr/bin/sandbox-exec` 存在 [E：C1 盘点 `ls -la`，argv/exit/sha256 在 `origin/hermes/m2c1:deliveries/M2C1/boundary-evidence.json`]；它是 BSD/macOS 的 **Seatbelt** 框架命令行封装，profile 规则由内核强制 [D：Apple 公开文档 `sandbox(5)` man page；本提案未在本机验证 man page 可读性，属文档推断，不靠想象补 URL/语法]。
- 语法（依据 `sandbox(5)` 文档 [D]，具体行为全部 [H] 待 C2A 实测）：
  - `(version 1)`；`(deny default)` 后按需 `(allow ...)`，或 `(allow default)` 后逐项 `(deny ...)`；C2A 推荐**默认拒绝 + 最小允许**方向。
  - 文件：`(allow file-write* (subpath "…"))`、`(deny file-write*)`；读限制可用 `(deny file-read* (subpath "…"))`（读 deny 的可行性标 [H]）。
  - 网络：文档中存在 `network*` 操作族（connect/bind 等）[D]；**按地址/端口粒度的 allow 规则能力是模糊区，标 [H]**：C2A 第一实验就是能力探测（全 deny / 按子路径 deny / 回环 allow 的可行性），不成立则网络边界降级为"全断网 + 无外部正向项"，不做模糊声明。
  - 进程：`(process-fork)`、`(process-exec*)` 可限制 [D]；fork 后子进程 profile 继承行为标 [H]。
  - 路径语义：profile 内路径解析、符号链接跟随、别名（`/tmp` → `/private/tmp`）处理标 [H]；**C2A 必须用 `realpath` 后的实际解析路径写 profile，并用符号链接逃逸子测试实测**。
- 平台一致性：本提案写作时的 Mac 元信息是 `Darwin Mac-mini.lan 27.0.0 / kernel 27.0.0 / arm64` [E：`uname -a`，本规划会话实跑]。但"平台存在性证据不等于当前可用"：C2A 合同开工时必须重新采集 `sw_vers`/`uname`/`sandbox-exec` 行为探针并记录，与合同记录不一致即停（防止跨机器/跨版本执行）。

### 2.2 不选其他后端的原因（仅记录，不保留为并行可选）

| 后端 | 不选原因 |
| --- | --- |
| Linux 容器（Docker/lima/colima） | Docker daemon 未运行 [E：C1 盘点]；安装/启动是宿主配置变更，授权面大；留给后续独立合同，不进入 C2A |
| 第二账户 + POSIX 权限 | 不满足威胁模型（同 UID 恶意代码不可防）[D] |
| 完整 OS VM | 未安装 [E：C1 盘点]，授权成本最高，未来候选 |

### 2.3 平台后端抽象（C2A 冻结的合同 API 方向）

- Worker 侧引入 `sandbox_profile` 概念：把"边界意图"（可写子树、只读子树、deny 子树、网络目标集合、进程策略）翻译为平台强制机制（当前唯一实现：Seatbelt profile 文本；Linux 容器 flags 留给后续）。
- 意图与实现分离：拒绝测试针对意图断言，不在测试里硬编码 Seatbelt 语法。
- 能力不足（某边界无法强制）→ 该边界 `enforced=unknown` + live 门禁关闭，不静默降级，不把未覆盖写进声明。

## 3. 威胁模型

区分 **OS 可强制的边界**（内核/运行时拒绝，测试可实证拒绝行为）与 **协调流程保证**（依赖会话纪律、Git 流程、人工核对，不是 OS 证据）。**最终门禁按此分类，不要求 7 项全部 `enforced=yes`**：MCP 当前无软件实现可验证（§4.1 T4），fresh_review 是流程边界；这两项不得计入 OS 强制门禁。

| # | 边界 | 性质 | 威胁 | OS 可强制部分 | 协调流程保证部分 |
| --- | --- | --- | --- | --- | --- |
| T1 | 文件系统 | OS 可强制 | 受测进程写授权根内、Worker 白名单外路径、写受保护子树、符号链接/穿越逃逸 | 可写范围限定为 `work/`；授权根内、Worker 白名单外与 `ro/`/`protected/` 全 deny | 冻结包导出到实施目录之外；实现者不 merge main |
| T2 | 控制面只读 | OS 可强制（文件）+ 流程 | 受测进程修改控制面存储/状态/策略配置 | 控制面 mock 位于授权根内 Worker 只读区；写 deny；SQLite 与证据目录不进入可写子树 | 控制面与执行面分目录（未实现为强制，当前是布局约定）；状态转换只在可信进程内发生 |
| T3 | 网络 | OS 可强制 | 受测进程外联下载供应链、回传数据 | C2A 用全断网 profile + 回环正向 allow 的对照设计（§4.1 T3）；网络规则粒度能力待 C2A 实测 | 端点清单由可信配置签发；真实认证不通过假密钥 |
| T4 | MCP | 当前不可验证（无软件能力） | Agent 经 MCP 工具获得文件/网络/命令副作用 | **无**：已接受的 M2-B 无 MCP 配置/禁用/执行能力（§1.2 能力事实），C2A 范围内一律 not_run/unknown | 未审计 MCP 默认禁用是设计意图，不是已实现行为；真正验证在后续真实 Agent 独立合同；不用 mock/fixture 冒充 |
| T5 | 凭证 | 混合 | 受测进程读取授权根内、Worker 不可读区凭证文件、环境变量全集泄漏 | 可读范围限定（合成凭证哨兵在授权根内 Worker 不可读区）；C2A 不接触任何真实凭证路径 | 真实环境 env allowlist 由 Adapter 构造最小环境（后续合同）；日志脱敏；密钥测试只用合成哨兵值 |
| T6 | 进程树 | OS 可强制（部分） | Worker 崩溃/取消后子进程逃逸、leader 退出但树未回收 | 取消作用于本任务可确认进程组（`start_new_session` + `killpg`，已读 main 上 `process.py` 确认）；fork/exec 策略可限制 [H] | `tree_cleanup_confirmed` 诚实三态；无法确认整树回收时不得宣布成功（§5）；不执行范围不明 pkill；ps 回退身份的弱点（PID 重用/重父化）见 §4.1 T6 |
| T7 | fresh review | 纯协调流程 | 实现者会话自我审核、同上下文续接、借分支名冒充新会话 | 无 OS 可强制部分 | 独立会话/进程记录；Reviewer 独立克隆精确候选；`fresh_session` 与 `independent_provider` 分开记录；同模型新会话只算上下文独立；分支存在 ≠ fresh |

不可约弱点的诚实声明：T4 在 C2A 范围内不可验证（无软件能力），不得由 Seatbelt "OS 拒绝测试"覆盖；T7 无法用 OS 边界单独保证；T5 中环境变量泄漏只能靠最小 env 构造 + 脱敏，不能靠 OS 完全阻止（进程可以 `printenv` 自己拿到的东西）；T6 的 ps 回退身份表不能抵抗 PID 重用与重父化。因此任何"全部 7 项 enforced=yes"的声明在本平台都不可信，验收必须逐项绑定拒绝测试证据，且门禁分类见 §3 开头。

## 4. 合成无秘密目录中的测试设计（全部目标为合成文件与自建回环服务）

### 4.0 通用规则

- 授权根：`/tmp/m2c2-sandbox/`（唯一；无其他临时目录）。attempt 目录布局（每 attempt 一个目录，`<attempt_id>` 为安全 ID）：
  - `work/`：合成 Git 仓库（Worker 可写子树，唯一）；
  - `ro/`：**Worker 只读材料**（冻结包、控制面 mock、自建回环服务脚本、**冻结 fixture 脚本（`ro/fixtures/`，sandbox 内 Worker 可读可执行**））；
  - `denied/`：Worker 应无法写的拒绝目标区（初始由可信 harness 填充，含合成 `AGENTS.md`、合成 `.git`、合成 `tests/protected/`，前后 sha256 校验）；
  - `out/`：Worker 可写区（正向测试产物、哨兵文件、符号链接逃逸测试用）；
  - `secret/`：Worker 应无法读的区（合成凭证哨兵，如 `SENTINEL_CREDENTIAL_M2C2_NOT_REAL`）；
  - `harness/`：harness 专属目录（Worker 全 deny：不可读、不可写）；子布局：`harness/profiles/`（Seatbelt profile 文件）、`harness/capture/`（Worker stdout/stderr 捕获，Worker 不可见、不可写）、`harness/evidence/`（每子项结构记录）、`harness/state/`（状态 sidecar）、`harness/deps/`（C1 依赖导出）。

  子目录总览：`work/`（Worker 可写）、`out/`（Worker 可写区）、`ro/`（Worker 只读，含 `ro/fixtures/`）、`denied/`（Worker 不可写）、`secret/`（Worker 不可读）、`harness/`（Worker 全 deny）。`summary.json` 由 harness 在持久化阶段统一生成到持久化根（引用持久化根相对路径），不在 attempt 内生成。
- 可信 harness 与受测 Worker 的权限分离（permission-request.md §2 逐项对应）：
  - **harness**（可信，运行在 sandbox 外）：可在授权根内任意写（setup/teardown）；可起自建回环监听服务；可排他创建/删除 attempt 目录；持有合成 profile 文件；唯一可执行 `harness/` 内写入与清理的主体；**唯一可写 `ro/fixtures/` 的主体**（fixtures 由 harness 写入，sandbox 内 Worker 只读执行）。
  - **Worker**（受测，运行在 `sandbox-exec -f <harness/profiles/<profile>>` 内）：可写仅限 `work/` 与 `out/`；只读 `ro/`（含 `ro/fixtures/`）；对 `denied/`/`secret/`/`harness/` 全 deny；网络默认全断网（仅 §4.1 T3 的正向/同目标对照 profile 对 harness 自建回环端点 allow）；env 白名单最小。
  - **Worker 输出捕获**：Worker 进程的 stdout/stderr 由 harness 通过管道直接捕获写入 `harness/capture/`（Worker 不能写入、不能篡改）；Worker 可写的 `work/` 与只读的 `ro/` 本身不作为证据源。
  - **attempt 目录创建规则**（防复用/符号链接/路径逃逸）：harness 在授权父根 `/tmp/m2c2-sandbox/` 下**排他创建**新 attempt 目录（`mkdir` 不带 `-p`，O_EXCL 语义：存在则拒绝并记 `attempt_exists`，不覆盖、不重用）；创建前用**路径组件检查**（逐段比对，非字符串前缀）验证目标父目录的 `realpath` 等于授权父根的 `realpath`；创建后验证该目录不是符号链接；所有后续路径操作先 `realpath` 解析再验证仍在授权根内（不跟随符号链接逃逸）；macOS `/tmp` → `/private/tmp` 别名在创建时绑定实际解析路径（`realpath /tmp/m2c2-sandbox`）并记录。
  - **sandbox 内命令范围**：Worker 只运行冻结 fixture 动作（§4.1 各子项列出的受测 argv；fixture 在 `ro/fixtures/`，sandbox 内可读可执行）；harness 专属操作（attempt 创建/清理、profile 生成、`ro/fixtures/` 写入、捕获写入、证据记录、只读盘点）不通过 `sandbox-exec` 运行，由 harness 直接执行，不计入 Worker 授权范围。
  - **清理**：只有 harness 可执行（`rm -rf` 仅限 `/tmp/m2c2-sandbox/<attempt_id>`，创建时已验证为真实目录非符号链接）；未知进程未清理时保留必要恢复证据（不先删现场），按 LOCAL-MODEL-RUNBOOK §5–6 处理。
- 每项测试：外部 watchdog（单项 wall ≤ 120 秒）、输出捕获 ≤ 64KiB（harness 管道截断并记 `output_limit`，截断必须终止命令并标记）、`finally` 清理（仅本 attempt 可确认 PID 集合，禁止通配 kill）、argv 用参数数组（禁止 `shell=True`/字符串拼接 shell）、**sandbox 内命令范围仅限冻结 fixture 动作**（`python3 <ro/fixtures 绝对路径> <固定参数>`；harness 专属操作不通过 `sandbox-exec` 运行）。
- **有效拒绝测试的定义**：受测动作真正启动并执行了越界动作，且被边界机制拒绝（deny 导致的非零退出/权限错误/连接拒绝），或受测动作成功但边界声明与之矛盾（= 隔离失败）。进程启动失败、命令不存在、参数错误 **不算** 有效拒绝测试，记 `not_run` 并给缺失前提。
- 每项测试产出 `boundary-evidence.json` 兼容的 check 记录（7 个 ID），用 C1 校验器（`validate_evidence`）做结构校验；`enforced=yes` 必须满足 `executed=True + observed=yes` 且绑定上述有效拒绝证据（联合证据齐备），否则保持 `unknown`。
- **逐子项记录字段与示例**：每子项记录存 `harness/evidence/<attempt_id>/<test_id>.json`，字段：`test_id`（如 `T1-R4`）、`boundary`（如 `filesystem`）、`action_argv`（**版本化 Python fixture**，形如 `["python3", "<fixture 绝对路径>", "--target", "<绝对路径>"]`，禁止 `/bin/sh -c "<string>"` 之类的 shell 重定向固化）、`action_exit_code`（受测动作**真实退出码**：int 或 `None`；**绝不写 errno**，errno 单独存 `action_errno`）、`action_errno`（受测动作**真实 OSError.errno 名称**，如 `EPERM`/`EACCES`/`ENOENT`/`ECONNREFUSED`/`EAGAIN`/`ETIMEDOUT`/`ENOSPC` 等，可空 `null`；**只由 fixture 通过 `try/except OSError as e: capture(e.errno)` 捕获**）、`harness_exit_code`（harness 断言退出码，0 表示断言正确包括预期拒绝）、`observed`（yes/no/unknown）、`enforced`（yes/no/unknown）、`capture_file`（持久化根相对路径 `capture/<test_id>.log`，**完整脱敏合成 captured bytes**，由 harness 管道捕获写入；Reviewer 实际可读取，不是仅事后 sha256）、`capture_sha256`（capture 文件 sha256）、`record_ref`（`summary.json` 对本记录的引用，持久化根相对路径 `evidence/<test_id>.json`）、`denied_target_sha256_before`/`denied_target_sha256_after`（拒绝目标区 sha256 前后比对，基线见 §4.0 单文件流程步骤 4）、`positive_control`（子段：`ran`、`argv`、`cwd`、`isolation_mode`（`allow_target_profile`，即仅隔离配置不同）、`exit_code`、`errno`、`target_sha_before`/`target_sha_after`）、`result`（pass/fail/not_run/unknown，按 §4.0 逐子项判定，**不写 pass unless 联合证据齐备**）、`class`（`positive` / `expected_refuse` / `timeout_cleanup` 之一）、`test_kind`（与 `class` 同源）、`recheck`（§4.0 单文件流程步骤 9 重放旁证）。

**逐子项判定：** `action_exit_code` **非零不等于拒绝**。判定**预期拒绝**（`result=pass, class=expected_refuse`）必须同时满足：
1. `action_exit_code != 0`（动作真失败）**AND**
2. `action_errno ∈ {EPERM, EACCES}` 是**真实权限错误**（不是 ENOENT/ECONNREFUSED/EAGAIN/ETIMEDOUT/EIO/ENOSPC 等环境性错误）**AND**
3. **同目标正向对照成功**——harness 用 §4.0 单文件流程步骤 3 的对照 profile（仅隔离配置不同）跑同一 fixture、同一 argv，`action_exit_code==0` 且越界断言满足（写入改目标/读到越界内容/连接成功）；不跑正向对照的拒绝项 `observed=unknown`（不可证为拒绝）**AND**
4. 拒绝目标存在且内容不变（`denied_target_sha256_before == after`，基线为步骤 4 harness 恢复后的初态）**AND**
5. 网络类还需 `connect()` syscall 直接命中 EPERM 而非 ECONNREFUSED（无监听）或 DNS 失败。

`action_exit_code == 0` 且越界副作用发生（目标被改/越界内容读到/未授权连接成功）= 隔离失败（blocking，"越界成功 ≠ 正向通过"）。`action_exit_code != 0` 但 `action_errno` 是 ENOENT/ECONNREFUSED/timeout 等非权限错误 = 环境性失败，**该 item `result=not_run, observed=unknown`**。timeout（watchdog TERM → 5 秒 → KILL）= `result=timeout_cleanup, observed=unknown`（仅当 PID 集合空 + 宽限期过）；`output_limit` 截断（capture 超 64 KiB）= `result=not_run, class=output_limit, observed=unknown`，截断必须终止命令并标记；启动失败 = `result=not_run, class=startup_fail, observed=unknown`；crash = `result=not_run, observed=unknown`。**四类各自分类，不写 pass**。

**示例（T1-R4 拒绝写 `denied/AGENTS.md`，版本化 Python fixture：fixtures 在 `ro/fixtures/`，harness 传入明确 `--target` 绝对路径，fixture 只解析固定 argv 不猜相对层级）：**

**sandbox 内 action_argv（拒绝 profile 与对照 profile 完全相同）**：

```json
[
  "python3",
  "/tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/t_r4_try_write_denied.py",
  "--target",
  "/tmp/m2c2-sandbox/<attempt_id>/denied/AGENTS.md"
]
```

**正向对照**：argv 与上完全一致（同一 fixture、同一 `--target` 指向同一 `denied/AGENTS.md`、同一 cwd）；**唯一差异是隔离配置**——对照 profile 明确 allow 该目标（`isolation_mode: "allow_target_profile"`），其余 profile 规则相同。对照由 §4.0 单文件流程步骤 3–4 执行：对照成功后 harness 把目标恢复初态，重测 sha256 建立拒绝测试基线。目标初始化与恢复都由 harness 独立完成，不靠 fixture 增删文件补偿；fixture 动作模式在两次运行中恒为 `O_WRONLY|O_APPEND`，无改变 syscall 模式的参数。

**`/tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/t_r4_try_write_denied.py` 内容（冻结版本化 fixture，只解析固定 argv）：**

```python
"""Fixture for T1-R4: attempt to open() --target for append (O_WRONLY|O_APPEND).

argv: --target <absolute_path>

Exits:
  0  -- write+append succeeded (positive control under allow-target profile)
  1  -- OSError caught, prints "errno=<n> name=<msg>" to stdout
  72  -- argparse error
"""
import argparse, os, sys

p = argparse.ArgumentParser(prog="t_r4_try_write_denied", allow_abbrev=False)
p.add_argument("--target", required=True, help="absolute path to attempt")
args = p.parse_args()

try:
    fd = os.open(args.target, os.O_WRONLY | os.O_APPEND)
    os.write(fd, b"pwned")
    os.close(fd)
except OSError as e:
    print(f"errno={e.errno} name={e.strerror or 'unknown'}")
    sys.exit(1)
sys.exit(0)
```

**fixture 内部 FSM**：
- `argparse` 错误 → exit 72，harness 记 `not_run, observed=unknown`（fixture 内部控制失败/观测不足按 unknown，不混作 OS 拒绝）。
- OSError EPERM/EACCES → exit 1，print `errno=1` / `errno=13`，harness 记 `errno="EPERM"`/`"EACCES"`，符合联合证据 → expected_refuse.
- OSError ENOENT/磁盘满/timeout → exit 1，harness 记相应 errno（不是 EPERM/EACCES）→ not_run, observed=unknown（环境性失败，不是 sandbox 拒绝证据）。
- exit 0 + 目标已改 = positive-control 通过（`work/AGENTS_positive.txt` 存在）；exit 0 + 拒绝目标 `denied/AGENTS.md` 已改 = **blocking**（隔离失败，越界成功即便 fixture 成功也是阻断，不是 positive pass）。拒绝读凭证/网络连接同理：越界成功 ≠ 正向通过。

**完整 test_id.json（T1-R4 拒绝项 + 正向对照）：**

```json
{
  "test_id": "T1-R4",
  "boundary": "filesystem",
  "action_argv": [
    "python3",
    "/tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/t_r4_try_write_denied.py",
    "--target",
    "/tmp/m2c2-sandbox/<attempt_id>/denied/AGENTS.md"
  ],
  "action_exit_code": 1,
  "action_errno": "EPERM",
  "harness_exit_code": 0,
  "observed": "yes",
  "enforced": "yes",
  "capture_file": "capture/T1-R4.log",
  "capture_sha256": "<64hex>",
  "record_ref": "evidence/T1-R4.json",
  "denied_target_sha256_before": "<64hex>",
  "denied_target_sha256_after": "<64hex>",
  "result": "pass",
  "class": "expected_refuse",
  "test_kind": "expected_refuse",
  "positive_control": {
    "ran": true,
    "argv": [
      "python3",
      "/tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/t_r4_try_write_denied.py",
      "--target",
      "/tmp/m2c2-sandbox/<attempt_id>/denied/AGENTS.md"
    ],
    "cwd": "/tmp/m2c2-sandbox/<attempt_id>/",
    "exit_code": 0,
    "errno": null,
    "isolation_mode": "allow_target_profile",
    "target_sha_before": "<denied_target_sha256_init>",
    "target_sha_after": "<sha256 after control write succeeded>",
    "restored_sha_after": "<denied_target_sha256_init>"
  }
}
```
- **capture 文件定位与 hash**：capture 文件在 attempt 内 `harness/capture/<attempt_id>/` 下，文件名 `<test_id>.log`，harness 在 Worker 进程退出后立即 `shasum -a 256` 计算并写入对应 `test_id.json` 的 `capture_sha256` 字段；capture 文件不进入 Worker 可写范围，Worker 不能篡改。capture 文件**包含完整脱敏合成 captured bytes**（截断至 64 KiB，stdout+stderr 合计；超限触发 `output_limit` 终止并标记），不是仅 sha256；Reviewer 必须能实际读取捕获验证拒绝行为。
- **summary 关联方法**：`summary.json` 是逐子项记录的索引数组，每条含 `test_id`、`record_ref`（逐子项记录相对持久化根的路径，如 `evidence/T1-R4.json`）、`result`、`test_kind`、`positive_control` 摘要、`cwd`、`action_argv`（完整 sandbox 数组）。持久化时由 harness 统一生成（引用指向持久化根相对路径，见 §4.0 证据包算法）。
- **动作 exit 与 harness exit 区分**：`action_exit_code` 是受测动作（sandbox 内 Worker 执行的 argv）的**真实退出码（int 或 None）**，**绝不写 errno**——errno 单独存 `action_errno`。`harness_exit_code` 是 harness 断言退出码，0 表示断言正确（包括预期拒绝）。C1 summary exit 0 不能冒充原动作 exit 0。
- **流程 fresh 的独立供应者按 provider 而不是模型名判定**：`independent_provider` 字段按实际 provider（如 `mlx-local` vs `minimax-cn`）判定，不按模型名（如 `Qwen3.8-27B-8bit` vs `MiniMax-M3`）判定；同 provider 不同模型名不算独立供应者。
- **单文件拒绝测试全流程**（§4.1 每项 `expected_refuse` 子项统一按此 11 步执行；全部由可信 harness 驱动，Worker 只在第 5、8 步被 sandbox 启动）：
  1. **目标初始化**：harness 独立创建/重建合成拒绝目标（如 `denied/AGENTS.md`，固定合成内容），记录 `denied_target_sha256_init`。
  2. **fixture 与 profile 校验**：harness 校验 `ro/fixtures/<t_id>.py` sha256 与冻结版本一致；确认拒绝 profile（Worker 全 deny 该目标）与对照 profile（明确 allow 该目标）都已生成。
  3. **正向对照（同 fixture、同目标、同参数、只换隔离配置）**：harness 用**允许该目标的对照 profile** 启动 `sandbox-exec` 跑同一 fixture、同一 argv、同一 cwd（无改变 syscall 模式的参数）；要求 exit 0 且 `target_sha_after != target_sha_before`（或网络/读类的对应断言满足），产出 `positive_control` 段（含 `isolation_mode: "allow_target_profile"`）。
  4. **对照恢复基线**：harness 把该目标恢复到 `denied_target_sha256_init` 记录的初态，重测 sha256 确认一致——拒绝测试基线由此建立，目标状态由 harness 独立完成，不靠 fixture 增删文件补偿。
  5. **拒绝动作**：harness 用**拒绝 profile** 启动同一 fixture、同一 argv、同一 cwd；管道捕获 stdout/stderr 到 `harness/capture/<attempt_id>/<test_id>.log`（≤ 64 KiB，超限记 `output_limit` 并终止）。fixture 可写目标仅限 `work/`/`out/`；拒绝目标在 `denied/`（全 deny）或 `secret/`（全 deny），fixture 对拒绝目标的写/读/连接动作在拒绝 profile 下应被 OS 拒绝。
  6. **目标不变校验**：harness 重测目标 sha256 得 `denied_target_sha256_after`，与步骤 4 的基线比对。
  7. **判定**：按 §4.0 逐子项判定（5 条联合证据）写 `result`/`class`/`observed`/`enforced`；越界副作用发生（目标已变/越界读到/未授权连接成功，即便 exit_code=0）= blocking，attempt 终止且保留现场。
  8. **写逐子项记录** `harness/evidence/<attempt_id>/<test_id>.json`（字段见 §4.0 示例；`record_ref` 写 `evidence/<test_id>.json`，`positive_control` 含对照 argv/隔离模式/target sha 前后）。
  9. **重放复核**：harness 用拒绝 profile 重跑同一 fixture/argv，确认拒绝可复现（exit/errno 一致、目标仍不变）；结果只作旁证记入该子项 `recheck` 段，不改变判定。
  10. **网络/读类对照同理**：同一 fixture、同一文件/端点、只换隔离配置（对照 profile 明确 allow 该端点/文件）；纯回环证据只覆盖实际端点/协议。
  11. 完成后进入 #13 进程残留确认；capture 与记录文件留在 attempt 内，随 #14–#16 持久化并清理（下节算法）。
- **证据包生成与清理算法**（唯一顺序，不可重排、不可预填未来结果；对应 §4.2 纸面演练 #14–#16）：
  1. **持久化并改好引用（演练 #14）**：harness 建持久化根 `deliveries/M2C2/evidence/<attempt_id>/`，用 `shutil.copy2` 把 attempt 内 `harness/evidence/<attempt_id>/*` 与 `harness/capture/<attempt_id>/*` 复制到持久化根的 `evidence/`、`capture/`，再写 `summary.json`（引用持久化根相对路径）、`process_tree.json`、`denied_manifest.json` 到持久化根。**所有会改变字节的内容变换在这一步完成**（引用重写、脱敏擦除并记 `redaction_event`）；变换后 capture 原字节 hash 不变，JSON 被改引用则记录原/最终分别摘要，不要求字节相同。复制前后对每个 capture 文件核对 hash，不一致 → 持久化失败。
  2. **预清理校验（演练 #15）**：harness 在持久化根逐文件重读算 sha256、解析 `summary.json` 与逐子项记录的所有引用（`record_ref`/`capture_file`），确认每个被引用文件都存在且 hash 与记录值一致。任一不可访问或不一致 → 持久化失败 → 不删 attempt（保留现场）→ NEEDS_HUMAN。前置校验只依赖步骤 1 已产生的文件，**永不依赖未来记录**。
  3. **生成 pre-cleanup manifest（演练 #15 后半）**：基于持久化根写 `manifest.json`——条目 = 步骤 1 落定的全部文件（`evidence/*`、`capture/*`、`summary.json`、`process_tree.json`、`denied_manifest.json`、`redaction_events` 如有），每条目 `{relative_path, sha256, bytes}`；**不含 manifest 自身，也不含尚未产生的 `cleanup.json`**（无自引用）。manifest 落盘后重读自身与全部条目复算 sha256 比对；任一不一致 → 不进入真实清理。
  4. **真实清理（演练 #16 第 1 段）**：步骤 3 全部一致后，harness 执行 `rm -rf /tmp/m2c2-sandbox/<attempt_id>`（精确路径，创建时已验证为真实目录非符号链接），随后 `ls` 该路径验证 ENOENT；记录 argv/exit/完整 ls 输出/时间戳。**不得提前填 ENOENT 或 exit_code=0**。
  5. **写 cleanup.json（演练 #16 第 2 段）**：清理真实执行完成后在持久化根写 `cleanup.json`：`attempt_id` / `cleanup_argv` / `cleanup_exit_code` / `post_cleanup_ls_output` / `cleanup_enoent_confirmed` / `cleanup_timestamp_utc` / `pre_cleanup_manifest_sha256`（步骤 3 的 `manifest.json` 文件 sha256）。**不含最终 manifest 摘要**（避免循环）。清理失败 → 如实写 cleanup.json，attempt 记"清理未确认" → NEEDS_HUMAN，不重试。
  6. **生成最终 manifest（演练 #16 第 3 段）**：更新 `manifest.json` 追加 `cleanup.json` 条目（其 sha256 以步骤 5 落盘文件实算）；**manifest 始终不包含自身，也不包含 `CHECKSUMS.sha256`**；最终 manifest 落盘后写外置 `CHECKSUMS.sha256`（含 manifest.json 与全部条目的 sha256，一行一个）。
  7. **最终校验与提交（演练 #16 第 4–5 段）**：harness 重新打开持久化根内每个被引用文件（含 `CHECKSUMS.sha256` 所列全部条目）重算 sha256 与 manifest/CHECKSUMS 比对；全部一致才算证据包完整。随后 `git add deliveries/M2C2/evidence/<attempt_id>/ && git commit && git push`（已授权范围）。任何 mismatch → attempt 证据失败，保留现场，NEEDS_HUMAN。**不得在已删 attempt 内再复制任何东西，不得提前填成功**。
  8. **最终证据包树**（`deliveries/M2C2/evidence/<attempt_id>/` 下）：
     ```
     evidence/<attempt_id>/
     ├── manifest.json          # 全部文件条目；不含自身、不含 CHECKSUMS.sha256
     ├── CHECKSUMS.sha256       # 外置摘要表：manifest.json + 全部条目
     ├── summary.json           # 逐子项索引（record_ref → evidence/<test_id>.json）
     ├── process_tree.json      # T6 ps 脱敏观察与 tree_cleanup_confirmed
     ├── denied_manifest.json   # denied/ 区 sha256 前后
     ├── cleanup.json           # 真实清理结果 + pre-cleanup manifest sha256
     ├── evidence/<test_id>.json
     └── capture/<test_id>.log
     ```

### 4.1 逐项测试

每条格式：**允许行为（应成功）/ 拒绝行为（应失败）/ 预期结果 / 失败判定 / 清理**。

**T1 filesystem**

- 允许：在 `work/` 内创建/修改/删除文件；`git` 在 `work/` 内 commit。
- 拒绝（全部目标在授权根内，不碰真实仓库）：
  1. 写 `denied/AGENTS.md`（合成，应 deny）；
  2. 写 `denied/.git/config`（合成，应 deny）；
  3. 写 `denied/tests/protected/test_x.py`（合成，应 deny）；
  4. 写授权根内、Worker 白名单外路径（如 `/tmp/m2c2-sandbox/<attempt_id>/denied/AGENTS.md`，harness 预先创建并记录 sha256，测试后校验未变）；
  5. 符号链接逃逸：`work/link -> denied`，经 link 写 `denied`（应 deny 或按解析后路径 deny，实测后记录真实行为）；
  6. 路径穿越 argv `../`（Worker 层路径解析拒绝，流程级）。
- 预期：允许项 exit 0 且产物在预期位置；拒绝项全部失败，`denied/` 与 `secret/` sha256 前后一致。
- 失败判定：任一拒绝项成功写入 = 隔离失败（blocking）；允许项失败 = 后端配置错误（记录为 ENVIRONMENT_FAILURE 候选，需核对 profile）。
- 清理：统一 §4.0 单文件拒绝测试全流程与证据包算法；`denied/`/`secret/` 单独验证未被触碰。

**T2 control_readonly**

- 允许：Worker 读 `ro/frozen-task-bundle`、读 `ro/control/state.db` 只读字段。
- 拒绝：经文件路径写 `ro/control/state.db`（deny）；经 `work/` 内符号链接指向 `ro/control` 写（同 T1-5）。
- 预期：读成功；写全部失败且 `ro/control/` sha256 前后一致。
- 失败判定：控制面字节变化 = blocking。
- 清理：控制面 mock 每次测试前从固定源重建（可重放，无宿主副作用）。

**T3 network**（全部目标为 harness 自建回环服务，不访问现有 15721/18080 未知协议服务，不连接 93.184.216.34）

- 允许：连接 harness 自建回环服务 `127.0.0.1:<harness端口>`（harness 起固定回环监听，Worker 用 Python 标准库 socket，2 秒超时，固定字节回读）。
- 拒绝：
  1. 连接 harness 起的第二个回环服务（`127.0.0.1:<harness端口2>`，未授权）—— 该端口确认 LISTEN（排除 ECONNREFUSED 歧义）；
  2. 连接回环上无监听的端口（对照，预期 sandbox deny 而非无监听）；
  3. UDP 探测（若 profile 不区分，记能力未知，不宣布通过）。
- 判定区分：拒绝原因必须是权限/策略拒绝（`EPERM`/`ECONNREFUSED` 由 sandbox 产生），不是 DNS 失败或网络不可达；无法区分时该子项记 `observed=unknown`。
- 失败判定：未授权端点连接成功 = blocking。
- 清理：harness 自起的监听端口在 finally 关闭；无宿主副作用。
- 范围声明：纯回环证据只证明实际覆盖的端点/协议拒绝，**不能直接声明所有外网/UDP/IPv6 均被验证**。

**T4 mcp**（P1：当前不可验证，全部 not_run/unknown）

- 允许：无（当前无软件能力可测）。
- 拒绝：无（不用 mock/fixture 冒充软件能力）。
- 记录：`executed=false, observed=unknown, enforced=unknown`，`reason` 写明"M2-B 候选无 MCP 配置/禁用/执行能力（§1.2），真正验证移到后续真实 Agent 独立合同"。
- 失败判定：不适用。
- 清理：无。
- 依赖声明：C2A 不依赖 M2-B 合并；M2-B 合并也不补足此能力。

**T5 credentials**（全部目标为合成哨兵，不访问真实凭证）

- 允许：Worker 使用 env allowlist 中的合成变量（如 `M2C2_SYNTH_TOKEN=SENTINEL_NOT_REAL`）。
- 拒绝：
  1. 读 `secret/.env`（合成哨兵，在 Worker 不可读区，应 deny）；
  2. 读 `secret/auth.json`（合成哨兵，应 deny）；
  3. 环境泄漏：子进程 `printenv` 输出中不得包含 allowlist 之外的变量名（断言变量**名**集合，不断言值）。
- 失败判定：合成哨兵可读 = blocking（且停止后续所有测试）；哨兵值出现在非预期输出中 = 泄漏失败。
- 清理：哨兵文件随 attempt 清理；C2A 不接触任何真实凭证路径（`~/.hermes/.env` 等不访问）。
- 范围声明：合成哨兵只证明授权根内不可读区的行为；真实凭证路径的隔离在后续真实 Agent 合同验证。

**T6 process_tree**

- 允许：Worker 启动一个受控子进程（如 `sleep 1` 包装脚本），正常完成后整树退出。
- 拒绝/边界：
  1. 子进程再 fork 孙进程后 Worker 超时取消：断言取消后 `work/` 无残留监听/文件句柄，ps 过滤本 attempt 可确认 PID 集合后无存活后代；
  2. `tree_cleanup_confirmed` 三态验证：能确认回收 → True；确认有残留 → False；无法确认（ps 回退不可判定）→ None。**无 /proc 不等于必然 None**：按当前 Worker 实际能力实测判定（已读 `process.py` 确认 `_process_table()` 回退到 `ps -axo pid=,ppid=,pgid=,stat=,lstart=` 身份表，`require_tree_cleanup=True` 时身份表不可用直接 `environment_failure`）；
  3. 子进程尝试读取父进程（Worker）的 `/dev/fd` 或控制面路径：由 T1/T5 规则覆盖，这里只记录进程维度观察。
- 失败判定：残留后代存活超过宽限期且可确认 = 失败；把 None 写成 True = 证据违规（blocking）。
- 清理：只 kill 本 attempt 可确认 PID 集合（记录 argv），禁止 `pkill` 通配；清理后复查 ps。
- 身份弱点声明：现有 `ps` 回退用 `lstart` 字符串作身份，不能抵抗 PID 重用/重父化/脱离进程组；C2A 需实测该弱点。进程组（`start_new_session` + `killpg`）不能解决脱离进程组的问题，**不作为整树确认兜底**；有无法跟踪的后代只能 `unknown`，另提方案（不在本提案暗含例外）。当前 Worker 既有实现（`start_new_session` + `killpg` + `ps` 回退）不在 C2A 隐含改写，C2A 只测试现有能力。

**T7 fresh_review**

- 无 OS 测试。验证物是**流程证据**：两个独立会话/进程启动记录（会话 ID 或进程启动日志，来源说明）、Reviewer 独立克隆精确候选的 git 记录、`review.schema.json` 中 `fresh_session=true` + `independent_provider` 如实（同模型则 false）。
- 通过条件：证据齐全且可被第三方核对；分支名/角色名不同**不是**通过证据。
- 失败判定：只有单一会话记录或 Reviewer 参与过实现 = 该候选的审核无效，重开 fresh 会话。
- 清理：无。

### 4.2 完整 attempt 纸面演练（C2A 一次性走完依赖→创建→profile→正反测试→清理）

下列演练从依赖准备到清理，每一步标注**执行主体**、**argv 类别（§4 P1–P9 + 外部命令）**、**真实路径**、**触发门禁**、**回收动作**、**预期与失败处置**。本演练是纸面预测（不是真实运行）；它存在的目的是把每一项权限与验收条件从"已声明"推平到"应一次跑通"。本演练本轮不实施（无授权）。

| # | 阶段 | 执行主体 | argv/类别 | 真实路径 | 触发门禁 / 通过条件 | 失败处置 / 回收 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 平台元信息核对 | 本机 harness（不在 sandbox 内） | §4 P7 只读：`sw_vers`、`uname -a`、`which sandbox-exec`、`ls -la /usr/bin/sandbox-exec`（仅 Python 读，不写 shell redirect 当只读命令；`shasum -a 256` 对只读源文件计算） | 本机直接调，cwd=`/` | 元信息与 §2.1 一致；`/usr/bin/sandbox-exec` 存在且可执行 | 元信息不符 → 立即停，本机 NEEDS_HUMAN，不进入 §6 |
| 2 | 授权父根探查 | harness | `realpath /tmp/m2c2-sandbox/`（记录绑定实际解析路径：macOS `/private/tmp/m2c2-sandbox`） | `/tmp/m2c2-sandbox/` | 父根存在且为目录（首次）或不存在（首次创建后存在） | 父根是符号链接或路径组件不匹配 → 拒绝使用；NEEDS_HUMAN |
| 5 | attempt 目录排他创建 | harness | `mkdir -p /tmp/m2c2-sandbox/`（首次，父根）；对每个新 attempt：`os.mkdir('/tmp/m2c2-sandbox/<attempt_id>', 0o755)`（**不带 -p**，O_EXCL 语义：存在则抛 `FileExistsError` → 记 `attempt_exists` 不覆盖、不重用） | `/tmp/m2c2-sandbox/<attempt_id>/` | attempt 目录是真实目录（`os.path.islink` False + 路径组件逐段比对等于父根 `realpath`） | attempt 已存在 → 改 attempt_id；符号链接或路径逃逸 → 拒绝使用此 attempt，NEEDS_HUMAN |
| 6 | 子目录创建 | harness | `os.makedirs('<path><subdir>', exist_ok=False)` Python 调用（**不是 `mkdir -p` 命令**）创建 `work/ ro/ denied/ secret/ harness/{profiles, capture, evidence, state, deps}` + `ro/fixtures/`（C1 依赖导出需 `harness/deps/`；fixtures 在 `ro/fixtures/`，Worker 可读可执行） | 同上 | 子目录全部为真实目录，非符号链接 | 任何子目录创建失败 → 整体 attempt 失败，按 §4.0 证据包算法尽力持久化已完成部分 + 清理 attempt |
| 7 | ro/fixtures 写入 | harness | `open('/tmp/m2c2-sandbox/<attempt_id>/ro/fixtures/<t_id>.py', 'wb').write(...)` Python 文件 I/O（**不是 `cat >` shell 重定向**）；fixtures 内容版本化提交在 `tests/fixtures/`；每个 fixture 只解析固定 `--target`/`--endpoint`/`--secret-dir`/`--child-script` 等 argv，不猜相对层级 | `<attempt>/ro/fixtures/<t_id>.py` | 所有 fixture 写入成功；harness 校验 fixture 文件 sha256 | fixture 写入失败 → 整体 attempt 失败，清理 |
| 3 | C1 依赖准备（在 #5、#6、#7 之后执行） | harness（运行在获准目录 `/Users/william/Public/AI project/supervisor-M2A` 内，非 sandbox） | `python3 -c 'import subprocess; subprocess.run(["git","-C","/Users/william/Public/AI project/supervisor-M2A","rev-parse","436e3b0e026580a6b39ece891e8ffe47ac1bb698:src/supervisor/workers/boundary.py"], capture_output=True, check=True, text=True)'` 取 `blob_oid`（**用 `<commit:path>` 语法——不是 `^{blob}`，那个会 deref 到 tree 失败——codex R4 独立实测确认**）；`python3 -c '... cat-file blob <blob_oid> ...'` 取 bytes（限制 ≤ 64 KiB，harness 检查 `len(bytes) <= MAX_DEP_BYTES`，否则 ENVIRONMENT_FAILURE；exit_code != 0 → ENVIRONMENT_FAILURE）；`open('<attempt>/harness/deps/boundary.py', 'wb').write(cat_file_bytes)`（Python 文件 I/O 禁 shell redirect；**禁 `cp -R` 命令**）；`hashlib.sha256(cat_file_bytes)` 与重读落盘文件的 `hashlib.sha256(open(path,"rb").read())` 比对；可选对象级核对 `git hash-object --no-filters --stdin` 拿 `git_blob_oid_from_bytes` 与 step 1 的 `blob_oid` 比对；落盘到 `<attempt>/harness/deps/c1-boundary-manifest.json`（含 `blob_oid, expected_sha256, actual_sha256, git_blob_oid_from_bytes, source_commit, source_path, attempt_id, importer_python_module_name`）；`python3 -c 'import importlib.util; spec = importlib.util.spec_from_file_location("c1_boundary", "<attempt>/harness/deps/boundary.py"); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); assert hasattr(module, "validate_evidence")'`（**禁止 `sys.path` 注入——spec_from_file_location 是标准方式**） | `<attempt>/harness/deps/boundary.py`（attempt 内） | 两步 hash 一致 + importlib 加载成功 + `validate_evidence` 可调用 | 不一致/加载失败 → 停 C2A，记 ENVIRONMENT_FAILURE；不重试；不换源；不复制进生产模块（`src/supervisor/`）；不动 sys.path；不 shell redirect 作只读 |
| 8 | 合成材料填充 | harness | `work/.git init`、`work/AGENTS.md 写入`、`work/.gitignore`、`work/tests/protected/test_x.py 写入`；`ro/frozen-task-bundle` 从获准只读路径（`handoffs/M2C2/v1/task-bundle/`，需 main 内引入 — **本提案 §10 列为待办 P-A 依赖；若 main 未有 vendored 副本则拒绝开始本轮**）；`ro/control/state.db`（控制面 mock）；`secret/.env`/`secret/auth.json`（合成哨兵，固定内容如 `SENTINEL_CREDENTIAL_M2C2_NOT_REAL`） | attempt 内对应路径 | sha256 前后一致；`secret/` 内容仅由 harness 知晓 | 填充失败 → 整体 attempt 失败，清理；`secret/` 内容被读（PT3 失败）→ 立即停 attempt 全部后续测试 |
| 9 | 拒绝目标区填充 | harness | `denied/AGENTS.md`、`denied/.git/config`、`denied/tests/protected/test_x.py` 写入；记录 sha256 (before) | attempt 内 `denied/` | sha256 写入 `harness/evidence/<attempt_id>/denied_manifest.json`（harness 专属） | 写入失败 → attempt 失败，清理 |
| 10 | Seatbelt profile 生成 | harness | 生成 `harness/profiles/<profile>` 文本（`(version 1) (deny default)` + 最小 allow 集合：file-write\* (subpath "work")；file-read\* (subpath "ro") + 必需的 `/usr/lib/*`、`/System/*`、`/dev/*`、harness 写入的 profile 路径不在 Worker 可读范围内 — 必须在 profile 中 deny 自身路径）；**`/coresignal/sandbox` 等未核实机制路径不得写入 profile** | `harness/profiles/<profile>.sb` | profile 文本语法符合 `sandbox(5)` 文档 [D]，具体行为 [H] 待 #10 探针 | 生成失败 → attempt 失败，清理 |
| 11 | sandbox 能力探针 | harness | 多次 `/usr/bin/sandbox-exec -f <profile> -- /usr/bin/true` / `/usr/bin/false` / 读写小文件，记录每条 argv/exit_code/errno/sha256；同时确认对照 profile（allow 指定目标）可生成 | 启动自 sandbox 文档规定 | 网络全断网、读 `ro/` allow、写 `work/` allow、读/写 `denied/` deny（拒绝 profile）；对照 profile 可写该目标 | 任一 deny/allow 与预期不符 → 相应边界降级为 `enforced=unknown`（不写假通过），记录实测行为 |
| 12 | 正向测试（应在 OS 允许） | harness 启动 sandbox 执行 Worker（每个测试用**版本化 Python fixture**，fixtures 在 `ro/fixtures/`，Worker 可读，harness 显式列实际 argv/工作目录） | T1：在 `work/` 内 `python3 <attempt>/ro/fixtures/t_posix_write_work.py`（harness 提前 `rm -f` + 记录初始 sha256）；T2：读 `ro/control/state.db` 只读字段 fixture（harness 提前写入合成控制面 mock）；T3：连接 harness 自建回环 #1 fixture（harness 用 Python `socket`/`socketserver` 起 `127.0.0.1:<port>`，2s 超时，固定字节回读，**harness 显式传 `--endpoint 127.0.0.1:<port>`**）；T5：使用 env allowlist 中 `M2C2_SYNTH_TOKEN=SENTINEL_NOT_REAL` 做 `printenv` 变量名集合断言 fixture；T6：Worker 启动受控子进程（深度 ≤ 2、固定时长 ≤ 5 秒）正常完成 fixture | sandbox 内 argv（`python3 <fixture> <argv...>`，含 cwd）；harness 用 `subprocess.Popen(stdout=PIPE, stderr=STDOUT)`（禁 shell redirect）管道捕获 → attempt 内 `harness/capture/<attempt_id>/<test_id>.log`（**完整脱敏合成 bytes**） | `action_exit_code==0` 且 `harness_exit_code==0` 且 `action_errno=null` 且 harness 断言满足（文件存在/字节正确/连接字节匹配等，不是仅看 exit_code） | 任一 action=death/超时 → watchdog 触发：TERM → 5 秒宽限 → KILL（仅本 attempt PID 集合）；该 item `result=timeout_cleanup, observed=unknown`；启动失败 → `class=startup_fail`；output_limit 截断 → `class=output_limit` 终止命令并标记 |
| 13 | 拒绝测试（统一单文件流程） | harness 对每项 `expected_refuse` 子项执行 §4.0 单文件拒绝测试全流程（11 步）：目标初始化 → fixture/profile 校验 → 同目标正向对照（只换隔离配置）→ harness 恢复目标建基线 → 拒绝动作 → 目标不变校验 → 判定 → 写逐子项记录 → 重放复核 | T1 R1–R6（含符号链接、路径穿越）；T2 C1/C2；T3 N1/N2/N3；T5 K1/K2/K3；T6 PT1/PT2（`test_kind=timeout_cleanup`，按 timeout_cleanup 联合证据：PID 集合空 + 宽限期过） | sandbox 内 argv（含 cwd = `<attempt>/`）；harness 管道捕获 | `expected_refuse` 联合 5 条（见 §4.0 逐子项判定）：`exit_code!=0` + `errno∈{EPERM,EACCES}` + 同目标对照 profile 正向 `exit_code==0` + 目标 sha256 基线不变 + 网络类 `connect()` 直接命中 EPERM；越界副作用发生（目标已变/越界读到/未授权连接成功，即便 exit_code=0）= blocking；fixture argparse 错误 → `not_run`（不混作 OS 拒绝） | blocking → 整 attempt 失败，保留现场；ENOENT/ECONNREFUSED/timeout 等非权限 → `result=not_run, observed=unknown`，不可声明拒绝 |
| 13 | 进程残留确认 | harness 在 attempt 结束时 | `ps -axo pid=,ppid=,pgid=,stat=,lstart=`（仅本 attempt 可确认 PID 集合）；按 §5 决策表赋值 `tree_cleanup_confirmed`：能确认 → True；确认残留 → False；不可判定（ps 回退身份表不可用）→ None | attempt 内 PID 集合 + `ps` 输出（脱敏：仅 pid/ppid/pgid/argv 首 token） | 写入 `harness/evidence/<attempt_id>/process_tree.json` + `summary.json` | None → live 门禁保持关闭（`full_pass` 仍要求 T6 通过，但如 T6=None 整体只能 partial，不能 false pass） |
| 14 | 证据持久化并改好引用 | harness 在 attempt 结束、真实清理**前** | 按 §4.0 证据包算法步骤 1–2：1) `os.makedirs('<persist>/<attempt>', exist_ok=True)`（Python mkdir）；2) `shutil.copy2` 把 `<attempt>/harness/evidence/<attempt_id>/*` 与 `<attempt>/harness/capture/<attempt_id>/*` 复制到 `<persist>/<attempt>/evidence/`、`capture/`；3) 写 `summary.json`（`record_ref` 指向持久化根相对路径如 `evidence/T1-R4.json`）、`process_tree.json`、`denied_manifest.json`；4) 内容变换（引用重写、脱敏）全部完成；5) **预清理校验**：重读持久化根每个被引用文件算 sha256、比对记录值、确认全部可访问 | `<persist>/<attempt>/` = `/Users/william/Public/AI project/supervisor-M2A/deliveries/M2C2/evidence/<attempt_id>/`（独立写入根，**Worker 全 deny**，是提案待批准范围，**非 git push 隐式授予**） | 全部 capture/evidence 文件复制后 hash 与 attempt 内一致；全部引用文件存在且 sha256 与记录值一致 | 持久化失败或预清理校验任一项不通过 → attempt 失败，**不清理 attempt**（保留现场），NEEDS_HUMAN |
| 15 | 生成 pre-cleanup manifest | harness | 按 §4.0 证据包算法步骤 3：基于持久化根写 `manifest.json`——条目 = `evidence/*`、`capture/*`、`summary.json`、`process_tree.json`、`denied_manifest.json`、`redaction_events`（如有）；每条目 `{relative_path, sha256, bytes}`；**不含 manifest 自身、不含尚未产生的 `cleanup.json`**；落盘后重读自身与全部条目复算 sha256 比对 | 同上 | 全部条目 sha256 一致 | 任一不一致 → 不进入真实清理；保留现场，NEEDS_HUMAN |
| 16 | 真实清理 → cleanup.json → 最终 manifest → 最终校验（顺序固定） | harness（仅 harness，不通过 sandbox-exec） | 按 §4.0 证据包算法步骤 4–7：1) **真实清理** `rm -rf /tmp/m2c2-sandbox/<attempt_id>`（精确路径）+ `ls` 验证 ENOENT，记录 argv/exit/完整 ls 输出/时间戳，**不得提前填**；2) 持久化根写 `cleanup.json`（含 `pre_cleanup_manifest_sha256`，**不含最终 manifest 摘要**）；3) 更新 `manifest.json` 追加 `cleanup.json` 条目（实算 sha256；仍不含自身），写外置 `CHECKSUMS.sha256`（含 manifest.json 与全部条目）；4) **最终校验**：重读持久化根每个被引用文件重算 sha256 与 manifest/CHECKSUMS 比对；5) 通过后 `git add + commit + push` 证据包 | 同上 | 最终校验全部一致；`cleanup_enoent_confirmed` 反映真实 ls 结果 | 清理失败 → 如实写 cleanup.json，attempt 记"清理未确认"，NEEDS_HUMAN，不重试；最终校验 mismatch → 证据失败，保留现场，NEEDS_HUMAN；不得在已删 attempt 内再复制任何东西 |

**演练整体一致性自检（用户/Reviewer 复核时按此核对）：**

- 所有写入路径都在 `/tmp/m2c2-sandbox/<attempt_id>/` 内；harness 持久化副本写 `/Users/william/Public/AI project/supervisor-M2A/deliveries/M2C2/evidence/<attempt_id>/`（授权根外，Worker 不可达，版本控制内）；其他一切路径一律零写入（与 §6 拒绝目录一致）。
- 执行主体分级清晰——harness（sandbox 外）/ 受测 Worker（sandbox 内）/ Reviewer（独立 fresh 会话，process.py 路线外）；三主体不互授权限。
- argv 类别与 §4 P1–P9 一一对应；sandbox 内命令范围严格只跑 §4.1 列出的受测 argv（P3–P7 类别中除 P8 之外，含拒绝项的同目标对照 profile 运行——同 fixture、同 argv、只换隔离配置）；harness 专属操作（#3 #5 #6 #7 #8 #9 #10 #14 #15 #16）不通过 `sandbox-exec` 运行，不在 P2 授权内。
- 通过条件按 acceptance-matrix 通用约定；partial vs full_pass 按 §4.2 通用规则 + acceptance-matrix 通过条件定义统一。
- 失败处置按 §5 决策表；崩溃/断线按 LOCAL-MODEL-RUNBOOK §5–6。
- 真实 Hermes 不在任何 argv；任何 `hermes chat/agent` 调用超出 C2A 范围（Step 3 独立合同）。
- 没有任何 `sudo` / `chflags` / `chmod`（授权目录外）/ `launchctl` / `systemsetup` / `pfctl` / `networksetup`；不在授权内。

**纸面演练结果（本轮交付，不实施）**：预期失败/降级点（提前标红，避免实施时归错人）：

1. **#3 C1 依赖** — 若 `handoff/M2C2/v1/task-bundle/` 不在 main 上（与 C1 同等待遇），本演练预期 `ENVIRONMENT_FAILURE`，C2A 立即停。这是 C2A 的真实前置，不在 C2A 范围内解决（走独立规格）。
2. **#9 Seatbelt profile** — `[H]` 待实测的具体行为：网络 allow 粒度、读 deny、fork 后继承、`/tmp` 别名绑定；任一不成立 → 相应边界降级 `enforced=unknown`，不写假通过。
3. **#10 网络：纯回环证据只证明实际覆盖的端点/协议拒绝** — 不声明外网/UDP/IPv6 全部被验证。
4. **#13 进程树条件 → T6 unknown (None)** — macOS 平台按 `process.py` 实测判定（已读源码确认 `ps` 回退身份表）；按 §5 决策表 None 触发门禁保持关闭，**整体只能 partial**。
5. **#16 清理后 ENOENT 校验** — 若 macOS `realpath` 路径组件检查失败或符号链接尝试 → attempt 拒绝创建；演练预期此路径走不到 #16。预清理校验（#14 步骤 5）在真实清理之前，只依赖已持久化文件；最终 manifest 单向引用 cleanup.json（含 pre-cleanup manifest 摘要），无自引用。

## 5. `tree_cleanup_confirmed` 决策表

| 观测事实 | 值 | 单项测试结论 | 整个 attempt 是否可宣布成功 | 后续动作 |
| --- | --- | --- | --- | --- |
| 有确定证据：本 attempt 全部后代进程已退出（ps/proc 精确匹配 PID 集合为空） | `True` | 通过（若其他项也过） | 可以（需 T1/T2/T3/T5/T6 + T7 全部通过，T4 标 out_of_scope 不计分母） | 无 |
| 有确定证据：存在存活的后代（超出宽限期） | `False` | 失败（blocking） | 不可 | 记录残留 PID/argv，修复取消路径，重开 attempt |
| 无法确认（macOS 无 /proc、ps 回退不可判定身份、崩溃窗口内） | `None` | 该项记 unknown | **不可宣布成功** | 保持 live 执行门禁关闭；在报告中单列"平台限制"；不阻塞其他边界记录的继续收集 |
| 崩溃/断线后状态未知，无法排除后代存活 | `None`（禁止写 True/False） | not_run/unknown | 不可 | 按 LOCAL-MODEL-RUNBOOK §5：先核对实际进程，不启动重复操作；NEEDS_HUMAN 或恢复流程 |

硬性规则：

1. 任何情况下 `tree_cleanup_confirmed` 不得从 `None` 推断为 `True`；M2-B Adapter 已把 `!=True` 判 failed，本提案保持并扩展到平台级门禁。
2. 无 /proc 不等于必然 None：按当前 Worker 实际能力实测判定（已读 `process.py` 确认 `_process_table()` 回退到 `ps -axo pid=,ppid=,pgid=,stat=,lstart=` 身份表，`require_tree_cleanup=True` 时身份表不可用直接 `environment_failure`）。
3. 如果 T6 最终只能得到 `None`，则 M2-C2 的验收结论是"OS 可强制部分（T1/T2/T3/T5）按 §5 决策表记 unknown/True/False + 协调流程部分（T7）证据齐全 + T6 进程树确认受平台限制（None）"，**真实 Worker/Agent 执行门禁保持关闭**，直到 (a) 在 Linux 后端取得 True 证据，或 (b) 用户明确接受受监督模式（见 §6 解锁条件）。T4（MCP）标 out_of_scope/not_run，不计分母。**T6=None 时整体只能 partial，不可记 full_pass。**
4. 该表是决策规则不是豁免条款：None 不免除记录义务，也不允许把其他边界写成通过以"补偿"。
5. 受监督模式如要放宽，必须独立提出规格，不在本提案暗含例外。

## 6. 从纯校验器到真实 Worker/Agent 集成的步骤（收敛为唯一可执行路径）

前提：以下每一步都是**独立合同/独立验收**的候选边界，不是 M2-C2 一次做完。M2-C2 合同本身只覆盖 Step 1–2（后端与拒绝测试）；Step 3–5 属于后续（M2-C2b / M2-D / M2-E 或等价拆分）。**C2A（Step 1–2）不依赖任何合并操作**：C1 校验器 API 以绑定不可变 ref（`436e3b0e026580a6b39ece891e8ffe47ac1bb698`）的只读依赖方式引入（§6 唯一可执行路径），M2-B 合并不是 C2A 前置。

**唯一可执行路径（单一方案，无备选）：** C1 校验器 API 必须以绑定不可变 ref `436e3b0e026580a6b39ece891e8ffe47ac1bb698`（`origin/hermes/m2c1`）的只读依赖方式引入。`git rev-parse <ref>^{blob}` 会 deref 到 tree 而失败，不是可行备选。按顺序执行 5 步：

1. **创建并验证父根 + 新 attempt + `harness/deps/` + `ro/fixtures/`**：依赖准备必须先有父根存在、新 attempt 已排他创建、`harness/deps/` 子目录已存在、`ro/fixtures/` 已由 harness 填充 fixture 脚本。前序步骤顺序：①父根探查（`realpath /tmp/m2c2-sandbox` + macOS `/private/tmp` 别名绑定）；②attempt 排他创建（`os.mkdir(path, 0o755)` 不带 -p，O_EXCL 语义）；③子目录创建（`work/ ro/ denied/ secret/ harness/{profiles, capture, evidence, state, deps}` + `ro/fixtures/`）；④`ro/fixtures/` 由 harness 用 Python 写入 fixture 脚本（fixture 在 `ro/`，sandbox 内 Worker 可读可执行）。
2. **参数数组 `git rev-parse` 取 `blob_oid`**：在获准目录 `/Users/william/Public/AI project/supervisor-M2A` 内，由协调者执行 `python3 -c "import subprocess; subprocess.run(['git','-C','/Users/william/Public/AI project/supervisor-M2A','rev-parse','436e3b0e026580a6b39ece891e8ffe47ac1bb698:src/supervisor/workers/boundary.py'], capture_output=True, check=True, text=True)"` —— 用 **`<commit:path>` 语法**取 blob OID（不是 `commit^{blob}`，那个会 deref 到 tree 失败；参数数组调用，禁 shell redirect）。stdout 第一行 = `blob_oid`（40-char SHA-1）。
3. **参数数组 `git cat-file blob` 取 bytes**：`python3 -c "import subprocess, sys; r = subprocess.run(['git','-C','/Users/william/Public/AI project/supervisor-M2A','cat-file','blob', blob_oid], capture_output=True, check=True); sys.stdout.buffer.write(r.stdout)"`，harness 用 Python `subprocess.run(..., check=True, capture_output=True)` 取 bytes，**限制大小**（如 ≤ 64 KiB，harness 检查 `len(bytes) <= MAX_DEP_BYTES`，否则 ENVIRONMENT_FAILURE）；**检查 exit_code**（!= 0 → ENVIRONMENT_FAILURE）。
4. **Python 写 `<attempt>/harness/deps/boundary.py` 并核对**：
   - 用 Python 文件 I/O `open("<attempt>/harness/deps/boundary.py", "wb").write(cat_file_bytes)`；**禁 shell 重定向**；**禁 `cp -R` 命令**。
   - `hashlib.sha256(cat_file_bytes).hexdigest()` 算出 `expected_sha256`；再读落盘文件 `hashlib.sha256(open(path,"rb").read()).hexdigest()` 算出 `actual_sha256`；`assert expected_sha256 == actual_sha256`，不一致 → ENVIRONMENT_FAILURE。
   - 另核 Git 对象（可选）：`python3 -c "import subprocess; r = subprocess.run(['git','-C','/Users/william/Public/AI project/supervisor-M2A','hash-object','--no-filters','--stdin'], input=cat_file_bytes, capture_output=True, check=True); print(r.stdout.decode().strip())"` 取 `git_blob_oid_from_bytes`；与 step 2 的 `blob_oid` 比对，**一致**则对象级别核对通过（cat-file 真的返回该对象的字节）。
   - 两步 hash 一致 + 对象级核对（推荐）都通过 → 落盘到 `harness/deps/c1-boundary-manifest.json`（JSON：{blob_oid, expected_sha256, actual_sha256, git_blob_oid_from_bytes, source_commit, source_path, attempt_id, importer_python_module_name}）。
5. **`importlib.util.spec_from_file_location` 加载**：
   ```python
   import importlib.util, sys
   spec = importlib.util.spec_from_file_location("c1_boundary", "<attempt>/harness/deps/boundary.py")
   if spec is None or spec.loader is None: raise RuntimeError("spec loader missing")
   module = importlib.util.module_from_spec(spec)
   spec.loader.exec_module(module)
   # 变量名：c1_boundary, validate_evidence（与 module 内符号对照，禁止拼错）
   if not hasattr(module, "validate_evidence"): raise RuntimeError("validate_evidence missing")
   ```
   - **不用 sys.path 注入**（可变工作区是反模式）；spec.from_file_location 是指定文件加载的标准方式。
   - 验证 `module.validate_evidence` 可调用 + 接受 (record, *, expected) 签名 → return deep copy or raise on err.

**执行主体**：harness（运行在 sandbox 外、获准目录内）。Worker 不参与任何依赖准备/导入操作。`/bin/sh -c "echo"` 之类 shell 字符串拼接不作为依赖导出路径（与 §4.0 "argv 用参数数组，禁止字符串拼接 shell" 一致）。

**验证失败处理**：hash 不一致 / importlib 加载失败 / Worker 读 `<attempt>/harness/deps/` / cat-file exit_code != 0 / 落盘大小超阈值 → 记 `ENVIRONMENT_FAILURE`，停止 C2A，不继续测试；**不重试、不换源、不复制进 `src/supervisor/`、不动 sys.path**。

**冻结任务包来源**：冻结任务包由正常规格流程准备到 main；本提案只引用 `handoffs/M2C2/v1/task-bundle/`，**不把未发布任务包当 C1 模块来源**。

C2A 不运行真实 Hermes，因此 M2-B 合并不是 C2A 前置；M2-B 合并是后续独立集成操作（用户授权后由协调者执行，模型可参与 review 但不能自行合并）。

| Step | 内容 | `live_execution_disabled` 状态 | 解锁条件（全部满足才进入下一步） |
| --- | --- | --- | --- |
| 1 | M2-C2 实施合同：平台后端抽象 + Seatbelt profile 生成/校验 + 在合成目录跑 §4 全矩阵（**不运行真实 Hermes，只跑受控合成 argv**） | 保持 | C1 校验器 API 按 §6 唯一可执行路径从绑定不可变 ref `436e3b0e026580a6b39ece891e8ffe47ac1bb698`（`origin/hermes/m2c1`）以只读依赖方式导出/校验/导入成功；新规格经 fresh 规格 Reviewer 接受并冻结 |
| 2 | M2-C2 验收：T1/T2/T3/T5/T6 拒绝测试证据 + `validate_evidence` 结构校验 + T7 流程证据 + fresh Reviewer 审核 + 按 §5 决策表给出平台结论（T4 标 out_of_scope/not_run，不计分母） | 保持 | §4 全部有效执行（或明确 not_run + 缺失前提）；fresh 审核 accept |
| 3 | 真实 Hermes 最小 smoke：无秘密合成目录、工具禁用（shell/写/MCP 全禁）、单一本地模型端点、外部 watchdog；**仍不授予任何写权限给模型工具** | 保持（smoke 是观察，不是解锁） | Step 2 accept；用户单独授权真实模型调用（端点、模型标识、工具禁用配置）；smoke 通过且 enforced 证据留存 |
| 4 | Worker 集成：`execute()` 在平台后端内启动真实 Agent 进程，最小 env allowlist，输出/超时/取消走既有 ProcessRunner | 保持 | Step 3 smoke 通过；取消与输出上限故障注入通过；T1–T6 在真实 Agent 进程（非合成 argv）下重跑矩阵 |
| 5 | 受监督端到端（M2-E 范围）：无秘密小仓库真实任务，一次成功 + 一次返修路径，人工在环 | **逐任务门禁**（不是全局开关） | 每边界 enforced=yes 且有绑定证据；`tree_cleanup_confirmed` 能稳定 True（或在用户书面接受受监督模式后以 None 限制运行）；M2-D 可信验收器就绪 |

后续独立操作（不属于 C2A 步骤；C2A 不依赖任何合并操作）：
- **M2-B 合并**（用户授权后由协调者执行，模型可参与 review）：普通 merge `77920b99f279956cbe88bc2b3b2364b5ae078ce7` 到 main；集成检查（Linux 全套 + 保护测试 + specs + ruff）；发布集成基线 SHA。不可逆的 Git 历史操作（需授权）；每一步的代码变化都可能使之前所有验收证据失效（代码变化使旧通过失效是项目不变量），重跑义务随新候选产生。
- **M2-C1 合并**（用户授权后由协调者执行）：普通 merge `436e3b0e026580a6b39ece891e8ffe47ac1bb698` 到 main；集成检查同上。与 M2-B 合并相互独立，可分别授权。

## 7. 建议任务拆分（收敛为一条可执行的 C2A 方案）

原则：每个任务足够长、可独立交付、有明确验收；避免碎片轮次。角色按 LOCAL-MODEL-EXECUTION-PLAN：Planner/Reviewer 可同模型不同 fresh 会话，Implementer 独立会话。

**唯一可执行路径**：C2A 不运行真实 Hermes，因此 M2-B 合并不是 C2A 前置；C1 校验器 API 以绑定不可变 ref（`436e3b0e026580a6b39ece891e8ffe47ac1bb698`）的只读依赖方式引入，不依赖 M2-B 合并。M2-B 合并是后续独立集成操作（用户授权后由协调者执行，模型可参与 review 但不能自行合并）。

### 任务 C2A：隔离后端与拒绝测试矩阵（实施合同主体，唯一可执行）

- 范围：§2 平台后端抽象（含 Seatbelt profile 模板与生成器）、§4 全部测试 harness（合成仓库生成、watchdog、输出捕获、清理、证据记录）、§5 决策表实现。不运行真实 Hermes。
- 文件（建议，冻结时定）：`src/supervisor/workers/sandbox/`（新模块，profile 生成 + 能力探测）、`tests/fixtures/sandbox_cases/`（合成场景）、`tests/unit/test_sandbox_backend.py`、`tests/integration/test_boundary_matrix.py`、`deliveries/M2C2/boundary-evidence.json`、`deliveries/M2C2/hermes-report.md`。
- 依赖：C1 校验器 API（绑定不可变 ref `436e3b0e026580a6b39ece891e8ffe47ac1bb698`，只读依赖，§6 唯一可执行路径）；用户按 permission-request.md 授权宿主操作。
- 预算建议：wall 建议 8h、Agent 启动建议 8 次（advisory）；单进程 120s / 64KiB；文件/行预算冻结时定（参照 C1 的 4 文件/1800 行，本任务因含 harness 建议放宽到 8 文件/4000 行，含报告）。
- 验收：§4 每项测试有 executed/observed/enforced 真实三态；结构校验通过；拒绝测试有效性判定（§4.0）逐条可复核；平台结论按 §5 + acceptance-matrix 通过条件定义（C2A full_pass = T1/T2/T3/T5/T6 全部 `enforced=yes` + T7 流程证据齐全；任一 required 子项 `unknown`/`not_run` 整体只能 `partial`，不可升级 full_pass）；T4 标 out_of_scope/not_run 不计分母；live 始终关闭；fresh Reviewer accept。
- 兜底：
  - Seatbelt 某能力实测不成立（如网络 allow 粒度不够）→ 该边界降级为 `enforced=unknown`，改由 Linux 后端或流程保证覆盖，报告中单列；不修改测试使其"通过"。
  - 合成测试 harness 自身 bug 导致环境失败 → ENVIRONMENT_FAILURE 单列，修复后重跑该子集，不重置整体证据。
  - 额度明显超额 → 记录原因与剩余工作量，继续或 checkpoint，不以额度为停止理由（预算语义为 advisory）。

### 后续独立合同（不属于 C2A）

- **M2-B 合并**（用户授权后由协调者执行，模型可参与 review）：普通 merge `77920b99f279956cbe88bc2b3b2364b5ae078ce7` 到 main；集成检查（Linux 全套 + 保护测试 + specs + ruff）；发布集成基线 SHA。不是 C2A 前置。
- **C2B：真实 Hermes 最小 smoke**（独立小合同，Step 3）：工具全禁下的单次非交互本地模型调用，合成目录，端点限 127.0.0.1 单端口；fresh 会话证据；不授予写权限。依赖 C2A accept；用户单独授权真实模型调用。
- **C2C：Worker 集成真实 Agent 进程**（Step 4，独立合同）：`execute()` 在后端内启动真实 Agent；T1–T6 矩阵在真实进程下重跑；取消/输出上限/超时故障注入。依赖 C2B 通过；M2-D 验收器就绪。

### 任务拆分不做的理由

- 不把 §4 每项边界拆成独立任务：拒绝测试共享 harness，拆开会产生大量重复环境与碎片轮次。
- 不把 M2-B 合并交给模型角色：合并是授权门禁，必须用户决定。
- 不把 Step 5（端到端）并入 C2A：端到端依赖 M2-D 可信验收器，提前合并会放大单次任务失败面。

## 8. 工作量、不确定性与超时检视

### 8.1 预计工作量（advisory 估计，非硬预算）

| 任务 | 建议 wall | Agent 启动 | 主要风险驱动 |
| --- | --- | --- | --- |
| C2A | 8h | 8 次 | Seatbelt 语义实测（网络/fork 粒度）是最大不确定项；harness 首跑调试 |
| M2-B 合并（后续独立） | 0.5h（协调） | 0 | 合并冲突概率低但非零 |
| C2B | 3h | 4 次 | 本地端点稳定性、Hermes CLI 实际行为与 M2-A 证据偏差 |
| C2C | 8h | 8 次 | 真实进程下的进程树确认（macOS None 概率高） |

### 8.2 主要不确定性（按影响排序）

1. **Seatbelt 能力粒度 [H]**：网络按端点 allow 的可行性、fork 后能力继承、sandbox 内 exec 行为。缓解：C2A 第一周只做能力探测子集（每项独立记录），不成立即降级，不重设计。
2. **macOS 进程树确认 [H]**：ps 回退身份表不能抵抗 PID 重用/重父化/脱离进程组（已读 `process.py` 确认 `lstart` 字符串身份）。缓解：§5 决策表把 None 变成合法终态而非失败，门禁保持关闭；C2A 实测该弱点。进程组不能解决脱离进程组，不作为整树确认兜底；有无法跟踪的后代只能 `unknown`，另提方案。
3. **M2-B 合并冲突 [H]**：`77920b99f279956cbe88bc2b3b2364b5ae078ce7` 与 `436e3b0e026580a6b39ece891e8ffe47ac1bb698` 都基于旧 main，且 main 已前进 3 提交。缓解：M2-B 合并是后续独立操作（用户授权后由协调者执行），C2A 不依赖；冲突即停，走规格流程。
4. **本地模型端点行为 [H]**：15721/18080 端点属于用户现有工具（cc-switch / Python 服务），其 API 语义未经本仓库核验。缓解：C2B 先做 connect + 固定字节回读的最小探测，再决定是否作为 smoke 端点。
5. **证据可复核性 [D]**：C1 已暴露"云端/异地 reviewer 无法核实本机捕获字节"的问题。缓解：C2 证据记录 source 时写明捕获方法与重放方式（byte-stable 与 byte-variable 分开标注）；关键拒绝测试设计成 byte-stable 输出（固定合成输入）。

### 8.3 超时/停滞后的检视方式（不设"耗尽额度便放弃"规则）

- wall 超过建议值 1.5 倍或连续 3 次无新证据时：暂停启动新操作，写 checkpoint 报告（最后可靠 SHA、当前阶段、已产生证据、无进展原因分类：环境/能力缺口/实现 bug/证据标准过高），然后 (a) 缩小当前操作粒度重试，或 (b) 把不可行子项降级为 unknown 并继续可执行子项。历史消耗不重置。
- 能力缺口型停滞（如 Seatbelt 不支持某规则）：不是"失败"，是平台结论，按 §2.3 的诚实降级交付。
- 环境型停滞（端点断、内存不足）：ENVIRONMENT_FAILURE 记录，等待恢复，不切换云模型兜底。
- 唯一真正的停止条件：用户终止、安全违规、或所有剩余子项都被诚实判定为不可行且已交付降级结论。

## 9. 与既有文档的一致性声明

- 本提案不修改 AGENTS.md、tasks/、handoffs/、schemas/、保护测试、生产代码、依赖。
- 本提案与 `docs/security-model.md` 的"默认拒绝"一致：能力不足保持 live 门禁关闭。
- 本提案与 `docs/verification.md` 一致：enforced 必须绑定实际操作证据；fresh 审核记录两个维度。
- 本提案与 M2-C1 冻结合同一致：C1 的"不能凭报告扩权"规则延续到 C2——C2 合同必须根据真实后端明确授权（见 permission-request.md），不能用 C1 盘点自动扩权。
- 本提案是待审核提案；冻结需要走规格流程（fresh 规格 Reviewer + 协调者发布 handoffs/M2C2/v1）。
