# T93 单个匿名佐证PDF开发稿

`supporting-evidence-development.pdf`将平台兼容、真实UI、访问采集、实验摘要、上游贡献准备及工程接入调查合并成12页。证据截止固定为 **2026-10-17 12:50:41.317 UTC**。这是开发稿，非最终提交版。

正文不显示学校、账号、组织身份、完整AIC或绝对文件路径。只复制匿名字段投影和一张经查看的真实UI截图，不搬运原始AMP/平台消息、数据库、环境文件、身份资料或私密日志。PDF元数据不写作者和工作目录。

## 内容

01 范围与阅读索引；02 正式三旧域兼容、两个巡检周期和新版镜像边界；03 F12真实UI；04 本地access/AMP与后台缺口；05 历史模型逐次摘要及完整工具M1负例；06 E1分段结果、负载与计时；07 MCP与scope版本边界；08 四Issue及PR草稿；09 工程接入调查和人类调研缺口；10-12 原件定位与SHA。

平台后台截图/访问曲线、公开Issue/PR与社区反馈、独立用户访谈/试用、新机器部署均未补造。正式平台仍为三旧参与域两次健康巡检，不代表新七角色、正式接管或24小时验收。历史45主格为声明组合版本，旧M1仅自由观察；完整工具M1的F01两批各一次另列。E1模型调用与token为0，17连续加1控制器续验，不宣称wire节省。

## 复现

使用原项目已有`.venv-report`（ReportLab、Pillow）和已有Poppler，未安装新依赖。项目根目录执行：

```powershell
.venv-report/Scripts/python.exe artifacts/T93-supporting-evidence-development-20261017/build.py
.venv-report/Scripts/python.exe artifacts/T93-supporting-evidence-development-20261017/validate.py
```

`build.py`仅需包内`content.json`、`data.json`和`assets/`，并使用本机已有微软雅黑字体；字体文件不随包分发。生成的是单个PDF，`validate.py`负责渲染与文本/数据/元数据检查，自动检查不代替目视。已有字体路径和Poppler后备位置是本机默认值，异机复现应指向合法安装的同类工具。

`prepare.py`是原开发项目的可选重新投影入口，需要其已闭合公开来源和冻结匿名聚合。正常重建PDF无需重新提取原件。`data.json`里的原件locator和SHA以原开发项目根目录及各自捕获时点为基准，不保证团队副本同路径存在或同字节。包内截图和正文数值是供审阅的公开派生投影，不能把SHA索引视为已公开全部原始日志。

## 文件与审阅

必要源：`build.py`、`content.json`、`data.json`、`prepare.py`、`validate.py`及`assets/f12-unknown-missing-key.png`。`validation.json`记录确切PDF摘要、逐页渲染清单、自动检查和实际目视状态。`previews/`、`extracted.txt`、`build-info.json`只用于本地QA，不纳入建议上传白名单。

`source-ready.json`仅为原项目审核清单，团队副本通过其批次清单/SNAPSHOT-MANIFEST溯源，不要求把该审核文件复制为成品。公开派生包建议位置为`deliverables/supporting-evidence-development-20261017/`。本目录不直接写团队副本、不上传或提交Git。
