# MQ Group API endpoint lookup — 2026-10-17

Result: No production MQ Group API HTTPS origin was found within this bounded public-source search. This is an unresolved configuration prerequisite, not a demonstrated transport or SDK failure.

## What was checked

- The official Dingdang entry point is linked by Wutong's public docs. Its public HTML and explicitly named main application JavaScript were read. The frontend delegates to its own `/api`; it does not publish an MQ Group service origin.
- The official Flux documentation entry point is linked by Wutong's public docs. Its explicit `main.js` → router → `DocsView.vue` → documentation index imports were followed read-only.
- Three directly indexed public WIT documents were read: AIP Group, `wit.acps.group.acl`, and ACPs infrastructure configuration. All raw module responses and extracted Markdown are preserved in this directory.
- The pinned official ACS `AgentEndPoint` model has `url`, `transport`, and `security`, but no standard advertised MQ ACL URL. The pinned SDK expects `auth_service_url` separately.
- The pinned gateway-nginx template states that it is a minimal starter, not production routing configuration. Its `/health` and catch-all routes cannot identify the hosted Wutong ACL service.

Thirteen named public resources were requested in this subtask. No path enumeration, port scanning, credentials, cookies, tokens, registry submissions, MQ authorization changes, group creation, or messages were used.

## Precise useful findings

1. `flux-group-document-0.response.md:23` says `mq_url` and `mq_group_api_url` must be configured together. Strict mode requires AMQPS on explicit port 5671 and `/acps` vhost. Its example MQ Group URL is only `https://mq-auth.example.com`.
2. `flux-group-document-1.response.md:39-43` specifies that the Group API is Leader-only, uses mTLS, and the `base_url` must be an HTTPS origin without credentials or path components.
3. `flux-group-document-2.response.md:122-136` documents `AcpsConfig.ioa_pub()` as using ioa.pub's fixed infrastructure addresses. Its signature still accepts optional `mq_url` and `mq_group_api_url`, so the public documentation alone does not establish whether a real hosted MQ Group URL is preset. Inspecting that official package method is the next evidence-based route.

## Exact question for the official platform team

我们使用官方 ACPs v2.2.0，准备由同一参赛账号注册的两个智能体进行 AIP Group 通信，已确认 Broker 是 `amqps://wt.ioa.pub:5671/acps`。请提供生产环境 MQ Group ACL API 的确切 HTTPS origin（用于 SDK `rabbitmq_config.auth_service_url`、CLI `[mq].group_api_url` 或 WIT `AcpsConfig.mq_group_api_url`），并确认其 mTLS 客户端证书申请渠道及 Leader 角色/群组授权前置要求。当前公开 Registry 前端配置仍是 `https://localhost:9007`，官网接入文档未列出该服务地址。若官方当前推荐通过 WIT 的 `AcpsConfig.ioa_pub()` 接入，请给出兼容版本与可直接运行的双智能体最小示例。

This question is prepared only; it has not been sent to anyone.

## WIT package follow-up

Four more explicitly indexed public resources were checked: installation guide, quickstart, manual homepage, and manual header component. They do not provide a WIT wheel download URL or source repository link in this scope.

- `wit-install-source-0.response.md:3-12` requires the distributed `wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl` beside `acps_sdk-2.2.0-py3-none-any.whl` and `release-manifest.json`.
- `wit-install-source-0.response.md:56` explicitly says WIT ships `.pyi` declarations and CPython bytecode, and the original implementation is not directly viewable. No wheel was guessed, downloaded from an unofficial source, or installed.
- The manual homepage and header link to the installation guide but do not expose a release download. Therefore `AcpsConfig.ioa_pub()` could not be independently inspected from the publicly linked materials available here.

The precise additional official request is: “请同时提供 WIT 2.1.0 完整发行包（两个 wheel 与 release-manifest.json）的官方下载地址，并确认 `AcpsConfig.ioa_pub()` 是否默认配置生产 `mq_group_api_url`；若否，请给出正式地址。”
