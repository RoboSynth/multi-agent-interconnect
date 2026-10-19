# 当前 SDK 测试整合与完整验证（2026-10-19）

以团队源码 `613ecbfc6e7500a30264bfec3c702d17152f0b6a` 为起点，当前 vendor 已补齐两个公开 PR 中此前遗漏的排序/并发测试，并采用两 PR 共有的 MetricsEmitter 可移植性修正。SDK 产品源码保持原字节一致。整合后的完整 SDK 测试树在隔离副本实际运行：**605 项收集、605 项通过，pytest 和执行器均退出 0**，用时约 40 秒。

## 三份测试的来源

| vendor 内路径 | 原件提交 | SHA256 |
| --- | --- | --- |
| `acps-sdk/tests/aip/test_task_ordering.py` | [PR13 head 09fe13b](https://github.com/RoboSynth/ACPs-community/blob/09fe13bd699f4a9df279507ed23861f6f817babe/acps-sdk/tests/aip/test_task_ordering.py) | `cd8573acaac6a0b754039dc63b619aaf1496997f4332cd331f0725012c674411` |
| `acps-sdk/tests/amp/test_message_emitter_concurrency.py` | [PR14 head 72a994b](https://github.com/RoboSynth/ACPs-community/blob/72a994bfb8cd5cc832beb0204a4715a2c090f983/acps-sdk/tests/amp/test_message_emitter_concurrency.py) | `12c4eb6a6879da7932cc29eb1b3b4a32d4dffe6f030549f83d87348f92806136` |
| `acps-sdk/tests/amp/test_amp_metrics_emitter.py` | [两 PR head 内容一致](https://github.com/RoboSynth/ACPs-community/blob/09fe13bd699f4a9df279507ed23861f6f817babe/acps-sdk/tests/amp/test_amp_metrics_emitter.py) | `559812c1ed5bc2bad5c381e3a0a64c38664f75a8216d7136bb49666d20265e09` |

排序测试覆盖迟到 working 不覆盖实际 awaiting-completion、真正较晚 continue 可回到 working，以及持久记录保留迟到事件但不回退终态。并发测试覆盖同一 sink 的相对/绝对路径、混合同步/异步实例、不同文件并发、schema/trace 保留、写入异常后锁释放。Metrics 测试改用临时普通文件阻挡父路径，避免对根目录权限作跨平台假设；Emitter 本身没有改变。

三份原件均从本机已保存的精确 Git blob 读取，原件 worktree 与 blob 字节一致，复制后的字节再次核对。完整清单覆盖整合后 **147 份 SDK 文件**；[当前源码清单与运行回执](../evidence/sdk-test-integration-20261019/README.md)将本次结果绑定到全部源码和测试。

## 本次检查实际覆盖什么

一次完整执行 `acps-sdk/tests`，保留原生测试和集成测试，包含可接续、排序、MessageEmitter、durable access 和 coordinator 进程恢复。依赖采用已有的独立 36 包冻结环境；关闭无关插件自动加载，显式启用 pytest-asyncio 与 AnyIO，不按测试名或标记过滤。

官方 TLS 测试在导入期需要 SDK 同级 demo 目录的 8 份证书/密钥文件。运行时在临时副本复用既有生成器创建 synthetic CA 和 3 张 leaf，保留官方测试原文；真实监听仅为 `127.0.0.1` 随机临时端口。MQ、Registry 和 OIDC 路径使用 fake、MockTransport、ASGI 或内存实现。进程恢复测试只操作自身创建的临时 Python 子进程和 SQLite。

源码与临时 TLS 夹具的测试前后哈希一致，已加载 SDK 模块全部来自这棵隔离副本。唯一 warning 是 pytest-asyncio 插件已导入，不能进行 assertion rewrite；全部 call/setup/teardown 通过。生成的私钥留在本机测试副本，证据中仅保存证书/公钥摘要及文件哈希。

605 是这一次当前组合套件的实际数量。旧 PR13 的 581 项与 PR14 的 558 项共享 553 项，本次结果不与其相加，也不与此前 durable17、coordinator2 单项记录重复累计。

## 一条命令复现

按[SDK 检查入口](../tools/sdk-suite/README.md)准备独立 Python 环境后，在仓库根目录执行：

```text
python tools/sdk-suite/run_sdk_suite.py --repo-root . --output ../sdk-suite-run-01 --python .venv-sdk/Scripts/python.exe
```

入口复制当前完整 SDK、生成临时 synthetic TLS 并运行全部测试，不必手工拼接原开发机的 artifact 路径；输出目录必须为新目录。`--python`也可指定自己的既有环境；Linux 的 venv 路径为`.venv-sdk/bin/python`。

[可移植入口的两次验证](../evidence/sdk-suite-reproducer-20261019/README.md)各自实际605/605、0 warning；修复后的入口另在独立复制仓库及其内部36包venv上通过，147份源码前后相同。两次和本页原605结果不重复累计。两份已验证程序保持原字节，其他操作系统尚未实测。

## T01 边界

这次补齐 vendor 测试树并给出当前组合 SDK 的完整本地验证。当前 vendor 仍包含两 PR 及较新的 durable access/coordinator 扩展，不能称为任一单独 PR 的 checkout。T01 的最终 fork 集成提交与 vendor 绑定、AtomGit 镜像及上游 CI 尚未完成。平台 fault、Monitor 入库、正式七身份重新连接及长期运行也不由这组本地测试证明。

[此前 SDK 来源截面](sdk_attribution_20261019.md)继续以 `afb46e1` 为截止保留；其 140 文件/行数统计不改写为当前 147 文件。历史验收失败和缺失 access 记录也保持原有结论。
