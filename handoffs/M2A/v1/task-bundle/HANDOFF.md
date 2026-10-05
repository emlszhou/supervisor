# 源规格交接与执行边界

先读 README、requirements、acceptance 和本仓库架构/接口/安全规则。

M1 main 集成基线和用户 MiniMax 路由许可已确认；协调者完成全新规格审核、外部包冻结与完整 manifest 后发布执行交接。不能拿源 draft 自行宣布冻结。

正式实施时在 `hermes/m2a` 提交且只写：

- `deliveries/M2A/capabilities.json`
- `deliveries/M2A/hermes-report.md`

能力报告的各 checks 字段见 `validate_delivery.py`；baseline 由协调者替换 `${BASELINE}`，外部只读包由协调者替换 `${CONTRACT}`。不得把文件中的变量字符串当成实际值。

必须执行外部 validator、完整项目测试、specs、仓库级 lint/format；保留真实 exit/计数。所有模型调用、角色启动、等待与超时计入冻结预算；调用前先核对无未知副作用。原始日志私有，只提交脱敏摘要；先 evidence commit 后 report commit，正常 push，不 merge main。

Reviewer 用真正全新会话、独立检出精确 candidate，读取外部冻结输入，核对 scope、报告和真实无副作用验证。审核写入独立 `local/m2a-review-1`。缺少 fresh 或安全调用能力时保持 blocked，不在同聊天模拟审核。
