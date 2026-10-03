# 独立验收与证据

## 三类检查

- Project Tests：项目自带测试，可能由实现者同时修改。
- Protected Tests：控制面维护、执行者不可写的验收基线。
- Independent Checks：Reviewer 或 Supervisor 独立执行的功能、范围和证据检查。

当前 `tests/protected/` 是开发约定中的保护区，还没有 OS 权限保护；真实部署必须复制到 Worker 写入范围外。实现者可以运行这些检查，但不能修改它们或自己签发最终通过。

## 证据绑定

每轮验收必须记录 task/run/attempt、bundle SHA256、候选 snapshot SHA256、命令 argv、工作目录、时间、退出码、实际测试数和报告摘要。记录测试工具版本。验证前后快照不一致、报告过期、零测试、失败退出码、未知结果、必需检查跳过都不能 accept。

通过要求：必需检查实际完成且通过、没有 blocking finding、任务和快照摘要匹配、Reviewer 会话全新且未参与当前修复。实现者最终代码不能在通过后继续变化。

代码 authorship 以 attempt/session 和差异记录，不以同一家 provider 判定。报告分开表示 `fresh_session` 和 `independent_provider`；缺失证据不能默认为 true。

## 必需与可选

当前脚手架必需：安装 frozen lock、spec schema 验证、CLI 诊断/错误退出测试、pytest、Ruff、wheel/sdist 构建与 wheel 安装冒烟。它们只证明脚手架可开发。

后续任务必需：合同指定的功能检查、受保护回归、失败分支、预算和权限检查。真实 Codex/Hermes、其他 OS 或远程 Worker 仅在对应里程碑要求时作为必需。未运行必须明确标注。

## M0 独立验收计划

由 Reviewer 在合同冻结后新增受保护的黑盒检查，不能让实现者同时决定实现和所有验收。覆盖：正常 stdout/stderr、非零退出、不存在可执行文件、包含空格/非 ASCII 的路径、取消、超时、输出洪泛、启动子进程、错误 JSON、缺失字段和退出码/协议矛盾。

固定验收输入不可更改。只有明确支持的平台才能声称子进程树回收有效。`tasks/M0/acceptance.md` 指定细节；这些执行器测试当前尚未实现，现有 schema/CLI 测试不能替代它们。
