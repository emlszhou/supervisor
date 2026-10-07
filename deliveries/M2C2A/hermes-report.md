# M2-C2A 实施报告（Hermes PI 会话）

## 0. 实际运行信息

- provider: minimax-cn；model: MiniMax-M3（Hermes 云端配置当前 provider，`HERMES_PROVIDER=minimax-cn`）。
- 实现检出：`/Users/william/Public/AI project/supervisor-M2A`（git worktree；主库 `supervisor/supervisor-M1/.git`），分支 `hermes/m2c2a`。
- baseline（实施分支初始 HEAD，精确）：`51d497cae7f20872e5a5f9c8825fd0f83323a92f`（= 检出前 `origin/main`；`origin/main` 后前进到 `3fcdd78`，未 merge 进实施分支）。
- 冻结合同导出（`prepare_git_handoff.py --ref origin/main --contract-prefix handoffs/M2C2A/v1 --output ../M2C2A-v1-contract`）成功；`verify_handoff.py --bundle-sha256 f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef` 通过（exit 0）。
- 预算建议 8h/10 调用：本会话持续工作约 1.5h，模型调用次数以 Hermes 会话历史为准（未单独计 10 次；未超额硬停，按"超额分析不自动停"执行）。

## 1. 提交范围与分支累计范围

- 本提交（候选）改动文件（8）：
  - `src/supervisor/workers/backend.py`（classify_case / summarize_results / require_live_execution / build_profile）
  - `src/supervisor/workers/evidence.py`（verify_package）
  - `src/supervisor/workers/preflight.py`（可信合成测试 harness：授权门、attempt/profile/capture/持久化/finalize）
  - `tests/fixtures/seatbelt_probe.py`（固定 fixture）
  - `tests/unit/test_seatbelt_backend.py`、`tests/unit/test_boundary_package.py`
  - `tests/integration/test_seatbelt_preflight.py`
  - `deliveries/M2C2A/hermes-report.md`（本文件）
  - 另：删除无主的 `tests/fixtures/__pycache__/hermes_cli.cpython-312.pyc`（M2-B 线 `tests/fixtures/hermes_cli.py` 在 main 上不存在的陈旧编译残留，非提交内容）。
- `deliveries/M2C2A/evidence/**`（allowed 通配）：本轮未提交任何证据包文件（probe 未授权，见 §4）。
- 分支累计范围（相对 baseline `51d497c`）= 本提交（实施分支无其他提交）。
- 未改：`pyproject.toml`/`uv.lock`/`tasks/**`/`handoffs/**`/`tests/protected/**`/`src/supervisor/workers/process.py`/`boundary.py`/agents/workspace 等（forbidden 与"不扩依赖"约束）。

## 2. 实现要点（按 requirements 唯一算法）

- **backend.py**
  - `classify_case`：字段类型严格校验（bool 不被 int 字段接受；缺键/多键/未知 test_kind → ValueError 固定消息不回显输入；不修改输入）。优先级：`expected_refuse` 有越界 effect 或 `target_unchanged=False` 立即 fail；pass 需 completed + 非零真实 exit + errno∈{EPERM,EACCES} + 同目标对照 pass + 目标未变（文件目标须 True，网络可 None）+ 已启动 + 观测完整 + 未输出超限。`positive`：启动+完成+exit 0+errno None+effect。`timeout_cleanup`：真实负信号（watchdog 触发、未完成）+ cleanup True + 观测完整 → pass；cleanup False 立即 fail；未确认 unknown。
  - `summarize_results`：T1/T2/T3/T5/T6 非空列表 + T4 固定 `out_of_scope`（不计分母）+ T7；任意 fail→fail，任意 unknown→partial，全 pass→full_pass；缺键/空/多余/非法值 ValueError。
  - `require_live_execution`：恒 `RuntimeError("live_execution_disabled")`（含任意 kwargs）。
  - `build_profile`：纯文本生成，default deny；五区目录绝对/规范/互不重叠/NUL 控制字符拒绝；SBPL 引号/反斜杠转义（防规则注入）；`allow_target` 仅限 denied/secret 下单文件（同目标对照）；`allow_endpoint` 仅 127.0.0.1 真实 int 端口 1..65535；网络默认全 deny；harness 全子区（profiles/deps/capture/evidence/state）全 deny。解释器最小只读允许清单以注释标注"须 Mac 实测逐项披露后方可 probe，此前不构成强制证明"。
- **evidence.py** `verify_package`：不执行/不写文件/不跟随包内符号链接；manifest 严格 schema（`{schema_version:1, files:[{path,sha256,bytes}]}`，不含自身/CHECKSUMS、不重复、相对路径无绝对/..//NUL）；CHECKSUMS 单行 = 最终 manifest 裸 sha256；全 payload size+hash 校验；库存（包内非清单文件）拒绝；summary/record/capture 交叉引用与 capture_sha256 校验；全部失败为固定消息 ValueError；返回深拷贝 manifest。
- **preflight.py**（可信 harness）：
  - 授权门：`run()` 在平台非 darwin、授权文件缺失或 contract_sha256 不匹配时**在任何路径创建/监听/sandbox-exec 之前**返回 `not_run`（提示词/仓库自写 JSON 不是授权）。
  - `ensure_attempt`：排他创建、存在即拒、符号链接拒；`build_profiles`：每 case 一份 profile（同 fixture 同 argv 同目标，仅隔离配置不同）；`run_worker`：`/usr/bin/sandbox-exec -f <profile> -- <fixture> <argv…>` argv 数组、120s、64KiB 截断（超限终止并记 `output_limited`）、TERM→5s→KILL 仅限本 attempt 可确认 PID；`process_tree`：`ps -axo pid=,ppid=,pgid=,stat=,lstart=`（argv 数组）；`persist_package`/`_write_manifest_files`/`finalize_package`：pre-cleanup manifest（不含自身/未来 cleanup/最终 manifest/CHECKSUMS）→ 真实清理结果（argv/exit/post-cleanup ls/enoent 三态）写 `cleanup.json`（含 pre-cleanup sha，不含最终 manifest sha）→ 最终 manifest + 外置 CHECKSUMS 单行 → `verify_package` 复核。
  - `export_c1_dependency`：`git -C <repo> cat-file blob <commit>:<path>`（argv 数组、禁 shell、64KiB 限、120s、双 sha256 一致、不改 sys.path）；代码基线无 C1 非 environment_failure，缺 Git 对象记 `not_run`。
- **fixture** `tests/fixtures/seatbelt_probe.py`：纯 argv 数组动作（write O_WRONLY|O_APPEND / read / connect / 受控 depth≤2 子进程 / 30s timeout / env 名称断言），结构化 JSON 实际状态（completed/errno/effect）；未知/损坏输出上游记 unknown，不以自述推导无副作用。

## 3. 离线验证（实际 exit/计数）

| 检查 | 命令 | exit | 计数 |
| --- | --- | --- | --- |
| protected（冻结 46 用例，`${CONTRACT}` = 导出 task-bundle 绝对路径） | `uv run python -m pytest ../M2C2A-v1-contract/task-bundle/tests/protected/test_contract.py -q` | 0 | 46 passed |
| 新增 unit/integration | `uv run python -m pytest tests/unit/test_seatbelt_backend.py tests/unit/test_boundary_package.py tests/integration/test_seatbelt_preflight.py -q` | 0 | 39 passed |
| 项目全套（macOS） | `uv run python -m pytest -q` | 1 | 285 passed, 1 skipped, **55 failed** |
| specs | `uv run python scripts/check_specs.py` | 0 | 6 schemas + 样例工件 |
| ruff check | `uv run ruff check .` | 0 | All checks passed |
| ruff format | `uv run ruff format --check .` | 0 | 全部已格式化 |
| build | `uv run uv build --no-sources` | 0 | wheel 构建成功 |

- **Mac 既有失败单列**：全套 55 失败**全部**为既有 M1 用例（test_m1_fallback_regressions 21 / test_m1_changes 10 / test_m1_bundle 10 / test_m1_snapshot 9 / test_m1_baseline 5），同一 stash 基线对照（55 failed / 245 passed）逐文件一致——即 APFS 大小写不敏感既有失败（"case-insensitive filesystem is not supported"），与本候选无关；未关闭测试、未硬编码 Mac 路径。
- Linux 全套独立验收：本会话在 macOS 执行，**未运行** Linux 容器/远端（无该授权），Linux 全套结果由 fresh Reviewer 独立检出时复跑；候选不据此声明 Linux 通过。
- `protected` 中 46 用例在实施前全部失败（模块不存在），实施后**全部实际运行通过**（此前仅 collect）。

## 4. 宿主门禁与 not_run 事实

- Mac probe **未授权**（用户本轮明确 + handoff `mac_probe_authorized=false` + permissions.md 待 operator 批准）。本会话**未**创建 `/tmp/m2c2-sandbox`、未监听任何端口、未运行 `sandbox-exec`、未运行真实 Hermes、未读真实凭证、未访问 15721/18080/外网。
- 全部 required 子项（T1/T2/T3/T5/T6 各子项）记 **not_run**；T7 记 **unknown**（fresh 流程证据由独立 Reviewer 填）；平台能力 **partial**（后端能力已交付但未获真机强制验证）。
- 交付语义：诚实有限候选（代码 + 离线保护通过 + probe not_run + partial）。**不声明 full_pass、不宣布安全边界就绪**；live 恒拒绝。

## 5. 已知未决项（交付时如实列出）

1. profile 的最小运行只读允许清单（解释器 dylib/encodings 等）须在真机逐项披露与实测；当前为注释占位 + 默认 deny，不构成强制证明。
2. 46 冻结保护用例中 pre-cleanup 阶段 `verify_package` 语义：harness 在 pre-cleanup 阶段写空 `CHECKSUMS.sha256` 占位并拒绝未 finalize 包（"not finalized"）；最终交付树以 finalize 后单行 CHECKSUMS 为准。若 Reviewer 认为占位不当，可改为 pre-cleanup 阶段不写 CHECKSUMS、verify_package 对该阶段文件直接比对 pre-cleanup-manifest（需 protected 用例不变前提下的最小调整）。
3. T3 回环（两个 127.0.0.1 监听）与 T6 超时取消的**真实**执行路径已实现（`run_worker`/`process_tree`），仅在授权后运行；离线以 not_run 交付。
4. `deliveries/M2C2A/evidence/<attempt>/` 提交仅在授权 probe 产生真实捕获后进行（本轮无包）。

## 6. Git 事件

- 普通提交 + 普通推送 `hermes/m2c2a`（已授权）；无 force/reset/clean/删除分支；无 main 合并。
- 精确 SHA：`88232d470c261c2daeb38055d3db73c45b412217`（commit 后 `git rev-parse HEAD` + `git ls-remote origin hermes/m2c2a` 核验一致）。

## 7. fresh Reviewer 说明

- 按 HERMES-START 交付语义：本会话无法证明"真正 fresh"的独立审核（同 CLI 新开会话与"自演 fresh"的边界）；按规范执行"交付候选等待外部审核"路径，不模拟。fresh Reviewer 应：独立精确 candidate + bundle `f01525c5…`、复跑 §3 检查（Linux 全套 + Mac 单列）、填 T7 真实流程证据（可同 provider 但 `independent_provider=false`）、核对授权记录来源与可定位捕获。返修后以新精确 SHA 重新 fresh 审核；Reviewer 修改实现则换另一个 fresh 审核。
