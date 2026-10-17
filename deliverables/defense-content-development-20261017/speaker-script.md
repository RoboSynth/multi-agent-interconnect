# 匿名答辩开发稿逐页讲稿

证据截止：2026-10-17T12:50:41.317Z。本文件为内容准备稿，PPTX/PDF因官方演示runtime缺失尚未生成。

## 01 凭据不出域的跨组织故障协同

协调者组织排障，资源域保留凭据与执行权。

基于官方ACPs SDK的可接续任务与MCP受控接入

匿名答辩开发稿，非最终提交版

本稿按方案15页结构组织。只有已闭合结果进入数字图表。新版身份的客户端证书按用户安排暂缓领取，新七角色尚未启动。后续巡检不进入本稿截止窗口。

证据：S01 docs/高分方案_需求架构创新与任务_20261017.md；S02 docs/P0完成审计_20261017.md

## 02 真实失败时间线

应用已经退出，路由回退仍可能成为错误选择。

F01首批开发验收：M0、M2恢复，M1失败。三种方法各一次。

共享资源域随后增加路由前置条件，成功复验另存，不覆盖失败。

观察：模型收到应用退出的真实事实。错误动作：M1选择路由回退，路由本来已是v2。结果未知：工具等待健康确认失败，账本记录unknown。保守停止：引擎停止修改，保留本次失败。

这是首批完整工具M1的实际负面结果，不是模拟示例。route MCP发生过一次修改型调用。modifications=0只表示没有成功动作回执，不能解释为零修改尝试。unknown来自工具错误后的保守效果判定，不是旧fence拒绝。精确相对路径见证据S03；后续guard复验见S04。

证据：S03 eval/results/local/M1-full-tools-pilot-20261017/report.md；S04 eval/results/local/M1-full-tools-pilot-v2-20261017/report.md

## 03 协调权限与资源权限

事实可以共享，资源凭据由各域保管。

已检查的工作台启动与证据范围：资源凭据计数为0。

诊断：接收症状、汇总事实、选择任务：提供结构化事实与局部假设。

资源修改：发起请求、转交独立审批：校验身份、参数、前置条件与账本。

凭据：本域身份证书和审批签发材料：本域数据库或管理接口凭据。

结案：汇总服务与原请求状态：独立验证新业务，另查原请求回执。

此表描述本作品的权限设计，不把假想单体系统当作实测基线。协调者拥有自己的客户端证书，审批密钥也不是资源凭据。application、database、ops各自持有本域所需材料，verification不需要管理凭据。凭据计数引用实际运行摘要，只覆盖明确检查范围。

证据：S05 eval/results/platform/workbench-partial3-20261017/results.json；S06 output/playwright/f12-cold-ui-20261017/results.json

## 04 总体架构与信任域

官方协议连接参与者，资源动作在本域落地。

接入体检域只检查公开发现与能力资料。

资源凭据、资源账本、动作前置条件保留在对应域。

此页是实现架构，不是七个新版身份已经在线的运行截图。IFC是本项目业务数据契约，不宣称是新的AIP标准。数据库主备共享本资源域账本。当前本地或同机容器边界不能代表生产环境的跨组织OS硬隔离。实现位置：incident/coordinator、incident/wutong_transport.py、incident/platform_worker.py、acps_mcp_bridge、domains。

证据：S01 docs/高分方案_需求架构创新与任务_20261017.md；S07 eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/results.json；S08 integration/incident/high-score-registration-20261017/review-status-and-public-aic-20261017T120745Z.json

## 05 原生、改造与新增

贡献集中在任务接续、受控工具接入和协调逻辑。

公开贡献正文与审阅补丁已准备，尚未发布Issue或PR。

原生复用：身份与证书、ACS、ADP、群组通信、AMP Emitter：官方CLI、registry schema、acps_sdk。

改造SDK：持久任务记录、fence、操作账本、状态单调合并、群组打点：aip/resumable、aip/_task_order.py、amp/group_access.py。

项目新增：MCP策略网关、能力确认、自由工具循环、工作台与业务验证：acps_mcp_bridge、incident、domains、demo-ui。

官方基线版本为ACPs SDK 2.2.0，基线提交3985c1330209f075c124669cc9d31f0e75448140。GroupAccess是新增统计能力的语义设计，不能称为上游原有access故障。真实上游复现问题是TaskResult乱序导致旧Working覆盖较新状态。本项目保留原始失败与修复后的正式通信结果。

证据：S01 docs/高分方案_需求架构创新与任务_20261017.md；S09 docs/contributions/README.md

## 06 平台接入进度

三旧参与域已完成真实通信，新七角色仍未运行。

证书由用户选择稍后处理，当前新版EAB与客户端证书为0。

注册：七新版身份显示审核通过，五个详情公开AIC已核实：另两详情核实、七域证书领取。

发现：三旧域真实ADP与describe生命周期完成：新版全角色发现及能力确认。

互联：正式AMQPS三旧域及真实Postgres只读查询：新版运维、高风险恢复和主备接管。

访问：原始AIP生命周期、六类本地AMP证据存在：Monitor后台入库、访问统计与排行。

注册审核通过不等于客户端证书签发，也不等于平台Inbox已经启动。旧身份使用新版代码的兼容结果，与新版ACS发布、运行结果分别记录。正式AMQPS消息乱序问题的失败及修复复验都存在。这里没有平台全流程完成的声明，后台截图仍是材料缺口。

证据：S02 docs/P0完成审计_20261017.md；S07 eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/results.json；S08 integration/incident/high-score-registration-20261017/review-status-and-public-aic-20261017T120745Z.json

## 07 可接续任务与效果核验

交付状态、资源效果与业务结果分别记录。

同一操作ID绑定参数摘要及资源域，冲突参数不能复用。

unknown没有可核验资源事实时保持未决，不盲目重试。

旧令牌由资源域共享账本拒绝。

任务记录：逻辑任务与多次传输尝试关联。新任期接管：资源域先确认更高fence。效果核验：已生效则跳过，未知则查资源。业务验证：确认服务与原请求状态。

实现位置：vendor/ACPs-community/acps-sdk/acps_sdk/aip/resumable/{journal,ledger,partner,takeover}.py。applied重放返回skipped_already_applied。executing或unknown只能通过显式资源核验解析。fence发生在资源域账本，不是PostgreSQL原生fence。三策略共用账本，零重复不能归因于ResumePackage独有优势。

证据：S10 eval/results/local/E1-native-20261017/analysis/summary.json；S11 eval/results/local/E1-native-20261017/analysis/segmentation.json

## 08 MCP到AIP的受控网关

粗粒度技能用于发现，细工具及风险由describe确认。

两项第三方MCP已有本地真实stdio验收。新Docker精确scope适配另经离线验证。

db.observe：read_only、blocking_sessions：Postgres MCP读取模板。

db.act：恢复写入、终止实验阻塞根会话：固定SQL模板、审批与账本。

ops.observe：container_state、route_version：Docker MCP及域内路由查询。

ops.act：固定目标重启、受前置条件约束的回退：不可变容器ID、项目与服务守卫。

真实第三方版本：postgres-mcp 0.3.0、mcp-server-docker 0.3.0。Docker上游list_containers的all默认false，正式新profile显式all=true并精确绑定Compose project、service、container name。三scope字段全配或全无；缺目标或不支持的状态返回unknown，不能推断exited。修改守卫解析immutable ID。现native行为及共享route guard保持，历史真实Docker验收早于本轮scope适配，不混写为同版本全通过。

证据：S12 output/database-bridge-20261017T085554Z/results.json；S13 output/docker-mcp-bridge-20261017T094625Z/results.json；S14 output/docker-scope-offline-20261017/results.json

## 09 证据驱动协调与比较方法

方法负责选择，权限与效果判定由共同资源域约束。

同一审批、工具白名单、前置条件、账本与业务验证。

动作unknown、旧fence或效果未决时停止；不靠规则偷偷替代M1。

M0 固定顺序：不调用模型，按固定观察顺序推进。M1 完整工具循环：模型自由选择观察、受控动作与验证。M2 假设排序：模型给出假设，按证据收益选择探测。

实现位置：incident/coordinator/engine.py、eval/methods/free_tools.py及共享资源域。M1的明确关联rejected可以反馈后重选，act tool_error及unknown/executing/reconciliation_required/stale_fence须停止。方案中的新正式45格尚未运行，不能把历史观察M1数据改名为完整工具M1。模型小样本schema验证也不等于故障实验。

证据：S03 eval/results/local/M1-full-tools-pilot-20261017/report.md；S04 eval/results/local/M1-full-tools-pilot-v2-20261017/report.md；S15 docs/evaluation.md

## 10 安全边界与业务结案

服务恢复后，原订单仍可能需要人工核对。

调用方白名单与身份校验，审批由独立签发材料验证。

固定SQL、精确容器目标与动作前置条件共同约束资源修改。

高风险动作保留审批、操作ID、参数摘要与审计证据。

原请求键遗失或回执404时保持unknown/manual，不造替代原键。

业务恢复 ＝ 服务已恢复 ＋ 原意图已解析

F12端到端输入original_request_unknown为严格bool，默认false。提供原键时保持旧行为自动查询解析。未知且缺键、或原键receipt404，不发原请求重建，status为needs_attention/manual。service_recovered可以true，但original_request_resolved必须false，business_recovered不能true。共享route guard仅当策略明确配置expected_before时生效；路由已v2的多余rollback在修改前拒绝，三方法共用同一约束。

证据：S05 eval/results/platform/workbench-partial3-20261017/results.json；S06 output/playwright/f12-cold-ui-20261017/results.json；S14 output/docker-scope-offline-20261017/results.json

## 11 真实工作台的未决原请求

缺失原键时，健康服务仍显示“需要处理”。

真实浏览器勾选未知原请求，30.016秒完成10个新业务流程。

服务已恢复，原订单仍待人工核对。修改任务与高风险审批均为0。

这是一次真实Playwright浏览器和冷容器验收截图，未作为正式平台全流程截图。原键不存在的第二分支也完成30秒/10流程，原键receipt仍404，不造替代键。截图经本轮目视检查，无学校、账号、完整AIC、provider、密钥或绝对文件路径。截图是既有运行素材，本稿不重新操作服务。

证据：S06 output/playwright/f12-cold-ui-20261017/results.json

## 12 历史小模型结果

探测少了8.3%，M2在五场景中的恢复中位数仍更慢。

Qwen3-1.7B-Q8_0，M1为历史自由观察版。

45主格由四场景v2与F06-v3组合。原F06-v2九次失败保留。

三图分别是恢复估计中位数、探测总数和模型token总数。M0/M1/M2探测108/99/99，token0/57335/122372，实际模型调用0/99/114。恢复中位数保留原数据三位小数，图中可显示一位小数以减少拥挤。跨场景为声明的两个源码版本，各场景内三方法条件一致。本结果不支持M2一般优于其他方法，不对其他模型或生产场景泛化。

证据：S15 docs/evaluation.md；S16 eval/results/local/model-fairness-comparison-20261017/primary-rows.json

## 13 接续结果与平台稳定性边界

本地接续18例闭合，正式平台目前只有两次健康巡检。

E1：17例连续完成，1例控制器中断后续验。DB MCP修改18次、重复0、旧fence拒绝18次。

三策略实际模型调用与token均为0。共享账本解释零重复，恢复包不享有独占安全收益。

正式三旧域：30.003秒与30.002秒，两周期各30请求、10流程；未证明24小时。

E1-a三断点各3次，E1-b三策略各3次，总18次真实注入。A8连续加1controller续验，B9连续；不称一个进程连续18次。图值为E1-b各策略3次中位数：完整IFC字节1084/4594/5223，信息字节325/3835/2388。信息减少37.7%，实际wire增加13.7%，不能称模型token或wire收益。额外app观察1/0/0。续办30.531/30.390/30.375秒含验证与probe，排除检测和接管，不是纯恢复时延。T07是三旧域健康inspection，非故障恢复，高风险自动审批与演练关闭；周期2自然触发，不是人工刷量。

证据：S10 eval/results/local/E1-native-20261017/analysis/summary.json；S11 eval/results/local/E1-native-20261017/analysis/segmentation.json；S17 eval/results/platform/T07-scheduled-partial3-cycle2-20261017/summary.json

## 14 贡献准备与后续验收

代码与证据已可审阅，社区采纳和完整平台验收仍待完成。

开源贡献：四条Issue草稿、SDK PR说明与审阅补丁：实际公开Issue/PR及反馈。

标准建议：任务接续、MCP能力映射、AMP任务级对账：官方或社区讨论与采纳。

新版运行：独立七角色配置与镜像断网只读验证通过：证书、正式target preflight、全域平台任务。

正式成效：历史组合数据、F01开发复验、两周期巡检：新版45格、平台接管、后台数据及24小时验收。

最新镜像证据captured_at为2026-10-17T12:50:41.317Z：build/probe exit0，network none、root read-only、无env与挂载，以非root用户检查三类导入、官方ACS schema及12个固定源码SHA。它不是新七域部署成功或业务恢复记录。外部贡献尚未发布，不能称已提交或合并。本页贡献材料与标准建议不是已被官方接受的事实。

证据：S09 docs/contributions/README.md；S18 artifacts/new7-image-build-20261017/image-proof.json；S19 docs/开发进度_高分方案.md

## 15 工程结论与下一步

跨域协同需要可核验的执行边界。

任务接续依靠持久记录、资源效果核验与旧主隔离。

MCP网关让工具进入互联流程，同时保留域内权限和审批。

独立业务验证把服务健康与原订单未决分开。

正式验收下一步：新版身份领证与全域通信、冻结条件下的45格比较、连续运行与后台数据。

本稿没有宣称完成全部P0。当前最重要的材料缺口是新版平台全角色真实任务、正式接管、后台入库及长期数据。后续仍需新的连续主演示和新机器验收。完整工具M1的首批负面结果和修复后的单场景复验都保留，不从材料中删除。

证据：S01 docs/高分方案_需求架构创新与任务_20261017.md；S02 docs/P0完成审计_20261017.md
