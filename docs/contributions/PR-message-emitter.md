# Serialize MessageEmitter writes per resolved file path

Synchronous and asynchronous MessageEmitter instances can append to the same file from different
threads. Against official commit `94077d10b336bfdb9a7d68e4859390bf44a67a27`, an isolated
concurrency regression produced malformed JSON, and a separate regression showed a relative
destination following a later working-directory change.

The change resolves the destination at construction and shares a lock for the normalized path.
The lock covers opening, writing, flushing and closing each record. Different files can write
concurrently. The guarantee applies within one process.

The two-file patch adds five focused regressions under `acps-sdk/tests/amp/`: path aliases and
working-directory changes, mixed synchronous/asynchronous writers, independent destinations,
schema/trace compatibility, and lock release after a write error. The two selected cases failed
on the unmodified current SDK (one assertion failure and one JSONDecodeError). All five passed
after the patch was applied in an isolated SDK-only tree; applied source bytes matched the
expected LF-normalized code. The five migrated test method ASTs match the original focused tests.
The existing three project integration checks are separate historical evidence.

From the upstream root, with Python 3.12:

```text
python -m pip install -e "./acps-sdk[amp-sign]"
python -m unittest discover -s acps-sdk/tests/amp -p test_message_emitter_concurrency.py -v
```

This patch excludes resumable changes, project business code, identities, credentials, logs and
runtime state. This is a PR draft; no public fork, branch or PR has been created.
