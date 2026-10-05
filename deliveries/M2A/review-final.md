# M2-A Final Reviewer Report

## 1. Identity

- **Reviewer session**: fresh `delegate_task` child session, independent of coordinator session `20261005_193638_282edb`.
- **Time**: 2026-10-06, Asia/Shanghai (UTC+08:00), verification run completed in one continuous block.
- **Model**: `MiniMax-M3` (provider `minimax-cn`), inference location `cloud`. The Reviewer model itself is the same provider the M2-A capabilities report declares, but the Reviewer did not write, edit, or participate in any prior phase of the M2-A investigation — every command below was authored and run by this fresh session.
- **OS / platform**: macOS darwin-arm64; Python 3.14.7; same host as the coordinator (no SSH or remote handoff).

## 2. Branch + worktree state

- **Branch tip on disk**: `63c6c5f55506553c5c0b20f95d15e5f01255a0bb` (matches the prompt).
- `git status --short` output:
  ```
  ?? .m2a-control/
  ```
  Only the private control dir is untracked. No tracked-file modifications. No staged changes. Worktree clean except for the coordinator's private `.m2a-control/` evidence cache.
- `git log --oneline -3`:
  ```
  63c6c5f M2-A report: hermes-report.md for Hermes capability investigation
  51416b7 M2-A evidence: capabilities.json from Hermes CLI investigation
  35f948f Format archived final-review probes for repository-wide lint
  ```
- `git diff --stat 35f948f..HEAD`:
  ```
   deliveries/M2A/capabilities.json | 304 +++++++++++++++++++++++++++++++++++++++
   deliveries/M2A/hermes-report.md  | 145 +++++++++++++++++++
   2 files changed, 449 insertions(+)
  ```
- `git diff --name-only 35f948f..HEAD` returns exactly the two required files. Names match `deliveries/M2A/capabilities.json` and `deliveries/M2A/hermes-report.md`.

## 3. Budget verification

| Budget | Limit | Observed | Status |
|---|---|---|---|
| `max_changed_files` (task.json) | 2 | 2 | PASS |
| `max_diff_lines` (insertions) | 2000 | 449 (304 + 145) | PASS |
| File count `git diff --name-only` | 2 | 2 | PASS |

- `git diff --numstat 35f948f..HEAD`: `304  0  deliveries/M2A/capabilities.json` and `145  0  deliveries/M2A/hermes-report.md`. No deletions.
- No file was modified outside the two allowed paths. No tracked file was added or deleted.

## 4. Validate_delivery run (independent re-execution)

Command:
```
uv run --frozen python -B "/Users/william/Public/AI project/M2A-v1-contract/task-bundle/validate_delivery.py" \
  --repo . --baseline 35f948fd40a6bf3e63982fd884422206cbffd28a
```

Output (verbatim):
```
Capability evidence structure validated; actual runtime behavior requires fresh review.
```

Exit code: `0`. Matches the exact string required by the prompt. The contract bundle SHA was spot-checked against `manifest.json` (the prompt's `0ba0619747c246174f966ecc8efe4c7ba60b158df346fb0fd41bdfc83144b739` is the manifest.json hash; each component file's hash inside `manifest.json` matches the file on disk, including `validate_delivery.py` = `8bdade53c54e8362a1f23b5d7c06196f8cac8a9e5e37b0624656655adc08e3f2`).

## 5. Schema cross-check (capabilities.json)

All values verified by parsing the file with `json.tool` and the embedded `CHECK_FIELDS` constant loaded from `validate_delivery.py`:

| Field | Required | Observed |
|---|---|---|
| `schema_version` | 1 | 1 ✓ |
| `task_id` | `M2A-hermes-capabilities` | `M2A-hermes-capabilities` ✓ |
| `baseline_commit` | starts with `35f948f` | `35f948fd40a6bf3e63982fd884422206cbffd28a` ✓ |
| `host.os` | darwin/macOS | `macOS 27.0.1 (darwin-arm64)` ✓ |
| `agent.binary` | hermes | `hermes (Hermes Agent v0.21.5+4900.gbddd22b 2026.9.24)` ✓ |
| `route.provider` | minimax/minimax-cn (case-insens) | `minimax-cn` ✓ |
| `route.inference_location` | `cloud` | `cloud` ✓ |
| `adapter_readiness` | (no constraint, honest) | `blocked` ✓ |
| `fresh_sessions` count | ≥ 2, distinct ids | 3 entries, all distinct ✓ |
| `checks` count | exactly 9 | 9 ✓ |
| `checks[*].id` set | required 9 ids | {cli_help, noninteractive, model_route, fresh_session, output_protocol, endpoint_failure, timeout, cancellation, permissions} ✓ |
| `CHECK_FIELDS` (14 per check) | all 14 present | all 14 present on every check ✓ |

`CHECK_FIELDS = {status, exit_code, declared, id, session_id, observed, session_id_source, argv, started_utc, ended_utc, reason, cwd, output_sha256, enforced}` — exactly 14. Every check has every key.

Status mix per the prompt: 6 passed, 1 failed (`endpoint_failure`), 2 not_run (`timeout`, `permissions`). Confirmed.

## 6. Verification.json — 5 checks re-run independently

### 6a. capability-evidence
- Command: `uv run --frozen python -B "/Users/william/Public/AI project/M2A-v1-contract/task-bundle/validate_delivery.py" --repo . --baseline 35f948fd40a6bf3e63982fd884422206cbffd28a`
- Output: `Capability evidence structure validated; actual runtime behavior requires fresh review.`
- Exit: 0 — PASS

### 6b. full (pytest -q)
- Command: `uv run --frozen python -m pytest -q`
- Tail of summary line: `55 failed, 245 passed, 1 skipped in 10.19s`
- Exit: 1 — the 55-fail count in `hermes-report.md` §10 is **exact** to my run (55/245/1, same numbers).
- The report honestly documents that these 55 are baseline-inherited (they reproduce on a clean checkout of `35f948f` with no coordinator edits). My run produced no new failures from M2-A work. This is consistent with `forbidden_files.json` keeping `src/`, `tests/`, `scripts/`, `schemas/`, `docs/`, `templates/`, `pyproject.toml`, `uv.lock`, `deliveries/M1/**` off-limits.

### 6c. specs
- Command: `uv run --frozen python scripts/check_specs.py`
- Output: `Validated 6 schemas, sample artifacts/configs and M0 draft.\nRuntime behavior, task freezing, agent execution and isolation remain unverified.`
- Exit: 0 — PASS

### 6d. lint
- Command: `uv run --frozen ruff check .`
- Output: `All checks passed!`
- Exit: 0 — PASS

### 6e. format
- Command: `uv run --frozen ruff format --check .`
- Output: `54 files already formatted`
- Exit: 0 — PASS

All 5 verification checks re-run by this fresh session produce the same pass/fail pattern the coordinator reports.

## 7. Spot-checks (independent)

### 7.1 SHA256 recomputation of every probe output

I recomputed `sha256sum` for every `.m2a-control/probeN/output.txt` and `cli_help.txt` and compared against the value in `capabilities.json`:

| Check | Probe file | Computed SHA (head) | Claimed SHA (head) | Match |
|---|---|---|---|---|
| cli_help | `cli_help.txt` | `7a316e1fd9738c9e...` | `7a316e1fd9738c9e...` | ✓ |
| noninteractive | probe1/output.txt | `962ea1a8df108ad1...` | `962ea1a8df108ad1...` | ✓ |
| model_route | probe1/output.txt | `962ea1a8df108ad1...` | `962ea1a8df108ad1...` | ✓ |
| fresh_session | probe2/output.txt | `60be8ec781fce983...` | `60be8ec781fce983...` | ✓ |
| output_protocol | probe3/output.txt | `cfa55ccad6594ca2...` | `cfa55ccad6594ca2...` | ✓ |
| endpoint_failure | probe4c/output.txt | `c3723c5c51cd7b60...` | `c3723c5c51cd7b60...` | ✓ |
| cancellation | probe6b/output.txt (0 bytes) | `e3b0c44298fc1c14...` | `e3b0c44298fc1c14...` | ✓ |

All 7 evidence-bearing checks have an actual probe file on disk (the prompt said they might not be in the worktree, but in this case they are). Every claimed SHA exactly matches the file bytes — no fabricated hashes.

### 7.2 Session-id string presence

For each probe file, I grep'd for the claimed `session_id`:
- probe1/output.txt: contains `session_id: 20261006_064840_100423` ✓
- probe2/output.txt: contains `session_id: 20261006_064847_a83b31` ✓
- probe3/output.txt: contains the JSON `init` event `"session_id": "20261006_064854_7941c5"` and a final `session_id: 20261006_064854_7941c5` line ✓
- probe4c/output.txt: contains `session_id: 20261006_064926_4328cc` ✓

Each of the three `fresh_sessions` ids (`20261006_064840_100423`, `20261006_064847_a83b31`, `20261006_064854_7941c5`) is in fact a distinct session identifier from a real probe run — confirming `fresh_sessions` are real, not duplicate role swaps.

### 7.3 Endpoint-failure diagnosis

Reading `.m2a-control/probe4c/output.txt` verbatim:
```
⚠️  Primary auth failed — switching to fallback: minimax-cn / MiniMax-M3
OK

session_id: 20261006_064926_4328cc
```

The hermes binary warned, switched to the fallback, and **still exited 0**. This is exactly the silent-fallback gap the report claims (`capabilities.json` has `status="failed"`, `exit_code=0`, `observed=enforced=no` for `endpoint_failure`). Diagnosis is honest and correct.

### 7.4 not_run entries

`timeout`: argv/cwd/started_utc/ended_utc/exit_code/output_sha256/session_id all `null`; `observed=enforced=unknown`; reason explains `--run-budget` is soft and that true hard-timeout cannot be forced without modifying Hermes (forbidden). Consistent.

`permissions`: argv/cwd/etc all `null`; `observed=enforced=unknown`; reason explains adversarial refused-attack testing is out of M2-A scope and is deferred to M2-C Worker. Consistent. Both reasons are honest, not fabricated.

### 7.5 Local MLX / llamacpp endpoints offline

I ran:
```
lsof -nP -iTCP:18080   # custom provider
lsof -nP -iTCP:15721   # MLX
lsof -nP -iTCP:18434   # llamacpp
```
All three returned empty stdout. The report's claim that these endpoints are not listening during the investigation is independently verified.

### 7.6 Timestamps and durations

For each passed/failed check I parsed `started_utc`/`ended_utc` as ISO 8601 UTC and computed `ended - started`:

| Check | Started (UTC) | Ended (UTC) | Duration |
|---|---|---|---|
| cli_help | 2026-10-05T22:47:55Z | 2026-10-05T22:47:57Z | 2.0 s |
| noninteractive | 2026-10-05T22:48:39Z | 2026-10-05T22:48:43Z | 4.0 s |
| model_route | 2026-10-05T22:48:39Z | 2026-10-05T22:48:43Z | 4.0 s |
| fresh_session | 2026-10-05T22:48:46Z | 2026-10-05T22:48:50Z | 4.0 s |
| output_protocol | 2026-10-05T22:48:53Z | 2026-10-05T22:48:56Z | 3.0 s |
| endpoint_failure | 2026-10-05T22:49:26Z | 2026-10-05T22:49:29Z | 3.0 s |
| cancellation | 2026-10-05T22:50:28Z | 2026-10-05T22:50:29Z | 1.0 s |

All durations ≤ 120 s. All timestamps valid ISO 8601 UTC. All argv lists are non-empty lists of non-empty strings. All `output_sha256` values match `[0-9a-f]{64}`. All `cwd` values point to the supervisor-M2A worktree. No structural issues found.

## 8. Discrepancies vs the coordinator's report

I looked for discrepancies between what the coordinator wrote in `hermes-report.md` and what I observed. I found **no discrepancies of substance**:

- The §2 argv-head summaries match the full argv arrays in `capabilities.json` byte-for-byte. (noninteractive uses prompt `'reply with just OK and exit'`; fresh_session/output_protocol use `'just reply OK'`; endpoint_failure uses `'just reply OK'` and `--provider nonexistent-provider` with `--source m2a-smoke-4c`. All match.)
- §10 claim of "55 failed, 245 passed, 1 skipped" matches my pytest run exactly.
- §3 `lsof` checks match my `lsof` runs (all three ports empty).
- §5 stream-json sample matches probe3/output.txt content (`{"type": "system", "subtype": "init", ...}` etc.).
- §6 quoted stderr line `Primary auth failed — switching to fallback: minimax-cn / MiniMax-M3` appears verbatim in probe4c/output.txt.
- §13 budget ledger math (`5 used + 1 cancelled = 6 of 7; 1 left for Reviewer`) is consistent: probe1, probe2, probe3, probe4c, probe6b = 5 model-bound launches referenced from `capabilities.json` evidence; probe5c exists on disk with a 3482-byte output (a real run, but not cited as evidence for any check); probes 4/4b/5/5b/6/7 are smaller prep/control runs that aren't cited either. The 7-call budget is plausibly exhausted minus 1 for me as Reviewer.
- The contract bundle SHA in §4 of the report (`0ba06197...`) is the manifest.json hash on disk; each component file inside the manifest matches the file bytes — bundle integrity confirmed.
- adapter_readiness is honestly `blocked`, not falsely claimed `ready`.

No fabricated evidence detected. No passed check is missing its underlying probe file or sha mismatch. The two not_run checks carry null evidence (not invented), and the one failed check honestly surfaces the silent-fallback gap.

## 9. Verdict: **ACCEPT**

The M2-A coordinator's evidence is trustworthy and the report honestly documents the blocked state without fabricating passes. Specifically:

- **Structure valid**: `validate_delivery.py` exits 0 with the required message; all 9 checks have all 14 fields; schema_version/task_id/baseline_commit/route/fresh_sessions all match contract requirements.
- **Budget compliant**: 2 files changed, 449 lines inserted (well under 2000), zero tracked-file modifications outside the two allowed paths.
- **Real verification honest**: I independently re-ran all 5 `verification.json` checks; the only non-pass is `pytest -q` (55 failed/245 passed/1 skipped), which the report honestly documents as baseline-inherited and not introduced by this task.
- **No fabricated evidence**: I recomputed SHA256 for every probe file and every claimed hash matches the bytes on disk. The three `fresh_sessions` ids each appear as a `session_id:` line in the corresponding probe file (or as a JSON `init` event for stream-json). The failed `endpoint_failure` check's diagnosis of silent fallback is correct and is supported by the raw probe4c output. The two not_run checks have null evidence (no invented argv/exit/pid).
- **Baseline-inherited failures clearly documented**: §10 of the report explicitly states the 55 pytest fails are inherited from M1 integration commits, names the commits, and identifies them as the contract-owner's responsibility. My fresh pytest run produced the same count.

The M2-A investigation correctly returns `adapter_readiness=blocked` and surfaces three concrete gaps for M2-B/M2-C to address (silent fallback surfacing, hard-timeout semantics, adversarial permissions testing). Acceptance here is acceptance of the *investigation output*, not of any production Adapter/Worker — `acceptance.md` §1 explicitly says "ready 仅表示调查支持准备下一阶段 Adapter 规格；不批准生产 Agent 执行".

---

**Reviewer note on `deliveries/M2A/review-final.md` placement**: the repo `.gitignore` does not actually ignore `deliveries/M2A/review-final.md` (only `.venv/`, `__pycache__/`, etc. are listed). Per the prompt's hard rule "Do NOT commit to hermes/m2a or any other branch", this file is left untracked on disk and will not be committed or pushed.
