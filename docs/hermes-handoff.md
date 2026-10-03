# Mac mini 上 Hermes 的 Git 交接

当前采用用户已授权的 Git 推拉流程，具体命令见 [Git 交接协议](git-handoff.md)。不再要求 Mac 读取云端 /workspace 路径。

## 1. 克隆与导出合同

克隆 hermes/m0，fetch main，运行 scripts/prepare_git_handoff.py，将 main 的 handoffs/M0/v2/ 导出到检出目录之外。脚本核验精确 Git 基线、干净检出、普通文件模式和 manifest 摘要，不覆盖已有导出目录。

仓库 tasks/M0/ 是源草案，外部 task-bundle/ 是 frozen 执行包。保留原始 v1 离线包，不改写旧冻结内容。Git 导出是受监督开发的完整性校验，不证明 OS 隔离已经实施。

## 2. 本机前提

准备 Python 3.12、Git、uv 0.12.19，运行 frozen 安装和 doctor。使用 Mac 已有 Git/Hermes 认证与本地模型，记录版本和模型标识，不传递凭证或原始会话。

M0 不要求实现真实 HermesAdapter；由 Hermes 承担开发，目标代码使用 Mock。真实 CLI 接入参数、输出和权限能力属于 M2 核验。

## 3. 实现与交付

读 AGENTS.md、HERMES.md 与冻结合同，包括 api.md 和允许/禁止范围。只实现四个模块、新增合同允许的单元测试，并在 deliveries/M0/hermes-report.md 写交付报告。

运行完整测试与合同检查，分别记录通过/失败/跳过/未运行。先提交代码，再在报告中引用代码提交 SHA、基线和 bundle 摘要，单独提交报告。推送 hermes/m0；不向 main 推送，不 force-push，不扩大范围。无须为已授权的这类交接再次请求确认。

## 4. 独立审核与返修

把实现分支最终 SHA 提供给 Codex。新 Reviewer 会话拉取准确候选，检查范围、保护输入与基线，再重新执行验收。

findings 写入 Codex 审核分支。Hermes fetch 指定审核提交并只读其报告，不合并审核文件进实施分支；最多返修一次。再次失败由协调者接管，接管代码需要另一个 fresh Reviewer 验收。

通过不等于合并 main 或发布，后续合并单独决定。
