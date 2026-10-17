# Gateway implementation and verification, 2026-10-17

Implemented T20–T24 in `acps_mcp_bridge/`, `acps-mcp-bridge/` and `domains/`.
The local native backend follows the user's Windows deployment requirement.

| Check | Result and evidence |
| --- | --- |
| Policy, approval, ledger, resume, official AIP models, official ACS schema | 23 tests passed: `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_bridge*' -v` |
| Actual MCP stdio protocol | Test starts the official SDK FastMCP server and performs tools/list and tools/call; no protocol simulation |
| Actual third-party PostgreSQL MCP | `output/database-bridge-20261017T085554Z/results.json`: real PostgreSQL16 health/read-only/blocking-session tools, CREATE privilege false, approved restore_writes applied, second domain instance skipped the same operation |
| F06 actual controlled blocker termination | `output/database-blocker-bridge-20261017T091119Z/results.json`: orders_app blocker/waiter observed, missing approval and ordinary nonblocking PID rejected, approved blocker terminated and waiting query completed, duplicate skipped, both ready probes passed after cleanup |
| Actual native process and Nginx MCP tools | `output/native-ops-bridge-20261017T085959Z/results.json`: registered process/route observations, route rollback and process restart applied, both duplicates skipped |
| Actual third-party Docker MCP | `output/docker-mcp-bridge-20261017T094625Z/results.json`: upstream mcp-server-docker 0.3.0 / MCP 2.3.0 in an isolated container, official MCP 1.30 client stdio tools/list, labeled list/logs, missing-approval denial, approved app-v2 stop/start, replay skipped; 18082/ready and 18088/ready both returned 200/v2 afterward |
| Live Docker label boundary | `output/docker-label-denial-20261017T094953Z/results.json`: an explicitly created unlabeled, never-started control container was denied before logs forwarding, then removed by its immutable ID |
| Resource lifetime | After both MCP sessions closed, fresh connections to 8082 and 8088 both returned api_version v2. The ops supervisor owns the persistent app process |
| Local cross-domain AIP data path | `output/local-transport-readonly/results.json`, produced by the SDK integration: official TaskCommand/TaskResult/Product across separate domain processes |
| Reproducible domain setup | `domains/setup_local.py --start-supervisor` ran successfully while preserving secrets, configs and the current application |

This evidence covers local native AIP IPC and actual MCP/database/process/Nginx
execution and the actual third-party Docker MCP backend. New-domain Wutong group
execution and live ADP/ACS admission remain separate integration acceptances.
Local native processes share an OS; their
logical domains are not an OS security boundary.

Preserved failures explain compatibility and lifecycle changes:

* `output/database-bridge-20261017T084652Z/failure.json`: postgres-mcp 0.3.0 has
  an unbounded MCP dependency but still uses v1 FastMCP. The domain environment
  now pins `mcp==1.30.0`.
* `output/database-bridge-20261017T084831Z/failure.json`: FastMCP wraps the
  upstream's text blocks in structuredContent.result. Normalization now handles
  this wrapper, Python literal rows, and upstream `Error:` text.
* `output/native-ops-bridge-20261017T085617Z/failure.json`: directly spawning
  the application from a Windows MCP stdio process tied its lifetime to the
  SDK's process job. The dedicated local supervisor now owns persistent app
  processes and exposes only a fixed token-protected restart operation.
* `output/native-ops-bridge-20261017T085910Z/failure.json`: the next route test
  started before the application had been restored. The final run passed after
  restoring the registered process; the route tool confirms public api_version
  convergence after Nginx reload.
