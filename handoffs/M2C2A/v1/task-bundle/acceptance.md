# 验收

1. 范围仅allowed_files，标准库，不改Agent/ProcessRunner/任务合同；恒拒绝live，无云/模型probe。
2. 冻结protected tests全部通过、unit/project/specs/Ruff/build通过；Mac原APFS失败单列，Linux全套在独立干净精确候选通过。禁止硬编码开发机路径。
3. classify_case按种类及副作用优先级；invalid输入ValueError不回显；summary范围与partial一致。profile参数注入/重叠/非法端点拒绝；不以profile文本存在声明OS强制。
4. verify_package必须检测真实内容/引用/库存/链接/摘要篡改，清理后Reviewer仍可读取capture与对照，不形成hash自引用。
5. 真实Mac测试仅批准后执行，实际argv/time/exit/capture留证；不能跑就not_run/partial，不用mock升级通过。无监听诊断不计required、MCPout_of_scope、fresh由独立会话证据证明。
6. root临时/持久化写权限主体明确，fixture可读、profile/依赖/证据不可读；attempt和输出包防复用/路径逃逸。取消不能确认整树->unknown/live拒绝，不能以PGID空推全部后代已回收。
7. freshReviewer绑定完整候选和contract manifest，复跑离线检查，并在Mac侧重新执行已批准测试或核对可定位捕获；不能自演fresh，无能力就等待外部审核。同provider不声明独立供应者。
8.报告精确baseline/candidate、提交与分支累计范围、check exit/测试计数、provider/model、预算历史、not_run/partial原因、授权记录来源（脱敏），Git事件不能隐藏。额度建议超出说明原因，不自动改scope/权限。
