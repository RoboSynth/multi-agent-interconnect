# 云端四例接管复验结果

本批 `cloud-four-20261020-7c082190d0` 已执行并取回结果：**2/4 通过，2/4 在故障注入前的业务基线失败**，保留 `finished_with_failures`、退出码 1。四例资源恢复、独立 30 秒 / 10 完整订单流程、远端群组正常关闭、六域正常退出均通过。统一租约归还后，实际巡检已恢复并完成两轮。

## 逐例结果

| 例子 | 原始状态 | 功能结论 | 本例任务配对 | 最终独立 H00 |
| --- | --- | --- | --- | --- |
| F10 / M0 | completed | 复合故障观察与三项修复完成，模型调用 0 | 17/17，34 条 access | 30.002 秒，10 完整流程，通过 |
| E1-a 观察后中断 | failed / ValueError | 初始基线失败，未进入故障注入及计划中断，接管尚未复验 | 6/6，12 条 access | 30.002 秒，10 完整流程，通过 |
| E1-a 修改前中断 | failed / ValueError | 初始基线失败，未进入故障注入及计划中断，接管尚未复验 | 6/6，12 条 access | 30.003 秒，10 完整流程，通过 |
| E1-a 修改完成后中断 | completed | 主智能体实际退出 83，修改 MCP 调用 1 次；备用返回 already-applied、不重复修改；正式业务验证通过 | 13/13，26 条 access | 30.003 秒，10 完整流程，通过 |

共 **42/42 个真实捕获任务完成两端 access 配对，84 条记录，缺失 / 多余 / 重复 / 冲突均为 0**。修改后中断的原始崩溃任务仍保留非终态生命周期；原 journal 在断网恢复容器中补齐 1 条 access，并保留未知结果，没有伪造任务完成。

[核对汇总](audit/summary.json)、[批次原始结果的可审阅副本](batch-summary.json)、[逐例结果](cases/)、[逐例 access 对账与按本批 taskId 过滤的两端记录](audit/) 已保存。四例六项 SDK 关闭检查全为 true，六域均取得精确批次 session 的正常退出回执。资源 / 清理通过与功能通过分别保留。

## 两例基线失败根因

数据链路：`incident/partners.py:171` 将 incident_id 和已经包含事故编号的 logical_task_id 再次拼接；`business/load.py:48` 加上 load 前缀、序号和 cancel 后缀；`business/order_app/main.py:16` 要求创建 / 取消编号均不超过 128 字符。

| 基线 | 创建编号长度 | 取消编号长度 | 原始 HTTP 结果 |
| --- | --- | --- | --- |
| 观察后中断 | 125，合法 | 132，超限 | 创建 / 查询各 1 次 200，取消 28 次 422；0 完整流程、1 个原始 pending intent 保留 |
| 修改前中断 | 129，超限 | 136，超限 | 创建 30 次 422；0 完整流程、1 个原始 pending intent 保留 |
| 修改后中断 | 117，合法 | 124，合法 | 创建 / 查询 / 取消各 10 次 200 |

[离线诊断](audit/key-validation-diagnosis.json) 用原样捕获的请求内容和真实 API Pydantic 模型复现 `string_too_long`，没有发送 HTTP 或修改资源。两例都只有一个 baseline verify 产品，没有产生计划主智能体退出 / 修改证据。因此这是工作负载编号与 API 约束不一致，不能作为已观察到的接管逻辑故障。

原 runner 只记录 ValueError 类，没有保存实际 message 或 traceback。按唯一执行到的基线分支，可定位到 `eval/platform_resume_experiment.py:831` 的 `Initial target does not pass the clean business baseline`；这是源码与结果推断，不是补造的原始 traceback。

修复保留 OrderObserver 短编号兼容，对过长组合使用完整运行编号的稳定摘要，保证创建 / 取消均在 128 字符内；已有 pending intent 继续使用原编号。本批冻结及执行时尚未应用此修复。后续[单文件维护](../observer-key-maintenance-20261020/README.md)已于03:57 UTC完成部署、长编号真实H00与首轮巡检验收；本批两例失败保持原判，未追加第五例或补跑两个接管中断点。长编号业务验证与真实接管复验分别验收。

## 实际巡检与采集恢复

- 统一交接于 **03:09:29.955 UTC** 恢复，同 host session `ac07184a92394a15bddc43bd7e14a0bb`。
- 恢复后的真实巡检分别于 **03:14:39.404**、**03:25:14.624 UTC** completed。[事件证据](audit/collector-scheduler-r2.json)
- **03:26:25.821 UTC** 的 [runtime snapshot](audit/post-batch-runtime.json) 11 项检查全为 true：三个服务 active / enabled、host running、正式连接、协调者资源凭据 0、模型关闭、七身份在线、600 秒巡检、自动故障审批关闭、原采集器运行。
- 原采集器和 offset 卷保留，当前启动时间早于本批，重启次数 0；七个日志源和只读子目录绑定一致。42 行 offset 的标识 / inode 不变，文件 inode 与 offset 范围全部有效，行创建时间均早于本批；两次快照间 **14 行进度增加，共 12,076 字节，没有倒退**。[连续性汇总](audit/offset-continuity-summary.json)

held-all-six 回执的旧启动时间早于此前计划内服务器重启，不能直接与当前 boot 的 StartedAt 比较为异常；当前两次 StartedAt 一致且早于本批。未清空 offset、未请求历史补发。实验协调者 AMP 位于各例输出目录，未纳入常驻协调者采集源，因此本地配对不等于全部实验调用已经进入平台统计。

## 冻结与取回

| 项目 | 本批记录 |
| --- | --- |
| 云项目 / 端口 | incident-pilot-new7-cloud-20261019；38081 / 38082 / 38088 / 38090 |
| 镜像 | sha256:91e51b8c1c6a92ad60eeee9c67810307671d8f32e45454c94016771cecdcdac4 |
| Git 基线 | c39038626ba7981a6ccbb3d55643c116b5cadc8c，实际文件含已上线的公开体检补丁 |
| 计划 SHA256 | 29f4f521359be6d116217d6a559d35f130db3f7b1fff36cede2b40db9048eb91 |
| 冻结范围 | 174 个产品文件、51 个 helper / 配置输入，以实际 SHA 绑定 |
| 离线检查 | Windows 9 项通过，0.255 秒；云 Linux 9 项通过，0.023 秒 |
| 原始归档 | 124 文件，123 项内容 SHA 核对通过；归档 SHA c4f32fa575de3de967fef3350e9137037f12c14a87b6403e0ab8b24f5f1b20b3 |

[取回与脱敏说明](retrieval-provenance.json) 保存原始与可审阅结果 SHA；可审阅 JSON 仅将 action approval 的 proof 换为摘要。原始归档留在本机私密 artifacts，原始失败不变。云原始结果仍位于 `/opt/incident-pilot/eval/results/platform/cloud-four-20261020-7c082190d0/`，私密计划授权位于 `runtime/private/cloud-four-revalidation-20261020-r1/`。

执行后曾因本机公网源变化暂时无法 SSH；恢复放行后已完成上述实际核验，先前待取回描述已替换。[终端回执](execution-terminal-receipt.json) 和 [F10 当时进度回执](f10-progress-receipt.json) 保留为历史记录。
