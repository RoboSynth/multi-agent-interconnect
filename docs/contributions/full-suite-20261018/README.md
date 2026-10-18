# 完整官方 SDK 本地测试与测试可移植性修正（2026-10-18）

两个公开 draft PR 已分别完成整个 `acps-sdk/tests`（含已有 integration 与新增组件）：接续分支581/581、日志分支558/558，实际pytest及外层退出均0。两套测试共享上游用例，不能相加为1139个不同检查，也不再加上此前3/5个组件结果。每套保留1条PytestAssertRewriteWarning；未执行上游CI，未声明合并。

[PR #13](https://github.com/AIP-PUB/ACPs-community/pull/13)当前head为`09fe13bd699f4a9df279507ed23861f6f817babe`、14文件；[PR #14](https://github.com/AIP-PUB/ACPs-community/pull/14)当前head为`72a994bfb8cd5cc832beb0204a4715a2c090f983`、3文件。两次正文PATCH200与随后GET200均逐件核对，均为draft、未合并，没有另发PR、Issue或评论。见[当前公开状态](../../../evidence/upstream-public-submission-20261018/followup.json)；[最初六项提交快照](../../../evidence/upstream-public-submission-20261018/submission.json)完整保留。

两份首次完整suite分别580/581与557/558，均仅失败未修改上游的`test_emit_sync_write_failure_only_warns`：它假定根目录路径不可写，提升权限后的Windows却真实写入成功。修正只改[这一测试](metrics-test-portability.patch)，在测试自己的临时目录内放置普通文件作为父路径阻塞，触发真实文件系统错误，保留原caplog断言并检查阻塞文件未改、日志未生成；未mock发射器、未改产品、未跳过用例。两候选SDK源差集严格1文件，收集nodeid前后相同，setup/call/teardown全部通过，JUnit失败/错误/跳过均0。公开提交源字节与已测试候选逐件一致，提交后未重复跑相同输入。

[独立安全摘要](../../../evidence/upstream-sdk-full-suite-20261018/summary.json)按原件SHA绑定完整结果与JUnit，并分开保留：首次两suite失败、默认工作区权限/TLS探测受控终止、自有clone包装失败、依赖安装ambient警告及402字节/2行纯测试根目录输出的归档清理。权限探测不是一套完成的suite，也不推断为产品失败；原失败和警告未覆盖。无需读取私钥、证书正文或原始traceback即可复核该摘要。

复现使用官方`uv.lock`固定的[直接依赖](locked-requirements.txt)与[约束](locked-constraints.txt)，独立target的36个distribution/43条活动依赖核验问题0。fresh venv不启用system site；仅载入该target、当前SDK与标准库，显式pytest-asyncio/AnyIO插件、关闭自动插件载入，AnyIO4.13可用后端仅asyncio。整个tests未加`-k`、`-m`或ignore。真实HTTP集成仅使用临时loopback TLS端口、合成测试证书；AMQP/OIDC使用已有fake/mock，未接入真实NEW7身份或服务。

`review-code/`四份`.py.txt`是实际准备/执行工具的原字节审阅副本，不是直接运行入口：[初始树与合成TLS准备](review-code/prepare_suite_trees.py.txt)、[原完整suite](review-code/run_original_full_suite.py.txt)、[一测试候选准备](review-code/prepare_metrics_candidate.py.txt)、[修正后完整suite](review-code/run_metrics_full_suite.py.txt)。它们保留当时的固定提交、源SHA和本地artifact布局守门；新机器应重新准备公开checkout、独立依赖与短期测试TLS，不复用开发者本机私密材料。证书/私钥、venv、安装目录、原始安装报告与凭据客户端均未打包。

这组本地测试不代替正式NEW7 E1故障接管、24小时/7天运行、Kafka/Monitor入库或上游CI。T06另见[本机采集准备](../../../deploy/fluent-bit/README.md)：13个不同Python离线检查及PowerShell解析通过，未启动真实采集器，外部Kafka/Monitor仍待配置和验收。
全新检出运行项目T06离线测试前，在项目根先执行 `New-Item -ItemType Directory -Force artifacts | Out-Null`；只创建测试临时目录，无需启动服务。
