# Bound acceptance plan preparation

This task-specific helper reuses the existing worker, formal E1 and F12/E5
file-only preparers and persisted-plan validators. It has no experiment execution
option. Wait until the agent image build succeeds and this checkout's source and
deployment inputs are frozen before using it.

Pass the actual successful build result with `--image-result`. The helper requires
integer build/inspection exits of zero, a terminal build process, the exact new
image reference and a full immutable `sha256:` image ID. A failed build result
cannot generate plans.

The default invocation validates the inputs without writing plans. Add `--prepare`
only for file preparation. The helper requires both the fixed plan root and result
root to be absent. Partial preparation is retained and cannot be overwritten.

Private plan root: `checkout/runtime/private/acceptance-plans-20261019/`.
Future result root: `checkout/eval/results/platform/acceptance-20261019/` (not created
by this helper). Safe summaries are written beside this README only after all 22
plans pass the existing validators.

The run-review table orders the first eight distinct cases before the remaining
14 repeats. All runs must be serial because they share the same seven identities
and deployment. E1-a has three interruption points × three repeats; E1-b has three
information methods × three repeats; E1-c has three same-process suspend/revival
plans; F12/E5 is one case with its existing missing-key control.

No authorization JSON is generated. `AUTHORIZATION-EXPECTED-FIELDS.md` documents
the existing runner contract for a separate later authorization step. Prepared
plans, armed worker files and a successful image build do not establish runtime
ownership, platform delivery, image-import attestation or experiment success.

The five guard checks import only this helper's Python standard-library code.
They do not import project preparers, read identity profiles or run subprocesses.
