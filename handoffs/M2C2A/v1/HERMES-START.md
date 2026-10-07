# Hermes M2-C2A 开工

用户已授权云端模型，报告实际provider/model。目标优先，周期建议8小时/10调用，超额分析原因不自动停、不重置历史。普通fetch/commit/push已授权；禁止force（含lease）、reset、clean、删除分支、main实施合并。非快进拒绝后保留分叉推新分支，不覆盖原ref。

## 初始检出与冻结导出

先保存未提交文件。实施分支hermes/m2c2a初始HEAD必须精确51d497cae7f20872e5a5f9c8825fd0f83323a92f，不要merge新main规格进实施分支、不要从旧提案或审核分支开始。实现检出干净；已有冲突/不同baseline先报告不重置。外部目录必须不存在，在实施检出之外。

```bash
git fetch origin
python scripts/prepare_git_handoff.py --ref origin/main --contract-prefix handoffs/M2C2A/v1 --output ../M2C2A-v1-contract
python scripts/verify_handoff.py ../M2C2A-v1-contract --bundle-sha256 f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef
uv sync --frozen --group dev
```

权威manifest f01525c5b92dd516c7d2fbf9f7c2e8034514c1353d5d270460d7fcdca383b9ef。完整读取task-bundle各文档及保护测试。source_spec 03ecc058a404f8df3f470e81be282b623ec63e5e，fresh_spec_review 933f9d59b8ee57895efdcbed22c40e855541552f。只读导出不是OS隔离。

## 持续执行范围

实现backend/evidence/preflight三个模块、固定fixture、新增unit/integration、报告及合成证据包，allowed八静态文件+evidence子树，累计<=80文件/6000diff行；不扩依赖、不改现有Worker/M1/Agent/C1代码。46冻结保护用例目前仅collect，尚无实现不能写通过；实施后全部实际运行。C1 API从固定436e3b0e026580a6b39ece891e8ffe47ac1bb698对象导出到harness/deps，不需要M2-B或C1合main。

按照requirements唯一算法实施，勿照抄旧提案冲突句子。拒绝/正向/预期超时判定分开，同目标同fixture仅profile变化，对照后恢复基线；越界成功fail。fixture放ro可读，profile/deps/capture/evidence/state Worker全deny。manifest不含自身，cleanup真实执行后写，完整capture/对照可读且持久化包引用/hash都校验。

## 宿主运行门禁

当前Macprobe尚未授权。先完成代码、离线测试与harness。不得因用户允许云模型或Git推送自行创建/tmp探测目录/监听/运行sandbox-exec。只有operator明确批准冻结permissions.md和实际两个写根、回环范围后，外部授权记录交给harness才能运行合成矩阵；仓库自写批准JSON不是授权。未批准记not_run，平台能力未知记partial；可以交付诚实有限候选，不虚构full_pass。不得读取真实凭证、访问现有模型端口/其他项目/外网，不安装/账户/挂载/容器或网络配置，不运行真实Hermes；live恒拒绝。

## 检查与交接

external CONTRACT替换为导出task-bundle绝对路径，用uv run --frozen跑verification的protected/full/specs/Ruff/build。Linux项目全套独立验收；MacAPFS既有失败单列，不关闭测试或硬编码Mac路径。operator批准后Mac实际probe捕获真实argv/UTC/exit/hash和动作结果，结构校验不证明真实性；未知整树回收保持partial/live禁用。额度建议超出说明，scope/权限/单进程限额不自动扩大。

提交普通推送hermes/m2c2a。fresh Reviewer独立精确candidate及bundle，复跑检查，填T7真实流程证据（可同provider但independent_provider=false），核对主机授权和可定位捕获。若当前CLI无法新建真正fresh会话，交付候选等待外部审核，禁止同会话模拟；返修后新精确SHA重新fresh审核。Reviewer修改实现则换另一个fresh审核。

最终报告完整candidate/report/review SHA，提交范围与分支累计范围，实际测试exit/count、not_run/partial、provider/model、真实预算历史与权限来源。初始Mac授权尚缺不阻止代码进展，但不能跨过相关操作门禁。不合main、不部署、不启用live。
