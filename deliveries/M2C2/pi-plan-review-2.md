# PI M2-C2 修订提案审核：request_changes

精确候选d261ee545fb1b849aa86c56f6f23317322e4525f。四份文档独立阅读全文和差异，diff --check通过；未运行宿主探测、真实模型或main合并。此为外部文档审核，不是冻结规格fresh签署。

P1接受：M2-B的能力假设已纠正，MCP当前not_run/unknown。P2主要方向接受：真实凭证/仓库和现有模型服务已从具体主要测试移除，网络改自建回环。P3–P5部分处置，但旧条款仍可直接导致实施偏离，不能只靠新增“P已修复”文字覆盖。

## A — major：授权根外写入仍明确存在

plan §4.1 T1第4项仍要求harness预建/tmp/m2c2-outside-<attempt_id>；permission P3仍写“授权根外”；矩阵R4仍称授权根外目标、外部哨兵。它们与唯一根矛盾。全部统一为harness授权根内、Worker白名单外的denied目标；不预建任何根外路径。attempt创建规则“mkdir -p前校验存在且为目录”不能防复用：改为校验授权父根后排他创建新attempt（存在则拒绝），使用路径组件检查而非字符串前缀，明确不可跟随符号链接。P2仍引用P3–P8，包含harness专属清理P8；必须明确sandbox内命令排除P8及harness盘点/记录，仅运行冻结fixture动作。profile和证据捕获不能置于Worker可写out中让其篡改，另放harness专属目录；Worker输出通过harness管道捕获。这些不是要求实施新功能，而是先把权限提案写一致。

## B — major：前置路径仍自相矛盾，依赖获取不具体

plan §6正文说不依赖M2-B合并，但Step0仍合并两候选、Step1仍要求Step0完成。删掉C2A对该Step0的依赖，合并明确后续独立操作。C1绑定ref须写完整436e3b0e026580a6b39ece891e8ffe47ac1bb698，并具体说明如何导出/校验/导入单个标准库模块，不把不可用分支API当已安装依赖。明确依赖准备在哪个获准目录、谁执行、验证失败如何处理；不要求main合并、不改sys.path读取可变工作区、不复制进生产模块。若不选择外部固定依赖，就改为唯一的C1集成前置提案，而不是同时保留两条互斥路径。

## C — major：证据和通过条件仍不一致

矩阵说unknown只能partial，又说T6 unknown可“矩阵通过”；MCP恒unknown也让通用unknown规则冲突。统一：C2A full_pass=明确纳入范围的T1/T2/T3/T5/T6 required子项全部通过+T7流程证据；T4标out_of_scope/not_run，不计分母；任一范围内unknown/not_run只能partial，live始终关闭。plan §5仍写“6项OS边界+fresh通过”，删除错误计数和未经测试的通过结论。逐子项记录不能只写“另存结构”：给出字段/示例、capture文件定位及hash、summary关联方法，区分动作exit与harness exit。指定脱敏证据持久化/推送位置，不能清理attempt时连唯一证据一起删除。流程fresh的独立供应者按provider而不是模型名判定。

## 非阻塞但在同次一致性修订处理

Seatbelt技术依据出现/coresignal/sandbox及未经核实man页名；删除不可靠机制路径，标明未验证来源，不靠想象补URL/语法。进程组不能解决脱离进程组，删掉“必要时进程组作主身份”作为整树确认兜底的暗示；有无法跟踪的后代只能unknown，另提方案。当前Worker既有实现不要在C2A隐含改写。只读profile/证据和harness权限应与permission逐项一致。

## 下一步

一次一致性修订原四文件：不仅添加新结论，逐处替换旧矛盾条款。提交前搜索m2c2-outside、授权根外、Step 0、P3–P8、矩阵通过、6项OS、coresignal，逐条人工判读；不能只报告搜索执行过。用一个完整attempt走纸面演练，从依赖准备到清理，确认每个路径/动作有明确主体与权限。无需全套代码测试或宿主探测，不合main。正常推送精确SHA、处置表后外部复核，再进入正式规格准备。

PI表现：能读代码并纠正局部错误；长文跨段一致性仍需外部审核，不能据本次结果判定可无人值守制定执行权限。预算仍为建议，不因次数停止，也不以换任务ID绕过问题。
