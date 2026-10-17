# 提交材料的有界匿名检查

在项目根目录执行：

```powershell
python -m eval.material_scan path/to/report.pdf path/to/script.md --output output/material-review/results.json
```

PDF需要现有Poppler的`pdftotext`和`pdfinfo`在PATH；也可用`--poppler-dir`指定其目录。入口读取明确列出的文件，检查PDF提取正文、文档属性和XMP，以及UTF-8文本材料。支持Markdown、TXT、JSON/JSONL、YAML和CSV。原件不修改。

默认规则覆盖院校通用词、待赛方确认的身份命名空间、用户目录、电子邮件和已有凭据模式。实际学校简称、指导教师姓名及ACS provider名称应逐项通过`--forbid-term`补充。命中只记录类别和来源区域，不回显匹配正文或个人信息。缺文件、不支持格式、缺提取工具或无可提取文字的PDF均报告错误，不作为零命中通过。

`machine_checks_passed`仅代表列出文件及规则的自动检查通过。它不证明全部提交材料已匿名：校徽和截图须逐图检查；PDF附件、视频、未生成的最终材料以及未提供的个人名称未覆盖。最终PDF仍需按确切SHA查看全部渲染页面，视频需逐镜头检查；这些记录与本检查结果一起保存。当前不需要答辩PPTX，本入口不添加PPTX生成或检查依赖。
