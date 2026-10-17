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
