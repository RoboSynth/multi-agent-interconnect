# 本批遗留群组关闭复核

本次只执行了 1 次已授权的 cef7 官方 SDK 正常关闭，实际退出码 1，清理未通过。没有启动第 4 项故障实验，也没有重跑前 3 项。

- cef7 的唯一创建成功事件、原协调 AIC、冻结计划和证书 CN 一致；原 journal 任务表为空，没有业务消息。原 runner 已退出，10 个自有容器实际停止，keeper 退出码 0。
- AMQPS 连接成功；DISBAND 返回原 exchange 不存在。随后精确 ACL DELETE 连接报 ConnectError，没有删除确认；这次未执行队列和交换机删除。finally 已关闭连接，失败原件保留。
- 后续 1 次只读核查使用 AMQP passive 查询，cef7 与 7bed 的两个 exchange 和两个 leader queue 均由 broker 返回 NOT_FOUND，证明它们在核查时不存在。
- 7bed 仍只有本批创建意图，远端是否曾成功创建、ACL 是否残留未知。本次未向 7bed 发出删除请求。源码中的资源名和 ACL key 均包含精确 leader AIC 和随机 group_id；所读本地官方鉴权实现要求证书 CN 等于 leader 路径参数。该源码规则不代替已部署服务的实际策略证明。
- 原 ACL endpoint 的 /health GET 在默认代理行为与仅本客户端忽略代理两种模式下均返回 200。这是之后的可达性快照，不回填关闭失败，也不证明 ACL 已不存在。系统代理配置未变。

独立核查时 SQLite mode=ro 自动产生了空 WAL 和 32768 字节 SHM；原 journal SHA 与修改时间未变。两文件保留，后续核查使用 immutable=1；详细元数据见 independent review。

批次仍为 3 项已尝试（1 通过、2 失败）、第 4 项未执行。完整清理需得到精确 ACL 删除回执或权威只读 ACL 状态。下一步先审查失败和接续条件，当前不再追加真实运行或重试。

本目录原始脚本是固定批次的归档证据，依赖原 BATCH 布局和本机私密配置，不是队友可直接启动的新实验入口。public projection 不含证书/私钥、运行配置或原始 SDK/异常输出，仅保留选定结果及原件哈希；原件全部保留在本机。
