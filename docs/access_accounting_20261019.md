# 18条访问缺端的后续诊断

原闭合检查仍是289条Start、预期578条access、实有560条、缺18条，T05严格双端对账未通过。

新增逐条关联已确认18条都缺接收端：17条数据库、1条业务验证。每条都有发送端access与目标接收端MessageEmitter receive，排除了本次按错关联键造成的假缺端。14条能用同一原请求的crash marker和实际81/82/83退出码证明主库硬退出跳过finally；3条full_history没有保留主进程trace/exit，原因仍不确定；首例环境失败缺的是incident.verification记录，不能归到主库退出。

当前项目新增GroupAccessMiddleware在任务回调返回或抛异常后写access。os._exit不会运行finally，SIGSTOP恢复后可继续执行。E1-c三例最终都有原主access，但各有一条AIP生命周期不完整，说明两种统计不同。

高分方案T05原门槛是一次F10任务与access对账。本批故意退出任务的全量双端完整性是更强观察，二者不能互相改判。未来若要求硬退出后也恢复日志，需要明确进入处理与异常恢复语义；提前写成功状态会误报。本轮没有更改日志中间件或原统计。

[逐条安全诊断](../evidence/access-accounting-20261019/missing-access-diagnosis-final.json)与[来源和原初分析失败](../evidence/access-accounting-20261019/source-ready.json)保留哈希和证据边界。原151输入、7相关源码逐字核对，未调用平台、WSL、Docker或业务。复现脚本针对本机保留原件目录，需按来源记录恢复原artifact结构；它不是fresh clone中可直接运行的平台实验入口。
