# M2-C2 Planner 报告（PI 会话）

角色：M2-C2 Planner（规划 + 提案修订）。历史会话记录：P1–P5（本地 mlx-local / Qwen3.8-27B-8bit）、R2（本地会话）、R3 / R4（云端 minimax-cn / MiniMax-M3）。本轮为 R5 修订接管（本地 MLX 会话），只修订 `proposals/M2C2/` 文档；不实施宿主隔离、不运行真实 Hermes、不开展越界探测、不合 main。

## 1. 模型路由及确认方法

- 实际路由：本轮本地 MLX。本会话实际 provider=`mlx-local`，模型标识 `/Users/william/mlx_models/Qwen3.8-27B-8bit`（本地 MLX 8bit 量化）。确认方法：会话开头读取 PI runtime 环境变量 `PI_PROVIDER` / `PI_MODEL`（值来自本地 mlx 基础设施）；未发起云端模型调用。
- 与历史路由的关系：R3 / R4 修订由云端 `minimax-cn` / `MiniMax-M3` 完成（用户 2026-10-06 授权改用云端模型）。本轮回到本地 MLX 会话。历轮 SHA、处置内容按各自会话记录保留于 §10–§15 历史处置表；本轮不重复核验旧会话路由。

## 2. 已阅读的 Git refs 与精确 SHA

仓库：`/Users/william/Public/AI project/supervisor-M2A`（worktree of `emlszhou/supervisor`）。

| ref | SHA | 阅读内容 |
| --- | --- | --- |
| `origin/codex/m2c2-plan-review-5` | `76a54ccdfd096fc9c6407a4f60fe4e872449da8b` | 本轮审核分支；`deliveries/M2C2/pi-plan-review-5.md`（R5 候选 `22952883` 的 `request_changes`，R5-control / R5-manifest 两项 major） |
| `local/m2c2-plan-pi`（审核前） | `22952883ccafc2b84adfdb89041a060afc4e0466` | R5 审核的精确候选；`proposals/M2C2/` 四文件（plan / acceptance-matrix / permission-request / pi-report） |
| `origin/main` | `51d497cae7f20872e5a5f9c8825fd0f83323a92f` | 提案基线 |

本轮未做宿主探测（无 sandbox-exec 探针、无真实仓库写入、无 15721/18080 访问）。

## 3. 修改文件（本轮，全部在 `proposals/M2C2/`）

- `plan.md`：重写 §4.0 证据算法与 §4.1 示例。
  - **R5-control 关闭**：T1-R4 示例与单文件拒绝测试全流程改为同目标对照——正向对照与拒绝动作使用**同一 fixture、同一 argv、同一 cwd、同一拒绝目标**（`denied/AGENTS.md`），唯一差异是隔离配置（拒绝 profile vs 明确 allow 该目标的对照 profile，`isolation_mode: allow_target_profile`）；删除改变目标与 O_CREAT 动作模式的旧对照。目标初始化/恢复由 harness 独立完成（对照前记录初态 sha256，对照后恢复并重测建立基线），不靠 fixture 增删文件补偿。fixture 重写为只解析 `--target`（动作恒为 `O_WRONLY|O_APPEND`，无 `--allow-write`）。
  - **R5-manifest 关闭**：§4.0 新增"证据包生成与清理算法"唯一顺序——持久化并改好引用（summary/record_ref 统一为持久化根相对路径，内容变换先完成）→ 预清理校验（只依赖已持久化文件）→ pre-cleanup manifest（不含自身、不含未产生的 cleanup.json）→ 真实清理 → cleanup.json（仅记真实清理结果 + pre-cleanup manifest 摘要，不含最终 manifest 摘要）→ 最终 manifest（含 cleanup.json，仍不含自身；摘要放外置 `CHECKSUMS.sha256`）→ 最终校验。给出最终证据包树。
  - 删除 §4.0 中重复的"已修复"叙述（R3/R4 补丁段落），判定规则收敛为单一定义；§4.2 纸面演练 #14/#15/#16 与自检同步更新。
- `acceptance-matrix.md`：删除与 plan §4.0 重复的判定规则（改为引用）；`summary_ref` 统一为 `record_ref`；expected_refuse 第 4 条改为同目标对照 profile 正向成功（只换隔离配置）。
- `permission-request.md`：清理策略与证据持久化描述改为新算法（pre-cleanup 校验 → manifest → 清理 → cleanup.json → 最终 manifest + CHECKSUMS.sha256）；P2 白名单加入拒绝项同目标对照 profile 运行；删除历史"已修复"标记。
- `pi-report.md`：本文件重写为紧凑版（历史处置表保留，去除重复冗余）。

## 4. 实际运行的检查

- `git fetch origin`、`git show` 审核文件、`git diff --stat` 四文件、grep 检查旧规则残留（旧引用字段名 / 旧对照参数 / 外置摘要残留 / 自引用 manifest 等）。
- 未运行 pytest / ruff（本轮只改 Markdown 文档）。

## 5. 未运行项目及原因

- 宿主探测（sandbox-exec 探针、15721/18080 连接、真实凭证路径）：未授权（permission §9 N1/N9）。
- 真实 Hermes：C2B 独立授权范围。
- main 合并：用户授权门禁。

## 6. R5 处置摘要（R5-control / R5-manifest）

| # | 问题 | 处置 | 文件 |
| --- | --- | --- | --- |
| R5-control | 正向对照换了目标（`work/AGENTS_positive.txt` + `--allow-write` 改 O_CREAT），不是同一目标同一动作 | 对照与拒绝动作同 fixture/argv/cwd/目标，仅隔离配置不同；目标初始化与恢复由 harness 独立记录初态并重测基线；删除 `--allow-write`；越界成功仍 blocking | plan §4.0/§4.1；matrix；permission P2 |
| R5-manifest | manifest 自引用 + cleanup 记录未来 manifest 摘要形成循环；#14 依赖 #15 未来产物 | 唯一顺序：持久化改引用 → 预清理校验 → pre-cleanup manifest（不含自身/不含 cleanup.json）→ 真实清理 → cleanup.json（仅记真实结果 + pre-cleanup 摘要）→ 最终 manifest（含 cleanup.json，不含自身）+ 外置 CHECKSUMS.sha256 → 最终校验；不提前填成功、不在已删 attempt 复制 | plan §4.0/§4.2；permission §7 |

收敛方式：直接重写相关算法与示例、删除仍被当有效规则的重复旧段落，不再追加"已修复"说明；两项关闭后本提案可进入正式规格流程（R5 §下一步），不为非执行性错字再追加规划轮次。

## 7. 尚待用户决定的事项

- permission §10 各项（授权根、网络目标集合、合并授权、平台优先级、受监督模式、task-bundle 前置）不变，仍待决定。

## 8. 自审与 fresh 审核的区别；审核状态

- 本会话参与全部修订，不能自证 fresh。当前软件栈无法由本会话自主新建独立审核会话。审核状态 = **等待外部审核**：用户需另起独立会话（Hermes 新会话或独立 Codex 进程）对本轮精确提交 SHA 做审核，或人工审阅。此前本修订只是修订后的提案，不得作为冻结合同或实施依据。

## 9. 提交与推送（本轮）

- 分支：`local/m2c2-plan-pi`（基于 `origin/main = 51d497c`；从 R5 审核分支 `origin/codex/m2c2-plan-review-5` 恢复四文件后修订）。
- 本轮提交内容：4 文件（plan.md / acceptance-matrix.md / permission-request.md / pi-report.md），全在 `proposals/M2C2/`。
- 推送：普通 `git push origin local/m2c2-plan-pi-r5` 建立新分支 `origin/local/m2c2-plan-pi-r5`（R5 修订线，基于 R5 审核分支 `origin/codex/m2c2-plan-review-5`）。注：R4 线 `origin/local/m2c2-plan-pi`（`2295288`）与 R5 审核线（`76a54cc`）历史分叉（R5 审核分支含删除 `proposals/M2C2/` 的清理提交），无法普通 fast-forward；是否以 force-push 将 `local/m2c2-plan-pi` 指向 `2197894` 属 N7（force-push 永久禁止）范围，本轮不执行，待用户单独授权。无 reset/clean。
- 精确 SHA：`21978946382806baba2a89ba2056213f5804dad0`（commit 后 `git rev-parse HEAD` + `git ls-remote origin local/m2c2-plan-pi-r5` 核验一致）。

---

## 10. 历史处置表（P1–P5，回应 `codex/m2c2-plan-review-1`，本地 PI 会话）

| # | 严重度 | 问题摘要 | 处置（历史） |
| --- | --- | --- | --- |
| P1 | major | plan T4/矩阵 M1 假设 M2-B 提供未审计 MCP 零启用行为，但 M2-B 无真实工具配置/禁用/执行能力 | 四文件统一声明 M2-B 能力事实（无 MCP 能力）；C2A 范围 MCP 一律 not_run/unknown；真正验证移到后续真实 Agent 独立合同；fresh review 不宣称七项全 OS enforced |
| P2 | major | 探测目标偏离合成无秘密范围（真实 AGENTS.md / ~/.hermes/.env / 15721/18080 / 93.184.216.34） | 全部改为授权根内合成哨兵；网络只用 harness 自建回环；删除 93.184.216.34；纯回环证据范围声明 |
| P3 | major | 唯一写入根与 /tmp/m2c2-outside-* 冲突、trust 主体不清、attempt 创建可复用 | 统一授权根；排他创建（O_EXCL）+ 路径组件检查 + realpath 别名绑定；harness/Worker 权限分离；清理只归 harness |
| P4 | major | 拒绝证据与通过门禁不闭合（harness exit 0 冒充动作 exit 0；ENOENT 当拒绝；None 当通过） | 动作/harness exit 分离；联合证据 5 条；ENOENT/ECONNREFUSED 非拒绝证据；tree_cleanup_confirmed 决策表 + None 保持 live 关闭；门禁按 OS/流程分类 |
| P5 | major | 后端方案不唯一、C2A 依赖合并含糊 | §2 收敛为唯一推荐（macOS sandbox-exec）；§6 唯一可执行路径（C1 绑定不可变 ref 只读依赖，不依赖 M2-B 合并） |

## 11. 历史处置表（R2，`codex/m2c2-plan-review-2`）

- A：授权根外写入残留（`/tmp/m2c2-outside-*`、P3 文字、矩阵 R4、`out/` 目录）→ 删除，统一根内；P2 排除 P8。
- B：C2A 对 Step 0 合并依赖 → 删除 Step 0，C1 绑定完整 SHA 只读依赖；后续独立操作单列。
- C：证据与通过条件矛盾（unknown 既 partial 又"矩阵通过"）→ 统一 full_pass/partial 定义；逐子项记录字段与 capture 定位给出。
- 同次：`/coresignal/sandbox` 删除；进程组不作整树兜底；Worker 既有实现不隐含改写；harness/state 两文件一致；提前提取 `m2c2-outside` 等 grep 自检。

## 12. 历史处置表（R3，`codex/m2c2-plan-review-3`）

- R3-dependency：blob 对象 ≠ 文件 SHA256 → 导出到 attempt 内 `harness/deps/`（Python 文件 I/O，禁 shell redirect）；importlib 加载（不用 sys.path）；冻结任务包走正常规格流程。
- R3-evidence：只复制 evidence 丢 capture → 两目录整体复制；capture 含完整脱敏字节；cleanup.json 入持久化根；harness/state 统一全 deny；独立输出根列入 permission §2 第二张表（非 git push 隐式授权）。
- R3-verdict：非零 ≠ 拒绝 → 逐子项记录字段（action_exit_code int / action_errno 分离）+ 联合证据 + timeout/output_limit/startup_fail 各自分类不写 pass。

## 13. 历史处置表（R4，`codex/m2c2-plan-review-4`）

- R4-fixture：`harness/profiles/fixtures/` 路径错误 → fixtures 统一 `ro/fixtures/`（Worker 可读）；fixture 只解析固定 argv；permission P2–P6 同步。
- R4-dependency：`rev-parse <ref>^{blob}` 失败 → 单一 `<commit:path>` 语法 5 步算法（先 attempt 创建后依赖准备）；验证失败统一 ENVIRONMENT_FAILURE。
- R4-verdict：按 test_kind 分支判定；越界成功（无论 exit_code）= blocking；argparse 错误 → not_run。
- 证据引用/清理顺序：持久化根相对引用重写；cleanup 完成后才写 cleanup.json。
