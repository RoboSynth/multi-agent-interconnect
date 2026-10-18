# T06 真实七源日志卷 stdout 采集

一次实际运行通过：2026-10-18 11:37:34.425–11:39:17.985 UTC，观察窗口75.005秒，外层退出0。采到32,069条记录和32,069个唯一log_id，JSON解析/轻量AMP字段检查/未知AIC/重复计数均为0；七个配置AIC及六类日志的42个组合全部覆盖，七个来源均出现自然新增。

来源为六域的五个既有named volume（主备共享卷的不同amp-*子目录），加协调者日志只读bind。实际核验七源只读挂载、network:none；使用新独立状态卷并绑定来源映射哈希，形成42个offset DB。只启动一个新collector，正常SIGTERM退出0；原29个容器的ID、状态、StartedAt、restart count等完全保持，采集状态卷保留。没有发送业务、MCP或模型任务。

`summary.json`给出实际计数与边界；`lifecycle.json`保留逐命令实际退出和原始收据哈希；无Fluent Bit进程时的ps查询退出1属于预期空结果。`identity-counts.json`包含配置AIC/角色/类型计数及自然增长字节。`samples-42.jsonl`按每角色每类型最小log_id确定性抽取，一共42条原stdout行，字节和字段未改；索引保留其原完整stdout行号与行哈希。完整32,069行stdout与stderr继续保存在本机，完整SHA256/字节数见索引和lifecycle。

`verification-source.py`是这次实际执行的原源码副本，供审阅实际检查算法；它绑定本机目录和资源标识，不作为通用启动入口。字段依据为SDK LogRecord的aic/log_type/log_id；本次进行JSON和上述字段/身份计数检查，未进行完整SDK schema或签名验证。算法位置和已测源哈希见`source-inputs.json`。

镜像为官方5.1.3 Linux/amd64；`image-provenance.json`区分远端platform manifest、本地tar-load别名、tar和实装image ID，并保留首次直接Docker拉取超时。其他机器应从官方registry拉取远端manifest后重新inspect，不能照抄本机导入别名。

本轮完成真实七源到本地stdout的读取、身份/类型覆盖及自然追加观察。Kafka/Monitor实际投递仍待官方配置。现有原始失败、旧fixture证据和日志均保留；rename、copytruncate或停机归档未在此运行验证。
