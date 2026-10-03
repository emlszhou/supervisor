# 给 Mac mini 上 Hermes 的交接步骤

## 1. 先固定任务输入

由协调者审阅规格、形成 Git 基线提交，在 `tasks/M0/task.json` 填写真实 baseline，核对允许/禁止路径和验收。冻结包存 Worker 写入范围之外，记录 manifest 与 bundle 摘要。当前任务是 draft，没有被假装冻结。

冻结器尚未实现，初期可由协调者按 `docs/interfaces.md` 的摘要规范人工打包并独立复算。不要由 Implementer 生成并自行批准基线或 manifest。无法建立只读边界时只做受监督的合成测试，不宣称安全无人值守。

## 2. 本地前提核对

在 Mac mini 的独立开发检出核对 Python/Git/uv 版本，运行 README 的安装与检查。记录 Hermes 安装来源、版本、实际使用的本地模型标识和模型服务配置名称；不记录凭证值。

M0 不要求 HermesAdapter：可以人工把任务交给 Hermes，让它实现 Mock/ProcessRunner。Hermes 非交互参数、结构化输出、取消和权限能力的正式探测属于 M2。

## 3. 投递任务

投递 `tasks/M0/HANDOFF.md`、冻结后的任务包和必要代码。明确仅允许修改 `allowed_files.json` 的范围、不得修改受保护规格和验收、不得增加依赖或推送。不传云端环境变量或宿主凭证目录。

M0 按要求实现单元测试，输出到任务专用本地检出。超范围需求先报告，不自行扩展。

## 4. 交付

按 `templates/implementation-report.md` 提交脱敏报告、完整 diff/候选代码、基线提交、最终快照摘要、所用模型、命令退出码和真实测试结果。原始 Agent transcript 默认不交接。

## 5. 独立审核

开启全新 Codex 会话，以原始合同、候选代码、差异及可复验的证据为输入。重新安装 frozen lock、运行检查及 M0 黑盒验收。不能从 Hermes 的“完成”说明直接判通过。

不通过时只返给 Hermes 一轮明确 findings，之后由新 Reviewer 复审。再次失败按合同接管；接管者不能验收自己的修改，需要再次开启新会话并标注供应商独立性。
