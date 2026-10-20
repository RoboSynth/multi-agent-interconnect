# 实验与验收记录

当前算法参照见[强基线](../docs/BASELINE.md)。本目录保存原始批次及来源绑定；成功、失败、重试、人工中断、清理恢复各按原判保存。

## 主要入口

| 类别 | 入口 | 阅读重点 |
| --- | --- | --- |
| 当前本地 60 格 | [p5-local60-r3](p5-local60-r3-20261020/README.md) | 完整终态、配对成本、失败格及人工中断后的接续 |
| 前两批本地 60 格 | [首批](p5-local60-20261020/README.md) · [第二批](p5-local60-r2-20261020/README.md) | 原始失败与验证通道问题；不直接跨批比较算法收益 |
| 云端部署 | [八阶段部署](cloud-deployment-20261020/README.md) | 当时的七身份、日志、巡检与重启验收 |
| 云端接管复验 | [四例批次](cloud-four-revalidation-20261020/README.md) | 进入故障前的基线失败与真正接管结果分开 |
| 对外体检 | [公开接入验证](public-onboarding-20261020/README.md) | 非白名单调用、文本接口与使用边界 |
| 正式平台验收 | [原 22 例](platform-acceptance-20261019) · [修复复验](platform-revalidation-20261019) | 原成功率、失败与独立业务检查 |
| 开源贡献 | [提交记录](upstream-public-submission-20261018) · [状态快照](upstream-status-20261019) | 快照不能代替当前 PR 状态 |
| 来源与许可 | [来源审计](source-attribution-20261019/README.md) · [SDK 绑定](sdk-final-binding-20261019/README.md) | 逐文件来源及各自截止版本 |

## 引用规则

优先阅读批次 `README.md`、`summary.json`、`results.csv` 和来源绑定；需要解释失败时回到对应事故原件。目录中未列在表里的批次继续按原名保存。

区分代码检查、离线模拟、同机真实业务、平台通信与新机器部署。重新运行使用新批次，不覆盖旧日志或改写统计；无法比较的批次保留不可比较标记。
