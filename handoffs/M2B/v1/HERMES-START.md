# M2-B 开工交接

用户要求完成目标优先，周期预算用于检视而非自动停工。本轮建议6小时/10次Agent启动；超过约1.5倍或连续3次无新证据时记录原因、调整方法/交接，不重置账本。普通Git推拉已授权，不重复申请。不要merge main、force/reset/clean或部署。

## 初始准备

fetch origin，保存已有工作。实施分支hermes/m2b已经初始化，HEAD须精确为 `85fde6074d45ea0137a2dc55aae3362befa91639` 且干净；若有其他工作/分叉保留并报告。不要merge main到实施分支。导出目录须不存在且在检出之外：

```bash
git fetch origin
python scripts/prepare_git_handoff.py --ref origin/main --contract-prefix handoffs/M2B/v1 --output ../M2B-v1-contract
python scripts/verify_handoff.py ../M2B-v1-contract --bundle-sha256 9a46b4a424ffeab7c0f63ec9b3cbb1038b7d9168488da7697576613e38574703
uv sync --frozen --group dev
```

外部task-bundle是权威输入，完整读取requirements/acceptance/allow/deny/verification与保护测试。可信manifest SHA256 `9a46b4a424ffeab7c0f63ec9b3cbb1038b7d9168488da7697576613e38574703`，基线 `85fde6074d45ea0137a2dc55aae3362befa91639`。verification中的CONTRACT替换为外部task-bundle绝对路径；用uv run --frozen执行已锁定项目环境中的python/pytest/ruff。只读权限不是OS sandbox。

## 完整任务

实现 supervisor.agents.hermes.HermesAdapter 的离线NDJSON协议解析、tests/fixtures/hermes_cli.py及单元/真实模拟进程集成测试，报告deliveries/M2B/hermes-report.md。仅四个允许文件，总计2200 diff行，不改公共parser、Worker/M1/依赖/保护测试。真实build_request恒抛live_execution_disabled；不运行Hermes/网络/模型/读取凭证，无enable_live开关。使用现有ProcessRunner.run执行合成fixture，单fixture<=3秒、输出<=64KiB。保护验收29例，除此自行补充有效集成与故障测试。保护测试现在只有规格收集通过，不能写成实现已通过。

协议只支持合同列明init/text/result子集；严格UTF8/JSON/字段/数字/身份/摘要上限，stderr回退或任意未知诊断失败；实际进程超时/取消/输出限制优先，exit未知保留None，不被模型输出覆盖。终端summary<=4096，usage缺失None，session仅声明，可信身份来自expected。未来真实工具禁用与OS边界另立任务，本阶段不证明这些能力。

持续实现、运行外部保护测试/完整项目测试/specs/Ruff/build，记录真实命令/exit/计数与平台未知。Mac已有大小写不敏感文件系统故障单列，不能关闭测试或在本任务修M1；如Linux执行条件缺失，保存候选并交接Linux独立验证，不能伪造通过。

提交推送hermes/m2b后另起真正fresh Reviewer，独立检出精确candidate完整SHA、读取外部冻结合同，写local/m2b-review-1。若返修，报告历史失败并对最新精确SHA重新fresh审核；不能把修改前ACCEPT套给修改后候选。Reviewer本身若改代码则换fresh Reviewer。保留历史，候选/报告/审核提交都给完整SHA，不推main。

完成反馈：精确候选与审核SHA、外部manifest摘要、文件/行scope、29保护验收和项目测试真实结果、失败/unknown、建议额度实际消耗及检视原因。无需反复修改M2-A调查报告，不宣布真实Hermes或Worker运行就绪。
