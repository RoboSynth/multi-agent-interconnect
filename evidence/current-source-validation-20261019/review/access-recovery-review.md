# Access recovery independent source review

Reviewed the current uncommitted implementation against the requested contract: same AIC, original journal/path, no business callback replay, confirmed worker stop before an offline recovery container, failure retained while resource restoration continues, and explicit frozen plan/authorization binding. This was a read-only review; no behavior tests, Docker commands, platform connections or resource changes were run.

## Finding requiring correction

**P2 — An existing empty file can be initialized and reported as an original-journal recovery.**

At `incident/recover_access.py:33`, `is_file()` is the only precondition on the purported original journal. `DurableAccessEmitter.start_sync()` then executes `CREATE TABLE IF NOT EXISTS owner/attempts` and inserts an owner when `SELECT ... FROM owner` has no row. Consequently a pre-existing zero-byte file, empty SQLite database or otherwise unowned compatible database at the expected filename is initialized under the requested identity and can return `status=recovered` with zero rows. Presence of a pathname is insufficient evidence that this was the original same-AIC journal. No business result is forged, but the recovery receipt can falsely satisfy the original-journal gate.

Before opening a writable emitter, require a read-only SQLite inspection of the existing schema and exactly one owner tuple matching the expected AIC and canonical JSONL path. Missing/empty owner state must fail without changing the original bytes. A valid owned journal with no attempts can remain valid. Add bounded cases for an empty file, empty SQLite database and absent/duplicate owner rows, retaining the original bytes on refusal. This recommendation does not change the normal emitter's initialization behavior for ordinary workers.

## Contracts supported by the inspected source

- The recovery helper imports the durable emitter only; it reads `bridge.json` directly and does not construct MCP servers, read env files, load signing keys, call tools or connect to AIP. It checks the explicit expected AIC/name/directory and resolves the access path under the owned state root.
- A valid previously owned journal remains governed by the durable emitter's persisted AIC/canonical-log-path binding. Recovery emits immutable stored records or `OutcomeUnconfirmed`, preserving missing response/duration; no success payload or business callback is created.
- Controller restoration validates the current owned database workers, stops their exact container IDs, reinspects, requires the same IDs and non-running state, then invokes recovery. Commands use the frozen image ID, `--network none`, read-only root filesystem, dropped capabilities and no-new-privileges; no `/experiment` mount is passed to recovery.
- The original domain AMP directory from the frozen profile is used, rather than a new experiment-worker directory. The per-role state volume and profile are reused. Individual role failures are recorded and the loop continues; normal workers and business restoration are then attempted. The runner's `access_recovery_error_class` makes an incomplete recovery fail the case even if final H00 passes.
- `--recover-access` is represented explicitly in prepared plans and in their effects. Validation requires a real boolean; authorization requires an exact dictionary, matching plan SHA and `recover_access=True` when enabled. Old plans without this property cannot silently acquire the recovery action; merely passing the CLI flag on execute does not enable it independently of the plan.
- Source freezing includes `incident/recover_access.py`, both through the general `incident` source snapshot and the new `DOMAIN_SOURCE_FILES` entry. The deployed-domain source attestation therefore also requires the new recovery implementation.

## Additional observations

- The recovery state volume is checked for a single `/state` volume and a project-name prefix. Comparing its exact `Name` with `self.original[service]` would make “original volume” explicit, including partial-startup restoration paths. Current successful-start paths also retain exact experimental container IDs and validate the overlay's volume graph, so this is a strengthening recommendation rather than a demonstrated new wrong-volume execution.
- The recovery method docstring says “no ... keys”, but it bind-mounts the entire domain directory, which normally contains keys/env files. The helper does not read them and the container has no network. Say “does not load keys” or mount only the required `bridge.json` if the intended claim is that keys are unavailable to the container.
- Tests inspected cover real fixture hard exits, immutable replay, identity/path refusal, live writer refusal, strict plan/auth booleans, stop→offline recovery→normal restart ordering, and role-failure continuation. Runner-level classification tests were being handled by root; they were not rerun or assumed complete by this review. The empty/unowned-journal finding is not covered by the inspected cases.

## Source snapshot

SHA256 values at review capture (before requested fixes):

| File | SHA256 |
| --- | --- |
| `incident/recover_access.py` | `b363111af8f35c2e8ee6bf9b009dac0eee70447bab9fb1f5003ac57019e589e4` |
| `eval/platform_resume_experiment.py` | `16d65fa54d45d52727f8cd328ec78b27e40e04674c1e960cc6c036de45d68d2e` |
| `eval/targets.py` | `33133b738adf50eadf482c411482b629f642b1dc084782465b9735695b8ca21d` |
| `tests/test_access_recovery.py` | `289d16d88f61ea82a3d26c0de7dd91f99df6094e264ebfe480b24ea93ac704ee` |

The overall platform recovery claim remains unverified until a newly prepared, explicitly authorized real run exercises the feature. No historical missing rows are repaired by these offline changes.
