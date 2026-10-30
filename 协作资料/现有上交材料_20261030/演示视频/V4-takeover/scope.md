本素材来自 2026-10-29 同一租约批次中的真实 E1-a / after_applied。主库完成 db.restore_writes 账本记录后退出 83，Docker 原生 FinishedAt 为 09:41:44.663452691 UTC。协调器因原任务超时进入接管，重新执行 ADP 发现和能力确认，备用返回同一 operation 的 skipped_already_applied。

takeover-timeline.json 区分 Docker 退出时间、AMP 系统/消息/审计原生时间、AIP 消息 sentAt 和区间证据。备用入群没有单独保留原生完成时间，因此只给出它已经完成、后续 describe 命令已经发送的上界。交接包发送和备用回执按 messageId 与 AMP 消息记录关联，最终业务验证使用协调器 AMP 成功审计时间；引用消息摘录在 handover-message-excerpts.json。

本例修改类 MCP 调用计数为 1，且由原主库执行；这证明工具调用次数，不直接证明物理写入次数。原主库请求的域端 access 以 OutcomeUnconfirmed 恢复，响应状态码缺失，已如实保留；13/13 双端记录能够按 trace_id/correlation_id 配对，其余 12 条域端记录为 200。本例不包含旧主复活，也不包含旧主复活后的 fence 拒绝。

最终业务验证和资源恢复后的独立 H00 均为约 30 秒、10 个完整流程，failed=0、unknown=0。六个本例消费者正常关闭，巡检已恢复。录像是现有工作台前端对本次 transport payload/product 的观察投影，不虚构协调器规划或额外人工审批。视频起点至案例开始约 1.254 秒，时钟样本和 25 fps 误差边界见 run.json。
