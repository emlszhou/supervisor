# M2-C1 Round-2 Reviewer ACCEPT Note

**Branch**: `local/m2c1-review-2` (created from baseline `2805b1f`)
**Source**: Round-2 fresh Reviewer dispatched by coordinator as `deleg_9ff15ab2` / `sa-0-02870e70` at 2026-10-06T13:13:41Z, finished at 2026-10-06T13:19:09Z (327.69 s wall).
**Verifier**: model=MiniMax-M3 (minimax-cn cloud), platform=subagent, fresh isolated context.

## Verdict

**ACCEPT** — the M2-C1 coordinator honestly repaired all 3 Codex round-2 findings (UTC strict ASCII, evidence consistency, trace honesty) without fabricating evidence or expanding permissions. The new candidate is trustworthy.

## What the Reviewer verified (all green, real command output)

- Branch hygiene: `6b05c62` tip, 0 uncommitted tracked changes, 2 R2 commits (`0452c72`, `6b05c62`) on top of R1 commits.
- Budget: **4 files / 1397 insertions** (within 4/1800 limit); 0 deletions; exactly the 4 allowed filenames.
- Forbidden files: clean grep returned 0 hits.
- Protected contract: **23/23 pass**.
- Unit tests: **83/83 pass** (76 baseline + 7 new R2 regression tests).
- Full suite: **328 pass / 55 fail / 1 skip** (matches expected 245+76+7=328; all 55 fails in `test_m1_*.py` baseline-inherited).
- Specs/ruff/ruff-format: all exit 0.

## M2C1-R1-utc primary check (THE primary check)

- `_TIMESTAMP_PATTERN` at `boundary.py:103` uses `[0-9]{4}-...Z$` (ASCII-only).
- Fullwidth-digit reproduction (`２０２６-１０-０６T００:００:００Z`) raised `boundary_evidence_invalid:timestamp_format`.
- ASCII positive control accepted normally.

## M2C1-R1-evidence consistency

All 4 corrections verified in `boundary-evidence.json`:

- `control_readonly.observed="unknown"` (L31).
- `fresh_review.argv` lists 3 reviewer branches (L124).
- `network.reason` describes Python LISTEN on 18080 + ESTABLISHED clients (L68).
- `process_tree.source` explicitly says "no fresh probe was run for M2-C1" (L112).
- §9.3 (L207) says "hard validator rule, not a soft recommendation".

## M2C1-R1-trace honesty

- Timestamps are sequential real-host probes (`48s → 50s → 50s → 51s → 54s`, not on-the-minute +1).
- Filesystem sha256 `0215b0bb…` byte-exact reproducible as `sha256sum('Probe\nPROBE\n')`.
- Control_readonly sha256 flagged as "one-time capture" in §6.
- Filesystem side-effect (`/tmp/m2c1-fs-probe`) explicitly disclosed in both `source` and `reason` fields.

## M2-C2 recommendations (carried forward)

All 5 items present in §9.1/§9.2:

- Do not promote Docker version / sandbox-exec / `--safe-mode` to OS-sandbox attestation.
- Run real adversarial refused-attack tests.
- Optional case-sensitive Mac project checkout for re-running M1 tests.
- Formalize `tree_cleanup_confirmed=None` decision tree.
- Explicit permissions for adversarial probes.

Report consistently says "not a greenlight for live execution"; `require_live_execution` always raises `RuntimeError("live_execution_disabled: ...")`.

## Two non-blocking cosmetic notes (resolved in commit `6991f0b`)

1. §1/§2.2 said "76 unit tests pass" but real pytest says 83 (76 R1 + 7 R2). Corrected.
2. §15.1 said "Six regression tests" but actual count is 7. Corrected.

## Final SHA

- **`origin/hermes/m2c1 = 6991f0b487955744d0f93a2b1cabcc5c80a69438`** (post-cosmetic).
- **candidate tip at Reviewer dispatch** `6b05c62865cbddcfe8f5ed60b59bfab310d7d0e6` (Round-2 verifier ran against this SHA).
- **baseline** `2805b1f03d95d0d8de5ab81ea8538822198c397c`.

## Full Round-2 Reviewer report

`/Users/william/Public/AI project/supervisor-M2A/deliveries/M2C1/review-round2.md` (18987 bytes, untracked on `local/m2c1-review-2`; preserved in the implementation worktree).
