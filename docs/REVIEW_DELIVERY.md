# 匿名评审交付

默认启动入口已合入 `main`：Linux 使用 `bash deploy/up.sh`，Windows 使用 `pwsh -File deploy/up.ps1`。带显式部署清单的原入口继续可用。

## 导出范围

`deploy/review-package.json` 是明确的文件清单。代码只导出其中列出的源码、测试、部署脚本、配置样例和必要文档。佐证只选择：

- `cloud-deployment-20261020`
- `cloud-four-revalidation-20261020`
- `p5-local60-r3-20261020`
- `public-onboarding-20261020`
- `upstream-public-submission-20261018`
- `upstream-status-20261019`
- 明确列出的评审版验收文件及本次集成测试结果

佐证不复制 `research/`、`docs/`、`deliverables/` 或 `baselines/`，不递归复制工作目录中的虚拟环境、数据库或未跟踪日志。

## 匿名化与来源

`tools/package_review.py` 读取本机私有词表，替换身份名称、团队账号、用户目录及工作目录前缀；能力描述的 `provider.name` 统一为 `Incident Pilot Project`。词表不随匿名交付包分发，清单只记录类别、数量和词条指纹。

它检查文本、Unicode 转义、URL/HTML 转义和图片文本元数据。图片还要求有对应 SHA256 的人工查看记录；没有记录、存在不支持的二进制格式、残留命中或读取错误时停止打包。

原始文件保留在仓库，交付文件是匿名化副本。每个文件同时记录原始与交付 SHA256；JSON 数值与真假值逐项比较。统计结果不得因匿名化改写，历史摘要中的哈希仍指原文件，不能拿它直接校验匿名副本。

上游许可证和著作权声明保留。官方仓库和官方 PR 的公开链接可以保留；团队来源链接匿名化后使用占位或文字说明，不伪装成可访问的新仓库。

## 执行

先通过相关测试，提交当前代码，再执行打包。`--output` 使用不存在的新目录，以免覆盖上一版。示意命令：

```bash
python tools/package_review.py --repo . --config deploy/review-package.json --policy runtime/private/review-policy.json --acceptance artifacts/review-acceptance --extra-record artifacts/current-tests.txt --visual-review runtime/private/visual-review.json --output output/anonymous-review
```

`review-policy.json` 包含 `terms`（每项有 `value`、`category`、`replacement`）和 `path_prefixes`；短英文名称可设置 `whole_word: true`，避免误改其他词的一部分。`visual-review.json` 的 `sha256` 数组列已逐张查看的图片哈希。

生成的 `review-code.zip`、`review-evidence.zip` 各有独立顶层目录，可以解压在同一父目录。`delivery-manifest.json` 记录扫描结果、选取批次、文件来源和两个 ZIP 的 SHA256。
