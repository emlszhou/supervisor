# 准备阶段验证记录

日期：2026-10-03。验证机器：当前云实例，Linux、Python 3.12.14、uv 0.12.19、Git 2.52.0。

## 已完成

- 项目目标、架构、接口、状态机、权限边界、恢复规则、验收和开发交接文档。
- Python src 布局、CLI doctor、固定开发依赖与 uv.lock。
- 6 个 JSON Schema，示例配置和记录、任务/审核/交付模板。
- M0 草案：范围、预算、独立验收计划与 Hermes 交接。
- Linux/macOS/Windows 的基础 CI 定义。

## 当前实例实际验证

| 检查 | 结果与限制 |
| --- | --- |
| `uv sync --frozen --group dev` | 安装成功；锁文件重用 |
| CLI doctor | 基础 Python/Git 前提通过；不验证 Agent 或隔离 |
| `python scripts/check_specs.py` | 6 个 schema、示例、模板和 M0 草案通过 |
| `pytest` | 32 通过，0 失败/错误/跳过；仅脚手架与规格回归 |
| `pytest examples/synthetic -q` | 1 通过，0 失败/错误/跳过；合成算术示例 |
| Ruff lint / format | 通过 |
| `uv build --no-sources` | wheel 与 sdist 构建成功 |
| wheel 安装冒烟 | 独立 venv 安装成功，隔离模式 `python -I -m supervisor doctor` 通过 |
| 本地 Markdown 链接 | 无缺失目标 |

测试 XML 在忽略目录 `.supervisor/evidence/`，构建产物在 `dist/`。这些是当前运行产物，不是未来任务的通过证明。

## 尚未完成

- ProcessRunner、Mock Adapter 和完整工作流尚未实现，M0 行为验收尚未执行。
- Hermes/Claude 真实调用、Mac mini 连接、模型认证、OS sandbox 和恢复尚未验证。发现 Codex 命令不代表其协议/认证已验证。
- 其他平台 CI 尚未触发，不声称 Mac/Windows 兼容性已经通过。
- M0 尚无 Git 基线与冻结包；初次提交和独立黑盒验收准备完成后才能正式投递。
- 文件仍在本地工作区，尚未 commit/push。云环境发布和新任务恢复没有在本记录中验证。

下一步按照 docs/hermes-handoff.md 固定基线和 M0 输入，再交给 Mac mini 上的 Hermes 实现。
