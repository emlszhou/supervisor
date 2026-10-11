# M2-C2A 实施报告（M2C2A-seatbelt-synthetic，C2A-R1 返修）

> 文件名沿用 `hermes-report.md`（冻结合同指定的版本化路径，历史接口名）。本轮编码执行工具已由
> Claude/Hermes 切换为 **MiniMax Code CLI（mcode）**；合同、基线、验收、权限与既有消耗均未因此改变。

## 0. 实际运行信息（本轮）

| 项 | 值 | 证据 |
| --- | --- | --- |
| 工具 | MiniMax Code CLI（`mcode`） | `mcode --version` → `0.6.8` |
| 实现角色 | Implementer | 本轮 |
| provider | **未知** | CLI 未暴露 provider 查询；不据工具名推断 |
| model | 运行时声明 `MiniMax-M3.1-Flash-Preview` | 运行时声明值，**未做独立路由核验** |
| 实施检出 | `/Users/william/Public/AI project/supervisor-M2A`（git worktree） | `git worktree list` |
| 实施分支 | `mcode/m2c2a-r1` | 本轮自候选 `7e5920b` 新建 |
| baseline（继承） | `51d497cae7f20872e5a5f9c8825fd0f83323a92f` | 未改动 |
| 起点候选 | `7e5920b1d90ac8582e558c8c09573ea1c6f49704` | `git ls-remote origin hermes/m2c2a` 核验一致 |
| 输入审核 | `7ddec993c65876acf4f05e54eee5ef745948ecb6`：`deliveries/M2C2A/codex-review-1.md` | `git ls-remote origin codex/m2c2a-review-1` 一致 |
| 冻结合同 | `f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef` | `shasum -c CHECKSUMS.sha256` → 15/15 OK，exit 0 |

预算：周期/调用数为建议值，本轮未触及其余额度，未重置历史消耗。

## 1. 起点状态（必须如实记录）

进入本轮时工作区已有 4 个**未提交**文件（`evidence.py`、`preflight.py`、
`test_seatbelt_preflight.py`、`test_boundary_package.py`）与未跟踪的 `MIGRATION_PLAN.md`。
核对结论：这些是上一执行者对**同一任务**的返修产物（`MIGRATION_PLAN.md` 明确记录
"均为本轮整改产物，勿 stash/丢弃"）。本轮**全部保留**，未 stash、未丢弃、未 reset。

## 2. 6 项审核 finding 的逐项处置

| finding | 严重度 | 处置 | 关键改动 |
| --- | --- | --- | --- |
| C2A-R1-matrix | blocking | **已关闭（代码层）** | `run()` 现编排完整链路：排他 attempt 树 → C1 导出并 `importlib` 实际加载 → 逐 case profile → 逐 case 执行 → `backend.classify_case` 配对判定 → `backend.summarize_results` → 持久化 → 清理 → finalize。矩阵由 `_PROBES` 展开为 16 个 case，覆盖 T1/T2/T3/T5/T6 每个拒绝动作都有**同目标同 argv 仅隔离配置不同**的对照；T3 的拒绝侧与对照侧都由 harness 自建监听器**并发**服务（原先监听在 worker 之前阻塞 accept，控制侧从未真正被连接）。 |
| C2A-R1-process | blocking | **已关闭** | `_run_bounded_command` 独立看门狗循环（非管道读阻塞）、非阻塞 reader、`start_new_session` + `killpg` TERM→grace→KILL、共享 64KiB 预算、超限立即终止、**新增无条件 `proc.wait()` 回收**；返回值新增 `pid` 与 `cancellation_reason`。`process_tree` 改为**必须**传 attempt pid，只保留该 pid 及其后代行；`alive` 来自 `os.kill(pid,0)` 身份绑定探测，**不再**把"ps 成功 + 空表"当作已清理。 |
| C2A-R1-dependency | major | **已关闭** | `export_c1_dependency` 改为有界 reader（非先无界捕获再截断），按 `len()` 判定超限（bytes 与 int 比较的 TypeError 已不存在），超限不落盘、失败清理临时目录、源/落盘双 sha256 一致。新增 `_load_c1_dependency`：按显式文件位置 `importlib` 加载、不改 `sys.path`、加载前复核 hash，结果并入报告。 |
| C2A-R1-boundary | blocking | **已关闭** | `load_authorization` 缺 expected digest 时 fail closed、强制 platform/roots/loopback/scopes/timestamp 校验（保留）。`run()` 新增 `_bind_roots` 绑定真实根并返回 canonical sandbox root。**修正无效 ID 校验**（原 `"/" + id + "/" in id` 恒不成立）→ `_validate_attempt_id` 严格单路径组件。`ensure_attempt` 重写：`abspath` 不解析符号链接 + 逐组件 `lstat` + 原子排他 `mkdir` + params 与真实子目录绑定。CLI **无** `--platform` 覆盖口。 |
| C2A-R1-evidence | major | **已关闭** | `persist_package` 源名修正为 `<test_id>.json` / `<test_id>.log`（原先按裸 `test_id` 查找，**静默不复制任何文件**），逐份复制后重新 hash 核验，缺失 id 进 `missing` 不再静默。输出根改为**排他创建**（删除 `fresh=True` 复用通道，且不再忽略隐藏文件）。`_write_manifest_files` 修正 pre-cleanup 自引用（原先 final 阶段覆写已列入 manifest 的 pre-cleanup 文件，导致 size/hash 过期）。pre-cleanup manifest **先于真实清理生成并全量校验**（`_verify_pre_cleanup`），finalize 只在包真实存在且已校验时执行。 |
| C2A-R1-tests-report | major | **已关闭** | 删除测试对开发机外部路径 `../M2C2A-v1-contract/handoff.json` 的依赖（改为测试自建临时合同包 + `bundle_dir` 注入；生产侧 `_resolve_expected_bundle_sha` 亦改为可注入，默认行为不变）。`test_refuses_mismatched_contract_sha` 不再强断平台相关 reason，改为断言"绝不 completed"的不变量。`build_report` 的 provider 由硬编码 `"cloud-authorized"` 改为如实记录（默认 `unrecorded`）。 |

### 本轮额外发现并修复的阻断缺陷

上一执行者留下的返修代码**无法运行**：集成测试在 `test_full_orchestration_offline` 处永久挂起。

- `ensure_attempt` 父链遍历方向写反（从 `/` 向下走），而 `Path("/").parent is Path("/")`，
  `while current != resolved` 为死循环。已重写并补直接回归测试。
- `build_profiles` 把区域名（如 `denied`）当绝对路径传给 `build_profile`，且 `allow_endpoint`
  未带端口 —— 只要走到 profile 生成就必然抛 `ValueError`。
- `run()` 的 `finally` 块曾遗漏 `finalize_package`，包永远停在未完成态。

## 3. 离线验证（本轮实际 exit / 计数）

| 检查 | 命令 | exit | 计数 |
| --- | --- | --- | --- |
| protected（冻结用例） | `uv run --frozen python -m pytest "$CONTRACT/task-bundle/tests/protected/test_contract.py" -q` | **0** | **46 passed** |
| M2C2A 单元 + 集成 | `uv run --frozen python -m pytest tests/unit/test_seatbelt_backend.py tests/unit/test_boundary_package.py tests/integration/test_seatbelt_preflight.py -q` | **0** | **73 passed** |
| 项目全套（macOS/APFS） | `uv run --frozen python -m pytest -q` | **1** | 318 passed, 1 skipped, **55 failed** |
| specs | `uv run --frozen python scripts/check_specs.py` | **0** | 6 schemas + 样例工件 |
| ruff check | `uv run --frozen ruff check .` | **0** | All checks passed |
| ruff format | `uv run --frozen ruff format --check .` | **0** | 69 files already formatted |
| build | `uv build --no-sources` | **0** | sdist + wheel 构建成功 |

`${CONTRACT}` 使用**实际已校验的外部导出绝对路径**（`/Users/william/Public/AI project/M2C2A-v1-contract`，
`CHECKSUMS.sha256` 15/15 校验通过），未把开发机目录硬编码进生产代码或测试。

### 55 项失败的基线对照

55 项失败**全部**位于 M1 测试文件，与本任务改动文件无交集：

| 文件 | 失败数 |
| --- | --- |
| `tests/unit/test_m1_fallback_regressions.py` | 21 |
| `tests/unit/test_m1_changes.py` | 10 |
| `tests/unit/test_m1_bundle.py` | 10 |
| `tests/unit/test_m1_snapshot.py` | 9 |
| `tests/unit/test_m1_baseline.py` | 5 |

失败根因一致：`ValueError: case-insensitive filesystem is not supported`
（`src/supervisor/workspace/snapshot.py:158`），即交接单中已单列的 macOS 大小写不敏感文件系统既有失败。
数量与上一候选报告记录的 55 项一致，M2C2A 相关测试 0 失败。

### 未运行项（平台未测，单列）

- **Linux 联合验证**：本轮在 macOS 执行，**未运行** Linux 环境全套。上一候选在 Linux 上的
  "385 pass / 2 fail" 尚未复核；本轮已消除其中一类的根因（测试依赖开发机外部路径 +
  平台相关强断言），但**不据此声明 Linux 通过**，须由 fresh Reviewer 在干净独立检出复跑。
- **真实 Mac probe**：未授权，未执行。

## 4. 宿主门禁与 not_run 事实

- Mac probe **未授权**（handoff `mac_probe_authorized=false` + permissions.md 待 operator 批准）。
  本轮**未**创建 `/tmp/m2c2-sandbox`、**未**监听任何端口、**未**执行 `sandbox-exec`、
  **未**启动真实 Hermes / mcode Agent 子进程、**未**读取真实凭证、**未**访问外网。
- 全部 required 子项（T1/T2/T3/T5/T6）记 **not_run**；T7 记 **unknown**
  （fresh 流程证据由独立 Reviewer 填，probe 中不自签）；平台能力 **partial**。
- 离线集成测试中的 `run_worker` 被替换为直跑 fixture，因此**不构成**任何 macOS 强制隔离证据。
  该用例恰恰因为"拒绝动作真的成功了"而得到 `summary=fail`——这是策略被真实评估的证据，
  不是通过信号。
- `live` 恒拒绝：`backend.require_live_execution` 未改动，仍恒抛 `RuntimeError`。

## 5. 交付语义

诚实有限候选（代码 + 离线保护全绿 + probe not_run + partial）。**不声明 full_pass、
不宣布安全边界就绪、不自称 ACCEPT**。

## 6. 范围

- 本轮改动 4 个文件，全部在 `allowed_files` 内；累计相对 baseline 仍为 8 个允许文件。
- 未改 forbidden：`tasks/**`、`handoffs/**`、`schemas/**`、`tests/protected/**`、
  `src/supervisor/workers/process.py`、`boundary.py`、agents/workspace、`docs/**`、`AGENTS.md`、
  `pyproject.toml`、`uv.lock` 等。
- 未新增依赖（生产代码标准库）。
- `MIGRATION_PLAN.md` **保留在磁盘但不提交**：它是上一轮的过程快照，不在 allowed_files 内。

## 7. 尚缺权限与阻塞

1. Mac 两写根（`/tmp/m2c2-sandbox` 与 `deliveries/M2C2A/evidence`）与合成回环范围的明确批准。
2. profile 最小运行只读清单须在真机逐项披露并实测；当前仅为注释声明 + 默认 deny。
3. 真实 Mac 矩阵与证据审核（依赖 1）。
4. Linux 干净独立检出全套复跑（需 fresh Reviewer 环境）。
5. 实施合入 main 与部署：均未授权。

## 8. Git 事件

- 分支 `mcode/m2c2a-r1`，自精确候选 `7e5920b` 创建，未 merge 新 main、未 merge 审核分支。
- 普通提交 + 普通推送；无 force / reset / clean / 删除分支 / main 合并 / 部署。
- 候选 SHA：见交付消息（commit 后以 `git rev-parse HEAD` 与 `git ls-remote` 双向核验）。

## 9. fresh Reviewer 说明

本轮**不模拟** fresh 审核。请由独立 fresh Reviewer 绑定本候选精确 SHA 与合同
`f01525c5…`，复跑 §3 全部检查（Linux 全套 + Mac 55 项单列 + protected 46），
核对真实捕获与授权记录来源，并填 T7 真实流程证据。
同供应者执行则 `independent_provider=false`；Reviewer 若修改实现须换另一个 fresh 审核会话。
