# Hermes M2-A 开工指令

用户已授权 Hermes + MiniMax 云模型。执行能力调查与证据交付，不实现 Adapter/Worker。读取完整外部 task-bundle 的全部合同；按真实能力推进，不虚构 CLI 参数、本地推理、fresh 会话或通过结果。

## 初始检出与合同导出

先保存已有工作，不覆盖、不 reset/clean/force-push。fetch origin 后，在干净的 hermes/m2a 实施检出确认 HEAD 精确为 `35f948fd40a6bf3e63982fd884422206cbffd28a`；远端分支已经由协调者初始化。若不同或存在未提交文件，停止初始导出并报告，不自行回退。规格从 origin/main 获取，不能将 main 合入实施分支。

在该实施目录执行（输出目录必须不存在且在检出之外）：

```bash
git fetch origin
python scripts/prepare_git_handoff.py --ref origin/main --contract-prefix handoffs/M2A/v1 --output ../M2A-v1-contract
python scripts/verify_handoff.py ../M2A-v1-contract --bundle-sha256 0ba0619747c246174f966ecc8efe4c7ba60b158df346fb0fd41bdfc83144b739
uv sync --frozen --group dev
```

外部包可信 SHA256：`0ba0619747c246174f966ecc8efe4c7ba60b158df346fb0fd41bdfc83144b739`。将 `${CONTRACT}` 设置为导出的 task-bundle 绝对路径，`${BASELINE}` 设置为上述完整 SHA，不保留占位符。只读文件/Git 规则不是 OS sandbox。

## 连续工作与预算

从实际开始时间计时，整个周期上限 14400 秒；最多 7 次 Agent 启动，所有角色、probe、重启与恢复共同计数。最多 1 次返修与 1 次接管只是上限，不增加共享额度。调查者加 3 次 smoke 加 fresh Reviewer 通常已经占用 5 次，剩余 2 次仅足够返修与重新审核。预留审核时间和启动数，额度不足如实 blocked，不自动追加、不承诺所有路径都有额度。

调查范围包括真实 help/version、非交互调用、MiniMax 路由、fresh 身份、输出协议、端点失败、超时、取消和权限矩阵；做 3 次重复 smoke，其中至少 2 次 fresh 启动。每次最长 120 秒；先证实工具已禁用且仅使用无秘密合成目录，无法保证则不运行并填 unsupported。不要安装环境、变更网络/账户/权限或尝试宿主攻击。之后形成 Adapter 接口建议、失败用例、隔离能力比较与 M2-B/C/D 依赖规划，详情服从完整合同。

只允许修改 deliveries/M2A/capabilities.json 与 deliveries/M2A/hermes-report.md，总计最多 2 文件和 2000 diff 行。保留真实命令、退出码、时间、哈希、会话来源、未知能力和预算账本；原始日志私有，不提交密钥/环境/原始对话。先 evidence commit，再 report commit，正常推送 hermes/m2a，不合并 main。

## 验证与交付

按 verification.json 在真实环境运行外部 validator、完整 pytest、specs 与仓库级 Ruff check/format，记录真实退出码与计数。结构校验不证明证据真实性。Reviewer 必须另起 fresh 会话，在独立检出核对精确 candidate 和冻结输入；审核写到 local/m2a-review-1，不能在当前聊天模拟 Reviewer。如果无法启动 fresh Reviewer 或安全 smoke，提交能安全保存的证据并 blocked。

最终反馈 candidate 完整 SHA、审核分支/完整 SHA、真实预算账本、检查结果、未验证能力与剩余 findings；Adapter readiness=ready 仅允许准备下一阶段规格，不代表无人值守 Worker 已就绪。不自行推进 M2-B 或合并/部署。
