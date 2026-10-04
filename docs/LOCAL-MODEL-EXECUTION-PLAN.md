# Supervisor 全本地模型执行规划

版本：1.0；日期：2026-10-04（Asia/Shanghai）。
适用仓库：`emlszhou/supervisor`。

用户决定：后续规划、实现、测试分析、审核、返修、接管和交接均交给本地模型。云端 Codex 不再是开发流程的必需角色。本文件是后续本地执行入口；它不授权实现者改写冻结合同、可信策略或历史审核结论。

## 1. 最终目标与当前起点

构建确定性 Supervisor，调度本地模型完成：

```text
任务 → 本地 Planner → 冻结合同 → 本地 Implementer
     → 工具执行独立检查 → 全新本地 Reviewer
       ├─ accept → 合并门禁 → 完成
       └─ return_once → 原实现者返修一次 → 全新 Reviewer
                         ├─ accept → 合并门禁 → 完成
                         └─ takeover → 本地 Repairer 接管一次
                                        → 全新 Final Verifier
                                          ├─ accept → 合并门禁
                                          └─ reject/blocked → 停止
```

模型做判断和代码工作；Git、pytest、Ruff、摘要核验、预算和状态转换由确定性工具执行。模型口头说“全部通过”不构成门禁证据。

当前事实：

| 项目 | 状态 |
| --- | --- |
| M0：ProcessRunner、AgentResult、Mock、事件 | 已经由 M0R 修复并独立接受，集成 main |
| 接受的 M0R 候选 | `f71e94e5f87757b93d659d05e5ef6d6dec144fdd` |
| M0R 最终审核提交 | `4bd68d1c007a8d5b5e88be03fd4cb8672291d6b4` |
| M0R 集成提交 / M1 实施基线 | `c6e224587b930a5b96c7723009584424f6bc52d5` |
| M1 规格发布提交 | `b90e8840a2efe5d3300578eb8d5d3e615a1629c4` |
| M1 当前执行输入 | `handoffs/M1/v1/task-bundle/`，必须导出到实施检出外 |
| M1 合同 SHA256 | `47ea6c51c46570e92f97c89428c9783a90bcc10e301e3e8d6ce38d4fb25dd142` |
| M1 实现分支 / 报告 | `hermes/m1` / `deliveries/M1/hermes-report.md` |
| 已集成完整项目测试 | 194 项通过；与独立验收重叠，不重复相加为成功率 |
| M1 新独立验收 | 42 项已收集，基线缺实现导致 42 失败、0 跳过 |
| 原生 macOS / Windows 证据 | M0R 最终审核未运行；Linux与模拟Windows有证据 |
| 真正 OS 隔离、真实 Agent Adapter、自动状态机、完整恢复 | 尚未实现 |

这是交接时的基准，不保证远端分支永远停在这些 SHA。启动时 fetch 并检查最新状态；如果 Hermes 已交付 M1，先审核该候选，不覆盖已有实现。

“全本地”指所有模型推理在本机。GitHub 交接、首次下载依赖和模型仍可能需要网络。模型权重、Agent缓存、私有会话和凭证均留本机，不进入 Git。

## 2. 本地角色配置

A/B 是业务角色，不是模型品牌。可用同一 Hermes 软件创建多个独立会话，也可用多个已核验的本地 Agent。

| 角色 | 工作 | 可写范围 | 不能做 |
| --- | --- | --- | --- |
| Operator / Coordinator | 确认用户目标、路由、收集证据、执行既有授权的Git交接 | 协调记录；按授权操作分支 | 仅凭模型声明批准成功、自动扩权 |
| Planner | 分解任务，定义API、预算、固定验收和源合同 | 独立规格分支上的任务/文档/保护验收 | 把自己的建议视为可信权限，改旧冻结包 |
| Implementer | 按合同实现、实现方测试、报告 | 合同 allowed_files | 改受保护测试、依赖、schema、审核记录 |
| Reviewer | 精确候选范围检查、重新跑验收、补充故障探测 | 独立审核分支的报告/证据 | 修改候选后继续签发独立accept |
| Repairer | 一次接管，在同一合同边界内修复 | 与Implementer相同的许可范围 | 通过接管扩大文件/预算/权限 |
| Final Verifier | 检查接管后的精确候选 | 独立最终审核记录 | 复用参与修复的会话签发accept |

推荐先采用顺序执行，避免Mac内存竞争和共享目录并发写入：

1. 本地模型A承担Planner/Reviewer；本地模型B承担Implementer。
2. Repairer使用另一独立会话，可以仍用A；最终审核再另起新会话。
3. 若只能加载一个模型，同一权重可顺序承担角色，但每次审核必须新会话、清空实现聊天历史，并重新读取精确合同和候选。
4. 同一供应商或同一权重的新会话只表示上下文分离。审核写`fresh_session=true`、`independent_provider=false`；换另一个本地权重也不自动使provider独立。
5. 不承诺同模型审核能消除共同错误。用不可被实现者修改的验收、故障注入和限制权限补足。

记录实际模型标识、量化、推理服务版本、Agent版本、上下文上限和会话ID。未知写null或“未测”，不用猜测型号/命令行参数。

## 3. 本机目录与运行准备

建议使用独立克隆和外部控制目录；无需Git worktree：

```text
supervisor-control/          协调者main/规格记录；不开放给实现角色
supervisor-M1/               当前实施检出
supervisor-M1-contract/      只读冻结合同；在实施目录之外
supervisor-review-M1-<id>/   新Reviewer独立克隆
supervisor-local-state/     私有会话、运行元数据和数据库；不提交Git
```

这些名称是本地布局建议，不是已创建的Mac路径。使用你实际的目录。克隆前检查目录是否存在，不覆盖、不reset/clean、不force-push。

本地模型开工前：

- Python 3.12、Git、uv 0.12.19，按uv.lock frozen安装。
- 查阅实际 Hermes/Agent help 与本地推理服务文档，记录新会话、非交互、模型选择、输出、取消、权限和网络行为。
- 用无秘密的合成目录验证读写范围、启动、退出、取消和输出解析。
- 确认所有角色实际指向本地端点/本地模型；禁用自动切换云模型，端点不可用时停止。
- 不将Git/生产凭证注入用于运行不可信测试的环境。Git推拉由协调流程单独执行。
- 无可核验的fresh session或执行隔离时，保留人工监督，不宣称已有无人值守安全执行能力。

不要假定某个Hermes CLI开关存在。本文件提供角色提示词；正式程序调用由M2探测后确定。先手动启动本地新会话粘贴提示词即可，不需要云端模型。

## 4. 立即执行：完成现有 M1

现有 M1 API/预算/42项验收保持不变。用户这次只改变模型角色路由，不改变M1业务合同，不改冻结内容或摘要。包内历史“Codex审核”文字由本次用户明确的全本地指令覆盖其供应者选择；fresh-session、范围、预算和独立证据要求继续适用。

### 4.1 获取权威输入

如果已有M1实施检出，先检查`git status`、分支与HEAD，不重复克隆到同一目录。如果尚未开工，在一个不存在的新目录执行：

```bash
git clone --branch hermes/m1 https://github.com/emlszhou/supervisor.git supervisor-M1
cd supervisor-M1
git fetch origin
M1_SPEC=$(git rev-parse origin/main)
M1_TOOLS=$(mktemp -d)
git show "$M1_SPEC:scripts/prepare_git_handoff.py" > "$M1_TOOLS/prepare_git_handoff.py"
git show "$M1_SPEC:scripts/verify_handoff.py" > "$M1_TOOLS/verify_handoff.py"
python3 "$M1_TOOLS/prepare_git_handoff.py" --ref "$M1_SPEC" --contract-prefix handoffs/M1/v1 --output ../supervisor-M1-contract
uv sync --frozen --group dev
CONTRACT=$(cd ../supervisor-M1-contract/task-bundle && pwd)
uv run --frozen ab-supervisor doctor
uv run --frozen pytest -q
PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest "$CONTRACT/tests/protected/test_m1_acceptance.py" -q
```

导出器要求开工HEAD精确为基线且检出干净；已有实现不能重跑initial-kickoff覆盖合同。初始42失败应全部是缺实现，不能忽略其他异常。

### 4.2 M1实施顺序

保持一个合同，按内部小步骤实现，避免一次同时调试五个模块：

| 顺序 | 模块 | 先实现和验证 |
| --- | --- | --- |
| 1 | `workspace/baseline.py` | 实际Git根、有HEAD、clean/staged/untracked/ignored检查，链接/submodule/LFS拒绝 |
| 2 | `workspace/snapshot.py` | 规范路径、tracked/untracked、删除/模式、确定性摘要、陈旧快照拒绝、读取变化检查 |
| 3 | `workspace/bundle.py` | draft严格验证、输出不覆盖、源不改、manifest、自身及inventory核验、异常清理 |
| 4 | `policy/changes.py` | 快照先校验、forbidden优先、规范glob、新增/删除/模式变化、文件/行预算 |
| 5 | `storage/intents.py` | 事务reserve、绑定冲突、complete、unknown、持久化、并发、失败回滚 |
| 6 | 允许的单元测试/报告 | 覆盖全部失败路径，运行整套检查，准确绑定代码与报告提交 |

模块依赖和签名以冻结`api.md`为准。不得因为本规划表格而增加允许文件。

### 4.3 M1完成门禁

- 允许五个实现模块、`tests/unit/test_m1_*.py`、`deliveries/M1/hermes-report.md`。
- 从`c6e2245...`到最终候选累计最多14文件、2800新增+删除行，含报告；所有未跟踪交付文件纳入提交。
- 全部verification必需检查真实完成；外部42项、旧完整项目及实现方单元、specs、Ruff都通过。
- 新Reviewer复跑，而不是读取实现者测试摘要直接accept。
- 追加检查：父目录链接、硬链接、大小写冲突、LFS/submodule、读取期间变更、坏类型manifest、SQLite事务提交失败、不同连接并发和sidecar链接。
- 数据库pending/unknown永不自动重放。没有副作用证据时停止为NEEDS_HUMAN。
- 仅本地通过的系统可声明实测；macOS运行就记macOS，Windows未测就记未测。

代码先commit，使用外部`snapshot.py --commit <完整代码SHA>`计算tracked代码树摘要，再单独commit报告。M1 runtime快照算法覆盖工作区，包括untracked/删除，与报告工具tracked-commit摘要不是一个算法。

## 5. 全本地 Git 交接规则

用户已授权本仓库正常commit/fetch/pull/push。实现与审核分支继续分离：

| 类型 | 分支建议 |
| --- | --- |
| 规格 | `local/spec-<task>`，经规格核验后由协调者发布main |
| 实现 | 当前`hermes/m1`；后续`hermes/<task>` |
| 审核 | `local/<task>-review-1`、`local/<task>-review-2` |
| 接管 | `local/<task>-takeover` |
| 最终审核 | `local/<task>-final-verify` |

这些名字不要求Supervisor产品按`hermes/local`字符串分支调度业务。未来产品仅认识配置中的角色/provider/worker。

每次交付包含task/run/attempt、baseline、bundle、实际候选完整SHA、快照算法与摘要、author/session、检查时间/argv/cwd/退出码/收集数。代码变化使旧通过失效。

Reviewer示例（替换实际TASK、BRANCH、CANDIDATE，候选必须来自已fetch远端）：

```bash
git clone https://github.com/emlszhou/supervisor.git supervisor-review-TASK-1
cd supervisor-review-TASK-1
git fetch origin
git switch -c local/TASK-review-1 CANDIDATE
```

先检查基线祖先关系、所有差异和冻结保护输入，再运行测试。审核记录提交在其审核分支；实现者只读取记录，不merge/cherry-pick审核记录进入受限实施分支。

报告继续使用`schemas/review.schema.json`。接管者自己的会话不能成为最终Verifier。审核model字段填实际模型标识，provider/session不得沿用旧会话。附带证据文件记录完整候选SHA，避免schema未知字段。

合并分两件事：

1. 技术门禁：精确候选accept、范围/预算/检查/快照满足、远端没有未审核的新代码。
2. 授权门禁：当前任务用户已明确授权合并，或可信协调配置已预先授予该分支的合并权限。全本地路由不自动增加main合并/部署权限。未授权时保留可合并结果，交给用户决定。

获授权后由本地Coordinator执行普通merge，保留实现及审核历史，检查集成后的模块与已接受候选一致，运行集成检查，再正常push main。发生分叉或冲突先保留工作；需要改代码解决冲突时重新独立审核，不强推。

## 6. 每个新任务的规格与保护输入

M1之后只发布下一小任务，不一次让模型实现M2–M4全部。

1. Planner读main、前置验收、架构与用户目标。
2. 源规格必须给出问题、目标、非目标、固定API、允许/禁止文件、实际基线、预算、平台范围和必需检查。
3. 单独本地规格Reviewer检查可实现性、API冲突、权限扩大、遗漏失败路径和空/重复验收。
4. 用可信schema/路径/预算工具核验，协调者冻结新版本、发布摘要和实施分支；实现者不能签发自己的冻结包或修改保护验收。
5. 实施前验证包与基线，导出控制面包到实施写入范围之外。
6. 失败次数/时间/范围耗尽后停止。同一问题不能通过连续换任务ID重置预算和返修次数。

规格或受保护测试有错误时保留失败证据，提出明确规格变更；不得在实现分支悄悄修验收。批准后新版本标记旧run SUPERSEDED，重新绑定新验收，不冒称旧run成功。

## 7. M2：本地 Agent 接入与真实边界

M2目标是让程序安全调用本地模型Agent，而不是重新接入云端审核。HermesAdapter为第一优先，另一个本地角色配置用于Reviewer；云Codex/Claude接入为可选兼容扩展，不再是当前完成门槛。

建议顺序发布规格小任务，实际文件/预算由本地Planner逐个冻结：

| 子任务 | 交付 | 必须能失败的验收 |
| --- | --- | --- |
| M2-A 能力探测 | 实际Agent/推理服务版本、调用契约、能力矩阵；不猜CLI参数 | 非交互、模型实际路由、fresh会话、错误端点、断连、取消、输出形态 |
| M2-B Adapter | 本地Hermes构造请求、严格AgentResult、身份绑定、最小env | 正常/非零/超时/损坏/错身份/未知usage，不虚构token |
| M2-C LocalWorker边界 | 文件、进程、网络、MCP权限验证 | 不能写Supervisor/合同/保护验收/凭证，未授权shell/network/MCP操作被拒绝 |
| M2-D 可信验收器 | 控制面固定检查、候选只读、汇总与摘要 | 改保护输入、零收集、日志损坏、超时、陈旧候选均拒绝accept |
| M2-E 合成端到端 | 无秘密小仓库上的真实本地模型任务 | 一次实现成功、一次返修、权限攻击、取消与资源清理 |

能力表同时记录declared/observed/enforced。CLI帮助或模型宣称“sandbox”不能证明权限边界。

Mac上的隔离方案须实测选择：受限用户/专用VM/经核验的容器及挂载策略等。不能把独立Git克隆、只读提示词、Python路径检查当OS sandbox。macOS没有足够可强制能力时，保持受监督模式或使用经验证的隔离执行环境；不得关闭校验/权限绕过来获取“成功”。本地推理服务可在Mac宿主运行，执行Worker与其通信权限要单独最小化验证。

M2完成之前不运行无人监督、有广泛写权限和宿主凭证的真实Agent。

## 8. M3：确定性编排

| 子任务 | 范围 | 验收重点 |
| --- | --- | --- |
| M3-A 状态与路由 | CREATED到终态，角色/provider/worker分离 | 非法转换、身份/摘要不符拒绝；不能靠模型文字改变流程 |
| M3-B 审核守卫 | 验证检查与fresh review证据绑定 | 修改后旧accept失效；同实现会话无法审核自己 |
| M3-C 有限返修 | 实现、一次返修、一次接管、最终审核 | 各分支都运行到终态；预算耗尽停止，不无限循环 |
| M3-D CLI流程 | 明确的运行/状态/取消入口 | 参数错误真实非零；无副作用的预览；日志只含脱敏元数据 |
| M3-E 全本地真实任务 | 两个角色配置、固定任务包、小仓库 | 无云fallback，完整保存证据；不自动push产品目标仓库 |

调用模型前持久化operation意图，调用完成证据先落盘，再推进状态。operation pending不等于模型尚未执行，禁止重复启动第二份。

默认产品策略仍不自动push。当前开发仓库已授权的Git交接与Supervisor替用户项目执行操作的授权分开。

## 9. M4：恢复、兼容与运行验证

| 子任务 | 范围 | 验收重点 |
| --- | --- | --- |
| M4-A 故障窗口 | Agent启动前后、证据提交前后、DB提交、进程退出 | 每个窗口可注入崩溃，恢复不盲目重放 |
| M4-B 幂等导入 | 重复/过期完成、旧attempt、旧快照 | 只接受当前绑定，冲突保留证据并停止 |
| M4-C 资源恢复 | 断连、取消、崩溃、进程树、临时文件 | 诚实确认；不凭leader退出宣称完整树回收 |
| M4-D 平台验证 | 首先原生macOS；Linux/Windows按实际资源分批 | 原生测试有OS/工具版本；模拟测试不能改写为原生支持 |
| M4-E 脱敏和保留 | 元数据、摘要、usage未知、日志保留 | 哨兵秘密不泄漏，原始transcript默认不持久化 |
| M4-F 受监督运行评估 | 连续真实任务与停止条件 | 正确性、范围、安全违规、人工介入、时间/内存有记录 |

达到M0–M4全部必要门禁后才称第一版完成。M5远程Worker、其他Agent扩展和评测是可选，不阻塞本地第一版。

## 10. 本地模型资源与质量策略

不预设Mac内存或模型速度。先用固定小任务测实际峰值内存、首token延迟、吞吐、上下文长度、超时和取消。顺序运行角色；实测足够再考虑多个只读审核任务并行，不能两个实现者共享写同一目录。

给模型的是当前合同、固定API、相关模块和上一审核findings，不把整个长期聊天塞进每个任务。实现会话可在本轮续接；审核永远fresh。使用上下文摘要时标明来源，不把实施者的“修完了”变成事实。

质量记录按相同任务/基线/验收比较：首次通过率、返修后通过率、接管率、最终失败率、scope违规、独立探测缺陷、wall时间、峰值RSS、人工介入次数。样本不足只报告原始计数，不虚构通过率或模型能力。

若重复出现小样例通过但边界失败，强化固定回归和故障探测，再开下一个任务；不要靠增加对话轮数取得accept。

## 11. 可以直接粘贴的角色提示词

以下是角色说明，实际TASK/REF/SHA/CONTRACT必须由Coordinator填入并核验，不让模型自己编造。M1此刻无需重新Planner，直接使用既有冻结合同。

### Planner

```text
你是本地Planner。仓库emlszhou/supervisor；当前任务<TASK>。
先读AGENTS、LOCAL-MODEL-EXECUTION-PLAN、架构/接口/安全/验收/路线图。
只准备当前一个小任务的源规格、固定API、允许/禁止文件、预算、失败路径和独立验收。
不得实现生产模块，不改历史冻结包，不猜Agent CLI参数或权限能力。
产出规格分支和报告，交给另一个全新本地规格Reviewer核验后冻结。
无法从既有授权确定的权限/副作用必须明确列出，不自行批准。
```

### Implementer（M1直接使用）

```text
你是本地Implementer，完成M1-integrity-intents。
按main的handoffs/M1/v1/README.md，在hermes/m1和外部冻结合同开工。
合同SHA256=47ea6c51c46570e92f97c89428c9783a90bcc10e301e3e8d6ce38d4fb25dd142。
全部生产改动只在allowed_files；遵守api.md精确签名、14文件/2800行累计预算。
实现方补充test_m1_*.py，运行全部verification；不能改保护输入或skip核心验收。
先提交代码，再用准确代码SHA/摘要写deliveries/M1/hermes-report.md并单独提交。
正常push hermes/m1；报告代码和最终tip完整SHA、真实结果与未测平台。
不合并main，不修改旧M0/M0R，不使用云模型fallback。
```

### Reviewer

```text
你是全新本地Reviewer，未参与实现，当前stage=<review_1或review_2>。
候选完整SHA=<CANDIDATE>，baseline=<BASELINE>，外部合同=<CONTRACT>，trusted bundle=<HASH>。
先核验精确SHA、祖先、允许文件、全部差异、预算和保护输入，不相信实现者自述。
在独立克隆和最小环境里重新运行必需检查，确认收集数/退出码/时间/报告属于本候选。
补充有外部watchdog和清理的故障探测。不得修改候选实现或保护验收。
按review.schema记录decision，fresh_session真实，provider/model/session精确，同provider不写独立供应商。
review_1只accept/return_once/blocked/reject；review_2只accept/takeover/blocked/reject。
将报告及可复现证据提交到独立审核分支，交给Coordinator；不merge main。
```

### Repairer

```text
你是本地Repairer。当前合同只允许一次接管，使用与原实现相同的范围和预算。
读取精确候选与全部findings，修复并补充允许的回归测试，不扩大权限或改验收。
先代码commit，再准确报告commit，正常推送独立takeover分支。
你不能签发自己的final accept；完成后交给另一个全新本地Final Verifier。
```

### Final Verifier

```text
你是全新本地Final Verifier，未参与接管实现。
重新核验最后精确候选、合同、范围、预算、全部必需检查与故障探测。
stage=final_verify，decision只accept/blocked/reject；剩余blocking/major不能accept。
原生平台未测写明未测；不把路径校验或Git克隆称为OS sandbox。
提交最终记录和证据到独立final-verify分支。最终失败即停止，不要求再开一轮修复。
```

### Coordinator

```text
你是本地Coordinator。所有模型调用只能使用已核验的本地端点；不可自动回退云模型。
只按可信合同/配置路由角色，收集精确SHA和证据，禁止仅凭聊天声称成功推进状态。
对当前授权的本仓库正常commit/fetch/pull/push不反复询问；不force-push/reset/clean。
同任务最多一次返修、一次接管；不同作者会话与fresh审核记录必须保留。
有合并授权才合并已接受的精确候选；未知副作用、权限扩大或旧结果冲突则停止报告。
当前先完成M1，再逐个规划M2小任务，不一次实施整个项目。
```

## 12. 每轮交接清单与停止条件

每轮交接最少给出：

- task/run/attempt、角色、实际本地模型/Agent版本/session。
- baseline、spec/ref、bundle、代码SHA、报告tip SHA；快照具体算法。
- 所有修改文件，包括untracked新文件、删除、mode；累计新增+删除预算。
- 每个必需检查argv/cwd/时间/exit code/pass/fail/skip/unrun。
- 审核decision、全部findings、上一轮修复状态和新独立探测。
- 未实测平台、未实现能力、下一接收角色和只读报告Git路径。

发生以下任何一种情况停止当前依赖流程：保护输入改变、越界、预算超限、零收集/损坏报告、错误身份或陈旧snapshot、不能创建fresh审核、隔离能力不足、模型端点回退云端、未知外部副作用、返修/接管额度用尽。不要用“多让模型试几次”代替明确终态。

## 13. 现在应该做什么

1. 将本文件交给本地Hermes Coordinator阅读；按用户决定切换所有后续角色为本地模型。
2. 检查hermes/m1是否已有候选；没有则按第4节开工，有则起fresh本地Reviewer先验收。
3. M1通过并获得合并授权后集成main，保留准确接受记录。
4. 本地Planner逐个准备M2-A到M2-E，再完成M3和M4。
5. 后续代码流程由本地模型执行，无需再把代码交回云端Codex实现或审核。用户仍掌握目标、可信权限和停止决定。
