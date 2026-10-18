# T12 / 故障场景差距审阅（2026-10-18）

只读审阅当前方案、精确源码片段和既有公开结果索引；未运行测试、模型、实验或资源命令。结论属于源码与已保存证据核对，不是新增故障验收。

## 契约与完成范围

权威要求是 `docs/高分方案_需求架构创新与任务_20261017.md:417–431` 的 **H00 + F01/F02/F06/F07/F10/F12/F15/F19**。T12 在第509行要求这些场景可注入、复原并通过 H00。旧20场景表中的其它编号不自动成为本轮P0缺口；正式E3也只覆盖其中五个故障（第475行）。

| 范围 | 实现与离线边界 | 已保存真实运行证据 | 尚不能声称 |
| --- | --- | --- | --- |
| H00、F01/F02/F06/F07/F10 | `eval/inject.py:22–30,338–378`；显式目标、错误路径复原等检查在 `tests/test_eval_platform.py` | TEAM `docs/new7_e3_20261018.md` / `evidence/new7-e3-45-20261018-first/`：45终态、37确认、8个M1未确认；独立H00通过 | 45格全部恢复；旧未决键已解决 |
| F12 | 原键、缺键业务逻辑与旧专用入口存在；`eval/unknown_receipt_experiment.py`、`tests/business_verification_test.py`、`tests/test_public_order_version.py` | TEAM `evidence/eval/results/local/F12-container-20261017-initial.json`：9项检查全部通过、proxy停止、独立H00通过；`platform_group_tested=false` | 当前NEW7显式目标或正式AMQPS已完成F12 |
| F15 | `acps_mcp_bridge/experiment.py:17,123–152` 支持三个精确退出点；正式工作者有对应离线检查 | 旧本地接续证据与当前正式准备分开；TEAM `docs/new7_e1_implementation_20261018.md` 明确正式E1执行为0 | 三个时点的正式接管已验收；当前薄runner已支持全部组别 |
| F19 | `eval/participant_failure_experiment.py`、AMP事实及参与者故障状态实现存在；通用injector主动拒绝无所有权的杀进程调用 | `docs/participant_failure.md:37–47`：旧本地自有worker实际退出81、故障诊断、复原后的独立H00通过 | 正式AMQPS F19、远程Monitor或长期验收已完成 |

F15/F19由专用入口负责是合理边界，不能因为通用 `inject.py` 拒绝就判定项目完全未实现。F19还受方案第651行的降级顺序约束；本轮不建议重做已有本地F19。

## 建议先开发的两项

### 1. 补齐原请求回执的成功判据（优先）

**具体缺失行为：** `incident/partners.py:120–126` 请求原键回执后，仅以 `status_code == 200` 把原意图标为已解决。`business/load.py:22–27` 只验证响应是dict且版本为v2。因此返回 `{"order_api_version":"v2"}` 或 `outcome="unknown"` 的200响应也会被认定解决；若新业务窗口通过，就可令 `business_recovered=true`。这是源码推导的边界缺陷，本次没有发请求复现真实故障。

**已有测试恰好遗漏：** `tests/business_verification_test.py:21,59–69` 的200 fixture只有订单号和版本，没有 `operation_key/outcome`，并期望原请求解决。版本缺失/错误已有专门测试，不需要重复开发版本校验。

**可复用真实契约：** `business/order_app/store.py:149–150` 已返回 `operation_key / operation_kind / outcome=committed / order_id / order / changed`；旧F12解析器 `eval/unknown_receipt_experiment.py:26–29` 至少已要求 `committed`。

**最小改动与验收：** 在原键回执处理处校验已提交结果及原键绑定、合法订单标识；完整合法回执才解决。缺字段、错误原键、非committed、无订单标识的200保持未知/人工，仍可独立记录新业务健康；404/异常与缺键分支保持。先补少量离线负面fixture，不需要新模型、平台或故障窗口。生产文件可能属于冻结204输入，实施前由root核对重叠并建立新修订，不能覆盖旧实验输入。

### 2. 为F12建立可绑定显式容器目标的专用E5入口

**具体缺口：** `eval/targets.py:87–91` 只接受三个业务端口；`eval/inject.py:339–340,360–361` 与 `eval/run.py:109–110` 明确拒绝显式DockerTarget上的F12。现有 `reply_drop()` 的健康探针还固定在 `127.0.0.1:8090`（`eval/inject.py:318–336`）。旧专用入口虽可配置project/公开URL/proxy端口，但只绑定一份compose、按约定容器名查询PG，并自行 `up --build reply-drop`（`eval/unknown_receipt_experiment.py:40–56,68`），没有当前显式目标的多overlay、镜像/挂载/所有权守门。

**另一处接线缺失：** 通用 `eval/run.py` 接受native F12，但第233行仍仅 `engine.new(通用症状)`，没有交付实际未知原键/缺键标记；它会检查负载未决统计（`eval/observation.py:87–105`），但不能据此宣称协调者执行了F12原请求解析。正确的原键接口已在 `IncidentCoordinator.new()` 与Verifier存在，应复用。

**最小开发范围：** 新的E5目标/入口复用现有proxy、真实PG唯一性断言和原键/缺键分支；显式绑定proxy端口、compose输入、loopback与镜像/route/volume边界，复原仅停止自己创建的proxy并恢复原route。显式把实际未知意图交给协调者，真实原因仍只保留在评测记录。不要把F12塞进已冻结E3五场景协议或改写旧45格。

**验收：** 先离线验证目标/参数/错误路径finally复原与原键传递；之后另行安排明确资源窗口：确实提交但丢回包、同原键找到同一订单、同键重试仍只有一张、缺键不补单、原route恢复、独立H00通过。旧本地结果可作基线，不能冒称新目标已验证。

## 不建议本轮重复开发

- 五个E3注入及observer的finally恢复已有实现、离线错误路径和正式结果，优先保留失败证据。
- 正式E1当前只有 `E1-a/after_applied` 薄runner（`eval/platform_resume_experiment.py:107–108,145–178`）；另外两个时点已有worker钩子，正式执行和对比尚待独立授权及后续协议修订。当前不是再写一个同功能after_applied runner。
- 当前正式E3留下的七个旧未决阶段仍未解决，7次原键GET404不能证明未执行。不能用新的H00 pending0覆盖这一事实。

建议先做第1项：它是独立、可离线验证的业务正确性修复；第2项随后形成真正可复现的正式F12/E5链路。
