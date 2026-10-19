# 接续修复复验范围审阅

本批只准备文件，不生成执行授权，不启动服务或故障。准备范围为 12 例：每轮 E1-a `after_observation` 一例，以及 E1-b `after_applied` 的 `from_scratch`、`full_history`、`resume_package` 各一例，重复三轮。先审阅首轮 4 个不同条件，再继续剩余 8 例。

## 范围依据

原正式批冻结源为 `c1c09e569ef67b7f0f0c2b2e8a948afec53f0c31`，22 例终态为 18 通过、4 失败。三例 full_history 失败链涉及正式历史条目的可选 `aip_session_id` 被 Bridge 旧白名单拒绝，以及拒绝产品的 `operation=None` 掩盖原 reason。独立修复提交为 `2b4e28b1bed6978710abb1a0cdf8835a5a6149bf`，已包含在本次起点 `c75554d6b6de3bdaba53677e678a6fd35e4fef80`。

| 条件 | 数量 | 作用 |
|---|---:|---|
| E1-b full_history | 3 | 验证含合法 session 元数据的真实交接、Bridge 接受、账本与回执确认。 |
| E1-b from_scratch | 3 | 在同源、同镜像、同资源条件下保留对照。 |
| E1-b resume_package | 3 | 同条件对照并核查已有接续路径。 |
| E1-a after_observation | 3 | 补原首例环境失败，覆盖观察任务接管后重新观察的路径。 |

E1-c 的 adapter、Controller、ledger fencing 均不在该修复 diff 中；其成功路径的 control.operation 本来就是字典，新增 null 归一化不改变该分支。因此这 12 例足够作为本次修复复验，不包含 E1-c、F12/E5 或其余 E1-a 断点。原 E1-c 3/3 等结果继续只归属于原冻结源码，不拼成新批全通过；若要声明当前新镜像已完成脑裂验收，需另行准备 E1-c 三次。

## 绑定与执行边界

- 独立项目 `incident-pilot-revalidation-20261019`，端口 `58081/58082/58088/58090`。新计划、bundle 与结果目录不覆盖原批，结果目录在执行前必须不存在。
- 每份计划绑定当前完整 runner source_paths、配置、证书、审批输入、worker bundle、精确镜像 ID 和七身份映射。保留源变化检测；部分准备失败也保存，不覆盖重试。
- 必须重建并核验新镜像。bundle 只覆盖 `eval/platform_database_worker.py`、`acps_mcp_bridge/experiment.py`、`incident/local_worker.py`；修复 Bridge 来自镜像 `/srv`，旧镜像加新 bundle 无法证明修复部署。
- 新镜像需另有实际源/导入证明，包含修复 Bridge、vendor 与已安装 SDK；宿主协调器 `incident/wutong_transport.py` 由计划哈希与运行前源快照绑定。准备器本身不声称已完成镜像导入证明。
- 保留未来 Compose image 绑定、六域源证明、两数据库共享状态卷、只读配置及 bundle 挂载、身份独占、无第二 Inbox 消费者和无活动/未知操作前提。跨电脑身份独占不能由本机锁证明。
- 每例保留正常关组、资源/worker 恢复、独立 30 秒/10 完整订单流程 H00；保留实际退出码、真实发送与确认、MCP 调用计数及失败。E1 `model_calls=0`，不引入模型调用。
- 后续授权应明确包括本批启动、12 份绑定计划、计划内故障与修复、失败/中断后对本批可核实自有群组通过官方 SDK 正常关组，以及结束时停止本批项目进程。正常关组会删除对应远端队列、交换机和 ACL；不覆盖旧批、未知组或原始 broker 删除。保留卷、账本、未知状态和失败证据。

## 审阅来源

- `eval/platform_resume_experiment.py`：effects 28–49、source/config freeze 89–188、验证与授权 191–293、源/镜像及共享卷检查 373–538、正常关闭 629–645、执行/恢复/H00 700–859。
- `eval/prepare_platform_e1_worker.py`：bundle 三份源与 manifest 15–50、只读 overlay 53–65。
- `eval/platform_e1c_transport.py`：仅暂缓并最终执行旧主正常移除。
- `acps_mcp_bridge/bridge.py`：full_history entry 校验 99–118。
- `incident/wutong_transport.py`：拒绝原因、null operation 归一化、接管状态分支 366–404。
- `docs/platform_acceptance_results_20261019.md` 与 `evidence/handover-wire-fix-20261019/verification-summary.json`：旧批真实终态及 39 个不同离线方法通过的边界。

工具复用：旧 `p0-acceptance-prep-20261019/plan-preparation/prepare_bound_plans.py` 与对应 guard 测试。旧批源、计划、授权、输出和判定均未修改。
