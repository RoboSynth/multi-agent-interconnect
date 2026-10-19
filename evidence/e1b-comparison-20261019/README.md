# E1-b 三方法分批对照图与 CSV — 2026-10-19

本目录从 canonical `d8ae1958aef411c61742f57ddb96e0de453ec885` 已发布的两份冻结 summary.json 投影数据，不运行服务或实验。原 22 次的结果仍为 18 通过 / 4 失败，新 12 次仍为 11 通过 / 1 失败。本图只取每批各 9 次 E1-b，保留批次、源码引用、镜像和各自分母。

| 批次 | from_scratch | full_history | resume_package |
|---|---:|---:|---:|
| original22 的 E1-b | 3/3 | 0/3 | 3/3 |
| new12 的 E1-b | 3/3 | 2/3 | 3/3 |

这些是各单元 3 次的描述性观察，不作合并成功率、显著性或方法优越性结论，也不改写原失败。图表可供技术报告 T61/T90/T93 引用，不能单独代替这些任务的完整验收。

## 交付文件

- [e1b-cases.csv](e1b-cases.csv)：18 行逐例数据，保留 frozen_state、真实退出码、计划 SHA、准备大小、完整 IFC 发送/确认大小与 digest、子对象大小、剩余流程时间、额外观察、数据库 wrapper 计数及模型用量。
- [e1b-method-groups.csv](e1b-method-groups.csv)：6 行方法分组，包含每批每方法的通过分母，各数值字段的有效 n、最小值、中位数、最大值。
- 原批：[PNG](e1b-original22.png) / [SVG](e1b-original22.svg)；复验：[PNG](e1b-new12.png) / [SVG](e1b-new12.svg)。PNG 为 2720 × 1120，SVG 为矢量导出；英文图中文字采用已有 DejaVu Sans，避免字体缺字。原包 PDF 保留在本地，本次发布选择 PNG/SVG/CSV/JSON/MD/PY，不发布 PDF。
- [build_e1b_comparison.py](build_e1b_comparison.py)：可复现脚本。复用 [eval/plot_results.py](../../eval/plot_results.py) 的 Matplotlib Agg、每次散点、范围/中位数和 PNG/PDF/SVG 导出方式；原工具的数据模型属于 scheduling matrix，不能直接当作 E1-b 输入。
- [source-hashes-and-data.json](source-hashes-and-data.json)：原始生成记录，含两份输入 SHA、语义来源文件 SHA、原生成脚本 SHA、绘图库版本和完整分组数据；保持原字节。
- [render-check.json](render-check.json)：原始 PNG 视觉检查记录、文件哈希和最小数据核查，保持原字节；发布图像选择及 PDF 排除见映射记录，不改原检查或 PDF 哈希。
- [publication-projection.json](publication-projection.json)：原包到仓库发布副本的文件清单和 SHA 映射。仅脚本默认入口与 README 链接/复现说明有适配，原始数据、图像和检查记录逐字节保留。原始生成记录中的 generator_sha256 对应适配前脚本；映射记录另列当前发布脚本 SHA。

## 字段口径

| 项目 | 来源字段 / 限制 |
|---|---|
| 冻结通过/失败 | `cases[].state`。脚本交叉检查已通过行的终态、退出码、task phase、六项 close、恢复/H00、业务验证、journal 及确认；失败不会因恢复健康而变为通过。 |
| 准备大小 | `result.prepared_handover_metrics.resume_ifc_payload_utf8_bytes`；仅本地序列化，不证明发送，未画入发送曲线。 |
| 完整 IFC 捕获发送大小 | `result.captured_resume_send.sends[0].resume_ifc_text_utf8_bytes`；要求唯一匹配发送、目标/operation 匹配且无 parse error。记录点在 publisher 返回之后，不单独证明替代方确认。 |
| 完整 IFC 替代方确认大小 | `result.acknowledged_handover_metrics.native_transmitted_ifc_text_bytes`；与捕获发送的完整文本 SHA、字节数及 handover SHA 分别绑定。 |
| IFC 字节范围 | 完整 IFC 文本 UTF-8 字节，含实际序列化 args；不是外层 AIP/MQ/TLS 网络开销，也不是仅 handover 子对象。图用 KiB，CSV 保留原始 bytes。 |
| 子对象与重复表示 | `handover_information_utf8_bytes` 单列。当前 resume_package 同时位于 `args.resume_package` 和 `args.handover.package`，完整 IFC 大于 full_history；不能称作传输压缩或字节节省。 |
| 剩余流程时间 | `remaining_workflow_including_verification_seconds` 在 `verify_handover` 返回、确认接管之后开始，包含后续 pool rebuild 与约 30 秒业务验证；不是故障→接管、端到端恢复或独立 H00 时间。图时间轴为 30–36 秒，并显示有效 n。 |
| MCP 计数 | `mcp_operation_counts.operations[]` 为本 experiment/incident 的 primary/backup 数据库 modifying wrapper invocation/return，收集于后续 remaining workflow 之前；不包括后续应用 pool rebuild、查询、验证的总调用，不能解释为物理资源修改次数。 |
| 模型用量 | 18 行的 model_calls/model_tokens 均为源记录的 0，本批是固定无模型执行，不能据此声称“省 token”。没有使用子对象 bytes/4 估计充当 tokenizer 或模型实际 tokens。 |
| 缺失 | CSV 空单元格、JSON null，统计仅计有效 n；不以 0 填补未捕获发送、未确认或未完成计时。真实 `matching_resume_sends=0` 保留在其计数字段，但不产生 0-byte 发送。 |

原批 full_history 的三次失败均捕获到完整 IFC 发送（18164/18168/18168 bytes），但没有替代方确认、剩余流程计时及数据库 wrapper 计数。新批 full_history-r1 尚未发送接管消息：matching_resume_sends 为 0，其准备/发送/确认字节及剩余计时仍为缺失；r2/r3 为通过。四例失败均保留 TimeoutError。

其余 14 个通过行的发送大小与确认大小一致，数据库 wrapper invocations=returned=1。成功 from_scratch 额外观察为 1，其余成功方法为 0；这是当前固定流程观察，不延伸为总成本结论。

## 来源与复现

输入相对 canonical checkout：

- [原批 summary.json](../platform-acceptance-20261019/summary.json)，SHA-256 `02d8550cecdb2d4fe7a93918802487686d0809757c9d56e28b100c521ce8a60a`；该 summary 的 current_checkout_commit 为 `c1c09e569ef67b7f0f0c2b2e8a948afec53f0c31`，镜像 `ccc35272ab40…`。
- [复验 summary.json](../platform-revalidation-20261019/summary.json)，SHA-256 `d2e9f7ee61df106f10e15f7582e2e7ec5b47e1b3d4c32e0af33e4c56e17a8de1`；frozen_source_commit 为 `c75554d6b6de3bdaba53677e678a6fd35e4fef80`，镜像 `f7e91b059a7b…`。

原批 current_checkout_commit 是 summary 中的源码引用，复验 frozen_source_commit 是其冻结提交字段；不将两者当作同一实验版本。每批的镜像、prepared source map/summary SHA 可在原 summary 查询。

语义定位：[platform_resume_experiment.py](../../eval/platform_resume_experiment.py#L557)（557 行数据库 wrapper 收集，799 行确认接管后起计，818 行 remaining 计时结束）；[platform_handover.py](../../eval/platform_handover.py#L87)（替代方确认）；[handover_experiment.py](../../eval/handover_experiment.py#L82)（完整 IFC/子对象/重复 package 与字节估计）；[发布 collector](../platform-revalidation-20261019/tooling/collect_results_v4.py#L122)（三阶段投影）。这些源码仅用于解释字段，不替换两份冻结结果。

使用 Python 和 [requirements-report.txt](../../requirements-report.txt) 所列报告依赖（Matplotlib 3.11.2）。在仓库根目录、已配置的开发虚拟环境中执行：

```powershell
python evidence/e1b-comparison-20261019/build_e1b_comparison.py
```

默认 source-root 由脚本位置定位到当前仓库；输出到仓库旁的 `<仓库目录名>-e1b-reproduced-20261019`，保留已发布证据。也可显式指定一个仓库外的新目录：

```powershell
python evidence/e1b-comparison-20261019/build_e1b_comparison.py --output ../e1b-reproduced-20261019
```

脚本校验两份冻结输入 SHA 和 3 方法 × 3 重复矩阵，输出目录必须在输入 checkout 以外。CSV 数值与图中内容可复现；SVG/PDF 的生成时间或内部 ID 可能随重新导出变化。新生成的 source-hashes-and-data.json 将记录当前发布脚本的 SHA，而本目录保留原生成记录。旧源文件、旧结果与失败记录保持原件。

## 建议报告图注

原批：E1-b 三种信息交接方法的原批冻结观察（每方法 3 次）。from_scratch、full_history、resume_package 分别通过 3/3、0/3、3/3。完整 IFC 捕获发送与替代方确认分列，full_history 的三例失败保留发送量但缺少确认与剩余流程计时。

复验：独立复验批的 E1-b 观察（每方法 3 次），通过数分别为 3/3、2/3、3/3。full_history-r1 在发送接管消息前失败。时间从确认接管后起计，包含约 30 秒业务验证；两批的源码/镜像不同，未合并估计，缺失测量未补零。
