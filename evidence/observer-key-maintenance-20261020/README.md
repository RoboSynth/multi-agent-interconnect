# OrderObserver 长编号修复：云端维护已完成

2026-10-20 **03:57:08 UTC** 完成单文件维护。旧 91e 镜像上只覆盖 `business/load.py`，六域已运行新镜像；Linux 离线检查、原失败形状的真实长编号 H00、正常交接、下一轮定时巡检及最终在线 / 采集检查全部通过。没有追加接管故障，前批四例的失败结果保持原记录。

## 修改与源码绑定

短编号仍使用旧规则。当创建编号加 `-cancel` 后超过 API 的 128 字符限制时，用完整原创建编号的 SHA256 生成 `loadh-<摘要>`，创建 / 取消长度为 70 / 77。保留短编号的 `load-` 前缀与摘要前缀分开；已有 pending intent 的原编号、回执查询和未知结果语义保持。

| 项目 | 实际记录 |
| --- | --- |
| 审核提交 | `67a22d8599c8a9c74027b732ffc720826477e978`，独立分支 `codex/observer-long-keys-20261020` |
| 原镜像 | `sha256:91e51b8c1c6a92ad60eeee9c67810307671d8f32e45454c94016771cecdcdac4` |
| 当前六域镜像 | `sha256:110d145f430217affeb09ed85257f59738a3c7b19509bc37905e79818ccd7d8b` |
| 原 load.py SHA256 | `4c83a52f01e883d69d6424e9719f7bdb4b3c8bfd7a709b49f6ee672910c58dfc` |
| 当前宿主 / 镜像 load.py SHA256 | `a15e87a1222906271d4ab39d68f213887f5775a856911a7dc3daa23947f9890c` |
| 当前部署 tag | `incident-pilot-new7-cloud-20261019-agent:local`，已绑定新不可变 image ID |
| 执行 helper SHA256 | `6d017626450727649e11956f12843205680b5411405741526e7f93ce1d4e9c3e` |

[构建记录](build.json) 证实 26 个指定源码文件中仅 load.py 变化，另 25 个与原镜像一致，镜像的 CMD / ENTRYPOINT / 用户等继承配置一致。[激活记录](activation.json) 证实宿主和镜像的 26 项源码 SHA 全部一致，部署清单及私密输入仍通过原严格校验，其他已有 dirty 源码未变。[补丁](67a22d8.patch) 包含 5 行运行修改和新增测试。

## 实际验证

- Windows 新增 6 项、原有 21 项离线测试通过。[回执](windows-validation.json)
- 新镜像 Linux 同输入 **27 项通过，0.275 秒**。使用真实 VerificationPartner / OrderObserver、真实 API Pydantic 模型和 MockTransport；测试为虚拟时钟，单独保留与实际 H00 的证据层级。[完整输出](linux-tests.txt)
- 使用原基线失败的 **117 字符 run_id** 真实访问当前订单业务，**30.002 秒 / 30 次成功 / 10 个完整创建→查询→取消流程**，failed / unknown / unresolved 全为 0。实际创建键 70、取消键 77 字符。[原始 H00](long-run-h00.json)
- 两个独立 systemd 构建 / 激活单元均退出 0、Result=success；过程不依赖本机聊天或 SSH 连接维持。[回执](systemd-result.json)

## 交接、巡检和采集

复用原七身份及统一 control / leases，旧主管正常关闭六域并释放租约后才更新同一源码文件和镜像 tag。H00通过后归还身份，同 host session `ac07184a92394a15bddc43bd7e14a0bb` 恢复六域。

| UTC 时间 | 实际事件 |
| --- | --- |
| 03:51:39.419 | 请求正常空闲交接 |
| 03:51:44.275 | 原主管确认暂停 |
| 03:52:26.447 | 正常归还并恢复巡检 |
| 03:57:02.744 | 恢复后的首轮定时 inspect completed，耗时 35.537 秒 |
| 03:57:08.206 | 最终核验完成 |

[时间线](maintenance-timeline.json) 保留计划维护窗口。最终 [runtime snapshot](runtime-after.json) 的 11 项检查均明确为 true：三服务 active / enabled、host running、主管 PID 一致、正式连接、资源凭据 0、模型关闭、七身份在线、600 秒巡检、自动故障审批关闭和原采集器运行。

原采集器 ID、启动时间、offset 卷及 42 行 offset 标识 / inode 保持；七个日志源和只读子目录一致，没有 offset 倒退，**39 行进度继续增加**。[维护前](collector-before.json)、[维护后](collector-after.json)、[汇总检查](activation.json) 保存原始数据。未清空 offset 或请求历史补发。

这是一次实际计划内暂停，不能把跨此窗口的记录拼成 24 小时无中断运行。前批“观察后中断 / 修改前中断”仍是尚未完成的真实接管复验；本次正常业务 H00不替代它们。

## 取回与开发状态

本目录 14 个云端原始证据文件已取回，归档 SHA256 为 `e522fa8aff8d64b02ade1727b0ada801e4247640aa9dbda55f67be1f2608bdf7`，13 项内容 SHA 核对通过，见 [export manifest](export-manifest.json)。原云证据位于 `/opt/incident-pilot/evidence/observer-key-maintenance-20261020/`；旧源码与 91e 镜像均保留供必要恢复。

云端已使用审核补丁中的load.py；维护期间canonical产品源码因P5实验冻结而未合入。本轮60格完成、最终健康与停机确认后，原审核提交`67a22d8`已通过`9157415`合入开发分支；[合并后47项组合检查](../highscore-continuation-20261020/integration-validation.json)通过。云端上线、源码合并、旧两例接管仍待复验分别留证。
