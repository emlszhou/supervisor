# Claude Code 开发入口

遵守 [AGENTS.md](AGENTS.md)。Claude 是可替换的实现者或审核者，不在核心流程中写死其身份。

优先开发分工为 Codex 设计/审核、Hermes 实现。只有当前任务明确指定时才由 Claude 接入。权限参数和输出格式需核验，不能启用绕过权限或自动推送。
