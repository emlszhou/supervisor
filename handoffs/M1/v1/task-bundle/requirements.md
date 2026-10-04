# M1：完整性与操作意图

实现api.md五个模块：只读干净Git基线、M1工作区快照、任务包冻结/核验、改动范围预算、SQLite意图记录。
旧M0/M0R代码和所有保护验收不允许修改；生产仅标准库。不要实现CLI、Agent执行、Workflow状态机、自动Git写入、OS sandbox或exactly-once承诺。
合同输入输出的来源/信任边界必须明确。hash识别内容，不证明来源可信；diff检查是事后检测，不限制真实文件/网络访问。

冻结基线见task.json。预算按该基线到最终候选累计新增+删除计，含测试/报告，最多14文件2800行；不是每提交重置。最多1返修+1接管，不能以新合同无限重置次数。
实现方新增tests/unit/test_m1_*.py覆盖所有失败行为，Reviewer独立复跑冻结测试及链接/竞态/并发/SQLite失败窗口。保护测试通过不豁免未覆盖缺陷。
报告deliveries/M1/hermes-report.md：代码先commit、报告再单独commit，代码树snapshot用冻结snapshot.py的tracked算法另注明，与M1 runtime工作区snapshot不同；提供真实argv/cwd/退出码/收集数与完整代码/报告SHA、合同摘要和平台未运行项。日志/凭证/缓存不入Git。
实现分支hermes/m1，不修改main或旧hermes/m0(r)，不merge规格/审核分支，正常push；与用户授权Git交接一致。
