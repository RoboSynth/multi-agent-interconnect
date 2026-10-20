# Windows tests for the proposed M2v3 rerun

The code was tested from the team checkout on Windows; no real experiment services were started and no business or algorithm code was edited by this test task.

| Run | Interpreter | Tests | Failures | Errors | Skips | Exit |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| affected | repository `.venv`, Python 3.12.14 | 66 | 0 | 0 | 0 | 0 |
| full | repository `.venv`, Python 3.12.14 | 740 | 0 | 2 | 2 | 1 |
| report-revision | existing `.venv-dev`, Python 3.12.14 | 25 | 0 | 0 | 0 | 0 |

The original full result is preserved in `full.json` and `full.log`. Both errors were `ModuleNotFoundError: matplotlib`: one prevented discovery of the nine `test_evaluation_report_integrity` methods, and one affected `test_stability_bundle`. One skip was the report figure dependency gate. The other skip was the explicit opt-in fixture in `test_native_app_stop`; it remains skipped.

The report revision reused the already installed report dependencies in the existing dev environment rather than installing or copying packages into the repository environment. Both interpreters are Python 3.12.14. It ran only `test_evaluation_report_integrity.py` (9), `test_stability_bundle.py` (11), and `test_evaluation_reports.py` (5). All 25 passed, including the formerly failing paths and the report figure test. Dependency versions are recorded separately. No full suite was repeated.

After replacing the 17 original report discovery entries (including one failed-import placeholder) with these 25 actual report methods, the evidence covers 748 distinct test methods: 747 passed and one explicit opt-in fixture skipped. This is the combination of one full run and one scoped dependency revision, not a newly executed 748-test full run. The affected 66 tests overlap the full run and are not added to that distinct total.

Commands (PowerShell, with UTF-8 enabled and working directory explicitly set to the team repository):

```powershell
Set-Location -LiteralPath 'D:\AI + 开源\team-repository-multi-agent-interconnect'
$env:PYTHONUTF8 = '1'
& 'D:\AI + 开源\team-repository-multi-agent-interconnect\.venv\Scripts\python.exe' 'D:\AI + 开源\team-repository-multi-agent-interconnect\evidence\p5-local60-r2-20261020\windows-tests\run_windows_tests.py' affected
& 'D:\AI + 开源\team-repository-multi-agent-interconnect\.venv\Scripts\python.exe' 'D:\AI + 开源\team-repository-multi-agent-interconnect\evidence\p5-local60-r2-20261020\windows-tests\run_windows_tests.py' full
& 'D:\AI + 开源\incident-pilot\artifacts\p0-continuation-20261019\checkout\.venv-dev\Scripts\python.exe' 'D:\AI + 开源\team-repository-multi-agent-interconnect\evidence\p5-local60-r2-20261020\windows-tests\run_windows_tests.py' report-revision
```

Each JSON result records the exact interpreter, command, timestamps, elapsed time, counts, error tracebacks and skip reasons. The matching log retains test names and outcomes.