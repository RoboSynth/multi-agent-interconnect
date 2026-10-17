# ACS rejection research

The confirmed immediate requirement is a non-empty, accurate `provider` object. The submitted Partner ACS already contained `{}`; there is no evidence that the platform erased a populated provider in this attempt.

Public evidence agrees on provider being required:

- The current Registry public main JavaScript contains `ACS中Provider为必填项`.
- The official WIT trusted-registration guide says generated ACS must supply `provider`, and shows `organization` plus `country_code` as an example. This is an example, not a proven exhaustive production acceptance rule.
- The pinned public AgentProvider schema has optional fields and no `minProperties`. Therefore passing that schema does not prove compliance with the online admission service.

The exact rule identifier and exact rejection message were searched, with follow-up searches restricted by official domains. No relevant official explanation or implementation was found in the returned search results. The current public Registry main asset also does not contain the exact rule identifier. The remaining semantic review requirements are unknown.

Pinned backend source can replace provider with an approved identity/organization snapshot during approval, and can produce `{}` when no such records exist. That behavior is a possible later compatibility issue, but it must not be presented as the cause of this current rejection: this submission started empty, and creation preserves its supplied ACS in the inspected checkout.

The root agent separately observed a Leader rejection that also requires at least one valid Endpoint or webAppUrl. That is a different observed condition and should be handled using the actual intended transport and a genuine service address. Passing the Partner's provider check alone does not establish that the Leader endpoint requirement is met.

All source locators, certainty limits, request hashes, and search scope are recorded in `FINDINGS.json` and `EXCHANGES.json`. No platform state was changed.
