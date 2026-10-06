# M2-B 修复候选复核：request_changes（单一剩余缺陷）

精确候选 `1a10ed8a00e71a13df53cce11b39d89d827fe5c5`。范围4文件/1630新增行合规；原四个findings全部关闭。旧7探测全PASS；Linux原301+新增57+保护29=387 passed，0failed/skip；Ruff check/format、specs、sdist/wheel构建通过。真实执行入口仍拒绝。本次未启动真实Hermes或联网模型，Mac私有日志没有直接访问。

## M2B-R2-identity — major

现有 _ID_PATTERN/_SESSION_ID_PATTERN 用 re.match 且末尾$，Python允许$匹配最终换行前的位置。实际复现：init和result均session_id="s\n"返回completed，session_id保留换行；expected.task_id="M2B\n"也未抛ValueError而返回completed。合同只允许指定安全字符，expected身份须匹配完整字符串。

修复：所有身份/会话匹配使用re.fullmatch（或等效严格全字符串验证），不能strip后继续；expected身份非法应ValueError，输出session非法应返回failed安全错误。补三种可信id的末尾换行/边界，以及init/result session末尾换行回归；检查长度64/128及合法正常身份保持可用。无需扩大scope、改冻结测试或运行真实模型。

重现：构造合法init/result，将两事件session_id设为"s\n"；ProcessResult(completed,0,NDJSON,b"",0.1,False,True,None)。对expected.task_id设"M2B\n"重复正常session输入。两个案例均违背合同。

## 其他复核

Hermes fresh Reviewer在93cc84d执行，最终1a10ed8只改报告；本次独立执行覆盖最新完整候选，不把修改前ACCEPT当作修改后证明。今后fresh审核仍须绑定最新完整SHA。

强推披露给出的before85fde60和aftere3710df在当前Git图中为祖先关系（merge-base --is-ancestor exit0），未见这组tip丢失独有提交的证据。Git当前状态不能验证历史实际命令；保留披露，禁止后续force-with-lease，普通push即可。此事项不再阻塞代码验收。

建议一次小返修完成身份验证后，对精确新候选fresh复核。周期额度仍建议值；这不是预算阻断。未合并main、未解锁真实运行。
