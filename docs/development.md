# 开发环境

基线为 Python 3.12、Git 与 uv 0.12.19。云环境已提供这些工具；Mac/Windows 请先用官方可信安装渠道准备。uv 可在现有受控 Python 环境中用 `python -m pip install uv==0.12.19` 安装，保留 TLS 和包校验。

从仓库根目录运行，Linux/macOS/Windows PowerShell 命令一致，不必手动激活 venv：

```text
uv sync --frozen --group dev
uv run --frozen ab-supervisor doctor
uv run --frozen python scripts/check_specs.py
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv build --no-sources
```

`doctor` 的成功退出仅证明 Python 与 Git 的基础可用性；optional_agent_commands 是命令发现，不检查登录、CLI 协议、模型或 sandbox。

开发依赖使用 `uv.lock`，普通安装不运行 `uv lock` 或升级。更改依赖是经授权的独立任务。生成产物放 `.supervisor/`、`dist/` 或临时目录，避免改动合同输入。

## 云端与本地

- 云端：规格、独立审核和模拟测试；使用 `/workspace/supervisor` 当前检出。任务已隔离，不额外创建 worktree。
- Mac mini：Hermes 实现与真实集成；只同步仓库文件和脱敏任务/结果，不同步凭证、venv、缓存或原始会话。
- Windows：目标兼容平台，在对应 CI/真实机器通过前不宣称已支持。

无需服务、数据库服务器或云端模型密钥即可执行当前检查。SQLite 运行模块尚未实现。

## CI

`.github/workflows/ci.yml` 在 Linux/macOS/Windows 执行同一基础检查、构建及 wheel 安装诊断，不调用真实 Agent。当前云实例仅验证 Linux；CI 尚未触发不能视为其他平台已通过。

M0 独立验收加入后，完整 CI/pytest 会因 M0 未实现而失败，这是本阶段保留的真实未完成结果；实现后需通过全套检查，不通过排除这些测试获得通过。

## 初始基线

本仓库起初没有提交。开工阶段由协调者建立本地 Git 基线，在外部冻结包中填写其真实 SHA。仓库源合同保留 draft；只有外部 frozen 包是执行授权输入。基线以实际 git log 和交接 metadata 为准，不自动 push。
