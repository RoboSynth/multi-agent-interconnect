# 原请求只读回执工具验证

入口：[使用说明](../../docs/receipt_reconciliation.md)、[源码](../../eval/receipt_reconciliation.py)。

14个不同离线方法有通过证据：初版12方法通过后，窗口适配与总deadline修改影响其中6项，另新增2项，本轮重跑8项通过，未受影响6项复用；不是20个不同方法。源码及两个既有业务校验器的最终哈希见[source-ready-revision2](source-ready-revision2.json)，[独立审阅](peer-review.json)按最终三份源核对。

真实七份历史意图的默认CLI已校验通过：14份summary/trace原件及manifest前后未变，7意图，显式运行时最多6次GET，另1个原trace未发送的cancel跳过查询。本轮没有`--run`、实际HTTP、服务启动或旧结果修改；旧未决仍未解决。命令来源、原件哈希与首次失败保留在两个describe记录。

首次沙箱测试遇到临时目录权限错误；第二次卡在异步初始化，核实精确父子进程后仅停止本轮测试，旧退出码未提供。允许本机回环的环境中同版12方法通过。首次真实输入描述发现ContinuousObserver的summary仅统计故障窗口，而trace含暖场；后续按已有统计语义修正并增加行为测试。每项请求另加8秒总deadline，超时保持unknown并继续后项，不宣称响应字节上限。

证据不包含原键、订单号、响应正文、原summary/trace数据或私有manifest；只保存文件/字段定位和摘要。工具从已有原件派生意图并核对trace，仍需与原冻结清单核对摘要来源。404不证明未执行，create提交不代表完整流程结束，原结果保持。

本机绝对项目路径在部分JSON中以`[project]/`表示；这是元数据投影，非原私有运行输入。原件保持本机不变，原件与公开投影的SHA对应见[路径投影索引](metadata-projections.json)。其他证据中对这些元数据的哈希引用仍指原件；源/日志/计划哈希、计数及判定未变。
