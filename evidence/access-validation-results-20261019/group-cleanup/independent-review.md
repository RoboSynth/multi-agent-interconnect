# 本批 owned group 关闭独立核查

核查时间：2026-10-19 10:03:24 UTC。核查人：close_scope_review。本次仅检查本地证据与源码，未发起网络调用、未执行或重跑关闭。

## 归属和执行范围

`group-incident-cef7f4c704374de1a376eab9ed086e60` 是本批唯一有成功创建记录的对象。源码在官方创建调用成功返回后才记录 `group_session_created`。其 session、owner AIC、冻结计划、配置 `leader.aic`、证书 CN 一致；协调配置、证书、私钥、信任链、approval 五个文件的哈希均匹配计划。计划 SHA-256 为 `6f067bcb989e281e7175e0265c06592c8999752aa88539ebdb663e7cbc0772b8`。

协调 journal 的 coordinator_terms、takeover_events、task_attempts、task_events 均为 0，未发现业务消息文件。原 runner 已 terminal，实际退出码 1；10 个自有容器已停止，keeper 已 terminal，退出码 0。正常关闭属于用户 `call_eed3d32ab9a1402ebcb0e50876f1ed1e` 的原授权范围，原回答为“授权4次，确认七身份无其他消费者”。

`group-incident-7bed224810f3458b8e32433dcdfa1744` 只有创建意图及 ConnectTimeout，没有成功创建记录，远端结果不明。本次脚本明确排除该对象，不能据意图删除。

## 关闭脚本复核

未发现静态运行阻塞。脚本只绑定 cef7 的固定 session，连接现有 AMQPS 资源；`get_exchange/get_queue` 使用 `ensure=False`，不声明群组、队列或 Inbox，不启动消费者或业务任务。官方 dissolve 在 await 前移除唯一 session，后续 transport close 不会再次删除该群组；单用 attempt-1 目录防止自动重跑，失败无循环。

原复核发现的消息文件 guard 拼写已采纳：同时检查 `messages.json` 和实际捕获文件 `messages.jsonl` 均不存在。变更后的脚本和输入绑定在 `owned-group-cleanup/prepared-v2.json`，SHA-256 为 `a9ad8c85ebc17ba68beeef574e2c3d2d23fb877357dedaeb70654fa7089b4e6c`；脚本 SHA-256 为 `855b6b715890d48543d6f5f4d1fc3a9fd2b1799b1837aaef5e4944cb1f7d1cc2`。计划之外的 `integration/wutong_smoke.py` 通过同一冻结源码提交的实际 Git blob 绑定。journal 核查已改用 `immutable=1`，现有 sidecar 保留并纳入输入哈希。

## 实际结果：关闭失败

`owned-group-cleanup/execution/runner.exit.json` 记录实际 terminal、退出码 1，完成时间为 2026-10-19 10:01:02.979655 UTC。一次官方 dissolve 已调用，AMQPS 连接成功；发送 DISBAND 时收到 `NOT_FOUND - no exchange`。随后对精确 cef7 路径的 ACL DELETE 报 ConnectError，没有成功 acknowledgment；队列和 exchange 清理均未进入。

transport connection 已关闭，但 `owned_group_disconnected` 检查为 false。当前不能称远端清理通过，也不能由 exchange 不存在推断 ACL、队列全部清理。原失败结果保留；7bed 未触碰；本次记录没有新增群组、任务或 Inbox 消费者。详见同名 JSON 的实际结果和证据哈希。

## SQLite 核查副作用

独立核查早先使用 SQLite `mode=ro` 打开原 journal 时，SQLite 自动生成了空 WAL 与 SHM。这是核查造成的非预期副作用，已立即报告。此前 `review/access-batch-inspection.json` 记录 sidecars 为空。原 journal 哈希及修改时间没有改变；两个 sidecar 全部保留，未删除，之后核查人未再打开数据库。

完整目录为 `D:/AI + 开源/incident-pilot/artifacts/p0-current-source-validation-20261019/checkout/eval/results/platform/access-validation-20261019/e1a-before_modification-r1/coordinator/`。

| 文件 | bytes | SHA-256 | CreationTimeUtc | LastWriteTimeUtc |
| --- | ---: | --- | --- | --- |
| journal.sqlite | 36864 | `5fc4c4ce2124727bd82ca08f63877c493540d5779e2cd0ce411439119576e234` | 2026-10-19T09:31:03.8285297Z | 2026-10-19T09:31:03.8557127Z |
| journal.sqlite-wal | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 2026-10-19T09:56:51.5001708Z | 2026-10-19T09:56:51.5001708Z |
| journal.sqlite-shm | 32768 | `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb` | 2026-10-19T09:56:51.5012216Z | 2026-10-19T09:56:51.5021700Z |

本次只新增本核查的 MD/JSON 文件，未改原始结果、journal、sidecar、ROOT 源码或发布 checkout。
