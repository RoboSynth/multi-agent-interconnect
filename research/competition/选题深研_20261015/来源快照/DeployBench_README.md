# DeployBench: Benchmarking LLM Agents for Research Artifact Deployment 

A benchmark of 51 research-artifact deployment tasks. Each task pairs a published paper with its source repository, plus a hidden verifier that checks whether an environment was set up correctly. Tasks live under `mytasks/<task_name>/`; `papers.csv` is the index with metadata for filtering and analysis.

## `papers.csv` columns

| Column | Type | Meaning |
|---|---|---|
| `task_name` | string | Internal task ID, format `<abbrev>_<venue><yy>` (e.g., `adalora_iclr23`). Some papers appear in two variants distinguished by a `_cpu` / `_gpu` suffix. |
| `paper_title` | string | Title of the paper or project the artifact comes from. For tasks without a paper (`mmseg_github24`, `openfoam_github25`) the project's canonical name is used. |
| `difficulty` | `easy` / `medium` / `hard` | Manual judgment based on the number of setup steps, severity of under-documented dependencies, and amount of debugging observed during ground-truth construction. |
| `agent_time` | int (seconds) | Time budget to give an agent for environment construction, including its thinking, web lookups, and command execution. Roughly proportional to `difficulty`. |
| `type` | `ai` / `sys` / `scientific` | Domain of the artifact. `ai` covers ML/NLP/CV papers, `sys` covers OS/database/security/PL papers, `scientific` covers physics, chemistry, bioinformatics, CFD, speech, and other scientific computing. |
| `pre2020` | `yes` / `no` | Whether the paper was published before 2020. Pre-2020 artifacts often depend on EOL toolchains (Python 2, TF1, Torch7, OpenSSL 1.0, etc.) and are typically the hardest to reproduce on a modern host. |
| `gpu` | `yes` / `no` | Whether the task requires an NVIDIA GPU. Mirrors `vm_type` in `task.json` (`1gpu` → yes, `1cpu` → no). |
| `main_language` | string | The primary implementation language of the artifact, taken from explicit statements in the paper where available (e.g., "implemented in 16,600 lines of JavaScript"). Helper scripts in other languages are not counted as primary. |
| `qemu` | `yes` / `no` | Whether the task requires booting a QEMU virtual machine to run the verifier. All `yes` entries are OS-kernel papers (`kflex`, `nros`, `orbit`, `theseus`, `ward`) where the experiment cannot run on the host kernel. |
| `needs_external_artifact` | `yes` / `no` | Whether the verifier requires downloading a dataset, model checkpoint, or pretrained weights from outside the source repository (HuggingFace, public dataset URLs, etc.). Ordinary pip/apt packages and source archives bundled in `code.zip` do not count. |
| `patch_code` | `yes` / `no` | Whether `setup_reference.sh` applies a compatibility patch needed to make the artifact compile/run on a modern host, either by modifying source/build files or by injecting a compatibility shim into the runtime environment (e.g., writing CUDA-SDK compat headers, monkey-patching a removed PyTorch API, sed-editing a TF1 import to TF2, adding a `.pth`-loaded Python shim). External configuration (apt mirrors, DB conf, build prefs), helper scripts written into a fresh location that do not alter runtime compatibility, and dataset preprocessing do not count. |


## Per-task files

Each `mytasks/<task_name>/` directory contains:

- `task.json` — runtime metadata (paths, vm_type, agent_time, deploy_prompt for hints to the agent).
- `setup_reference.sh` — oracle environment-setup script, reproducible from a clean VM.
- `verify.sh` — runs the minimal verifiable experiment selected from the paper, captures stdout/stderr to `output.log`.
- `task_parser.py` — checks `output.log` for fatal errors and confirms expected artifacts exist; emits a JSON verdict.


## Demo website 

https://deploybench.vercel.app/

## Citation

```
@misc{wang2026deploybenchbenchmarkingllmagents,
      title={DeployBench: Benchmarking LLM Agents for Research Artifact Deployment}, 
      author={Yuanli Wang and Yaoyao Qian and Yue Zhang and Hanhan Zhou and Jindan Huang and Tianfu Fu and Qiuyang Mang and Huanzhi Mao and Wenhao Chai and Wendong Fan and Liqiang Jing},
      year={2026},
      eprint={2606.05238},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2606.05238}, 
}
```

