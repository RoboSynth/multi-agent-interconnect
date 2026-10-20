# NEW7 云端部署验收

本目录保存本次真实云部署可共享的回执。服务器的七个正式身份是唯一消费者；本地保持停止。部署操作说明见 [SERVER.md](../../deploy/SERVER.md)，实际工具归档见 [deploy/server](../../deploy/server/README.md)。

## 当前结果

- 阶段 5：H00 已通过 30.002 秒、30 次成功请求、10 个完整订单流程，failed/unknown/pending=0。修正 SDK 退组清理顺序后，六域及协调者正常关闭、远端自有群组已清理；`stage5-finalize.json` 保留原健康窗口复用和 3 秒短恢复检查的不同口径。
- 阶段 6：`stage6-log-scan.json` 为实际六类新日志扫描，命中/解析错误/读取错误均为 0。先发 heartbeat+access，等待七身份 aliveMap 在线后扩为六类；两个 collector 使用同一个 offset 卷，`read_from_head=false`，未补历史。
- 阶段 7：三个服务 active/enabled，巡检每 600 秒执行，模型和故障演练关闭，协调者资源凭据为 0。首轮巡检已完成；每天上海时间 00:15 生成本队状态与榜单报告。
- 阶段 8 已通过：北京时间 07:54:18 请求真实重启；07:56:23 的只读快照证明 boot_id 已改变、七身份和三服务自动恢复；08:04:01 首轮巡检自动完成，距请求 582.976 秒。没有手动启动恢复。09:46:49 的两小时定时查榜成功执行，退出码 0，七身份保持在线。

平台实际计数持续增长：07:52 基线 caller 榜发现一个本队身份、Access=1；08:32 为第 35 名、Access=34；09:46:49 正式验收时为第 29 名、Access=76、Message=360（合计 436）。另五个身份在含内部调用的 callee 榜，名次为 78、79、80、83、85。两榜分别保留，不虚构统一名次。

正式查榜距新日志上线 7201.082 秒，`stage8-two-hour-acceptance.json` 的五项检查全部通过。整个观察窗口完成 11 轮巡检、失败和 unknown 均为 0、故障演练 0；其中重启后完成 10 轮。三服务自重启后自动重启次数均为 0；内存采样约 38–40%。窗口包含计划内重启及其心跳缺口，不代表连续两小时无中断，24 小时连续运行仍待实际观察。

## 证据文件

| 文件 | 内容 |
| --- | --- |
| `stage5-finalize.json` | 原 H00、短恢复、六域/协调者正常清理及租约恢复 |
| `stage6-start.jsonl`、`stage6-expand.jsonl` | 新日志分阶段启动、七在线确认、旧 collector 正常退出及全部六类启动 |
| `stage6-log-scan.json` | 实际日志扫描结果，未复制原始日志内容 |
| `stage7-before-reboot.json` | 重启前 PID、服务、七在线和调度状态 |
| `stage8-reboot-request.json` | 实际重启请求时间与重启前 boot_id |
| `stage8-after-reboot-initial.json` | 重启后首次通过的只读观察 |
| `stage8-scheduler-recovered.json`、`stage8-reboot-acceptance.json` | 首轮自动巡检完成及与十分钟门槛的真实时间比较 |
| `stage8-after-one-hour.json`、`stage8-after-two-hours.json` | 一小时及正式查榜后的七在线、服务、租约主管和 collector 检查 |
| `stage8-two-hour-acceptance.json`、`stage8-two-hour-summary.json` | 已实际执行的一次性验收服务、两小时门槛和正数 Access 判断 |
| `stage8-two-hour-team-ranking.json`、`stage8-two-hour-local-status.json` | 正式榜单本队条目及七身份本地日志/巡检统计 |
| `stage8-scheduler-final.json`、`runtime-observation-trend.json` | 实际巡检完成、内存、服务重启次数及日志字节数采样 |
| `interim-summary.json`、`interim-team-ranking.json`、`interim-local-status.json` | 08:32 中间观察，区分于正式两小时验收 |
| `baseline-ranking-summary.json`、`baseline-ranking-team.json` | 仅含本队条目的实际平台基线，未保存其他队原始榜单 |
| `agent-image-manifest.json`、`agent-image-check-resumed.json` | 云端补丁镜像和成功续验记录 |
| `preserved-initial-image-check-failure.json` | 原验证脚本路径判断失败，保留失败，不覆盖成成功 |

运行源码提交为 `c39038626ba7981a6ccbb3d55643c116b5cadc8c`；后续归档与文档提交不表示镜像已重新构建。SDK 修复在云端 45 项测试和 7 个子测试通过；归档部署工具在 Windows 上 67 项 fake 测试通过，它们与真实云端验收分别记录。

后续验收要求：七身份在线单独查 aliveMap；满两小时后，含内部 caller/callee 榜至少一个本队身份有正数 Access。正常巡检没有使用备用库时不制造空转调用来凑齐榜单。24 小时连续运行需另外积累实际记录，本次两小时验收不代替它。

私钥、证书、私密配置和身份打包文件未复制到本目录；完整本机操作记录保留于原部署 artifacts，云端原证据亦保留。
