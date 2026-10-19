# T63 稳定性组合报告

状态：独立实现、必要测试、真实短窗口示例和补丁应用检查均已完成，可交由主工作副本合并；本包未自行修改主仓库、正式验收源码或 GitHub。发布清单是 `publication-files.json`：34 个带 SHA 的文件加清单本身，共 35 个文件。其输入以本包为根，目标路径以团队仓库为根；`checkout/` 依赖、临时目录与旧版图不在发布清单内。

基于团队提交 `3760b21c8a1ed62e8119925da6f24ebd8b851d14` 的独立工作副本。可应用改动只有三份文件：新增 `eval/stability_bundle.py`、新增 `tests/test_stability_bundle.py`、扩充 `docs/stability_report.md`。旧 `summarize`、原CLI与原JSON保持原字节。

`t63-stability-bundle.patch` 可应用到该提交；`checkout/`包含源文件和必要基线。补丁不包含已有真实日志、环境配置或私钥。采集输入、测试与示例的哈希和结果见`delivery-manifest.json`、`validation/result.json`、`real-example-r3/source-bindings.json`。

## 当前实现

- 只读固定窗口AMP，复用原统计；显式读取原生scheduler JSONL和最终coordinator incident JSON。
- 按run_id配对巡检/演练，保留缺端、跨事故、逆序和冲突；不从观察事件推算期望调度覆盖率。
- 单独统计coordinator任务的真实elapsed_ms，保留失败/未知效果任务计时；不从AMP或整场事故时长补任务耗时，也不把含审批等待的计时叫纯网络RTT。
- 输出JSON、四个CSV、PNG/SVG及SHA清单；未知数值写unknown，输入前后哈希变化则拒绝，已有输出目录不覆盖。

## 真实短窗口示例

`real-example-r3/`使用**已有同一次运行**的九个冻结原件：七份heartbeat、原生scheduler事件及首轮最终incident。原件SHA与已发布的heartbeat窗口/first-cycle来源绑定一致。示例公开输入只保留必要字段，替换身份/任务/事故标识，保留精确时间、状态和时长；完整映射规则和raw→projection SHA在`source-bindings.json`，原始材料未改。

窗口是2026-10-18 UTC `[06:55:21,07:25:21)`，30分钟；七身份840/840采样槽、一次巡检报告completed、六个任务实测耗时，median1531.5ms、p9531875ms。scheduler报告的39.094秒来自事故elapsed_seconds，不是事件墙钟差。输入没有演练和AMP access，因此相应结果是unknown，不能写为零延时、演练通过或关闭。该示例不证明连续在线率、24小时/7天、官方入库或生产验签。

在应用补丁后的仓库，可以直接复用匿名输入生成到另一个新目录：

```powershell
python eval/stability_bundle.py <本包>/real-example-r3/inputs/amp --output <新目录> `
  --window-start 2026-10-18T06:55:21Z --window-end 2026-10-18T07:25:21Z `
  --expected-aic A1 --expected-aic A2 --expected-aic A3 --expected-aic A4 `
  --expected-aic A5 --expected-aic A6 --expected-aic A7 `
  --scheduler <本包>/real-example-r3/inputs/events.jsonl `
  --coordinator <本包>/real-example-r3/inputs/incident.json
```

图形沿用项目现有Matplotlib/Agg；本机使用已有`.venv-report`，没有联网安装。`generate_real_example.py`只是从已有原件生成匿名示例的本地准备助手；正常复现不需要访问未公开原件。

## 验证与保留记录

31个不同相关方法有通过证据：原20方法在本轮最初相关套件实际通过，最终新11方法实际通过；不把多轮重复相加。新增边界包括缺数据、重复/冲突快照、来源变化、不同测量口径、窗口、非法时长、同run跨事故/结束逆序和输出不覆盖。当前PNG已实际打开检查，文字、unknown、轴与median/p95图例清晰，SVG为同一Figure的矢量输出。

首轮测试的TEMP落在不可访问沙盒目录，45个setup/cleanup错误均保留为失败；随后只为子进程设置本包可写TEMP，不修改系统配置。首轮示例准备把真实keep_awake事件误当多余事件而断言失败，部分投影和当时助手均保留；修正只影响本地准备助手。`real-example-r2`是上版图，最终使用`real-example-r3`，旧产物不覆盖。

本任务只做文件分析、合成测试和静态图，没有启动服务、平台身份、故障或模型。T07真实24小时窗口、官方Kafka/Monitor和独立新机器验收仍需各自运行证据。

最终只读审阅已对照该提交的八份真实 Git blob，检查九份示例投影与摘要的来源 SHA、七份报告产物 SHA 及 CSV unknown 值；PNG 已实际打开。补丁在一次性隔离目录通过 `git apply --check`，应用后三份目标文件与已测源码原字节一致。此阶段复用已有 31 个不同方法的通过记录，没有重跑测试。`finalize_delivery.py` 是本包一次性交付准备记录，重复运行会因隔离输出目录已存在而停止；队友正常使用上面的报告入口即可。
