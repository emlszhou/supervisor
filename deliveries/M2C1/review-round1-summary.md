# M2-C1 Round-1 Reviewer ACCEPT Note

**Branch**: `local/m2c1-review-1` (created from baseline `2805b1f`)
**Source**: round-1 fresh Reviewer dispatched by coordinator as `deleg_c5d1313b` / `sa-0-ab3a70cf` at 2026-10-06T12:57:10Z, finished at 2026-10-06T13:01:27Z (257.06 s wall).
**Verifier**: model=MiniMax-M3 (minimax-cn cloud), platform=subagent, fresh isolated context.

## Verdict

**ACCEPT** — the M2-C1 coordinator honestly delivered the boundary evidence validator; 23/23 protected + 76/76 unit tests pass; no forbidden files modified; real-host inventory matches; sha256s are real one-time captures (not fabrications); M2-C2 recommendations correctly refuse to promote config switches to OS-sandbox attestations.

## What the Reviewer verified (all green)

- Branch hygiene: clean detached HEAD at `a78cb40` (then `8893291` after cosmetic fixes), exactly two new M2-C1 commits.
- Budget: 4 files / 1239 insertions (limits 4 / 1800); filenames verbatim the allowed list.
- Forbidden files: 0 violations across 14 forbidden patterns.
- **23/23 protected contract tests pass.**
- **76/76 unit tests pass.**
- Full project: 55 fail / 321 pass / 1 skip; baseline-inherited macOS APFS, 5 test files, identical category to M2-A / M2-B.
- Specs / lint / format: all exit 0.
- Boundary module behavior (4 paths independently):
  - `require_live_execution()` raises RuntimeError with substring `live_execution_disabled`
  - `require_live_execution(allow_live=True, enable_live='1')` also raises (arguments ignored)
  - `validate_evidence(boundary-evidence.json)` returns deep copy with 7 checks
  - Mutation isolation holds (mutating result doesn't affect input)
  - Newline identity rejected via `re.fullmatch`
- Real-host inventory cross-check: macOS 27.0.1, Python 3.9.6/3.12.14, sandbox-exec 135136 root:wheel Sep 24 15:10 (matches report exactly), Docker 29.8.0 daemon NOT running, APFS case-insensitive confirmed by /tmp probe, cc-switch on 127.0.0.1:15721.
- `boundary-evidence.json`: schema_version=1, 7 checks, 4 executed with real argv/exit_code=0/1s timestamps/lowercase 64-hex sha256, 3 unexecuted with observed=enforced=unknown and all execution fields null. Re-validates via `validate_evidence`.
- M2-C2 recommendations: all 5 required items present (explicit refusal to promote config switches; real adversarial refused-attack tests with concrete per-boundary examples; case-sensitive Mac checkout; tree_cleanup_confirmed=None decision-tree; explicit permissions for adversarial probes).

## Three non-blocking cosmetic notes (resolved)

1. **"3 executed" → "4 executed"** in §1 and §6 — the JSON correctly listed 4 (filesystem, control_readonly, network, fresh_review); the text undercounted. **Resolved in commit `8893291`**.
2. **Python LISTEN on 18080 omitted from §5.3** — the actual host has a Python process LISTEN on 18080 with ESTABLISHED client connections. **Resolved in commit `8893291`**.
3. **sha256 are one-time captures** — `ls -la` timestamps are not byte-reproducible across runs. The Reviewer accepted with the explicit caveat that values are real one-time captures, not fabrications. **Documented in §13.**

## Full Round-1 Reviewer report

The full Round-1 Reviewer report lives at:

`/Users/william/Public/AI project/supervisor-M2A/deliveries/M2C1/review-round1.md` (untracked on `local/m2c1-review-1`; preserved in the implementation worktree).
