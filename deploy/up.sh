#!/bin/sh
set -eu
DEPLOY_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
command -v docker >/dev/null 2>&1 || { echo 'Docker is required.' >&2; exit 1; }
docker compose version >/dev/null
ENV_FILE=${INCIDENT_ENV_FILE:-"$DEPLOY_DIR/.env"}
PROJECT_NAME=${INCIDENT_PROJECT_NAME:-incident-pilot}
if [ ! -f "$ENV_FILE" ]; then
    echo 'Copy deploy/.env.example to deploy/.env and fill the three domain secrets.' >&2
    exit 1
fi
set -- docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yml"
if [ "${INCIDENT_AGENTS:-0}" = 1 ]; then
    set -- "$@" -f "$DEPLOY_DIR/agents.yml" --profile agents
fi
"$@" config --quiet
ROUTE_FILE="$DEPLOY_DIR/nginx/runtime/route.conf"
if [ ! -e "$ROUTE_FILE" ]; then
    mkdir -p "$DEPLOY_DIR/nginx/runtime"
    cp "$DEPLOY_DIR/nginx/route.default.conf" "$ROUTE_FILE"
fi
"$@" up -d --build --wait
echo 'Business target started. Run business/load.py for H00 acceptance.'
echo 'AIP participants require registered identities and domain configuration; follow deploy/README.md.'
