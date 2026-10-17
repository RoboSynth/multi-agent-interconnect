# [Docs/ADP] 明确省略 alive 条件时的发现行为，补充已登记身份的接入体检示例

两个已通过审核的身份按 AIC 查询时，默认 ADP 响应为空；保持 AIC 条件不变，显式把
online / offline / unknown 都纳入 extFilter 后，两者均返回。建议文档区分“身份已登记”
与“满足默认存活筛选”，并给出只读接入体检查询。

观察来自 2026-10-17 的 `https://wt.ioa.pub/discovery/acps-adp-v2/discover`，客户端使用
固定 ACPs SDK `2.2.0`，源码提交 `3985c1330209f075c124669cc9d31f0e75448140`。
我们不据此认定 Registry 丢失数据或 ADP 不支持已批准身份。

## 精确观察

两次请求都在 AIC-A / AIC-B 上执行相同 filtered 查询、limit=10；间隔不足 1 秒：

| UTC 时间 | extFilter | HTTP | result.acsMap 数量 |
| --- | --- | --- | --- |
| 04:20:47.014555 | 未提供 | 200 | 0 |
| 04:20:47.848885 | alive in [online, offline, unknown] | 200 | 2 |

第二次响应中两份 ACS 的 active 均为 true。两次响应都未返回 aliveMap，因此仅凭这组
响应不能断言默认一定只筛 online，也不能确定这两个对象各自的具体 alive 值。

## 最小复现

用自己已登记、已通过审核的两个 AIC 替换占位值，向上述端点 POST：

```json
{
  "type": "filtered",
  "limit": 10,
  "filter": {
    "logic": "and",
    "conditions": [{"field": "aic", "op": "in", "value": ["AIC-A", "AIC-B"]}]
  }
}
```

保留全部字段，再加：

```json
{
  "extFilter": {
    "logic": "and",
    "conditions": [{"field": "alive", "op": "in", "value": ["online", "offline", "unknown"]}]
  }
}
```

比较 result.acsMap 的键集合。复现需要选择当时不满足默认存活筛选的身份；对一直在线
的身份，两次结果可能相同。我们已保存原始成对请求，时间与匹配数量如上。

## 预期与建议

请明确 extFilter 省略时的有效 alive 策略，以及注册审核、AMP 心跳、ADP 存活同步之间的
关系。在接入教程增加“确认是否已同步登记”的全存活状态查询，并把它与正式调度查询区分。
条件允许时，响应增加可选的过滤诊断信息，有助于判断空结果来自身份、技能还是存活筛选。

不建议直接删除生产查询的存活保护。全状态查询适合接入诊断；选择执行方仍应确认其能力、
资源范围、身份和可用性。本 Issue 请求澄清默认语义与诊断路径，尚无证据把该行为定为
服务端实现错误。
