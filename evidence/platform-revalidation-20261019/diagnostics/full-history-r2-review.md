# E1-b full_history-r2 正式链路核验

本例 **completed / runner exit 0 / 收尾安全**，只代表这一正式重复成功；不改写 full_history-r1 的失败，也不扩大为 3/3。

实际消息第 58 行发送 `full_history` resume，7 条历史均含合法 `aip_session_id`，且逐条匹配此前捕获的正式请求或产品。实际发送 IFC 为 18413 字节，SHA 为 `d0f6db016a7309d9fe4b88ee5a39e8e11814f30d8efad20fb5e4121204ad7f39`；独立 payload、计划、结果和实际发送的方法一致。

备用端第 61 行返回 `status=ok` 与交接指纹 `681055903af4abd0bc964e93fa8a2b17d88e14c6c29236a00607f5924dc25c6b`，和实际发送 handover 的独立重算值一致；第 63 行确认 completed。其操作状态为 `skipped_already_applied`，有效 fence 为 `(7,1)`。因此，此正式部署已经接受了旧版曾拒绝的合法会话元数据。

正式 collector 记录主进程实际退出码 **83**；持久化 trace 记录 `after_applied`、ledger `applied`、尚未回传 AIP 产品。修改 MCP 次数为主端 **1**、备用端 **0**，主端一次调用正常返回。镜像 `sha256:f7e91b059a7b50b52294a6a3ab09dfb1d072841817480bbc2ad2b870f440f6ea` 的主、备 Bridge 源码摘要与冻结源码相符；两个启动 trace 均绑定此例准备包。实际退出码来自冻结 collector 的 Docker State 检查，保存的 inspect 原始输出仅留摘要；未另附原始 state 文件。

业务恢复验证和最终独立 H00 均达到 30 秒、30/30 请求、10 个完整订单流程；6 项关闭检查全真，清理告警 0。原 journal 保留预期的主端未确认记录 1 条，意外在途 0，备用 complete 已确认，未改写 journal。共享操作 ledger 的已应用状态由主端持久 trace 和备用 resume 产品互证，没有单独导出的域 ledger 文件。

输入文件 SHA 绑定及行号见 [full-history-r2-review.json](full-history-r2-review.json)。本核验只读本地已闭合证据，原用例文件未变。
