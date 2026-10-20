# NEW7 云端部署验收

本目录保存本次真实云部署可共享的回执。服务器的七个正式身份是唯一消费者；本地保持停止。部署操作说明见 [SERVER.md](../../deploy/SERVER.md)，实际工具归档见 [deploy/server](../../deploy/server/README.md)。

## 当前结果

- 阶段 5：H00 已通过 30.002 秒、30 次成功请求、10 个完整订单流程，failed/unknown/pending=0。修正 SDK 退组清理顺序后，六域及协调者正常关闭、远端自有群组已清理；`stage5-finalize.json` 保留原健康窗口复用和 3 秒短恢复检查的不同口径。
- 阶段 6：`stage6-log-scan.json` 为实际六类新日志扫描，命中/解析错误/读取错误均为 0。先发 heartbeat+access，等待七身份 aliveMap 在线后扩为六类；两个 collector 使用同一个 offset 卷，`read_from_head=false`，未补历史。
- 阶段 7：三个服务 active/enabled，巡检每 600 秒执行，模型和故障演练关闭，协调者资源凭据为 0。首轮巡检已完成；每天上海时间 00:15 生成本队状态与榜单报告。
- 阶段 8：北京时间 07:54:18 请求真实重启；07:56:23 的只读快照证明 boot_id 已改变、七身份和三服务自动恢复。重启后首轮巡检及满两小时查榜仍待真实观察。

07:52 的平台基线查询已在含内部调用的 caller 榜发现本队一个身份，access=1；这是实际平台计数证据，但不是两小时后的验收结果。两小时验收计划北京时间 **2026-10-20 09:46:49** 执行，以到期后的实际报告为准。

## 证据文件

| 文件 | 内容 |
| --- | --- |
| `stage5-finalize.json` | 原 H00、短恢复、六域/协调者正常清理及租约恢复 |
| `stage6-start.jsonl`、`stage6-expand.jsonl` | 新日志分阶段启动、七在线确认、旧 collector 正常退出及全部六类启动 |
| `stage6-log-scan.json` | 实际日志扫描结果，未复制原始日志内容 |
| `stage7-before-reboot.json` | 重启前 PID、服务、七在线和调度状态 |
| `stage8-reboot-request.json` | 实际重启请求时间与重启前 boot_id |
| `stage8-after-reboot-initial.json` | 重启后首次通过的只读观察 |
| `baseline-ranking-summary.json`、`baseline-ranking-team.json` | 仅含本队条目的实际平台基线，未保存其他队原始榜单 |
| `agent-image-manifest.json`、`agent-image-check-resumed.json` | 云端补丁镜像和成功续验记录 |
| `preserved-initial-image-check-failure.json` | 原验证脚本路径判断失败，保留失败，不覆盖成成功 |

运行源码提交为 `c39038626ba7981a6ccbb3d55643c116b5cadc8c`；后续归档与文档提交不表示镜像已重新构建。SDK 修复在云端 45 项测试和 7 个子测试通过；归档部署工具在 Windows 上 67 项 fake 测试通过，它们与真实云端验收分别记录。

后续验收要求：七身份在线单独查 aliveMap；满两小时后，含内部 caller/callee 榜至少一个本队身份有正数 Access。正常巡检没有使用备用库时不制造空转调用来凑齐榜单。24 小时连续运行需另外积累实际记录，本次两小时验收不代替它。

私钥、证书、私密配置和身份打包文件未复制到本目录；完整本机操作记录保留于原部署 artifacts，云端原证据亦保留。
