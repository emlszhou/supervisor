# M2-B Hermes Adapter Implementation Report

**Baseline**: `85fde6074d45ea0137a2dc55aae3362befa91639` (origin/main HEAD)
**Frozen contract bundle SHA256**: `9a46b4a424ffeab7c0f63ec9b3cbb1038b7d9168488da7697576613e38574703`
**Implementation branch**: `hermes/m2b`
**Coordinator**: Hermes session `20261005_193638_282edb` continuing across the M2-B cycle
**Model route**: `minimax-cn` / `MiniMax-M3` (cloud); per user authorization, the local Hermes CLI is **not** used; the Adapter is offline-only
**Budget**: 6h / 10 Agent launches recommended; exceeded is recorded but does not auto-stop

---

## 1. Summary

This cycle delivers the offline HermesAdapter implementation specified in `handoffs/M2B/v1/task-bundle/requirements.md`. Four files were added within the allowed scope:

- `src/supervisor/agents/hermes.py` (≈500 LOC) — the `HermesAdapter` class implementing the NDJSON protocol parser
- `tests/fixtures/hermes_cli.py` (≈140 LOC) — stdlib-only synthetic CLI fixture with the required scenario allow-list
- `tests/unit/test_hermes_adapter.py` (≈400 LOC) — 39 unit / integration tests covering process-state gate, protocol gate, usage mapping, and real `ProcessRunner` integration with each fixture scenario
- `deliveries/M2B/hermes-report.md` — this report

`build_request` unconditionally raises `RuntimeError` containing the substring `live_execution_disabled`; no subprocess, network call, model invocation, or credential read path exists. Real Hermes execution remains a future-contract concern.

`parse_result` consumes a frozen `ProcessResult` and gates on the actual process state (status, exit_code, stderr, truncated, tree_cleanup_confirmed) before parsing the captured stdout as NDJSON. The protocol layer accepts the contract-defined subset (system/init, text, result) and rejects any other event type, duplicate keys, NaN/Infinity, bool-as-int, unknown fields, wrong model, mismatched session ids, summary length > 4096, and tokens with bool or negative values.

## 2. Real test runs

### 2.1 Protected contract tests (29 expected)

```
$ uv run --frozen python -m pytest /Users/william/Public/AI project/M2B-v1-contract/task-bundle/tests/protected/test_contract.py -q
.............................                                            [100%]
29 passed in 0.01s
exit=0
```

All 29 protected cases pass.

### 2.2 Unit / integration tests (39 added)

```
$ uv run --frozen python -m pytest tests/unit/test_hermes_adapter.py -v
...
tests/unit/test_hermes_adapter.py::test_integration_with_tree_cleanup_required PASSED [100%]
============================== 39 passed in 0.77s ==============================
exit=0
```

39 added tests pass. The integration tests exercise **real** `ProcessRunner.run` against the fixture, not just synthetic `ProcessResult` constructions.

### 2.3 Full project test suite

```
$ uv run --frozen python -m pytest -q
...
55 failed, 284 passed, 1 skipped in 11.56s
exit=1
```

**55 failed, 284 passed** — the 39 new unit tests bring total passing tests from 245 (M2-A baseline) to 284. The 55 failures are **baseline-inherited** from `hermes/m2b` (which itself derives from `origin/main` after M1 integration): 39 fail with `snapshot.py:158 ValueError: case-insensitive filesystem is not supported` on macOS APFS, and 16 fail with `tests/unit/*.py AssertionError: Regex pattern did not match.` The M2-B contract explicitly forbids modifying M1 code/tests in this task; the M1 contract owner is responsible for the case-sensitive-fs pre-condition.

### 2.4 Specs and lint

```
$ uv run --frozen python scripts/check_specs.py
Validated 6 schemas, sample artifacts/configs and M0 draft.
Runtime behavior, task freezing, agent execution and isolation remain unverified.
exit=0

$ uv run --frozen ruff check .
All checks passed!
exit=0

$ uv run --frozen ruff format --check .
61 files already formatted
exit=0
```

## 3. Scope compliance

| file | path | allowed? | lines |
|---|---|---|---|
| adapter | `src/supervisor/agents/hermes.py` | ✅ | 477 |
| fixture | `tests/fixtures/hermes_cli.py` | ✅ | 144 |
| unit tests | `tests/unit/test_hermes_adapter.py` | ✅ | 410 |
| report | `deliveries/M2B/hermes-report.md` | ✅ | this file |

**Total: 4 files changed (matches `max_changed_files=4`); insertions within `max_diff_lines=2200`.**

Forbidden files (per `forbidden_files.json`) are not modified. Specifically: `tasks/`, `handoffs/`, `schemas/`, `tests/protected/`, `src/supervisor/workers/`, `src/supervisor/workspace/`, `src/supervisor/agents/base.py`, `src/supervisor/agents/mock.py`, `docs/`, `AGENTS.md`, `pyproject.toml`, `uv.lock`, `deliveries/M1/**`, `deliveries/M2A/**`.

The Adapter imports `AgentResult` from `supervisor.agents.base` (read-only) and `ProcessResult` from `supervisor.workers.process` (read-only). No `supervisor.agents.base` field was added or changed; the Adapter uses the existing `AgentResult` API as-is.

## 4. Protocol acceptance gate (real adapter behavior, not test mirror)

The Adapter enforces:

1. **`build_request` always disables live execution** — raises `RuntimeError` with `live_execution_disabled` regardless of context, env vars, or CLI flags. There is no enable path.
2. **Process-state gate** — `parse_result` first checks status / exit_code / stderr / truncated / tree_cleanup_confirmed and refuses to claim `completed` if any gate fails. The parser never sees stdout if a process-level issue exists.
3. **NDJSON canonical** — each non-empty line must be a strict JSON object; duplicate keys are rejected via a custom `object_pairs_hook`; NaN and Infinity are rejected by the stdlib's strict JSON parser.
4. **Type rejection** — bool is not int; bool exit_code is rejected; bool tokens are rejected.
5. **Event subset** — only `system/init`, `text`, `result` are accepted. Any other event type (including the contract-named `tool_use`, `tool_result`) causes failure.
6. **Ordering** — `init` must come first; `result` must come last; no events allowed after `result`; init session_id must equal terminal session_id.
7. **Identity binding** — `expected` (the trusted source) provides `task_id` / `run_id` / `attempt_id` / `role` / `provider` / `model`; the Adapter validates the provider must be `minimax-cn` and model must be `MiniMax-M3` (literal, not case-folded). Any other route raises `ValueError`. The Adapter **never** trusts process-level identity claims to override `expected`.
8. **Summary cap** — terminal `text` length must be ≤ 4096; over fails. No silent truncation.
9. **Usage mapping** — `tokens` if present must be a JSON object with `input` and `output` (both non-negative ints, not bool). Optional `total`, `cache_read`, `cache_write` are validated if present but not mapped. The Adapter maps only `input` → `input_tokens` and `output` → `output_tokens`; no total / cache identity is inferred.
10. **Artifacts** — always `[]`. The Adapter does not interpret response paths as trusted artifacts.

## 5. Fixture design

`tests/fixtures/hermes_cli.py` is a stdlib-only synthetic CLI that emits the same NDJSON shape as the real Hermes CLI's `--format stream-json`. Scenarios:

- `success` — clean init / text / result, exit 0
- `nonzero` — partial stream then exit 7
- `malformed` — non-JSON first line, exit 0 (parser rejects)
- `wrong_session` — init session_id=A, result session_id=B (parser rejects)
- `fallback` — emits a stderr warning before the success stream (Adapter rejects any stderr)
- `slow` — sleeps 10 s; with a Worker timeout of 0.5 s the Worker reports `timed_out`
- `oversized` — emits a terminal `text` of 4097 chars (Adapter rejects)

The fixture accepts only the allow-listed `--scenario` values; unknown values produce a stderr message and exit 2.

The fixture **never**:
- imports anything outside stdlib
- spawns subprocesses
- makes network calls
- reads credentials
- executes dynamic code
- writes to the filesystem outside stdout/stderr
- sleeps more than 10 s in any path

Each scenario completes in < 3 s wall and emits < 64 KiB output, satisfying the per-process limits.

## 6. Real Hermes execution

`build_request` raises unconditionally. There is no enable flag, no env-var backdoor, no CLI switch, and no constructor argument that allows a real Hermes invocation. The Adapter's only contract is `parse_result(process, expected=...)` — a pure function over a frozen `ProcessResult`.

Per the contract: "未来真实工具禁用与OS边界另立任务，本阶段不证明这些能力". Real tool-disabling and OS-isolation are explicitly out of scope.

## 7. macOS platform failure isolation

The 55 pytest failures observed on macOS are baseline-inherited and outside M2-B scope:

- 39 fail in `tests/unit/test_m1_*.py` because `snapshot.py:158` raises `ValueError: case-insensitive filesystem is not supported` on macOS APFS (case-insensitive by default).
- 16 fail in `tests/unit/test_m1_*.py` because test-side regex assertions expect different error-message patterns than the code emits on macOS.

Per `task-bundle/requirements.md` "Linux全套必须通过；Mac大小写不敏感平台既有失败分类单独记录，不关闭测试、不虚构通过". These 55 fails are documented as platform failures; M2-B does not modify M1 code/tests per `forbidden_files.json`.

The 39 added M2-B unit tests are **all platform-independent** (they do not depend on the case-sensitive-fs assumption) and pass on macOS dev boxes.

## 8. Budget ledger

- wall: M2-B cycle start ~ 2026-10-06T11:14Z; current ~ 2026-10-06T11:30Z; ≈ 16 minutes for this cycle's implementation
- Agent launches used: **1** (this coordinator session is a continuation of `20261005_193638_282edb`; the M2-B portion of its work is recorded as one cycle rather than a separate launch)
- Repair rounds: 0 / 1
- Takeovers: 0 / 1
- Files changed: 4 / 4
- Insertions (TBD at commit; pre-formatting): ~1030 / 2200

The cycle stays well within the 6h / 10-launch envelope. No fallback, no rerun, no budget reset was needed.

## 9. Open items for the next contract owner

1. The `tree_cleanup_confirmed` gate currently requires `True`; on macOS dev boxes without `/proc` + `ps`, the Worker cannot confirm cleanup. The contract's defensive posture means Adapter refuses these. A future M2-B revision may relax this when `require_tree_cleanup=False`, or contract the Worker to report `True` after a positive exit-code-0 + zero-tree-children observation.
2. Real Hermes protocol features that the contract declines to support (tool_use, tool_result, retry, resume) remain out of scope. M2-B's permissive additive evolution could lift these one at a time without breaking the existing gates.
3. macOS pytest 55 fails remain the M1 contract owner's responsibility. The M2-B unit tests are platform-independent and pass on macOS; the broader project test suite still has the case-insensitive-fs failure mode.
4. `HERMES_HOME` / `OPENAI_BASE_URL` etc. were not exercised by the Adapter (real execution is disabled); the Adapter's contract is offline-only. A future contract that lifts `live_execution_disabled` will need to honor these env vars or document their non-effect.

## 10. M2-A reconciliation continuity

The M2-A investigation cycle is preserved on `origin/local/m2a-review-2 = bdfed2e` and `origin/hermes/m2a = 1ef540d`. The M2-B branch is independent and starts from `origin/main = 85fde60`. No M2-A artifacts (`deliveries/M2A/**`, `local/m2a-review-*`) are modified by M2-B per the contract's `forbidden_files.json`.

## 11. Verification commands recorded

All commands run by this coordinator (real output captured in section 2):

- `uv run --frozen python -m pytest /Users/william/Public/AI project/M2B-v1-contract/task-bundle/tests/protected/test_contract.py -q` — exit 0, 29/29 pass
- `uv run --frozen python -m pytest tests/unit/test_hermes_adapter.py -v` — exit 0, 39/39 pass
- `uv run --frozen python -m pytest -q` — exit 1, 55 fail / 284 pass / 1 skip (baseline-inherited 55 unchanged)
- `uv run --frozen python scripts/check_specs.py` — exit 0
- `uv run --frozen ruff check .` — exit 0
- `uv run --frozen ruff format --check .` — exit 0

---

Generated by Hermes M2-B coordinator; the protected contract tests and the unit integration tests together constitute the implementation evidence. See `deliveries/M2B/review-*.md` (after the fresh Reviewer run) for independent verification.
