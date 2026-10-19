# 2026-10-19 P0 开发与离线检查

基线提交为 `5267a3a4a47aeb0188df4894031cf18c240667ba`。本轮实现与操作入口见 [继续开发说明](../../docs/p0_continuation_20261019.md)；全部检查使用合成输入、临时账本及资源 IO 模拟，尚未执行新的正式故障批次。

| 范围 | 本轮有效检查 | 记录 |
| --- | --- | --- |
| 正式 E1 三中断点、原任务/operation/fence 和 E1-b runner 集成 | 42 项通过 | [根检查](root-checks.json)、[测试原始输出](e1-runner-tests.txt) |
| 正式交接信息、实际发送字节、备用摘要确认及 TTL | 6 项通过 | [helper 收据](e1-handover/source-ready.json)、[详细结果](e1-handover/checks.json) |
| F12 显式目标、proxy 归属、精确复原及旧 target 兼容 | 24 个不同方法通过，包含 3 项更新检查及 21 项有效复用 | [目标修订2](f12-target/source-ready-v2.json)、[检查](f12-target/offline-checks.json) |
| F12/E5 协调器、原键验证、真实 Bridge/账本/route 工具链与相关回归 | 新入口 15 项、相关回归 19 项通过 | [源码收据](f12-runner/source-ready.json)、[不同方法清单](f12-runner/verification.json) |
| 部署第四端口与旧三端口配置兼容 | 13 项通过 | [根检查](root-checks.json) |
| 合成 ACS 样例、mapper、报告和图表 | 23 项通过，0 跳过 | [环境修订2](test-env/source-ready-v2.json)、[ACS](test-env/acs-results.json)、[报告](test-env/reports-results.json) |
| 全新单一开发环境安装 | 创建、安装及 pip check 均退出 0；10 个依赖模块归属新环境；8 个已覆盖方法复验通过 | [安装](test-env/dev-environment/installation.json)、[环境验证](test-env/dev-environment/verification.json) |

全新环境的 8 项复验、E1 早期 33/35 项和 F12 早期 6/14 项属于重复或先前版本，不与当前组数累加。这里只执行本轮受影响检查；队友旧全仓测试中的时序、权限等失败记录仍保留在原 [部署反馈](../../deploy-check-record.md)。

[当前源码集合](source-manifest.json)记录 160 个 evaluator/domain/SDK 等有界源文件的原字节 SHA。它属于新开发修订；真实执行仍须绑定实际镜像、完整私密配置、独立目标和对应授权。旧 E1 revision3、旧冻结输入、旧 18/45/45 批次及未决订单保持各自历史结果。

本目录保存了缺 ACS 文件的基线失败、受限执行器 TEMP/异步初始化中断，以及有效正常执行器结果。环境阻断没有冒充产品行为失败；有效通过也没有覆盖原始失败。原始安装和完整辅助运行日志保留在开发机 `artifacts/p0-continuation-20261019/`。

本轮实际新增了离线代码和一个开发虚拟环境。没有据此宣称真实 AMQPS 主备接管、F12/E5 故障效果、远端 ACL 库存、E1-c 旧主同进程复活、新机器部署或长期运行已通过。
