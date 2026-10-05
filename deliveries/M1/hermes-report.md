# M1 delivery: Codex fallback after Hermes takeover

- task/run/attempt: `M1-integrity-intents` / `m1-overnight-2026-10-05` / `attempt-1`.
- Baseline: `c6e224587b930a5b96c7723009584424f6bc52d5`.
- Frozen bundle SHA256: `47ea6c51c46570e92f97c89428c9783a90bcc10e301e3e8d6ce38d4fb25dd142`; all 25 manifest-listed input files verified before delivery.
- Fallback code commit: `b6cc97f0564d734b2977e32c9ec5a58953a80004`.
- Tracked-code snapshot SHA256: `f21de31f07fc8c8197ff8bc80f0d8a9faa6212e5f687d51be56c8153616a16eb`, 179 tracked files, using the frozen `snapshot.py --commit` algorithm. This is NOT the runtime workspace-snapshot algorithm.
- Delivery branch: `codex/m1-fallback`; report is committed separately after code. Obtain exact delivery tip from Git/published handoff, not a self-referential field.
- Runtime: Codex/OpenAI cloud, Linux, Python 3.12. Model version is not exposed by this environment. No local inference or Agent sandbox is claimed.

## Authorization and historical failures

User explicitly authorized one Hermes takeover followed by Codex fallback if it failed. The coordination supplement is on `codex/m1-local-recovery`, commit `ebee4b13072687f5cd93ea92b1255c653c34da2c`. M1/v1 frozen bytes, API, protected tests and net 14-file/2800-line budget remain unchanged. No main merge or deployment is authorized.

Original candidate `7f301ea72f759e4ec87128af68deb3e6dd8c9c45` failed fresh review `9c4abdb46d3dfa75353bec9be71ba0a3175124ad` (15 findings). Original repair=1 consumed; evidence `683164d9826d666dd013da5bf67ee36ce4c550ab` reports original wall overrun. Its three verified Hermes sessions do not establish the total cross-platform Agent-call count. These facts are preserved, not reset.

Hermes takeover `195ffe0037876aaa01704338e46c94407c6d68f9` reported a macOS required-test failure and exceeded the net code budget. Its reported ACCEPT-with-caveat cannot waive either gate; the final reviewer file was reported as local/untracked and was not independently available from that branch. Code inspection also found unresolved ignored inventory, bundle completeness and valid zero-budget schema handling. This fallback starts from that precise tip, preserving history. Tool-generated edits still involve model inference; prior reports claiming otherwise were incorrect.

## Final behavior and scope

Only the five allowed production modules, six `test_m1_*.py` unit files and this report differ from baseline (12 files). Production remains standard library only.

- Snapshot/baseline share actual Git-root checking and controlled inventory. Ignored files remain controlled; fixed generated-directory exclusions never hide tracked baseline/index files. Baseline deletions use the supplied commit, including staged removals. Submodules and LFS pointers fail explicitly.
- Directory/file opening uses no-follow descriptors with pre/post identities, sizes, modes, timestamps and inventory rechecks. Links, hardlinks, special files and case collisions fail; unsupported capabilities and detected case-insensitive storage fail explicitly. This is integrity detection, not a complete concurrent-attack isolation guarantee.
- Policy validates exact snapshot structures/digests and matches whole-segment globstar with zero or multiple directories, single-segment star and question mark. Forbidden takes priority; diff counts remain trusted caller input.
- Bundle validates v1 inputs, preserves every regular input byte including nested files, binds frozen task identity and writes canonical manifest plus read-only files. It detects observed source mutations, rejects parent links/overlap, exclusively claims output without overwriting a concurrent creator, and cleans only its own failed output. Verification checks full file inventory, implied directories, types, digests and frozen inputs.
- SQLite validates DB and all sidecar paths before opening, rejects dangling links/hardlinks/ancestor links, closes failed initialization, and rolls back transaction failures including injected non-SQLite exceptions. Pending/unknown are never replayed automatically.
- Bundle unit fixtures are self-contained; 35 new regressions cover ignored inventory, generated tracked files, staged deletion, capture mutations, ancestor escape, globstar denial, forged types, nested bundle bytes, source/output races, unsafe SQLite paths and commit rollback/reopen.

## Actual implementation verification

All commands ran from repository root against the committed fallback code. `UV_CACHE_DIR=/tmp/m1-uv-cache` is a runtime cache override; secrets/logs/cache are not committed. JUnit and command metadata are local under `.supervisor/evidence/M1-fallback-*`; counts are distinct checks and must not be added together as disjoint suites.

| Command | Exit | Collected / passed / failed / skipped |
| --- | --- | --- |
| `uv sync --frozen --group dev` | 0 | installation |
| `uv run --frozen pytest tests/unit -q --junitxml=.supervisor/evidence/M1-fallback-unit.xml` | 0 | 199 / 199 / 0 / 0 |
| `uv run --frozen pytest -q --junitxml=.supervisor/evidence/M1-fallback-full.xml` | 0 | 295 / 295 / 0 / 0 |
| `uv run --frozen python -B -m pytest -p no:cacheprovider <external-contract>/tests/protected/test_m1_acceptance.py -q --junitxml=.supervisor/evidence/M1-fallback-independent.xml` | 0 | 42 / 42 / 0 / 0 |
| `uv run --frozen python scripts/check_specs.py` | 0 | 6 schemas and sample artifacts |
| `uv run --frozen ruff check src tests scripts` | 0 | lint |
| `uv run --frozen ruff format --check src tests scripts` | 0 | 38 files |
| `uv build --no-sources --out-dir /tmp/m1-fallback-dist` | 0 | source distribution and wheel |

External input: `/tmp/m1-fallback-contract/handoffs/M1/v1/task-bundle`, exported from trusted main and rechecked after external pytest; no protection tests were modified or skipped.

## Limits and final review

macOS/Windows were not run by Codex. The earlier macOS 41/42 failure is preserved; Linux 42/42 does not imply macOS passed. Case-insensitive storage is explicitly rejected rather than claiming collision protection there. M1 excludes implementing OS sandboxing; it does not forbid use of an isolated test environment.

M1-13 is handled by the user's updated MiniMax/Codex routing authorization, not by pretending local smoke passed. M1-14 uses the explicitly authorized fallback, not a reset of consumed repair/wall history. M1-15's historical out-of-scope review files remain visible in Git history, despite their later revert.

Fresh final review is pending at this report commit. Implementer checks do not sign acceptance. Any later code changes require new precise code/snapshot binding and fresh verification. Final published review is kept on a separate reviewer branch; this branch does not merge main.
