# Production endpoint and certificate-route follow-up

## Result

No source-backed production MQ Group API origin was found. The missing value remains `rabbitmq_config.auth_service_url`, CLI `[mq].group_api_url`, or WIT `AcpsConfig.mq_group_api_url`. No guessed host, port, or path was probed.

The Registry infrastructure tooltip was traced to its actual current client-list JavaScript, not merely inferred from an environment block:

- Public module: `https://wt.ioa.pub/registry/static/js/client_list-BFH51SW2.js`.
- It destructures `VITE_MQ_AUTH_URL` as `M` and renders `M` in the infrastructure popover.
- Its public compiled value is exactly `https://localhost:9007`. There is no dynamic hostname replacement in the inspected rendering path.
- The same popover's discovery URL and RabbitMQ host are also localhost placeholders. They cannot be treated as the hosted deployment's real addresses.

## Current official repository

GitHub currently resolves main to `94077d10b336bfdb9a7d68e4859390bf44a67a27`, committed 2026-10-07, message `Update readme_en.md`. The pinned implementation is `3985c1330209f075c124669cc9d31f0e75448140`.

The official compare API reports 93 additional commits and 72 changed files. Supplied textual patches were searched for `wt.ioa.pub` and MQ HTTPS address declarations. Only localhost examples were added in an English testing document. Two large translated Markdown patches and image patches were omitted by GitHub's response, so this is bounded evidence, not a claim that every byte of current main was searched.

Current CLI README, current AIP tutorial, current Chinese root README, and the latest public issue list were read. No maintainer-published production MQ Group address was found in these materials. Public issue reports are not treated as verified maintainer guidance.

## Confirmed current public certificate endpoints

Fresh anonymous read-only HTTP checks returned 200 JSON for:

- `https://wt.ioa.pub/registry-server/openapi.json`
- `https://wt.ioa.pub/ca-server/acps-atr-v2/acme/directory`

The live Registry API advertises:

- Login: form POST `/registry-server/api/v1/auth/login`; required fields are `username` and `password`. The API also advertises a possible 410 response when local authentication is disabled. No login was attempted in this research, so its successful authenticated runtime remains unverified.
- EAB: POST `/registry-server/acps-atr-v2/eab/{agent_aic}`, Bearer authorization. Its live description requires an AIC owned by the current user and in active state.
- The CA ACME directory advertises `externalAccountRequired: true` and its own newAccount/newOrder/finalize certificate workflow.

The public platform guide's supported client sequence is:

1. Register and pass review in the existing Registry UI; obtain the assigned AIC.
2. `acps-cli --config acps-cli.toml auth login`.
3. `acps-cli --config acps-cli.toml cert eab fetch --aic <AIC> --output <private-file>`.
4. `acps-cli --config acps-cli.toml cert issue -a <AIC> --eab-file <private-file> -u clientAuth --key-path <private-key> --cert-path <certificate> --trust-bundle-path <trust-bundle>`.

These are source-backed commands, not a claim that this subtask obtained identities, EAB, or certificates. No credentials, cookies, token files, EAB material, or private keys were read; no authenticated request was made.

## Viable protocol alternative

Official AIP Direct does not use the MQ Group API. Once both AICs and client certificates are issued, a Leader can discover a Partner through the live platform and call the Partner's genuine reachable HTTPS JSONRPC endpoint. That route still needs a real public HTTPS Partner service and proper certificate configuration. It should be treated as an implementation choice if the platform team cannot provide the missing production Group address, not as a verified platform run.

All fresh HTTP metadata and response hashes are in `EXCHANGES.json`, `REGISTRY-TOOLTIP-EXCHANGES.json`, `OFFICIAL-LINKS-EXCHANGES.json`, and `CURRENT-CLIENT-EXCHANGES.json`. This research did not modify root configuration, ACS files, platform state, or runtime status.
