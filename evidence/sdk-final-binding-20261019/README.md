# SDK 最终 fork/vendor 绑定

已按新增公开授权，将真实集成提交 [6b701c635139387ca536164226523d851b0388be](https://github.com/RoboSynth/ACPs-community/commit/6b701c635139387ca536164226523d851b0388be) 推送到 `integration/incident-ext-20261019`，并通过独立远端查询核实。该提交包含原两个 PR 与后续 durable access / coordinator 进程恢复扩展；现有 PR 的审阅状态仍以其独立状态记录为准。

[绑定清单](../../vendor/ACPs-community/sdk-binding.json)列出147文件的Git模式、blob及SHA256。团队vendor与公开提交的SDK tree均为`2796a70756eba2405c108414e14b36186c188601`，全部原字节相同，继续使用普通vendored安装。完整605套件已验证的SDK字节未变，本次只更新来源元数据，未重复运行套件。

SDK保留MulanPSL-2.0、上游历史及原许可声明。应用项目总许可证未选择。[初版审阅包](../sdk-final-binding-review-20261019/LOCAL-COMMIT.md)按当时状态保留；当前完成情况见本页及verification.json。

T01的最终fork/vendor绑定已完成。AtomGit镜像和真正的上游CI仍待完成，不能用本地605结果替代上游CI。
