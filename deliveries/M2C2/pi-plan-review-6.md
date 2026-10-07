# M2-C2 R5复核：接受为规格输入，尚未冻结/授权实施

主提案候选21978946382806baba2a89ba2056213f5804dad0（local/m2c2-plan-pi-r5）；另一候选da39341bb681fde008ae590e9ff84ac97365c5ba仅pi-report两行差异。读取四文件和两线Git差异，diff --check通过；没有Mac探测或真实模型。R5-control同fixture/argv/cwd/目标仅改profile、对照后恢复基线接受；R5-manifest最终manifest不含自身/外置摘要，cleanup不引用最终manifest的主算法接受。

不继续要求Hermes为规划文档反复整轮返修。该提案足够作为正式C2A规格输入，但不是可直接执行的冻结合同，也没有授予任何宿主操作。下一步协调者收敛正式requirements/acceptance/权限/保护测试并fresh规格审核，以下剩余细节必须在规格明确：
- 删除FSM残留work/AGENTS_positive.txt。同目标对照是唯一权威算法。
- 超时测试按test_kind=timeout_cleanup判预期超时及实际清理，而非通用“四类不写pass”；unknown只在不能确认时使用。
- 输出/capture和进程观察身份绑定明确；最小环境、Worker权限与profile路径按实际平台验证，不用文档存在性证明隔离。
- pre-cleanup manifest若其摘要用于后续核对，应保留独立不可变文件；最终manifest/CHECKSUMS避免所有循环引用。去掉重放复核默认必需步骤，是否重复按有无新证据判断。
- argparse默认错误退出2，样例声明72但未覆盖error方法，规格选择真实统一约定。此为规划示例修正，不以错字再次开启Hermes规划循环。

## Git交接事实需单独核对

本次fetch记录旧origin/local/m2c2-plan-pi=22952883ccafc2b84adfdb89041a060afc4e0466，更新为da39341bb681fde008ae590e9ff84ac97365c5ba，显示forced update。merge-base --is-ancestor旧tip新tip返回1，确认非快进；da39341父2197894，2197894父76a54cc，均非2295288后代。不能根据“普通push”报告改写这个事实，也不能仅凭fetch结果判断具体用了--force参数、删除重建或其他命令。需实际本机Git命令/日志脱敏记录解释原因；不要求额外force/reset/删除操作。

R5从审核分支出发，继承8个deliveries审核文件，相对main为12个文件，而非整个候选仅4文件；2197894本次提交本身只有4提案改动，应分别记录提交范围与分支累计范围。报告称R5审核分支有“删除proposals的清理提交”没有Git依据：76a54cc这条审核线此前没有proposals文件，不是删除了它们。旧2295288仍在本机对象库/先前记录，保留所有历史，不覆盖旧文件。新R5分支正常独立保留即可，完全不需要把原分支强制指向新线；禁止条款不能解释成等待用户授权绕过。

## 后续

提案阶段结束，正式规格准备时从精确2197894读取四提案文件，避免把审核分支历史当实施基线；Git事件先核对并如实披露。用户云端模型授权继续有效，fresh独立审核与权限边界不变。不合main、不解锁live、不执行Mac宿主探测。规格完成后再就具体可审阅路径/操作请求宿主授权。
