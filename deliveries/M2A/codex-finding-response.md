# M2-A Reconciliation: Response to Codex Cloud Audit

**Branch**: `local/m2a-review-1` (created from `35f948f` baseline; pushed status pending operator authorization)
**Source audit**: `origin/codex/m2a-review-1 = 079a6f1fb33a54f20f6cc16f9b4f6b6413812e6e` (verdict=blocked, 8 findings)
**Coordinator**: Hermes session `20261005_193638_282edb` (continued via Feishu machine handoff)
**Cycle close**: 2026-10-06T07:00Z

This document is the **drafted response** to the 8 Codex findings. It is written for operator review. None of these edits have been pushed to `origin/local/m2a-review-1`; this branch is local-only and awaits authorization per Codex §3 + §4.

---

## Finding-by-finding response

### M2A-R1-tools — blocking: 缺少 smoke 前禁用工具及无秘密合成目录的控制证据

**Acknowledgment**: The M2-A Hermes tool calls (probe1-probe6b) ran in the default Hermes configuration without an explicit `--no-tools` / `--safe-mode` flag. The `--in /tmp` flag was passed, but `cwd` for the chat was the implementation worktree, not `/tmp`. This is a real control gap.

**Reconciliation options for operator**:

- **Option A (recommended, no model probes)**: declare `permissions.enforced=no` in `capabilities.json` for every check that ran without tool restriction, and reword `hermes-report.md` §11 ("Adapter contract recommendations") to state that Adapter must layer its own `--safe-mode` or equivalent by default. This is a documentation-only change to the existing `hermes/m2a` branch and does NOT require a new model probe.
- **Option B (requires new budget)**: re-run the 6 smokes with `--ignore-rules --safe-mode --in /tmp` argv. Requires 1 new agent launch budget.

**Operator decision required.**

### M2A-R1-budget — blocking: 共享启动账本未完成核对

**Acknowledgment**: The previous `hermes-report.md` §13 budget ledger listed "5 + 1 = 6" launches. Real launches were 1 coordinator continuation + 6 model-bound smokes + 1 reviewer = **8 launches**, exceeding the 7-launch contract budget by 1. The discrepancy is acknowledged and recorded in `.m2a-control/terminal-summary.md` §2 (committed as terminal state to the private control directory).

**Reconciliation**: This finding is closed by documentation only (the corrected ledger is in `terminal-summary.md`). No new launches required.

### M2A-R1-timeout — major: 实际执行的 timeout 被写为 not_run

**Acknowledgment**: Probe5c (session_id `20261006_064947_c93927`, argv `hermes chat ... --run-budget 1 --max-turns 1`) actually ran for ~15 seconds and returned a 500-word essay with exit 0. The probe5c output file is at `.m2a-control/probe5c/output.txt` (sha256 `30f1521d352caaa410e548788c6f504f537a96aebebd9447b4b08a65e39ae2d3`, 3482 bytes). I classified the check as `not_run` because `--run-budget 1` did NOT trigger a hard timeout — but the probe DID run, with observed behavior that contradicts the `not_run` semantic.

**Reconciliation option for operator**:

- **Option A (recommended, no model probes)**: amend `capabilities.json` `timeout` check to status=`failed`, observed=`yes` (probe ran), enforced=`no` (no hard timeout triggered), with reason quoting the actual probe5c argv + exit 0 + 15s wall + sha256 of the output. This is a documentation-only change to `hermes/m2a`.
- **Option B (requires new budget)**: re-run probe5c with `--max-turns 0` and a tight `--run-budget 1` to demonstrate that the wrap-up budget is observed by the model in 1s. Unlikely to materially differ from probe5c.

**Operator decision required.**

### M2A-R1-cancel — major: 取消退出码与回收结论证据不足

**Acknowledgment**: Probe6b sent SIGINT to PID 60784 and observed `ps -p` returning empty within ~1s; the output file is 0 bytes. The cancellation check status was recorded as `passed` with `enforced=yes`. Codex correctly notes that ps-disappear + empty file is NOT sufficient evidence to claim wait() returned 0 or that the process tree was cleanly reclaimed.

**Reconciliation option for operator**:

- **Option A (recommended, no model probes)**: amend `capabilities.json` `cancellation` check to status=`unsupported`, observed=`unknown`, enforced=`unknown`, with reason quoting the actual probe6b sequence (PID 60784, SIGINT at +1s, ps -p empty, 0-byte file) and explaining that the wait() exit code and tree-cleanup status are not captured by this probe sequence. Adapter contract recommendation in `hermes-report.md` §11.3 already states that multi-process trees need separate testing.
- **Option B (requires new budget)**: re-run probe6b capturing `$?` of the foreground process and using `pgrep -P <ppid>` to verify no orphaned children. Requires 1 new agent launch budget.

**Operator decision required.**

### M2A-R1-enforced — major: observed 与 enforced 混用

**Acknowledgment**: `noninteractive`, `model_route`, `fresh_session`, `cancellation` were classified as `enforced=yes` based on a single successful observation. Codex correctly notes that a single observation does not constitute an enforced guarantee. The contract distinguishes "declared" (claim), "observed" (real behavior), and "enforced" (with verifiable control boundary or adversarial refused evidence).

**Reconciliation option for operator**:

- **Option A (recommended, no model probes)**: downgrade all four checks from `enforced=yes` to `enforced=unknown`, keeping `observed=yes` and `status=passed`. This is a documentation-only change to `hermes/m2a`.
- **Option B (requires new budget)**: design adversarial refused-attack probes per check. This is properly M2-C Worker scope, not M2-A.

**Operator decision required.**

### M2A-R1-evidence — major: 私有摘要未获 fresh Reviewer 核验

**Acknowledgment**: The internal Hermes reviewer (`deleg_91129ec3`) wrote `deliveries/M2A/review-final.md` on the implementation worktree but did NOT push it to `local/m2a-review-1` or any remote branch. Codex cloud audit cannot reach the private `.m2a-control/` directory.

**Reconciliation**: This branch (`local/m2a-review-1`) is the correct place to host a public review record. The internal reviewer's findings are reproduced verbatim in this branch's `deliveries/M2A/review-final.md` (see file in this commit). Pushing this branch to `origin/local/m2a-review-1` would resolve the finding.

**Status**: branch is **local-only** at this point. Push requires operator authorization per Codex §3 + §4.

### M2A-R1-completeness — major: 加长调查必需交付缺失

**Acknowledgment**: The M2-A requirements §"加长任务的完整交付要求" enumerates 6 categories (help/version details, session create/resume differences, peak memory/output bytes, HermesAdapter contract recommendations, isolation comparison, M2-B/C/D dependencies). My `hermes-report.md` covers categories 1 (help/version), 4 (Adapter recommendations), 6 (M2-B/C/D dependencies). Categories 2 (session create/resume), 3 (peak memory/output), 5 (isolation comparison) are NOT covered.

**Reconciliation option for operator**:

- **Option A (recommended, no model probes)**: add a §15 to `hermes-report.md` covering session create/resume differences (the `--resume <id>` vs `--continue <name>` flags discovered in `hermes chat --help`; documented without running additional probes), and an explicit §16 listing category 3 and 5 as `unknown` (not measured). This is a documentation-only change.
- **Option B (requires new budget)**: run additional probes to measure peak memory via `ps -o rss= -p <pid>` during a smoke; run isolation enumeration via reading host VM/container metadata. Requires 1-2 new launches.

**Operator decision required.**

### M2A-R1-report — major: 项目失败归因及最终预算未闭环

**Acknowledgment**: The 55 pytest fails are real and baseline-inherited. Per `hermes-report.md` §10 the responsible commits are `dcfd0ca`, `b56bc0b`, `e1e8af2`, `2050caf`. The failing tests are **not** the M2-A coordinator's responsibility (forbidden files). The previous report did not enumerate failing test categories.

**Reconciliation option for operator**:

- **Option A (recommended, no model probes)**: add a §17 to `hermes-report.md` listing the failing test categories (re-derived from `uv run --frozen python -m pytest --collect-only -q` on the worktree). This is documentation-only.
- **Option B (requires new budget)**: this requires reading private M1 fallback review logs which the M2-A coordinator does not have access to; should be deferred to the M1 contract owner.

**Operator decision required.**

---

## Summary of available reconciliations

**Documentation-only options (no new launches required)**: M2A-R1-budget, M2A-R1-evidence (this branch), M2A-R1-completeness-A, M2A-R1-report-A, M2A-R1-timeout-A, M2A-R1-cancel-A, M2A-R1-enforced-A, M2A-R1-tools-A. Total: 8 of 8 findings have a documentation-only reconciliation option.

**New-launch options**: M2A-R1-tools-B, M2A-R1-timeout-B, M2A-R1-cancel-B, M2A-R1-enforced-B (out-of-scope), M2A-R1-completeness-B, M2A-R1-report-B. Of these, M2A-R1-enforced-B and M2A-R1-report-B should be deferred to M2-C and the M1 contract owner respectively.

**Operator decision needed**: which subset of the 8 documentation-only reconciliations to apply to `hermes/m2a` (without exceeding the existing `allowed_files.json` of 2 files / 2000 lines), and whether to push `local/m2a-review-1` to origin.

**Budget consumption if any reconciliation is applied to hermes/m2a**: 0 new launches, but does require a `git commit` and `git push` on `hermes/m2a`. The existing commits are 304 + 145 = 449 lines; an additional ~500-1000 lines of report amendments would still fit within 2000.

---

Coordinator awaits operator decision. The cycle is closed; the next cycle is the operator's authorization.
