# M0 开工与离线交接

本阶段由协调者固定公共 API 和独立黑盒测试、提交可引用的 Git 基线、生成外部冻结包。没有实现 ProcessRunner 或启动 Hermes。

**当前交接渠道已更新为 Git。** 按 docs/git-handoff.md 克隆 hermes/m0，并从 main 导出 v2 冻结合同；以下离线说明保留为原始 v1 交付历史，旧包不修改。

## 验收状态

`tasks/M0/api.md` 定义确切入口。`tests/protected/test_m0_acceptance.py` 验证实际进程与协议行为，不包含 skip/xfail，不用实现方自测替代验收。

未实现阶段完整 pytest 失败是明确的未完成结果，不是测试通过或环境问题。已完成的准备工具检查可单独执行：

```text
uv run --frozen pytest tests/test_cli.py tests/protected/test_specs.py tests/protected/test_handoff_verifier.py
uv run --frozen pytest tests/protected/test_m0_acceptance.py --collect-only -q
```

实现后必须运行完整 pytest、verification.json 的命令和独立验收，不能只运行上面子集。

当前云实例开工前结果：39 项准备工具/规格测试通过；57 项 M0 行为测试均收集成功并执行失败，原因均为四个实现模块不存在，0 错误、0 跳过。合成示例 1 项通过。失败日志和 XML 在 `.supervisor/evidence/`，交接包会保留这些记录。它们不构成 M0 功能通过证明。

## 基线与冻结源

基线提交包含全部规格、测试和脚手架。仓库内 task.json 保持源草案；外部交付目录 `task-bundle/task.json` 是绑定基线的 frozen 执行包。实现者不得回填或修改仓库合同。

manifest 对合同、api、验收文件和 schema 的原始字节做摘要；bundle digest 是规范化 manifest 的 SHA256。冻结包和所有验收文件都位于实施工作区之外。只读文件权限和校验只能辅助防误改，不等同于恶意 Agent 无法绕过的 OS sandbox。

## 离线交接结构

```text
M0-<baseline-short>/
  README.md                恢复、校验与交付命令
  HERMES-START.md           可直接交给 Hermes 的任务说明
  handoff.json             基线、冻结包摘要和测试状态
  supervisor.bundle        完整 Git 基线，可离线 clone
  task-bundle/             冻结合同与受保护输入
  verify_handoff.py         只检查身份/完整性，不执行 Agent
  evidence/                开工前检查记录
  CHECKSUMS.sha256          包内各文件摘要
```

在 Mac mini 解压后，先用可信交接提供的摘要执行 verify_handoff.py，再 clone supervisor.bundle 到一个单独的新目录并 checkout 基线。不要覆盖任何已有业务仓库。依赖通过 frozen uv.lock 安装，不复制云端虚拟环境。

按照包内 README/HERMES-START 投递。当前没有自动发送、远程连接或认证；本地真实 Hermes 的模型/版本/权限仍需核验。文件包不包含密钥和原始 Agent 对话。

## 交付回来

Hermes 只改 allowed_files 范围，保留外部冻结包，交付完整 diff、代码、真实测试报告和平台信息。新 Codex 会话核对基线、文件范围、保护输入摘要，再重新运行独立验收。通过之后再决定合并；此流程不会自动 push。
