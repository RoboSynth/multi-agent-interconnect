# Access recovery independent review, revision 2

Read-only reinspection after root's corrections. No tests were rerun and no project/platform/business processes were started. The original review remains intact at `access-recovery-review.md` (SHA256 `ddad6071fdcb8ed0615d4243edee9e23c4b6b7a5d6a3c874e8bff3cf579e0af3`).

**The initial P2 finding is resolved in the inspected source.** `recover()` now opens the existing SQLite journal with `mode=ro` and `timeout=0`, checks exactly one matching AIC/canonical-log-path owner row, and requires the existing attempts schema before starting the writable durable emitter. Missing tables, an empty file, absent/duplicate owner rows, mismatched identity/path or mismatched columns fail before normal journal initialization. The connection is explicitly closed. A live exclusive owner still prevents access, and a legitimate owned empty journal can remain valid.

The additional scope recommendations are also addressed: recovery's `/state` volume name must now equal the exact original worker volume, in addition to the project-prefix check. The method description now states that it does not open resource tools/credential files; it no longer claims the domain bind mount contains no keys.

The existing stop→same stopped container IDs→network-disabled recovery→normal resource restoration ordering, immutable/unconfirmed-outcome semantics, strict plan/effects/auth SHA binding, source binding and failure classification remain supported by this source review. No new definite code finding was identified within the requested scope. This conclusion is a bounded source review, not a real platform recovery result.

## Evidence inspected

- `recovery-evidence/domain-recovery-final.log.txt`: six DomainRecoveryTests report OK, including empty-file/unowned-database refusal and unchanged bytes. SHA256 `db52f5d913fdb4f466c0a812d3b14946cfc79df4099069a22575a161d8ba2cc3`. Root reported the corresponding actual terminal exit 0, chunk `c35618`.
- `recovery-evidence/controller-recovery-final.log.txt`: five RecoveryControllerTests report OK, including refusal to mount a different project-prefixed state volume. SHA256 `33bf0d6a543e62fda90f8b2291a475cfc22a6265c4077418b6e7838bc5359e2e`. Root reported the corresponding actual terminal exit 0, chunk `07cc1e`.
- The earlier `recovery-evidence/run-2/summary.json` reports 52 passing selected methods and binds an older source snapshot. It must not be used alone to claim that the subsequent read-only-owner/exact-volume changes were tested; the later bounded logs above address those changes. Runner classification was handled by root separately.

## Source binding correction and current capture

The original review's `recover_access.py` hash was captured concurrently with root applying the owner fix. Its table lists `b363111...`, which belongs to the corrected file, although the P2 reasoning came from the earlier source read (terminal chunk `8dddbd`) that had only `journal_path.is_file()`. Treat that original hash as a capture-time value, not a pre-fix snapshot binding. The old body is also identifiable in the earlier 52-method summary as SHA256 `fa57dca4503440946b2b76555ed970dd319910afc47786d6960ef74b6e91c3b8`. This revision records the distinction without rewriting the original review.

Current inspected SHA256 values:

| File | SHA256 |
| --- | --- |
| `incident/recover_access.py` | `b363111af8f35c2e8ee6bf9b009dac0eee70447bab9fb1f5003ac57019e589e4` |
| `eval/platform_resume_experiment.py` | `1c682bd45000108569e50a824891f82ad6be9be64ef7ad6bcac5033dbde5842e` |
| `eval/targets.py` | `33133b738adf50eadf482c411482b629f642b1dc084782465b9735695b8ca21d` |
| `tests/test_access_recovery.py` | `642b0c19e7fe8c9245b9d88e4a3c00751677cd18e01f16952bf2668fffe230fb` |

Real acceptance still requires a new frozen image/plan and an authorized run. Historical missing access rows remain historical evidence; this implementation and the reviewed tests do not repair those cohorts.
