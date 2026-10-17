# 真实订单业务

运行栈为 FastAPI + asyncpg + PostgreSQL 16，Nginx 为统一业务入口。
`services.py` 的一次性 SQLite 基线保持独立；此目录没有 SQLite 回退。

## 接口

| 接口 | 输入 / 返回 |
| --- | --- |
| `POST /orders` | `{request_key,item,quantity}`；返回 `order_id`、`order`、`operation_key`、`outcome=committed` |
| `GET /orders/{uuid}` | 当前订单，包括 `CREATED` / `CANCELLED` 状态 |
| `POST /orders/{uuid}/cancel` | `{operation_key}`；取消回执 |
| `GET /receipts/{operation_key}` | 原始持久回执，包括创建时的状态快照 |
| `GET /health` | 进程存活及版本 |
| `GET /ready` | 实际数据库 `SELECT 1` |
| `GET /admin/status` | 连接池大小、配置修订号、实际会话只读状态、近期错误码 |
| `POST /admin/pool/rebuild` | `{expected_revision?}`；建立新连接池再切换 |
| `POST /admin/config/rollback` | `{expected_revision?,target_version:"stable"}` |

管理接口要求 `Authorization: Bearer <APP_ADMIN_TOKEN>`，Nginx 公共入口拒绝 `/admin/`。
v2 响应新增 `order_api_version: "v2"`；v1 保持业务语义但缺少此字段，用于真实路由版本故障。

创建和取消的键共用 `operation_receipts.operation_key` 命名空间。
事务级 advisory lock 按操作键串行化重试，订单变更与 JSON 回执在同一事务提交。
同键同内容返回原结果；同键异内容或异操作类型返回 HTTP 409。
重复取消的同一操作键返回原取消结果；新的取消键可确认订单已取消，不产生第二次状态变化。

HTTP 503、502、504、连接中断及超时都应保留原键并视为结果未知。
`GET /receipts/{key}` 的 404 同样返回 `outcome=unknown`，只能说明当前没有查到回执。
继续创建时仍使用原 `request_key`，避免第一次请求稍后提交后产生第二张订单。
业务管理动作幂等账本由资源域网关承担，不能把这些业务回执误用成跨域动作账本。

## 配置

应用域环境变量：`PGHOST`、`PGPORT`、`PGDATABASE=orders`、`PGUSER=orders_app`、
`PGPASSWORD`、`APP_ADMIN_TOKEN`、`APP_VERSION=v1|v2`。
可选 `DATABASE_URL`、`DATABASE_URL_STABLE` 均只从本域环境读取，管理状态不会返回连接串或密码。
`DB_COMMAND_TIMEOUT` 默认 3 秒，`DB_CONNECT_TIMEOUT` 默认 3 秒，`DB_POOL_MAX` 默认 8。

`schema.sql` 由数据库管理员首次运行，业务账号仅有读、插入、必要的订单更新权限。
应用启动不执行 DDL，因此只读故障时进程仍能启动并提供查询与诊断。

## 负载与验收

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe business/load.py --duration 30 --output eval/results/local/h00.json
```

默认每秒一个 HTTP 请求，创建、查询、取消各占一拍，健康 30 秒完成 10 个流程。
输出区分成功、明确失败、结果未知、仍未解析意图、已解析未知意图。
`--state <路径>` 保存原始意图，恢复后继续相同请求键；`--run-id` 和 `--seed` 可固定实验输入。
只有至少 30 秒、至少 10 个完整流程、零明确失败且无剩余意图才给 `passed=true`。

```powershell
# 先在本应用域加载 PG* 环境，再启用真实数据库测试。
$env:BUSINESS_TEST_DATABASE='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p business_test.py -v
```

测试标明 ASGI 边界测试与实际 PostgreSQL 事务测试；未启用数据库时会明确跳过后者。
