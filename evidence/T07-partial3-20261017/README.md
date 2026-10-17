# T07：三旧身份正式巡检与30分钟循环

本次真实健康巡检通过：inc-288551bbd09b423c，经正式 ADP、AMQPS 邀请和完整 AIP 生命周期调用三个旧身份。数据库只读状态 false、应用可达、无阻塞会话，独立订单验证持续30.003秒，30次请求全部成功、10个创建/查询/取消流程完成、unknown和pending均为0。协调流程总计32.594秒，无资源修复动作或审批。

唯一持久循环已于12:05:36.517879Z启动，实际PID35572（launcher43540），间隔1800秒；下一次计划巡检12:34:50.142Z，基于成功确认时间加1800秒设置。公开快照覆盖首次127.675秒，未出现立即重复的job/incident。实际SetThreadExecutionState返回非零，日志为success=true、flags=0x80000001、previous=0x80000000。仅证明该进程存活期间的唤醒请求成功；尚未经历第二次周期或24小时运行。

8767实际工作台PID46332，三旧角色application/database/verification连接，mode=wutong-amqps，资源凭据数0；18088订单入口ready=v2。本次是同机三旧身份partial兼容联调，七新版角色尚未启动。新ADP候选在describe/invite前被可信名单排除；候选出现在ADP不等于证书签发或审核已完成。

进程环境为22个系统白名单变量加显式NO_PROXY=wt.ioa.pub,127.0.0.1,localhost；实际子进程环境名称探针资源变量0、额外变量0。默认HTTPX可读取Windows7890系统代理；只读GET对比为默认代理路径5.219秒、直连0.250秒，显式进程NO_PROXY后默认路径0.328秒。后续正式组创建和三域连接成功。未修改全局Windows/Mihomo/电源配置。WSL lease实际PID17780、wsl.exe9604维持会话。

历史失败按原样保留：初次巡检needs_attention；应用原始AMP拒绝为One inbound group is already active；用户明确授权后仅通过官方SDK正常关闭group-incident-cae62c25c8e74b71bf74ebc760ba7a4f；随后连接出现ConnectTimeout，其中下一次由新增日志明确定位到group-create。原始ConnectTimeout叶子未捕获，不能把代理延迟比较说成拿到了原异常路径。

健康巡检首次派发后，私有启动器Python输出句柄失效而exit120；唯一symptom/active已持久化。修复私有输出流后恢复同一个incident并确认completed，没有重新POST另一个incident。scheduler-events中两条job_started属于同一run/incident的派发与恢复；总派发1次。

源码改动仅5文件：selection增加可选可信集合和逐候选30秒deadline；Wutong按role在邀请前过滤并记录阶段；schedule只记录OS唤醒请求/释放的真实返回；两份测试覆盖过滤、空集合拒绝、超时继续、默认候选兼容及原接续语义。20项相关离线行为测试通过，真实健康巡检与首段loop另有运行证据。保持原按AIC排序、完整遍历并选择首个确认匹配的语义，可信列表顺序不是优先级。

证据：status.json为冻结状态；healthy-once-incident.json为完整健康回执；scheduler-events.jsonl保留原失败、同incident恢复及keepawake事件；aip-lifecycle-evidence.json保留7个任务的消息关联字段/原行哈希；环境、进程、可信过滤、官方组关闭与网络对比单独索引。公开白名单排除私有配置、凭据、数据库和完整消息树；运行日志仍写原私有目录，不继续修改本快照。
