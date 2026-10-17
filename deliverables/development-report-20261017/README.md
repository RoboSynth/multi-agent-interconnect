# 技术报告开发稿

13页、匿名、非最终提交版。只使用闭合结果；新E1-a/b为17例连续完成、1例控制器中断后续验，最终与独立核验均18/18，明确分段执行。正式平台仍为三个旧参与域partial，旧模型M1为观察选择版，M2更慢的结果保留。

**证据截止：2026-10-17 11:41:43 UTC（E1闭合）。不包含之后启动的完整工具M1 pilot；报告中“尚无真实故障对比”等描述均以此截止范围为准。**

本目录只包含编排内容源、匿名聚合指标、生成器、PDF及其渲染/检查产物，不含资源env、身份资料、原始AMP、运行日志或数据库。

在项目根目录使用已有环境执行：

```powershell
& .\.venv-report\Scripts\python.exe artifacts\technical-report-draft-20261017\build.py
& .\.venv-report\Scripts\python.exe artifacts\technical-report-draft-20261017\validate.py
```

依赖既有ReportLab、Pillow、Windows微软雅黑regular/bold及Poppler。字体仅嵌入PDF子集，不分发字体文件。没有自动安装或外部调用。`validate.py`只渲染和检查，视觉审阅记录须在看过最新预览后填写。

- `content.json`：13页结构、文字、表格；第10页按闭合E1独立核验更新，保留续验与计时边界。
- `evidence.json`：闭合模型与E1的匿名聚合值和来源SHA256，不复制逐事故原始日志。
- `build.py`：固定页框与矢量架构/状态/指标图，发现布局溢出立即失败。
- `validation.json`：最终PDF摘要、13页渲染、七章/方法边界/匿名扫描及视觉审阅状态。
- `previews/page-01.png`等：最新逐页预览；`contact-*.png`为全页版式检查缩略图。

关键审阅页：04架构信任域、06操作状态、09历史模型负面结果、10E1分段结果、11平台边界、13证据索引。原始28组素材映射见相邻`report-preparation-20261017/inventory.json`；该盘点早于新E1闭合，最新E1以本稿evidence.json的来源摘要为准。
