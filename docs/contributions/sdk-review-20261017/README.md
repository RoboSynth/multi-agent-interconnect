# SDK 独立审阅补丁

本目录是本地不可覆盖的审阅快照，尚未向上游提交 PR 或 Issue。

- 基线：`incident-v0.2.0-20261017T045307Z` 内的冻结 SDK，上游提交 `3985c1330209f075c124669cc9d31f0e75448140`，SDK 2.2.0。
- 补丁：仅 `vendor/ACPs-community/acps-sdk/` 内 12 个文件，10 新增、2 修改；1535 行新增、9 行删除。
- SHA256：`2df10ba1c1e0552003c514cdc30a1eff6f343886a96cd1ebad34e10f450c64b9`，91116 字节。
- 离线验证：基线 SDK 临时副本上的 `git apply --check` 与实际应用均成功；应用后的每个修改文件 SHA256 与当前 SDK 相同。SDK 源码和冻结基线未修改。
- 测试：引用已通过的三项排序和 25 项 resumable 行为测试，导出时未重复运行。SDK 外三项排序测试仍需在正式上游提交前移入合适目录。

`manifest.json` 记录来源、逐文件 SHA256、既有测试和旧导出差异；`diffstat.txt` / `numstat.txt` 展示范围；`validation.json` 保留临时应用结果。旧 11 文件补丁与本补丁不同，旧件保留。

在项目根目录检查：

```powershell
git -c core.autocrlf=false apply --check docs/contributions/sdk-review-20261017/acps-sdk-high-score.patch
```

在上游 ACPs-community 根目录使用同一补丁需加 `-p3`。本轮实际验证的是冻结项目路径，未把当前工作 SDK 当作待应用基线。

新 E1-a / E1-b 18 例只完成代码、相关单测和只读预检，真实资源启动被自动审批审查拒绝并等待用户授权；正式平台接管未运行。旧三点单次本地 F15 和既有三身份正式只读流程仍是独立证据，均不替代新 E1。PR 草稿详见上级 `PR-sdk-resumable.md`。

复现导出时选择新的输出目录：

```powershell
python docs/contributions/prepare_sdk_patch.py --output docs/contributions/sdk-review-another-snapshot
```
