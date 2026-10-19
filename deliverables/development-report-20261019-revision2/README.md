# 技术报告开发稿 · 第二修订（2026-10-19）

证据截止 `412f791ac8c4ef35217dca60d512c967c6b0d54e`。本稿新增信任域、准确 SDK 来源对照、三项创新原文片段与局部时序，以及 Windows、E2-c 和访问缺端补证。12 次新复验运行中，未纳入本稿，也不预判其结果。

旧报告和原实验保持原字节。原 22 例为 18 通过、4 失败；原 T05 严格对账未通过。平台日志入库、新机器、长期窗口和正式材料尚未完成，本稿不是 T90 最终提交。

复现：使用仓库 `requirements-report.txt`，先运行同目录 `build.py`，再运行 `validate.py`；Windows 需微软雅黑、Consolas 与 Poppler。布局直接复用相邻 `development-report-20261017/build.py`。`evidence.json` 绑定输入与原文片段，`build-info.json` 和 `validation.json` 绑定最终 PDF 与本次渲染；`visual-review.json` 只记录实际逐页检查。

预览 PNG 与文本提取保存在忽略的本地中间目录。PDF、正文、来源和检查记录供团队协作；尚无资料支持的门槛继续标为待验。正文与有限身份模式检查不等于完成全部学校、教师、provider 匿名审查。
