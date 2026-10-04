# M1 v1 开工交接

M0R已接受并集成；M1实施基线是c6e224587b930a5b96c7723009584424f6bc52d5，来源与范围见handoff.json及task-bundle/api.md。

Mac mini开工，使用新的不存在目录，不覆盖旧实施工作：

```bash
git clone --branch hermes/m1 https://github.com/emlszhou/supervisor.git supervisor-M1
cd supervisor-M1
git fetch origin
M1_SPEC=$(git rev-parse origin/main)
M1_TOOLS=$(mktemp -d)
git show "$M1_SPEC:scripts/prepare_git_handoff.py" > "$M1_TOOLS/prepare_git_handoff.py"
git show "$M1_SPEC:scripts/verify_handoff.py" > "$M1_TOOLS/verify_handoff.py"
python3 "$M1_TOOLS/prepare_git_handoff.py" --ref "$M1_SPEC" --contract-prefix handoffs/M1/v1 --output ../supervisor-M1-contract
uv sync --frozen --group dev
CONTRACT=$(cd ../supervisor-M1-contract/task-bundle && pwd)
uv run --frozen ab-supervisor doctor
uv run --frozen pytest -q
PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest "$CONTRACT/tests/protected/test_m1_acceptance.py" -q
```

先读外部合同，${CONTRACT}由调用者替换为外部task-bundle绝对路径。旧项目194测试应通过；新M1独立42项基线全部因缺少实现而失败，0skip，不是环境故障。不要修改保护输入获得通过；禁止skip/xfail核心行为。

允许五个模块、tests/unit/test_m1_*.py和deliveries/M1/hermes-report.md；总14文件/2800新增+删除行，固定基线累计。只推送hermes/m1，代码与报告分开commit。`python3 "$CONTRACT/snapshot.py" --commit <完整代码SHA>`给报告tracked-code摘要；M1 runtime工作区快照是另一算法，不混用。报告交接消息给最后tip完整SHA。

不merge main或审核分支，不向main推送，不force-push。真实Agent、隔离、状态机、自动重放不属此任务。冻结输入hash/只读文件不是OS sandbox。
