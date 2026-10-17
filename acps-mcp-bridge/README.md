# MCP → AIP gateway

Import `acps_mcp_bridge`. The client uses the official MCP Python SDK 1.30.0
`stdio_client`, `ClientSession.initialize`, `tools/list` and `tools/call`. Each
resource domain owns its own server processes, credentials and ledger.

```powershell
.\.venv\Scripts\python.exe -m pip install -r acps-mcp-bridge/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bridge*' -v
.\.venv\Scripts\python.exe -m acps_mcp_bridge --config domains/database/gateway.local.json --payload task.json --caller-aic YOUR_COORDINATOR_AIC
```

Copy `domains/database/gateway.example.json` to a local config. Provision
`DATABASE_URI` **only in the database domain** using the `bridge_operator` role
created by `domains/database/bootstrap.sql`. Run that SQL as the disposable
experiment administrator after creating the `orders` database and `orders_app`
role. Set the role password through the deployment secret mechanism. The MCP
role has monitoring access and two fixed security-definer functions; it has no
arbitrary DDL, orders-table DML or role-management grant. Only server-owned SQL
templates reach `execute_sql`; remote `sql` arguments are rejected.

Database primary and backup configs must resolve `ledger_path` to **the same
SQLite file** and both use domain `db`. A new identity is a separate process,
not a copied credential. The SDK ledger records uncertain operations and refuses
blind retries; production recovery requires a postcondition query before retry.

To serve real AIP, add `platform` to the local config with absolute `cert`, `key`,
`trust_bundle`, the official `amqps` `endpoint` and HTTPS `mq_auth_url`. With no
`--payload`/`--acs-base`, the entrypoint uses the baseline's single-Inbox
dispatcher and official `GroupPartnerMqClient`. Its incoming AMQP boundary calls
`assert_incoming_group_message_identity` before the gateway callback. The
callback requires identity binding, checks sender/group/session/task context,
enforces caller AIC policy, and returns official `Product` objects with
`StructuredDataItem` results. No platform registration or external write is
performed by generating ACS.

`Bridge(policy, clients, ledger, executor_aic, *, audit, resource_guard)` exposes
`await initialize()`, `await execute(payload, caller_aic)` and
`bind_partner(official_partner)`. `initialize()` verifies every configured tool
against live `tools/list`. `map_acs(base, policy, inventory)` publishes stable
`db.observe/db.act` or `ops.observe/ops.act`; `describe` returns fine tools,
their schemas, risk and resource scope. Validate via `integration/validate_acs.py`.

Approval is an independently authenticated HMAC record, not a trusted `approved_by`
claim. `ApprovalAuthority(secret).issue(payload, caller_aic,
approved_by='workbench', ttl_seconds=300)` creates the record to put in
`payload['approval']`. `Policy(..., approval_verifier=authority.verify)` checks
exact incident, operation, caller, tool, args, actor and expiry. The approval
secret grants no database or Docker access. Set `INCIDENT_APPROVAL_SECRET` to
at least 32 random bytes in the approval issuer and this resource domain. It
must never be transmitted in AIP messages.

In platform mode, audit uses the official AMP `CertificateAuditSigner` and
`AuditEmitter`; local contract probes have no certificate and no signed AMP
claim. The SDK's group-access middleware supplies AIP access telemetry. Every
gateway rejection and execution emits an audit event when a sink is supplied.
Server errors return exception types rather than potentially secret-bearing
stderr. Result output is bounded and known secrets/credential URIs are scrubbed.

## Third-party processes

* [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), MIT.
* [crystaldba/postgres-mcp](https://github.com/crystaldba/postgres-mcp), MIT;
  `postgres-mcp==0.3.0`, `DATABASE_URI` environment, `--access-mode=unrestricted`.
  The gateway and SQL role enforce safety, rather than relying on a read-only
  mode that cannot perform the two approved recovery actions. Upstream SQL rows
  are Python literal text and upstream SQL failures are `Error:` text; both are
  explicitly handled without executing received code.
* [ckreiling/mcp-server-docker](https://github.com/ckreiling/mcp-server-docker),
  GPL-3.0, `mcp-server-docker==0.3.0`. Use a **separate environment** with its
  required MCP v2. The gateway communicates only over stdio. `list_containers`,
  `fetch_container_logs`, `stop_container` and `start_container` are allowlisted;
  creation/removal/compose are not exposed. Container operations require live
  `incident-pilot` labels and immutable ID resolution. Docker absent means these
  operations cannot be accepted as verified. See `domains/ops/guard.py`.
  `domains/ops/policy.native.yaml` selects the local Windows experiment backend:
  the same `ops.containers` alias reports the registered app-v2 process state
  with `backend=native` in its source tool, while `ops.restart` controls only
  that registered project process after live command-line identity validation.
  It holds a Windows process handle during validation/termination and refuses
  arbitrary PIDs or commands. This local backend reads the application's local
  environment only to relaunch the already registered experiment application;
  the operating system is shared, so it demonstrates logical resource domains
  rather than OS-enforced organization isolation.
* `domains/ops/route_mcp.py` is the project's MCP route tool. It accepts only
  registered `v1/v2` upstreams, validates Nginx config before reload and restores
  the file on failure. `INCIDENT_ROUTE_FILE`, `INCIDENT_NGINX_BINARY` and
  `INCIDENT_NGINX_CONTAINER` are local process configuration.

## Docker 固定项目与目标

独立 profile 将 `domains/ops/policy.yaml` 复制到本域私有配置目录，并覆盖以下三项：

```yaml
resources:
  compose_project: incident-pilot-new7
  compose_service: app-v2
  container_name: incident-pilot-new7-app-v2-1
```

三项必须全配或全无，部分配置、空值和非法名称在加载策略时拒绝；全无仅保留旧标签验证兼容模式。
同时更新 `ops.containers.fixed_arguments.filters.label` 中的项目和服务标签，保留
`incident-pilot` 标签及 `all: true`。上游 `list_containers` 默认只列运行中的容器，
`all: true` 才能观察已退出的目标。将 `ops.restart.fixed_arguments.container_id` 固定为同一
`container_name`，其输入 schema 保持空对象；若日志工具也采用固定目标，同步更新它的固定参数。

观察仅输出项目、服务和名称均匹配的唯一目标，提供规划器使用的 `container_state` 及精简
`containers` 列表。缺失目标或未知状态返回 `unknown`，重复目标视为工具错误，不推断为退出。
重启须经独立审批，再由实时 `docker inspect` 核对标签、项目、服务和名称，以不可变 ID 停止、
启动该目标，最后只读重查状态。资源范围进入操作账本参数摘要，操作号不能跨项目复用。

本次补丁通过 50 项离线 Bridge 相关测试，记录在
`output/docker-scope-offline-20261017/results.json`。此前真实 Docker 验收使用的是旧版策略，
不能作为本补丁的真实容器验收；新 profile 的实际运行需另留证据。

Local native verification commands (coordinate write tests with other lab users):

```powershell
.\.venv\Scripts\python.exe domains/database/provision_local.py
.\.venv\Scripts\python.exe domains/database/verify_local.py
.\.venv\Scripts\python.exe domains/ops/verify_local.py
```

After the native PostgreSQL/application baseline is prepared, recreate domain
configuration with one command (it preserves existing secrets/configs):

```powershell
.\.venv\Scripts\python.exe domains/setup_local.py --install --provision-db --start-supervisor
```

The native ops supervisor listens only on `127.0.0.1:8093` with a domain token
stored in `runtime/private/ops-bridge.env`. Its single mutation is a fixed
registered app-v2 restart; the MCP tool supplies no command or PID. The separate
supervisor is necessary because the official SDK places Windows stdio servers
and their children in a job that terminates on client shutdown. Applications
started directly by a transient MCP server would otherwise be killed when that
server closes. Supervisor/app child environments use system-variable allowlists
and explicit application credentials only. The coordinator has neither the
supervisor token nor application/database credentials.

`resume` accepts `args.advance_fence=true` with a new `fence` and optional
`resume_package`. It atomically activates the shared domain fence before
returning state. `received` may be followed by `act` with the original arguments;
`applied` returns cached facts. For uncertain database-write/route operations,
resume performs the registered read-only postcondition and resolves only when
it proves the requested state. Other uncertain operations require review.

Add `--write` in an exclusive experiment window to verify actual controlled
recovery plus the ledger's duplicate skip. The PostgreSQL server environment
also pins `mcp==1.30.0`: upstream 0.3.0 has no upper dependency bound while its
code still imports v1 `FastMCP`, so a fresh unbounded install otherwise selects
MCP v2 and fails at startup. Native Windows Nginx uses the registered ASCII
`subst` drive from `deploy/native-runtime.json` for its `-p` prefix.

The automated stdio test starts a real MCP fixture to verify the protocol and
ledger replay; it does not assert that a PostgreSQL server, Docker daemon or
Wutong group was reached. Those require the corresponding live integration run.
