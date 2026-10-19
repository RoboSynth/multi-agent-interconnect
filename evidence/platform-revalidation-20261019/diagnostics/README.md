# full-history 诊断与独立复核

保留 [r1 首次诊断](full-history-r1-diagnosis.md)、[r1 运行取证补充](full-history-r1-diagnosis-r2.md) 和 [r2 独立核验](full-history-r2-review.md)。r1 保持 failed / TimeoutError / runner exit 1；补充 trace 证明主端走到 after_applied 退出钩子，但旧 daemon die 事件未返回，实际退出码 unknown。r2 是一次正式 full_history 成功：实际发送的 7 条合法会话历史被备用确认，未重复修改数据库；不写成 3/3。

r1 首次诊断反映其检查时刻尚无 worker trace，之后的 revision 2 补入运行记录；两份各自保留，不覆盖旧稿。运行取证目录附主备事件 trace、只读采集收据、共享卷身份白名单和空 daemon 事件响应。身份投影只保留共享 /state，其他挂载不发布。没有协调消息正文、handover 正文、订单正文或凭证材料。

`[checkout]`、`[batch]` 分别替代本批冻结 checkout 与 artifact 根的精确本机路径。原件未修改；嵌套 evidence 中的 SHA 仍指本机原字节。每个本包文件的原件 SHA 与发表副本 SHA、投影方式见 [publication-projections.json](publication-projections.json)。只做路径替换的材料保留全部诊断字段；容器身份采用显式字段白名单。未上传的原件引用用于定位与摘要核对，不代表其正文在本包内。

此目录已准备供根代理合并、最终扫描和审核；目录存在不代表 12 例全部完成、隐私扫描已通过或已提交 GitHub。
