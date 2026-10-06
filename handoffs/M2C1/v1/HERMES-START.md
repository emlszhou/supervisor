# Hermes M2-C1 开工

用户要求目标优先，周期建议额度不是硬停止。建议6小时/10次Agent启动，约1.5倍或连续3次无新证据时检视原因并调整方法，不重置历史。工具权限、真实日志、scope、进程限额及fresh审核有效。正常Git推拉已授权，不重复请求；禁止force/reset/clean，不merge main、不部署。

## 初始检出

fetch origin，保存已有工作，使用hermes/m2c1干净实施检出，HEAD精确 `2805b1f03d95d0d8de5ab81ea8538822198c397c`。不同/分叉/已有未提交工作时保留并报告，不重置。不要merge main或cherry-pick M2-B。外部导出目录须不存在且在检出之外：

```bash
git fetch origin
python scripts/prepare_git_handoff.py --ref origin/main --contract-prefix handoffs/M2C1/v1 --output ../M2C1-v1-contract
python scripts/verify_handoff.py ../M2C1-v1-contract --bundle-sha256 595511a65981bb7ddcca6a339939ae53584d0a3274f92c4e58aac3273ee71a40
uv sync --frozen --group dev
```

可信manifest `595511a65981bb7ddcca6a339939ae53584d0a3274f92c4e58aac3273ee71a40`；完整读取task-bundle全部文件。verification中CONTRACT替换成外部task-bundle绝对路径，在uv run --frozen环境执行python/pytest/ruff。只读权限不是sandbox。23保护用例已收集，尚无实现、不宣称已通过。

## 完成任务

在四允许文件内实现纯boundary证据validate_evidence、恒拒绝require_live_execution、新增单元测试与真实boundary-evidence.json/hermes-report.md；上限1800 diff行。不修改公共Worker/M1/Adapter/依赖/冻结保护输入。校验完整身份/未知字段/类型/UTC/摘要/重复检查，输入深拷贝，错误不回显秘密；executed=True且exit=None必须保留已运行记录，不能造0或抹成未运行。此校验只表示结构，不访问source、不证明真实隔离、不返回allow_live。

只读盘点已有隔离后端和Mac项目平台信息，按真实元信息记录declared/observed/enforced与未知，不安装/创建容器、账户、卷/挂载、不改网络、不读凭证或全量环境。仅现有已授权大小写敏感Mac检出可复跑原测试，否则not_run并列缺环境。不使用真实模型probe、宿主攻击或越界测试；每实际命令外部120秒/64KiB限额。给C2具体可实施平台方案与拒绝测试计划，不能把Docker版本、screen/PTY、sshd或Hermes flags当成已强制边界。

运行外部23保护验收、新增测试、完整项目测试/specs/Ruff/build；记录exit与pass/fail/skip，Mac原失败单列，缺Linux环境则交接验证不伪造通过。提交正常推送hermes/m2c1，另起fresh Reviewer独立检出精确candidate、外部摘要并核对日志证词；审核推local/m2c1-review-1。返修后针对新完整SHA再fresh审核，不沿用旧ACCEPT。Reviewer修改代码则换fresh审核。

最终反馈候选/报告/审核完整SHA、实际账本、真实命令exit/计数、未测前提与C2建议。接受仅C1，不解锁真实Hermes或宣称OS sandbox完成。M2-B未合main不阻塞当前纯模块，不申请或自行合并它。
