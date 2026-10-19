# 技术报告开发稿 · 第三修订（2026-10-19）

证据截止固定为 `613ecbfc6e7500a30264bfec3c702d17152f0b6a`。本稿 15 页，保留七章、三项创新、源码原文片段、信任域、来源和限制，新增两批 E1-b 图及本地持久化、协调者恢复和停止入口补证。

原正式 22 例为 18 通过、4 失败；独立复验 12 例为 11 通过、1 失败，两批版本与分母分列。原 T05 缺 18 条、新批缺 12 条，均保留失败；新批 T62 在已捕获材料的检查范围内为 true。新批每例恢复、H00、六域闭组均通过，不据此改判失败。

Durable Access 17 项、原群组 8 项、AMP 接入 20 个不同方法、T30 新 2 项及原相关 1 项、native stop 6 项按各自范围记录。本地修复尚未部署到正式平台镜像，命令 fixture 不代表真实全栈启动或停机。报告不包含截止提交之后的运行器与停机改动。原稿和第二修订保持原字节，本稿不是 T90 最终提交版，也不含 PPTX。

## 复现

在仓库根目录使用 `requirements-report.txt` 对应环境，依次运行：

```powershell
python -X utf8 deliverables/development-report-20261019-revision3/build.py
python -X utf8 deliverables/development-report-20261019-revision3/validate.py
```

需要 Windows 的微软雅黑、Consolas 与 Poppler（`pdfinfo`、`pdffonts`、`pdftotext`、`pdftoppm` 应在 PATH）。生成器复用 [原布局](../development-report-20261017/build.py)，图像来自 [已发布 E1-b 证据](../../evidence/e1b-comparison-20261019/)。不需要访问平台或启动业务。

[evidence.json](evidence.json) 绑定固定提交的 72 个输入与源码节选；校验同时检查实际使用的布局和两张图像字节。[build-info.json](build-info.json) 绑定 PDF 与生成输入，[validation.json](validation.json) 记录 24 项自动检查，[visual-review.json](visual-review.json) 记录实际逐页检查及预览 SHA。[artifact-manifest.json](artifact-manifest.json) 列出发布文件 SHA。[material-scan.json](material-scan.json) 记录文本、PDF 属性与 XMP 的有界扫描。[content-review.json](content-review.json) 记录结论口径与旧报告保留检查。

预览 PNG 和文本提取是本地忽略的中间文件；重新构建或校验后需按新 PDF 字节重新完成视觉检查。材料扫描范围不替代最终的学校、教师、provider 词表及视频、截图审查。平台日志入库、独立新机器 T11/T96、24 小时窗口、最终来源绑定和正式材料仍待验。
