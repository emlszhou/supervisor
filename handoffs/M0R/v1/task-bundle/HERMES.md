# M0R 新合同开工
仅本目录为新执行输入。先读task/requirements/api/allowed/forbidden/verification/acceptance。
现有实施检出必须干净且HEAD精确等于基线；fetch origin后使用协调者main上新版导出器，--contract-prefix handoffs/M0R/v1，导出到检出外新目录。不要运行旧默认M0/v2 kickoff，不merge main。
verification中${CONTRACT}为绝对外部task-bundle路径，由调用者替换为单个argv，不作为shell变量拼接执行。使用uv run --frozen提供测试依赖，从实施检出根运行：uv run --frozen pytest "$CONTRACT/tests/protected/test_m0_acceptance.py" "$CONTRACT/tests/protected/test_m0r_acceptance.py"；保护测试的schema从外部包读取。
新实现分支hermes/m0r，由基线新建并正常push，不更新hermes/m0或main，不force-push。报告仅deliveries/M0R/hermes-report.md。代码和报告分开commit，交接消息给全部SHA。读审核记录不merge/cherry-pick。
凭证/venv/日志不入Git；只读导出不是OS sandbox。旧AGENTS/docs中的M0固定分支指旧任务，此新合同仅针对M0R授权新分支/报告，不扩张其他规则。
