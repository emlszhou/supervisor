# 给 Hermes 的 M0 任务

你是主要实现者。先读根目录 AGENTS.md、HERMES.md，再读本目录所有合同输入及 docs/interfaces.md、docs/security-model.md。

仓库内文件是合同源草案；执行时只认协调者另外交付的 `task-bundle/task.json`、manifest 和可信摘要。该执行包必须是 frozen 并绑定实际 Git 基线，不能由实现者自行冻结和批准。`api.md` 与独立黑盒验收也是冻结输入。

只实现 ProcessRunner、Adapter/AgentResult 协议、Mock 和最小事件。允许文件由 allowed_files.json 明确列出；不要更改 schema、合同、protected tests、依赖、CLI 或其他文件。

按 requirements.md 完成标准库实现与新增单元测试，运行 verification.json 指定的可信检查，按 templates/implementation-report.md 交付真实结果。报告所有未验证平台和进程树能力。不要启动真实模型、连接远程机器或自动 push。

独立 Reviewer 会重新执行黑盒验收；若有 findings，最多返修一次。无法完成或需要扩展范围时，报告具体阻塞，不自行放宽验收。
