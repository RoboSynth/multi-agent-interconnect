本素材来自 2026-10-29 同一次真实云端 F10/M0 运行，workload seed=101，repeat=1，模型调用为 0。录像使用现有工作台前端接入本次独立采集适配器；它读取同一个协调器，关闭另起事故入口，不是原巡检服务的页面。身份、提供者姓名、端点和机器路径作匿名投影，业务数值保留原值。

与 10-20 包装命令的明确差别是审批方式：原评测每 0.1 秒预授权，本次通过真实 pending future 的原审批方法处理，在画面停留后由采集脚本点击批准。唯一一次高风险审批为 db.restore_writes，实际 pending 约 3.32 秒；不是临时伪造的审批记录，也不描述为现场人工点击。

events.jsonl 保留 20 条 transport 事件和 40 条协调器原生事件。order-samples.json 保留完整 52 条连续采样，含基线 5 条；summary.requests 为故障后的 47 条。完整采样中 36 条 success、16 条 unknown，随后原请求得到收敛，recovery_confirmed=true。诊断加域端验证为 42.748 秒，采样确认恢复为 48.002 秒，两者定义不同。

双端 access 按本次 trace_id/correlation_id 精确配对 18/18。案例结束后独立 H00 为约 30 秒、10 个完整流程，failed=0、unknown=0。正常关组、六个本例消费者关闭和资源复原均有回执，巡检已恢复 running，原工作台 connected=true。

录像与云端事件通过本次 HTTP 往返时间对齐，视频起点至案例开始约 1.075 秒；精确样本、误差说明见 run.json、browser-run.json 和 actions.json。视频为 25 fps，不声称亚帧精度。传输原始事件没有原生墙钟时间的部分标为采集到达时间；业务 monotonic 时间用同机本次时钟锚点换算。
