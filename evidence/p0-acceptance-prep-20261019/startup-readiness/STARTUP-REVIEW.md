# Acceptance startup image review

Image references were resolved by the current manifest and sanitized Compose config --images. Compose includes dependent images; exact project/service matching was used.

| Role | Compose reference | Immutable image ID |
|---|---|---|
| app-v2 | incident-pilot-acceptance-20261019-app-v2:local | sha256:165a53fd42371edbb3618b7dfd269208d080526c0ce07ef686ab2a53d1240c25 |
| agent | incident-pilot-acceptance-20261019-agent:local | sha256:ccc35272ab4086325292ddfcaedac156e95ab4086df6a0d93276c030efaab837 |
| postgres | postgres:16-alpine | sha256:530a5243e576c08debb4860c981029bd9896b96686a65140da9e3b11c92f698e |
| nginx | nginx:1.27-alpine | sha256:1c7709d5f4d86d38773f8f908825dbc968da1fe2ee9d1d2542eeeb504a6a4fa8 |
| app-v1 | incident-pilot-acceptance-20261019-app-v1 | sha256:165a53fd42371edbb3618b7dfd269208d080526c0ce07ef686ab2a53d1240c25 |

The app-v1 default reference has no explicit tag, so Docker resolves it as latest. It was absent before one successful alias action and now points to the same immutable app-v2 image. APP_VERSION differs only in the existing runtime environment. No existing different-ID tag was overwritten.

Proposed startup argv (review only; not executed):

```json
[
  "wsl.exe",
  "-d",
  "Ubuntu-22.04",
  "--exec",
  "env",
  "-u",
  "POSTGRES_PASSWORD",
  "-u",
  "ORDERS_DB_PASSWORD",
  "-u",
  "APP_ADMIN_TOKEN",
  "-u",
  "BRIDGE_DB_PASSWORD",
  "-u",
  "ORDER_BIND",
  "-u",
  "APP_V1_PORT",
  "-u",
  "APP_V2_PORT",
  "-u",
  "ORDER_PORT",
  "-u",
  "REPLY_DROP_PORT",
  "-u",
  "COMPOSE_FILE",
  "-u",
  "COMPOSE_PROFILES",
  "-u",
  "COMPOSE_PROJECT_NAME",
  "-u",
  "COMPOSE_ENV_FILES",
  "-u",
  "COMPOSE_DISABLE_ENV_FILE",
  "-u",
  "COMPOSE_PATH_SEPARATOR",
  "-u",
  "COMPOSE_CONVERT_WINDOWS_PATHS",
  "docker",
  "compose",
  "-p",
  "incident-pilot-acceptance-20261019",
  "--env-file",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/runtime/private/acceptance-20261019/compose.env",
  "-f",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/deploy/compose.yml",
  "-f",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/deploy/agents.yml",
  "-f",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/runtime/private/acceptance-20261019/deployment.overlay.yml",
  "--profile",
  "isolated",
  "up",
  "-d",
  "--no-build",
  "--pull",
  "never",
  "--wait",
  "--wait-timeout",
  "240"
]
```

Proposed project-scoped stop argv (review only):

```json
[
  "wsl.exe",
  "-d",
  "Ubuntu-22.04",
  "--exec",
  "env",
  "-u",
  "POSTGRES_PASSWORD",
  "-u",
  "ORDERS_DB_PASSWORD",
  "-u",
  "APP_ADMIN_TOKEN",
  "-u",
  "BRIDGE_DB_PASSWORD",
  "-u",
  "ORDER_BIND",
  "-u",
  "APP_V1_PORT",
  "-u",
  "APP_V2_PORT",
  "-u",
  "ORDER_PORT",
  "-u",
  "REPLY_DROP_PORT",
  "-u",
  "COMPOSE_FILE",
  "-u",
  "COMPOSE_PROFILES",
  "-u",
  "COMPOSE_PROJECT_NAME",
  "-u",
  "COMPOSE_ENV_FILES",
  "-u",
  "COMPOSE_DISABLE_ENV_FILE",
  "-u",
  "COMPOSE_PATH_SEPARATOR",
  "-u",
  "COMPOSE_CONVERT_WINDOWS_PATHS",
  "docker",
  "compose",
  "-p",
  "incident-pilot-acceptance-20261019",
  "--env-file",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/runtime/private/acceptance-20261019/compose.env",
  "-f",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/deploy/compose.yml",
  "-f",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/deploy/agents.yml",
  "-f",
  "/mnt/d/AI + 开源/incident-pilot/artifacts/p0-acceptance-prep-20261019/checkout/runtime/private/acceptance-20261019/deployment.overlay.yml",
  "--profile",
  "isolated",
  "stop",
  "--timeout",
  "20"
]
```

First capture exact newly created IDs carrying this acceptance project label; exclude original inventory IDs and any unrelated additional build containers. Use scoped stop and retain networks/volumes; do not down or remove volumes.

All original 34 container IDs remain. Six subsequently present containers are exited, have no Compose project/service labels, and are listed individually in readiness.json. They are not owned acceptance deployment services. The helper did not create or stop them.

Preserved failures: first image-query helper expected one output line despite Compose dependencies; later helper over-constrained the complete container set to exactly 34. Compose queries and all image inspections/tag/readback themselves succeeded. The original receipts were retained.

This proves local image availability only. Startup health, platform ownership, experiment effects and the faults-profile images are separate checks.
