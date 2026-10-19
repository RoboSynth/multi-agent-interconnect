# 固定版本 3760b21 的完整开发源码包

已从 Git 提交 `3760b21c8a1ed62e8119925da6f24ebd8b851d14` 实际导出 ZIP，并核对全部 **2018 个文件**与该提交的 Git blob、字节数和 SHA256，96 项必要入口齐全。重复路径、越界路径、符号链接、gitlink、非普通文件及实际运行时/凭据/数据库路径检查通过。

ZIP 为 `incident-pilot-development-3760b21.zip`，19,249,930 字节，SHA256：

```text
e80b8bc73c42200ce562c2f553f36377ac956f142dae1b4c054df76aa3ecb43a
```

在有权限的克隆目录内复现：

```text
git archive --format=zip --prefix=incident-pilot-development-3760b21/ --output=../incident-pilot-development-3760b21.zip 3760b21c8a1ed62e8119925da6f24ebd8b851d14
```

也可用自己的 GitHub 团队账号[下载固定提交源码](https://github.com/RoboSynth/multi-agent-interconnect/archive/3760b21c8a1ed62e8119925da6f24ebd8b851d14.zip)。GitHub 自动包的目录前缀及 ZIP 元数据可能不同；本页 ZIP 哈希只对应上面实际导出的包。

[当前完整清单](export-manifest.json)来自固定 Git 对象，包含全部2018项；[检查结果](verification.json)与[实际退出收据](verification-exit.json)单列。归档内原有 `SNAPSHOT-MANIFEST.json` 保留为历史源码内容，不能用来断言新提交完整性。本次没有依赖该旧清单来证明新包；当前清单独立保存在本证据目录，避免为了补入检查收据改变已冻结的源提交。

`verify_frozen_export.py`记录本机一次性验证过程，复用先前已审的只读 ZIP 检查器，依赖本机保留的旧归档工件；它不是队友的通用入口。队友导出源码使用上面的 Git 命令，安装和运行按[接手指南](../../../docs/开发者接手指南_20261018.md)。归档来源是已提交文件，既有官方 `.env.example` 模板仍按原精确字节例外核验，没有新增路径放行。

本次不解压、不构建、不启动服务或故障，不改变正式实验记录；不能计入新机器15分钟、F10、网盘永久分享或另一账号访问验收。该包固定在3760b21，不包含后来提交的代码或证据。
