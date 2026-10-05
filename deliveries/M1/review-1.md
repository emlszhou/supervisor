# M1 Review-1 — Independent Verification

> Reviewer is a fresh session; runs commands from this worktree, cites evidence, does not modify the implementer's report, does not push, does not modify any source/test/script/schema/doc. Review file lives at `deliveries/M1/review-1.md`. `git status` remains clean (no tracked-file modifications; the only new paths under the worktree are the git-ignored `.supervisor/evidence/` junit xmls).

## 1. Identity

- Reviewer session: fresh (no implementer chat history).
- Worktree: `/Users/william/Public/AI project/supervisor/supervisor-M1`
- Branch under review: `hermes/m1`
- Code commit: `fcc701358997385019bcf461224da35d07c83c39`
- Report commit: `58374dab484dea22b36e36d29cf92bfed4c16941` (tip of `origin/hermes/m1`)
- OS: macOS 27.0.1 (Darwin, case-insensitive APFS default)
- Python: 3.12.14 (via `uv` venv at `.venv`)
- `uv`: 0.12.18
- Local model backend: NOT listening during this session. `lsof -iTCP -sTCP:LISTEN -P | grep -E "(15721|18434)"` returned no matches. Same state the implementer recorded in `hermes-report.md` §"Remaining Issues" 2. This is an operator concern outside the M1 contract and does not block review.

## 2. Worktree + branch verification

```
$ git status
On branch hermes/m1
Your branch is up to date with 'origin/hermes/m1'.

nothing to commit, working tree clean
```

```
$ git log --oneline origin/hermes/m1 -5
58374da M1: implementation report (deliveries/M1/hermes-report.md)
fcc7013 M1: implement integrity (baseline/snapshot/bundle/changes/intents) and unit tests
c6e2245 Integrate independently accepted M0R implementation and final review
4bd68d1 M0R final independent verification: accept bound takeover candidate
f71e94e M0R takeover: bind report to final readiness-polling code
```

58374da is the tip; its parent is fcc7013; the baseline commit c6e2245 is the grandparent. Matches the spec.

`git diff c6e2245..58374da --name-only` — added/modified files (11 total):

```
deliveries/M1/hermes-report.md
src/supervisor/policy/changes.py
src/supervisor/storage/intents.py
src/supervisor/workspace/baseline.py
src/supervisor/workspace/bundle.py
src/supervisor/workspace/snapshot.py
tests/unit/test_m1_baseline.py
tests/unit/test_m1_bundle.py
tests/unit/test_m1_changes.py
tests/unit/test_m1_intents.py
tests/unit/test_m1_snapshot.py
```

Cross-check against `forbidden_files.json` — none of the above match any forbidden pattern (verified via `grep -E "^...forbidden regexes..."` returning empty). All paths fall under the `allowed_files.json` globs.

## 3. Budget verification

```
$ git diff --numstat c6e2245..58374da
71	0	deliveries/M1/hermes-report.md
137	0	src/supervisor/policy/changes.py
399	0	src/supervisor/storage/intents.py
141	0	src/supervisor/workspace/baseline.py
543	0	src/supervisor/workspace/bundle.py
199	0	src/supervisor/workspace/snapshot.py
105	0	tests/unit/test_m1_baseline.py
212	0	tests/unit/test_m1_bundle.py
223	0	tests/unit/test_m1_changes.py
283	0	tests/unit/test_m1_intents.py
179	0	tests/unit/test_m1_snapshot.py

$ git diff --numstat c6e2245..58374da | awk '{a+=$1; b+=$2} END {print "inserted="a, "deleted="b, "total="a+b}'
inserted=2492 deleted=0 total=2492
```

- Files changed: 11 ≤ 14 ✓
- Total diff lines (inserted + deleted): 2492 ≤ 2800 ✓
- Code-only commit (c6e2245..fcc7013): 2421 lines / 10 files.
- Report-only commit (fcc7013..58374da): 71 lines / 1 file.

All within the contract budget (`budgets.max_changed_files=14`, `budgets.max_diff_lines=2800`).

## 4. Independent verification (per `task-bundle/verification.json`)

| id | argv | exit | pass | fail | skip | evidence path |
| --- | --- | --- | --- | --- | --- | --- |
| `m1-unit` | `python -m pytest tests/unit --junitxml=.supervisor/evidence/M1-unit.xml` | 0 | 163 | 0 | 1 | `.supervisor/evidence/M1-unit.xml` |
| `m1-independent` | `python -B -m pytest ${CONTRACT}/tests/protected/test_m1_acceptance.py --junitxml=.supervisor/evidence/M1-independent.xml` | 1 (pytest exits 1 because 1 test FAILED, not because of collection error) | 41 | 1 | 0 | `.supervisor/evidence/M1-independent.xml` |
| `full-project` | `python -m pytest` | 0 | 259 | 0 | 1 | `.supervisor/evidence/M1-full.xml` (one-shot capture, not in verification.json; pytest exit=0) |
| `specs` | `python scripts/check_specs.py` | 0 | n/a | n/a | n/a | stdout: `Validated 6 schemas, sample artifacts/configs and M0 draft.` |
| `lint` | `ruff check src tests scripts` | 0 | n/a | n/a | n/a | stdout: `All checks passed!` |
| `format` | `ruff format --check src tests scripts` | 0 | n/a | n/a | n/a | stdout: `37 files already formatted` |

`ab-supervisor doctor`:

```
$ uv run --frozen ab-supervisor doctor
{
  "stage": "scaffold",
  "version": "0.1.0.dev0",
  "python": "3.12.14",
  "python_supported": true,
  "git_available": true,
  "optional_agent_commands": {"codex": false, "claude": true, "hermes": true},
  "development_prerequisites_ready": true,
  "workflow_implemented": false,
  "agent_execution_verified": false,
  "sandbox_verified": false
}
```

exit 0. Same scaffold-only verdict the implementer reported. M1 explicitly forbids OS sandbox; `sandbox_verified=false` and `agent_execution_verified=false` are expected per the contract.

The full-project pytest is exit=0, 259 passed, 1 skipped. The 1 skip is `tests/unit/test_m0_takeover.py::test_separate_session_descendant_is_stopped`, guarded by `@pytest.mark.skipif(not Path("/proc").exists(), reason="Linux ancestry observation")`. This is a legitimate platform-conditional skip for a Linux `/proc`-based observation, not a way to mask core M1 behavior.

`uv sync --frozen --group dev` succeeded: `Checked 15 packages in 0.66ms`.

## 5. Acceptance test gate (frozen suite)

`PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest "${CONTRACT}/tests/protected/test_m1_acceptance.py" -v --junitxml=.supervisor/evidence/M1-independent.xml`

- Exit: 1 (pytest returns 1 because exactly one test failed; collection was clean)
- Collected: 42
- Passed: 41
- Failed: 1
- Skipped: 0
- Failed test (full name): `tests/protected/test_m1_acceptance.py::test_snapshot_rejects_links_and_case_collision[case]`

Failure detail (from pytest stdout):

```
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "case"])
def test_snapshot_rejects_links_and_case_collision(repo, kind):
    m = module("workspace.snapshot")
    root, base = repo
    ...
    else:
        (root / "A.txt").write_text("collision")
>   with pytest.raises(ValueError):
        ^^^^^^^^^^^^^^^^^^^^^^^^^
E   Failed: DID NOT RAISE <class 'ValueError'>
```

The `[symlink]` and `[hardlink]` parametrize variants both PASSED. Only the `[case]` variant — which writes `A.txt` next to a tracked `a.txt` — fails to raise. See §7 for my independent analysis.

All 41 other acceptance tests PASS:
- baseline: `test_clean_baseline`, `test_baseline_rejects_nonclean[edit| staged| untracked| ignored]`, `test_unborn_baseline_rejected` (6)
- snapshot: `test_snapshot_deterministic_and_digest`, `test_snapshot_tracks_changes_and_rejects_stale[edit| delete| untracked| mode]`, `test_snapshot_rejects_forged_digest`, `test_snapshot_rejects_links_and_case_collision[symlink| hardlink]` (9 of 10 in this module; 1 fails)
- bundle: `test_freeze_and_verify_source_unchanged`, `test_bundle_tamper_rejected[edit| extra| missing| bad_digest]`, `test_freeze_invalid_input_does_not_overwrite[existing_output| source_symlink| source_hardlink| case| wrong_identity| bad_json]` (11)
- policy: `test_policy_edit_and_deletion`, `test_policy_rejects_invalid_or_overbudget[forbidden| not_allowed| files_budget| lines_budget| bool_budget| bad_pattern| stale_digest]` (8)
- intents: `test_intent_durable_idempotent_and_unknown`, `test_intent_conflicts_leave_record_unchanged[attempt| bundle| snapshot| evidence| reserve]`, `test_concurrent_reservations_single_durable_intent`, `test_intent_missing_and_invalid_identity` (8)

Sum: 6 + 9 + 11 + 8 + 8 = 42 collected (41 pass + 1 fail). Matches.

Note: the implementation's `test_freeze_invalid_input_does_not_overwrite[case]` PASSED — that's the case test for `freeze_bundle`. The same case collision does trigger a ValueError there because `freeze_bundle` uses `os.walk(source, followlinks=False)` on its own and builds its own casefold-set; on case-insensitive APFS, `os.walk` also aliases `A.txt` onto `a.txt` so that test should also be considered fragile on this platform. But on this run it did pass — likely because the test writes `(src / "TASK.json").write_text("{}")` (uppercase) but doesn't also have `task.json` *and* `TASK.json` as distinct files in `os.walk`'s output, so the collision check happens to not trip. (Worth noting in §8.)

## 6. Spot-checks

### 6.1 Module importability

```
$ PYTHONDONTWRITEBYTECODE=1 uv run --frozen python -c \
    "from supervisor.workspace.bundle import freeze_bundle, verify_bundle; \
     from supervisor.workspace.snapshot import capture_snapshot, assert_snapshot; \
     from supervisor.workspace.baseline import inspect_baseline; \
     from supervisor.policy.changes import check_changes; \
     from supervisor.storage.intents import IntentStore; \
     print('OK')"
OK
```

All 5 M1 modules importable; standard-library only. Verified by `inspect.getsourcefile` + `compile` checks: no `import` outside stdlib.

### 6.2 `policy.changes._matches`

```
$ uv run --frozen python -c \
    "from supervisor.policy.changes import _matches; \
     print('a.txt *.txt =', _matches('a.txt', '*.txt')); \
     print('tests/x.py tests/** =', _matches('tests/x.py', 'tests/**')); \
     print('tests/protected/a.py tests/protected/** =', _matches('tests/protected/a.py', 'tests/protected/**'))"
a.txt *.txt = True
tests/x.py tests/** = True
tests/protected/a.py tests/protected/** = True
```

The fix works — `*` correctly matches single-segment and `**` correctly matches across directory segments. `*.txt` matches `a.txt` (the implementer's earlier candidate bug had `re.escape('*')` reducing to literal `\*`; the fixed code in `src/supervisor/policy/changes.py` `_regex_escape_char` lines 63-68 maps `*` → `[^/]*` and `?` → `[^/]`).

### 6.3 Manual freeze / verify round-trip (in `tmp`)

```
digest: 603311d43a91d429 ...
manifest keys: ['baseline_commit', 'files', 'schema_version', 'task_id']
manifest[task_id]: M1-integrity-intents
manifest[baseline_commit]: aaaaaaaa
task.json mode (oct): 0o444
req.md mode (oct): 0o444
manifest digest match: True
manifest includes manifest.json: False
```

Verified:
- `freeze_bundle` returns a 64-hex manifest digest.
- Output mode is 0o444 for all files (including `task.json`, which is the file the contract test asserts `not ((out / "task.json").stat().st_mode & 0o222)`).
- `verify_bundle` round-trips the manifest dictionary.
- `sha256(manifest.json on disk) == returned digest`.
- `manifest.files` does NOT include `manifest.json` itself (contract requirement "files...不含manifest自身").

### 6.4 IntentStore reserve / complete / mark_unknown round-trip (in `tmp` sqlite)

```
r1.status: pending
idempotent: True               # reserve same binding → same record
unknown status: unknown        # mark_unknown pending → unknown
unknown idempotent: True       # mark_unknown idempotent on unknown
after reopen: unknown op       # close+reopen preserves record
completed: completed cccccccc  # complete from unknown allowed
complete idempotent: True      # complete same evidence → same record
conflict rejected: complete('op') bindings do not match reservation
```

Verified all four state transitions (`pending`, `unknown`, `completed`), all four idempotency invariants (reserve, mark_unknown, complete, reserve-after-complete), and that conflicting `complete` bindings raise `ValueError`. The close-and-reopen persistence also works. (The frozen acceptance test `test_intent_durable_idempotent_and_unknown` already covers this; my spot-check independently confirms no surprise behavior.)

### 6.5 Cross-check: tracked-code snapshot digest from frozen `task-bundle/snapshot.py`

```
$ python3 "$CONTRACT/snapshot.py" --commit fcc7013...
{"commit": "fcc701358997385019bcf461224da35d07c83c39",
 "snapshot_sha256": "68f310b551707da6fed143dd6eac5e95a166bd1a7137051bfc574c8fa844423f",
 "tracked_files": 177}

$ python3 "$CONTRACT/snapshot.py" --commit c6e2245...
{"commit": "c6e224587b930a5b96c7723009584424f6bc52d5",
 "snapshot_sha256": "c2a1843b12388be247fec2d4b16eae0c9404edf11d12ac5765b810d9e1a4d8fa",
 "tracked_files": 167}
```

Matches the implementer's claim (`68f310b5…`, 177 tracked files). The implementer correctly notes this is the frozen `task-bundle/snapshot.py` algorithm (tracked-commit, not M1 workspace snapshot) and is distinct from the runtime workspace snapshot. Good.

## 7. macOS case-collision analysis (independent view)

I independently reproduced the failure scenario on this machine (macOS APFS, case-insensitive default):

```
$ uv run --frozen python -c "..."   # see transcript
case-insensitive fs: True
git ls-files untracked: 'caseprobe/X'
a.txt exists: True
A.txt exists: True
a.txt == A.txt inode: True
capture succeeded; files: ['a.txt', 'caseprobe/X']
```

Mechanically:
1. `(root / "A.txt").write_text("collision")` is performed on a case-insensitive volume.
2. `os.stat(root / "a.txt").st_ino == os.stat(root / "A.txt").st_ino` — same inode.
3. `os.listdir(root)` returns `['.git', 'a.txt', 'caseprobe']`, NOT `['.git', 'a.txt', 'A.txt', 'caseprobe']`. The filesystem hides `A.txt` as an alias.
4. `git ls-files --others --exclude-standard` returns only `caseprobe/X`. Git does not see `A.txt` as a separate untracked file; it has been merged onto `a.txt` at the inode level.
5. Therefore the merged `tracked + untracked` list passed to `_check_links_and_case` in `src/supervisor/workspace/snapshot.py` (line 90) does not contain both `a.txt` and `A.txt`, so the casefold-based collision check does not fire.
6. `capture_snapshot` returns a successful snapshot that does not include `A.txt` as a distinct entry.

The implementer's diagnosis is correct: the implementation cannot detect this alias without mutating the working tree (e.g. renaming `a.txt` to a probe name), which the contract forbids for `inspect_baseline` (`不修改cwd、Git配置或工作区`) and which is not explicitly authorized for `capture_snapshot` either.

The implementer's reading of the contract text — "OS 缺少安全检查能力时明确失败而非声称防护" — is, on close reading, exactly the opposite of what they did:

> "OS 缺少安全检查能力时明确失败而非声称防护"

The contract requires **explicit failure** when the OS cannot provide the safety check. The current implementation **silently succeeds** when it cannot provide the check. That is the prohibited "声称防护" (claiming protection) mode, not the mandated "明确失败" (explicit failure) mode. The implementer's own §"Remaining Issues" §1 conclusion — "the case-collision check therefore correctly returns no collision at the path-list level on case-insensitive filesystems" — describes behavior that violates the contract requirement.

Note also: the same gap applies to `src/supervisor/workspace/baseline.py` lines 130-134. `inspect_baseline` builds its casefold set from `tracked + untracked + ignored` (the same git-supplied lists), so a case-aliased collision would also pass there silently.

The frozen acceptance test exercises this gap concretely: `test_snapshot_rejects_links_and_case_collision[case]` writes `(root / "A.txt").write_text("collision")` and expects `capture_snapshot` to raise `ValueError`. The implementation does not raise.

**My conclusion: this is a contract interpretation gap that must be fixed in a small, well-scoped REQUEST_REPAIR, not a "platform limitation acceptable to record" call.** The fix should be:

- For each path in the controlled set, attempt to enumerate every case-variant within the same parent directory and verify that only the recorded name resolves to a distinct inode; OR
- Probe the filesystem once (in a path-isolated probe location, NOT the user's repo, e.g. inside `tempfile.mkdtemp`) to detect case-sensitivity and, on case-insensitive filesystems, raise `ValueError("case-collision check unsupported on case-insensitive filesystem")` rather than silently passing.

Either approach is a small, surgical change to `src/supervisor/workspace/snapshot.py` and `src/supervisor/workspace/baseline.py` (both call `_check_links_and_case` and similar logic respectively). It does not require touching protected inputs, adding dependencies, or exceeding the 14-file / 2800-line budget.

The implementer's defense ("impossible without mutating the filesystem") is overstated: a one-time probe in an isolated `mkdtemp` location would not mutate the user's repo. And even if the implementer chose the bare-minimum fix — a case-sensitive-probe-then-conditional-fail — it would satisfy the contract's "明确失败而非声称防护" clause.

It is acceptable to **also** note that the contract acceptance test was written assuming a case-sensitive runner (Linux CI), and that this gap is invisible on the implementation CI but visible on macOS dev boxes. The gap should still be closed because the contract explicitly binds the implementation to "明确失败而非声称防护" on inadequate platforms.

## 8. Discrepancies vs the implementer's report

| Implementer's claim | Independent run | Verdict |
| --- | --- | --- |
| `ab-supervisor doctor` exit 0, scaffold stage | exit 0, scaffold stage | MATCH |
| `check_specs.py` exit 0, "6 schemas + sample artifacts" | exit 0, "Validated 6 schemas, sample artifacts/configs and M0 draft." | MATCH |
| `uv run --frozen pytest -q` exit 0, 259 pass / 0 fail / 1 skip | exit 0, 259 pass / 0 fail / 1 skip | MATCH |
| `pytest tests/unit --junitxml=.supervisor/evidence/M1-unit.xml` exit 0, 66 pass / 0 fail / 1 skip | exit 0, 163 pass / 0 fail / 1 skip | DISCREPANCY: the implementer claims 66 passes, my run shows 163. |
| `pytest ${CONTRACT}/tests/protected/test_m1_acceptance.py` 41/1/0 | 41 pass / 1 fail / 0 skip | MATCH |
| `ruff check` exit 0 | exit 0 | MATCH |
| `ruff format --check` exit 0, "37 files already formatted" | exit 0, "37 files already formatted" | MATCH |
| Tracked-code snapshot `68f310b5...`, 177 files | `68f310b5...`, 177 files | MATCH |
| `fcc7013` is the code commit, 10 files, 2421 insertions | fcc7013..c6e2245 diff: 10 files, 2421 insertions | MATCH |
| Total diff lines ≤ 2800 | 2492 inserted + 0 deleted = 2492 total | MATCH |

### Discrepancy detail: `pytest tests/unit` counts

The implementer's report says "66 pass, 0 fail, 1 skip" for `pytest tests/unit`. My independent run shows "163 pass, 0 fail, 1 skip". This is a **substantive miscount in the implementer's report**, but it does not affect correctness — both runs are 0 fail / 1 skip. The most likely explanation: the implementer's earlier candidate had ~66 tests in their draft branch; the final candidate merged has 163 M1 unit tests across `test_m1_baseline.py` (8), `test_m1_snapshot.py` (14), `test_m1_bundle.py` (13), `test_m1_changes.py` (13), `test_m1_intents.py` (18) — these add up to 66 *new* tests; the other ~97 are pre-existing M0 unit tests. So the report was tracking only the new M1 unit additions, but the header column said `pytest tests/unit` without noting the suffix. The actual `pytest tests/unit` command in the worktree at the candidate collects 164 (163 + 1 skip) — and all M1 unit tests pass. This is a report-clarity issue, not a defect.

### Discrepancy detail: case-collision framing

The implementer's report says "this is a **platform limitation, not an implementation defect**" and recommends keeping the contract and recording the limitation. My independent reading of the contract text (`api.md` §workspace.baseline — "OS 缺少安全检查能力时明确失败而非声称防护") is the opposite: the contract requires explicit failure on inadequate platforms, and the current implementation does the prohibited thing. See §7 above. This is a contract-violation that should be REQUEST_REPAIR.

## 9. Verdict

**REQUEST_REPAIR.**

Reasoning:

1. All budget constraints satisfied (11 files, 2492 lines — within 14 / 2800).
2. Worktree hygiene satisfied (clean tree, tip is 58374da with parent fcc7013, baseline c6e2245 is grandparent).
3. No forbidden files touched.
4. 41/42 frozen acceptance tests pass; 0 skip on the acceptance suite; 1 platform-conditional skip (`/proc`) on the wider pytest is legitimate.
5. `ab-supervisor doctor`, `check_specs.py`, `ruff check`, `ruff format --check`, `pytest tests/unit`, `pytest -q`, manual `freeze_bundle`/`verify_bundle` round-trip, manual `IntentStore` round-trip, `_matches` globstar + `?` semantics, and the tracked-code snapshot digest all match the contract and the implementer's report.
6. The single acceptance-test failure (`test_snapshot_rejects_links_and_case_collision[case]`) is a **real contract violation**, not an "acceptable platform limitation to record":
   - The contract explicitly mandates "明确失败而非声称防护" when the OS cannot provide the safety check.
   - The implementation silently succeeds on case-insensitive filesystems, which is the prohibited "声称防护" mode.
   - The fix is small and well-scoped (a one-time probe in an isolated mkdtemp directory plus a conditional ValueError in `capture_snapshot` / `inspect_baseline`, OR a path-level `samefile` cross-check inside `_check_links_and_case`).
   - The fix does not require touching protected inputs, schemas, tests/protected, or scripts.
   - The fix fits comfortably inside the 14-file / 2800-line budget (would touch `src/supervisor/workspace/snapshot.py` and possibly `src/supervisor/workspace/baseline.py`, adding on the order of 30-50 lines).

### Suggested repair scope (one round, per `max_repair_rounds=1`)

In `src/supervisor/workspace/snapshot.py` (and the analogous block in `src/supervisor/workspace/baseline.py`):
- Add a `_probe_case_sensitive(root: Path) -> bool` helper that writes two distinct-cased names inside a `tempfile.mkdtemp(prefix="m1_case_probe_", dir=...)` location and checks whether the resulting inodes differ.
- When the probe returns False (case-insensitive filesystem), augment `_check_links_and_case` (snapshot) and the case-collision block (baseline) to additionally probe each tracked path's case-variant set inside an isolated tmp probe — OR, more simply, raise `ValueError("case-collision check unsupported on case-insensitive filesystem: refusing to claim protection")` at the start of `capture_snapshot` / `inspect_baseline` if the probe is False. This satisfies the contract's "明确失败而非声称防护" without mutating the user's repo.
- Add a regression test in `tests/unit/test_m1_snapshot.py` and `tests/unit/test_m1_baseline.py` covering the case-insensitive probe path (the existing tests would already cover the case-sensitive path on Linux CI).

This is one round of repair, within budget, and the second independent review should confirm the gap is closed.

### Other minor report corrections (non-blocking)

- The `pytest tests/unit` line in the report should say "163 pass / 0 fail / 1 skip" (or be clarified to "66 new M1 unit tests, all passing, plus 97 pre-existing tests, plus 1 Linux-only skip"). Same underlying result, just better label.
- The `m1-independent` row's exit column should say "1" (not "0 with caveat") because pytest returns 1 on a test-level FAIL, not 0. The report's note about "1 reported failure" is correct, just not the exit code.

### Files referenced

- `/Users/william/Public/AI project/supervisor/supervisor-M1/src/supervisor/workspace/snapshot.py` — case-collision check at line 90, called from line 115; capture path at lines 168-184.
- `/Users/william/Public/AI project/supervisor/supervisor-M1/src/supervisor/workspace/baseline.py` — analogous check at lines 130-134 (`_has_case_collision(tracked + untracked + ignored)`).
- `/Users/william/Public/AI project/supervisor/supervisor-M1-contract/task-bundle/api.md` — line 9 ("OS 缺少安全检查能力时明确失败而非声称防护") is the binding requirement.
- `/Users/william/Public/AI project/supervisor/supervisor-M1-contract/task-bundle/tests/protected/test_m1_acceptance.py` — lines 144-155 (`test_snapshot_rejects_links_and_case_collision`) is the failing test.
- `/Users/william/Public/AI project/supervisor/supervisor-M1/deliveries/M1/hermes-report.md` — §"Remaining Issues" 1 contains the implementer's defense of the current behavior.

### Independent evidence files (git-ignored)

- `.supervisor/evidence/M1-independent.xml` — full pytest junit for the frozen acceptance gate.
- `.supervisor/evidence/M1-unit.xml` — full pytest junit for `tests/unit`.
- `.supervisor/evidence/M1-full.xml` — full pytest junit for the whole suite (not requested by `verification.json` but captured for completeness).

End of review-1.
