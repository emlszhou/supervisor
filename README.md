# AB Agent Supervisor

一个本地优先、跨项目、跨 Agent 的 Coding Supervisor。由确定性程序调度规划、实现、审核和有限返修，模型只承担明确角色。

**当前状态：设计与开发脚手架已准备，工作流、Agent Adapter、隔离和恢复尚未实现。** `doctor` 只检查开发前提，不代表应用或安全机制可用。

## 目标工作流

```text
A 规划 → B 实现 → A-fresh 审核
                    ├─ 通过 → 完成
                    └─ 未通过 → B 返修一次 → A-fresh 复审
                                              ├─ 通过 → 完成
                                              └─ 未通过 → A 接管修复 → A-fresh 最终验收
                                                                       └─ 失败 → 停止并报告
```

A/B 是角色绑定，可换 Codex、Claude、Hermes 或其他 Agent。审核均为新会话；同模型的新会话只算上下文独立，不能声称供应商独立。

开发本项目时优先采用：Codex 设计合同与审核，Mac mini 上的 Hermes＋本地模型实现，必要时再切换实现者。

## 开始开发

需要 Python 3.12、Git、uv 0.12.19。所有命令从仓库根目录执行：

```bash
uv sync --frozen --group dev
uv run --frozen ab-supervisor doctor
uv run --frozen python scripts/check_specs.py
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv build --no-sources
```

`uv.lock` 固定依赖；不需要云端模型密钥或 Mac mini 连接即可完成脚手架检查。真实 Agent 的运行是后续显式配置的检查，不纳入当前测试通过结论。Mac/Windows 的说明见 [开发指南](docs/development.md)。

M0 独立行为验收现已加入。执行代码尚未实现，因此完整 `pytest` 应报告 M0 失败，不能用跳过来获得通过。只检查已完成的准备工具时，显式运行 `uv run --frozen pytest tests/test_cli.py tests/protected/test_specs.py tests/protected/test_handoff_verifier.py`；这不替代 M0 验收。交接流程见 [M0 开工步骤](docs/m0-kickoff.md)。

## 文件入口

| 文件 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 所有开发 Agent 的工作范围与交付规则 |
| [项目规格](docs/project-spec.md) | 目标、范围和不变量 |
| [架构](docs/architecture.md) / [接口](docs/interfaces.md) | 模块边界、Worker 与 Adapter 协议 |
| [状态机](docs/workflow.md) | 有限返修、审核失效和异常终态 |
| [安全模型](docs/security-model.md) | 可信边界、执行限制和能力验证 |
| [验收规则](docs/verification.md) | 受保护检查、证据和快照绑定 |
| [路线图](docs/roadmap.md) | M0–M5 的依赖与完成条件 |
| [Hermes 交接](docs/hermes-handoff.md) | 本地实现与云端审核的具体步骤 |
| [Git 交接协议](docs/git-handoff.md) | 已授权的分支、克隆、推拉与报告路径 |
| [准备验证记录](docs/preparation-status.md) | 当前已验证能力与尚未实现的功能 |
| [M0 任务包](tasks/M0/README.md) | 第一个可交给实现者的任务草案 |
| [schemas/](schemas/README.md) | 版本化输入输出格式 |
| [templates/](templates/README.md) | 后续任务、审核和交付模板 |
| [examples/](examples/README.md) | 不启动真实 Agent 的示例配置与结果 |

## 目录职责

```text
src/supervisor/
  core/           状态、转换和事件
  agents/         Agent 适配器及统一结果
  workers/        执行节点与进程执行
  workspace/      Git 基线及代码快照
  policy/         可信规则与能力检查
  verification/   独立执行的验收
  storage/        SQLite 与持久化
schemas/          协议格式
tasks/            任务合同及允许/禁止范围
templates/        可复用文档模板
examples/         示例配置和协议样本
tests/unit/       实现者可新增的单元测试
tests/integration/ 集成检查
tests/protected/  实现者不可修改的验收基线
scripts/          规格检查工具
docs/             设计、操作与交接
```

目录中尚未实现的模块仅有说明文件。不会用占位的 `PASS`、空实现或跳过测试来代表功能完成。

## 当前交接边界

仓库内 M0 任务是 **draft 源合同**；当前 Git 交接使用 main 上 handoffs/M0/v2/ 的冻结执行包，校验后导出到实施目录之外。原始 v1 离线包保持不变。用户已授权本项目的正常 Git 推拉，Hermes 从 hermes/m0 开发和交付，Codex 从 main 发布规格并审核候选；不自动合并。Supervisor 产品本身的自动执行/推送能力尚未实现。云任务使用现有隔离检出，不额外创建 worktree。
