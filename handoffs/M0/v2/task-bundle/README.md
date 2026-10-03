# M0：进程执行与模拟 Agent

状态：**draft 源合同，尚未实现**。开工时由协调者生成外部 frozen 交付包；源合同不回填，执行以交付包 metadata 为准。本任务没有自动投递或执行。

任务输入：

- `task.json`：版本、角色、预算及基线。
- `requirements.md`：具体行为和非目标。
- `allowed_files.json` / `forbidden_files.json`：实现范围，禁止优先。
- `verification.json`：可信命令与必需检查。
- `acceptance.md`：Reviewer 应独立验证的行为。
- `api.md`：验收使用的固定 Python API。
- `HANDOFF.md`：给 Hermes 的短交接文本。

执行前由协调者建立真实 Git 基线、完善受保护黑盒验收、填写 baseline_commit、冻结包并复算摘要。冻结本身是后续功能；人工准备阶段按 docs/interfaces.md 的规则进行，不能伪造 SHA。

M0 只完成 Mock 和低层执行器；不声称有安全 sandbox、崩溃恢复或真实 Hermes/Codex 能力。完成后由全新 Reviewer 验收，最多返修一次。
