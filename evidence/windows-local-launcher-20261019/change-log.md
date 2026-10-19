# Windows native startup lifecycle correction

Base: `9cc215f5f3b4`.

- `deploy/local-up.ps1` now launches `tools/workbench_host.py --launch` through its existing `Run-Python` failure gate. The success URL is emitted only after the host command exits successfully.
- `tests/test_local_launcher.py` routes the real PowerShell entry through isolated Python and PowerShell resource stubs, checks the host arguments, checks configuration rejection before resource stages, and checks host rejection without a success URL.
- `docs/本地开发环境与操作_20261018.md` requires Windows x64 and CPython 3.12 AMD64 for the native path, gives a copyable implementation/version/architecture/bitness check, and uses the same session nonce stop workflow for the segmented and one-command entries.

`LocalStartupEntryTests`: 7 methods passed, 0 failures/errors/skips, 11.019 seconds. Actual execution exit code `0`, terminal tool chunk `2d4ac1`. The full log is `local-startup-entry-tests.log`; source and log hashes are in `source-ready.json`.

Scoped whitespace validation exited `0` (tool chunk `0bd965`). Only the three listed source files were edited by this task. The old `tools/start_workbench.ps1` script was preserved. No database, business service, model or platform was started. Legacy launcher tests and the host suite were not rerun.

The first execution request did not run because the approval-review transport disconnected. Its raw local tool failure is retained in `test-attempt-1-tool-failure.json`; the same reviewed action was retried and completed successfully. `test-execution.json` is the local execution receipt and contains local machine paths; use the relative-path `source-ready.json` for publication.
