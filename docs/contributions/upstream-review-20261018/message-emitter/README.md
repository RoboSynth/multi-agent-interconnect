# MessageEmitter concurrent append — current upstream review

Target: official ACPs-community `94077d10b336bfdb9a7d68e4859390bf44a67a27`, fetched into a separate local review tree. The SDK's 129 selected source files equal the pinned 3985 snapshot after CRLF-to-LF normalization (2 byte-identical, 127 newline-only). Both original CRLF patch apply-check failures remain recorded.

This patch is exactly the original upstream-path patch with CRLF replaced by LF; tokens, ASTs and paths are unchanged. Apply-check, actual application and expected LF byte comparisons succeeded on its own fresh official-source copy.

Two selected regressions actually ran against the unpatched current source; their real failure/error breakdown is in validation.json. All five focused tests actually passed after applying this patch. The lock covers normalized paths within one process; no cross-process guarantee is claimed. Resumable changes are excluded.

From the upstream root containing acps-sdk/:

```text
git -c core.autocrlf=false apply --check acps-sdk-message-emitter.patch
git -c core.autocrlf=false apply acps-sdk-message-emitter.patch
```

Use the SDK's declared dependencies. Formal NEW7 E1 has not executed. No Issue, PR, external fork or production change was made.
