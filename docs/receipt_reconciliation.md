# 原请求只读回执对账

`eval/receipt_reconciliation.py` 为已经保留原始观察器 summary 和 requests trace 的订单意图提供独立只读入口。队友使用自己的开发环境即可运行，不需要 GitHub、梧桐或他人的账号、证书。目标业务服务及其原数据库需由实例所有者提供；新数据库查不到旧键，不能据此判断旧请求未执行。

## 准备清单

1. 取得实例所有者保存的原 `summary.json` 和 `requests.jsonl`，保留原字节；每组对应一个 `state.pending` 意图。公开的 NEW7 E3 投影省略了原键，不能替代这两份原件。
2. 在新的本机工作目录保存 manifest，按原始记录填写文件路径及其 SHA256。路径以 manifest 所在目录为基准，也可使用绝对路径。原件摘要须与已有冻结记录核对；工具只能核查给定摘要和源内容的一致性，不能证明提供者没有同时伪造摘要与文件。
3. 由实例所有者确认本次连接的是原数据库的公开 v2 业务端口。入口只接受 `http://127.0.0.1:<端口>`，不接受域名、URL 用户信息、额外路径或查询参数。无需修改系统代理。

示例结构中的摘要是占位符，必须换为原件的真实 SHA256；不要填写原键或自己构造替代 pending JSON：

```json
{
  "schema_version": 1,
  "base_url": "http://127.0.0.1:38088",
  "entries": [
    {
      "label": "F06-M1-1",
      "summary": {"path": "original/F06-M1-1/summary.json", "sha256": "<summary SHA256>"},
      "trace": {"path": "original/F06-M1-1/requests.jsonl", "sha256": "<trace SHA256>"}
    }
  ]
}
```

使用已有开发 Python，安装项目开发依赖。以下命令从仓库根目录执行；若直接运行脚本，则使用脚本绝对路径，入口会自行添加项目根目录：

```text
python -m eval.receipt_reconciliation --manifest path/to/manifest.json
python -m eval.receipt_reconciliation --manifest path/to/manifest.json --run --output artifacts/receipt-observation-new
python -m unittest discover -s tests -p test_receipt_reconciliation.py
```

第一条只校验并描述计划，不创建 HTTP 客户端或输出目录。第二条使用新的、尚不存在的输出目录；重跑需另选新目录，保留旧观察。工具先写 `scope.json`，完成后写 `result.json`，每个已发送但结果未知的原操作至多一次 GET，每次请求总 deadline 为 8 秒，超时后保留 unknown 并继续后项；不启动服务、不重试、不重定向、不读取环境代理，不发 POST 或资源修复动作。

## 如何判断结果

工具从原 summary 派生创建键、取消键、类型和原订单号，通过原 trace 的方法、路径及阶段前进核实 pending 状态，并对账 summary 对应窗口的请求数及 success/failed/unknown 计数。`ContinuousObserver` 的 trace 含前置健康请求，而 summary 只统计故障后的末尾窗口；目标意图的状态仍按完整原 trace 回放。目标操作须有原 POST unknown 记录。已经创建和查询、但从未发送取消的阶段单列 `not_submitted`，执行零次 GET，不将其称作未知取消提交。

- `committed`：回执版本、原 operation_key、操作类型、committed 结果、合法订单号、原订单身份、创建键、item/quantity 和提交时状态快照均匹配。创建回执只确认创建提交，`workflow_terminal_confirmed=false`；完整流程仍需后续步骤。取消回执确认原取消提交快照，可标记本次观察的终态已确认。
- `unknown`：404、网络错误、非成功响应或无效回执。404 不证明未执行；工具不会换键补单或清除旧 pending。
- `not_submitted`：原 trace 未发送的取消，工具不代为发送。

回执为事务提交时快照，不是新查询的当前订单状态。请求次数和每次请求等待有界，入口没有额外承诺响应字节上限。输出只记录键/订单号/响应的摘要，不包含原值或完整响应。输入路径也会写入输出，分享前按项目资料发布规则检查路径和文件。

退出码 0 表示本次有界观察完成且原文件未变；即使全部 404 也可能为 0，不表示原流程已完成。输入不一致、无效回执、网络/其他响应错误或运行期间原文件变化会失败。`scope.json` 单独存在表示运行未完成，应保留并排查，不直接重复使用该目录。

本入口不回写原 summary、trace 或矩阵结果。后续如要对旧操作执行同键重试、取消或人工补偿，需要单独明确执行范围；不能用新健康订单或本次只读观察追溯改判旧失败。
