# T01 最新本地集成提交

在初版审阅包之后，已从 PR13 的固定 head 建立独立本地分支，并应用已审阅的原字节补丁，创建真实提交 `6b701c635139387ca536164226523d851b0388be`。完整仓库 tree 为 `a656374c5030ca59c37daa3e93f447d2fcada1cc`，SDK tree 为 `2796a70756eba2405c108414e14b36186c188601`，147 文件与此前已测版本一致；未重复运行 605 项套件。

该提交目前只在本机。建议公开推送到 `RoboSynth/ACPs-community` 的新分支 `integration/incident-ext-20261019`，用于最终 vendor 来源绑定。它组合既有两 PR 的内容，并增加本审阅包列出的 7 文件 durable access / 进程恢复扩展。新增扩展适用 SDK 的 MulanPSL-2.0，保留上游历史、原声明和许可证。团队应用总许可证仍未选择。

公开提交新扩展需要补充授权；现有公开授权的明确范围是两个 PR 和四条 Issue。具体代码可查看 `comparison-r2/pr13-plus-pr14-to-lf-minimal.patch`（新增 7 文件语义差异）和 `comparison-r2/pr13-to-raw-exact.patch`（可重建实际已测字节）。本目录的 `README.md` / `package-manifest.json` 保留初版审阅截面；最新状态以本页、`local-commit.json` 和 `final-binding-candidate.json` 为准。

T01 还需该 commit 在远端可解析后，再更新团队 vendor 绑定。AtomGit 和上游 CI 另列，当前未完成。这里只归档可审阅结果；取证脚本引用原本机 artifact 路径，不是接手开发者的通用安装入口。

本地准备曾出现两项已保留失败：沙箱内 clone 调用 Git shell 遭拒，随后使用正常本地 worktree；首次提交缺作者配置，随后读取并复用团队仓库已配置身份完成提交。两者均未向外部提交。
