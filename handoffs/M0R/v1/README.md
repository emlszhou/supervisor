# M0R v1 Git 冻结交接

原 M0 Review-2 拒绝记录保留；本任务修复其剩余缺陷，新基线见handoff.json，新分支hermes/m0r。只在新合同范围内实现。

Mac mini 开工（目录不存在时；已有目录先核对，不能覆盖）：

```bash
git clone --branch hermes/m0r https://github.com/emlszhou/supervisor.git supervisor-M0R
cd supervisor-M0R
git fetch origin
M0R_SPEC=$(git rev-parse origin/main)
M0R_TOOLS=$(mktemp -d)
git show "$M0R_SPEC:scripts/prepare_git_handoff.py" > "$M0R_TOOLS/prepare_git_handoff.py"
git show "$M0R_SPEC:scripts/verify_handoff.py" > "$M0R_TOOLS/verify_handoff.py"
python3 "$M0R_TOOLS/prepare_git_handoff.py" --ref "$M0R_SPEC" --contract-prefix handoffs/M0R/v1 --output ../supervisor-M0R-contract
uv sync --frozen --group dev
uv run --frozen ab-supervisor doctor
CONTRACT=$(cd ../supervisor-M0R-contract/task-bundle && pwd)
uv run --frozen pytest "$CONTRACT/tests/protected/test_m0_acceptance.py" "$CONTRACT/tests/protected/test_m0r_acceptance.py"
```

先读外部合同；最后一条基线有缺陷会失败（新增15项实测2通过13失败、0跳过），不是环境故障。不得skip/xfail或改保护测试，实现后重跑合同全部检查。shell示例中的CONTRACT是外部绝对路径，verification模板中的${CONTRACT}替换为此路径。

代码提交后 `python3 "$CONTRACT/snapshot.py" --commit <完整代码SHA>` 取得新代码树摘要，再单独提交报告。交接消息给代码SHA和最后报告tip SHA；Reviewer重算最终tip快照。不能把新报告自引用为其自身快照。

正常push仅hermes/m0r；不要merge main或审核记录。旧M0/API/schema和原57项测试未放宽。进程树、异常清理、Windows故障模拟另由fresh Reviewer复验，未实测平台明示未运行。
