# 设计决策记录

## D001：确定性控制面

流程由程序和可信规则决定，不增加调度 LLM。Agent 可以提出计划与 findings，不能增加权限或决定自己的最终验收。

## D002：Python 3.12 与 uv

标准库包含 argparse、tomllib、sqlite3、subprocess，生产依赖起步为零。开发检查使用 pytest/jsonschema/Ruff，依赖锁定。模型调用由现有 Agent Harness 承担，不直接集成供应商 SDK。

## D003：Mock 优先，真实能力后核验

先稳定 Worker/结果/事件，再根据 Mac mini 上的实际 Hermes 版本接入。Codex/Claude/Hermes 命令参数与输出格式都不从历史对话推断。Hermes 作为首批真实 Adapter 用来检验通用性。

## D004：恢复标识从 M0 定义

task/run/attempt/operation ID 与 artifact 摘要在接口起点确定。SQLite 与恢复实现在 M1/M4 逐步完成；禁止恢复时盲目重放非幂等 Agent 调用。

## D005：工作区与安全隔离分离

独立工作区用于变更管理，OS/工具/网络边界用于限制能力。仅支持能核验必需边界的平台，能力不足时明确阻断。

## D006：规格和实现分工

准备阶段生成文档、格式、模板、脚手架。核心实现交给 Hermes。schema/受保护验收/合同的变化走单独规格任务。一次主要返修、一次接管，然后停止。

## 待后续证据决定

Mac mini 的 OS/Python/Hermes/模型版本、结构化输出和隔离能力；Codex CLI 的当前参数；各平台子进程树控制机制；正式发布许可。上述信息不阻塞 Mock 开发，但阻塞相应真实能力声明。
