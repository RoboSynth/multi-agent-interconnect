# 此快照的来源

本目录以普通文件随团队仓库保存，当前安装使用其中的`acps-sdk`，不是Git子模块。

2026-10-19 技术方案本地增量：当前工作区已追加任务消息关联、ACL重试与清理错误保留，尚未提交或公开发布；下面的精确绑定及605项结果属于原公开快照。当前差异见[本地SDK增量清单](../../evidence/technical-plan-local-20261019/sdk-local-overlay.json)，本轮局部验证见[检查回执](../../evidence/technical-plan-local-20261019/sdk-checks.json)，不能把本地增量称作已经绑定到公开fork。

- 官方来源：[AIP-PUB/ACPs-community](https://github.com/AIP-PUB/ACPs-community)，SDK版本2.2.0；实现基线`3985c1330209f075c124669cc9d31f0e75448140`。
- 已公开贡献fork：[RoboSynth/ACPs-community](https://github.com/RoboSynth/ACPs-community)。当前SDK绑定到独立集成分支的提交[6b701c635139387ca536164226523d851b0388be](https://github.com/RoboSynth/ACPs-community/commit/6b701c635139387ca536164226523d851b0388be)，包含PR #13接续扩展、PR #14日志修复及后续持久化/进程恢复增量。
- [机器可读绑定](sdk-binding.json)保留原公开147文件的Git blob、原字节SHA256和模式；历史SDK tree为`2796a70756eba2405c108414e14b36186c188601`。该次远端分支与vendored文件精确一致，605项结果仅适用于该次源码；当前本地增量另行列明。详见[历史绑定收据](../../evidence/sdk-final-binding-20261019/README.md)。
- 官方原生代码和组件许可保留在本目录及各组件的`LICENSE`中；SDK、CLI、Registry片段使用原MulanPSL-2.0声明。
- [逐文件来源、改动行数及验证边界](../../docs/sdk_attribution_20261019.md)以团队提交`afb46e1b898faad4e5724db0cb6cf52d7d94ef81`为截止。本来源说明自身属于后来添加的元数据，不在该次SDK140文件统计内。

本目录保留了SDK以外的官方文档、规范和CLI材料，具体库存及基线差异见[第三方来源](../../THIRD_PARTY.md)。这些材料与本项目应用代码分别归属；根目录尚无覆盖整个应用的统一LICENSE。
