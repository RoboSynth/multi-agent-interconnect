# Windows collector preparation verification

The two supplied collector suites first passed unchanged on Windows: 23 preparation tests plus 8 Linux-preparation contract tests, 31 total. Logs are retained as `preparation-first-run.txt` and `linux-collector-first-run.txt`.

A real PowerShell `-CheckOnly -Kinds heartbeat,access` invocation then failed because the team's `.venv/Scripts/python.exe` does not exist on this machine. This first failure is retained as `powershell-first-run.txt`. The wrapper now accepts `-PythonExecutable` with an existing interpreter, keeps the previous default, and reports a direct missing-environment error. A Windows integration test runs the actual PowerShell wrapper with the existing development interpreter and synthetic log filenames; it passed without a collector or network operation.

The Linux staged plan previously described observing all six types even when only two were selected. Its observation field now names the selection, and the plan/CLI report the selected output count and routes. State labels intentionally exclude selection: the same sources and mode preserve the same offset volume and per-type database names during expansion.

After these corrections, 25 preparation tests and 8 Linux-preparation tests passed, 33 distinct tests total. Final logs: `preparation-final-run.txt`, `linux-collector-final-run.txt`.

Offset behavior verified here is configuration behavior: existing selected type DB paths remain unchanged when expanding types; Kafka defaults `Read_From_Head False`; explicit historical collection remains available. New-only behavior requires no prior offset for a newly added type. An existing DB resumes its old offset, and Linux stdout preparation still defaults to historical reads. Fluent Bit consumption, Kafka delivery, platform ingestion, and live container labels were not exercised.
