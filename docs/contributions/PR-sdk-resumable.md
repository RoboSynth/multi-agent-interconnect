# Add resumable group tasks, ordering protection and optional AMP access hooks

A delayed `working` TaskResult can move the projected state backwards after an
`awaiting-completion` result has arrived. Interrupted resource operations also need durable
evidence before a replacement partner can safely continue. This change preserves task-result
history while protecting the projection, and adds optional persistence and takeover adapters.

`TaskJournal` records intent, attempts and result events; `CoordinatorTerm` persists coordinator
epochs. A shared domain `OperationLedger` checks fences and argument digests, returns cached
applied results and requires inspection of uncertain effects before retry. `TakeoverManager`
uses discovery, capability confirmation, membership readiness and authenticated fence advancement
before dispatching a resume payload in a normal Start command. A delayed state still reaches
listeners, and a newer Continue can return the task to working.

Optional group access hooks record the first Start for each session/task/direction within each
client middleware instance and its LRU lifetime. Complete, Get and redelivery still follow normal
protocol handling. This counter describes task attempts; it is not a permanent or cross-process
deduplication guarantee.

The upstream-root patch changes 13 files: the existing 12 SDK changes plus three ordering
regressions moved into `acps-sdk/tests/aip/`. It excludes the independent MessageEmitter fix.
It was checked and applied to an isolated copy of official commit
`94077d10b336bfdb9a7d68e4859390bf44a67a27`; all expected changed-file bytes matched, and the
three migrated tests passed while importing only that copy's SDK. The unchanged 25 resumable
checks retain their historical component evidence; they were not rerun for this packaging step.
The existing six end-of-file blank-line warnings are retained in the validation record.

From the upstream root, with Python 3.12:

```text
python -m pip install -e "./acps-sdk[amp-sign]"
python -m unittest discover -s acps-sdk/tests/aip -p test_task_ordering.py -v
```

Primary and backup writers must share the same domain ledger. Fences constrain participating
actors; arbitrary external tools are not promised exactly-once effects. A separate formal AMQPS
healthy window reconciled 12 captured tasks with 24 endpoint access records, without missing or
extra entries. That healthy check does not establish formal fault takeover or Monitor ingestion.
Formal NEW7 E1 has not run. This is a PR draft; no public fork, branch or PR has been created.
