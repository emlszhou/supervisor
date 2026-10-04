# Codex / Hermes 的 Git 交接协议

用户已授权双方通过本仓库的 commit、fetch、pull、push 交接，无需每次重新询问。该授权不等于向其他仓库推送、force-push、合并或部署。

## 分支与冻结版本

- `main`：Codex 发布规格、冻结合同和协调记录。未实现阶段的 M0 测试失败如实保留。
- `hermes/m0`：Hermes 只在此提交实现和报告，由冻结的代码基线开始。
- `codex/m0-review-*`：Codex 的审核/返修记录分支；接管修改后再由 fresh session 验收。
- main 的 `handoffs/M0/v2/` 是 Git 交接冻结包；v1 离线包不修改。v2 仅增加 Git 交付和报告路径，M0 API/57 项独立验收不放宽。

冻结合同的 baseline_commit 是实施起点，不是之后发布该合同的提交。main 会比实现分支多出发布文件，Hermes 不把 main 合并到实施分支。

## Mac mini 首次开工

选择一个新的独立目录（已经存在时先核对，不覆盖），执行：

```bash
git clone --branch hermes/m0 https://github.com/emlszhou/supervisor.git supervisor-M0
cd supervisor-M0
git fetch origin
python3 scripts/prepare_git_handoff.py --ref origin/main --output ../supervisor-M0-contract
uv sync --frozen --group dev
uv run --frozen ab-supervisor doctor
```

助手会打印实际基线和 bundle SHA256，核验当前 HEAD、源 Git 文件模式和冻结文件摘要。执行合同在 `../supervisor-M0-contract/task-bundle`；实施目录是当前 supervisor-M0。已有导出目录不会被覆盖。仅导出文件，不启动 Agent，也不实施 OS sandbox。

先读 AGENTS.md、HERMES.md 和外部合同 api.md、requirements.md、allowed_files.json、verification.json。凭证使用本机已有 Git/Hermes 认证，不把 token 写入文件或聊天。当前只要求 Python 3.12、Git、uv 0.12.19；模型按用户本地配置使用。

## Hermes 提交与推送

本次允许四个实现模块、`tests/unit/test_m0_*.py` 和 `deliveries/M0/hermes-report.md`。保护输入、依赖和其他文件不允许改变。

1. 实现并运行完整 pytest、合同指定检查和 Ruff，记录所有失败/未运行平台。
2. 只添加允许的代码和单元测试，提交代码。记录这个代码提交 SHA。
3. 按模板写交付报告，引用代码 SHA 与冻结输入摘要，再单独提交报告，避免报告自引用自身提交。
4. 推送 `git push origin HEAD:refs/heads/hermes/m0`。报告分支最后的 `git rev-parse HEAD`，Codex 会独立核验。

提交前检查 `git status` 和暂存 diff，不使用无范围的 `git add .`。禁止 main 推送、force-push、reset/clean、提交凭证/缓存/原始对话。测试失败也可以交付明确的失败报告，但不声称通过。

## Codex 拉取与审核

获取 `origin/hermes/m0` 的完整候选 SHA，先校验冻结基线祖先关系、候选所有文件差异和保护输入，保持当前未提交工作。必要时用独立临时 clone 核验指定提交，不额外创建 worktree。

新 Reviewer 会话重新运行检查，结果绑定实际候选提交、合同摘要与代码快照；实现者报告只是证据线索。review 文件放在审核分支 `deliveries/M0/codex-review-1.json`，按 review schema 给出 findings；报告明确 code SHA 与报告 SHA，避免旧结果用于新代码。

需要返修时将审核分支提交推送，给出明确审核 SHA。Hermes fetch 后读取 `git show <审核SHA>:deliveries/M0/codex-review-1.json`，不 merge/cherry-pick 审核记录进入受限实现分支。最多返修一次，再次独立审核；接管后必须另一个 fresh Reviewer 验收。

正常更新用 fetch 和 `pull --ff-only`，不拉 main 到实现分支。出现分叉、脏工作区、远端已被他人更新或基线/合同冲突时保留并报告。完成后合并 main 另行决定，不把 push 成功当成验收通过。

## 权限边界

这里是人和开发 Agent 的协作授权，不改变未来 Supervisor 产品“默认不自动 push”的运行策略。分支约定/文件校验不等于已配置 GitHub branch protection、只读挂载或 sandbox；目前采用受监督开发，真实执行边界在 M2 核验。

## M0R：Review-2 后的新任务

原 M0 合同已拒绝并关闭，不再在 hermes/m0 返修。M0R-review2-remediation 从 fc479e760cbcd1e5259e2d62aeddaa6033d2c915 继续，冻结输入在 main 的 handoffs/M0R/v1；新分支 hermes/m0r，新报告 deliveries/M0R/hermes-report.md。本次1800行预算仅统计新基线到候选的新增+删除，旧1866行超限记录不变。其他范围/保护/凭证/禁止强推规则沿用。

Hermes 不合并 main。fetch 后先把 main 中 scripts/prepare_git_handoff.py、scripts/verify_handoff.py 用 git show 导出到检出外同一工具目录，使用新版导出器 --contract-prefix handoffs/M0R/v1，在干净且HEAD匹配新基线的实施检出根导出新合同。旧 exporter 默认仍是 M0/v2，不适用于新任务。具体可执行指令见新 handoff README。

snapshot区分代码commit与最终报告tip。代码报告先后提交；每个指定Git树按path排序[{path,mode,sha256(raw blob)}]，对json.dumps(sort_keys=True,separators=(',',':'),ensure_ascii=False) UTF8字节计算SHA256。不把旧candidate snapshot复制进新报告；最终tip由交接消息和Reviewer绑定。
