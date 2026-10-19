# Native stop exit-code correction — 2026-10-19

Base: `d8ae1958aef411c61742f57ddb96e0de453ec885` in the independent `../checkout`.

`deploy/native.ps1` now checks the exit code immediately after Nginx `-s quit` and PostgreSQL `pg_ctl stop`. A nonzero result raises an error naming the component and exit code, before runtime state is saved. The existing application-family stop calls, component order, Nginx PID-file gate, and successful save/exit remain unchanged. A failure retains the original on-disk runtime records even if an earlier component was already stopped.

The existing `NativeStopEntryTests` PowerShell fixture was extended with three cases: Nginx success followed by database success; Nginx failure stopping before the database command; and database failure after Nginx success. Both failure cases require nonzero entry outcome and unchanged saved runtime records. The three pre-existing entry tests still cover app-family arguments, app-family failure, and the no-managed-app branch.

Executed scope:

```powershell
& '[local-venv]/Scripts/python.exe' -m unittest discover -s '[project]/tests' -p test_native_app_stop.py -k NativeStopEntryTests -v
```

Before correction: 6 tests ran, 2 failed because the two failing component stubs incorrectly produced entry exit 0. The original log is `before-fix-entry-fixtures.log.txt`.

After correction: all 6 tests passed. See `after-fix-entry-fixtures.log.txt`. `git diff --check` also exited 0.

These are actual PowerShell entry executions with function stubs replacing application/Nginx/PostgreSQL commands. They start no database, Nginx, business service, platform identity, or listener. They validate failure propagation and saved-state behavior; complete native business startup/H00/shutdown remains the separate unexecuted scope described in `../review/deployment-review.md`.

No Git commit was created. Only `deploy/native.ps1` and `tests/test_native_app_stop.py` were changed by this task in the checkout. The independent work on AMP code belongs to the parent task and is not included in this correction.
