# Official Group ACL requirements

This is a read-only review of pinned official ACPs v2.2.0 source, commit `3985c1330209f075c124669cc9d31f0e75448140`. No remote permissions were probed and no authentication mechanism was changed.

## Precise conclusion

`auth_service_url` is optional for constructing `GroupLeader` and for an authenticated AMQPS connection or an agent's own Inbox. It is mandatory in the official high-level SDK's **Inbox invitation path**, which is the route currently described by our AMQP-only Partner ACS. A complete new group also needs membership authorization under the official broker-side policy. There is no same-Registry-account exception in that policy.

Our local required-field check is therefore too broad for a standalone certificate/Broker-readiness stage, but it correctly identifies a prerequisite for the intended end-to-end Inbox Group smoke test.

## SDK control flow

Paths below are relative to `vendor/ACPs-community/`.

1. `acps-sdk/acps_sdk/aip/aip_group_leader.py:1568-1586`: the constructor reads `auth_service_url` with `.get()`. `_group_acl_client` defaults to `None` and is created only for a non-empty string. Construction does not require the URL.
2. `aip_group_leader.py:1587-1640`: `_ensure_connection()` uses AMQPS+EXTERNAL and the supplied SSL context when no username/password is configured. It does not call the Group API. Its normal startup also prepares the Leader's own Inbox.
3. `acps-sdk/acps_sdk/aip/aip_group_partner.py:248-291`: `GroupPartnerMqClient.connect()` likewise needs the Broker and SSL context, not a Group API URL. `ensure_inbox_queue()` at 293 prepares its own Inbox; `start_inbox_consuming()` at 335 starts invitation handling.
4. `aip_group_leader.py:1743-1754`: `create_group_session()` calls `add_member()` for the Leader itself and each initial Partner **only if** `_group_acl_client` exists. The low-level group constructor can be invoked without this client, which is suitable only if the deployment supplies permissions by some separately supported means.
5. `aip_group_leader.py:1831-1860`: a same-Broker AMQP endpoint selects the Inbox invitation route. This branch does not automatically fall back to RPC merely because `_group_acl_client` is missing.
6. `aip_group_leader.py:1941-1944`: `_invite_partner_via_inbox()` explicitly raises `PartnerInviteError("auth_service_url is required for inbox-based invitations")` if there is no ACL client. Then line 1957 calls `add_member()` before sending the invitation.
7. `aip_group_leader.py:1898-1904`: the RPC-based Group invitation path only calls `add_member()` conditionally. This does not remove broker authorization requirements and does not establish that the hosted platform pre-authorizes this route.

## Broker-side policy

- `mq-auth-server/app/services/authz.py:205-224`: only the exact Leader AIC can configure its group exchange. Exchange read/write permissions then call `check_group_membership()` and deny a non-member.
- `authz.py:254-273`: an agent can configure/read its own Inbox according to the AIC encoded in the queue name. This is independent of Group membership.
- `authz.py:287-344`: Group queue access checks the exact member AIC and active Group membership; Group queue `read` requires membership even for a Leader reading its own Group queue.
- `mq-auth-server/app/services/group_acl.py:216-265`: membership is read from the Redis Group set, with only an existing local membership cache used on store failure. No membership and no cache return `False`; there is no default allow.
- `mq-auth-server/app/api/groups.py:91-115`: the Group API caller certificate's AIC must exactly match the Leader AIC in the route path.

These paths do not query Registry `created_by`, account ownership, or any same-account relationship. Two different AICs under one human account remain different principals for the broker.

## Supported next step

After real client certificates are issued, both agents can independently run the official Broker connection and own-Inbox initialization as a separate readiness check without `mq_auth_url`. Passing that check would prove real certificate authentication and authorized Inbox setup; it would not prove cross-agent AIP task exchange.

To complete the current AMQP Inbox-based Group workflow, obtain the supported production Group API URL and let the official Leader authorize the Group normally. Alternatively, use AIP Direct with an authentic reachable HTTPS Partner endpoint. Do not interpret constructor optionality as proof that the hosted broker grants new Group membership by default.
