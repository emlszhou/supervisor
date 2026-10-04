# M0R takeover implementation report

Task M0R-review2-remediation / run m0r-takeover / attempt m0r-takeover-1.
Implementer: Codex/OpenAI, root session. This is implementation evidence, not final independent acceptance.
Baseline: fc479e760cbcd1e5259e2d62aeddaa6033d2c915.
Frozen bundle: 75f3473029918da8be5ae52dbb0b4ccb06f20d2306bac2a48f248ff7a52d9fe5.
Code commit: 83bfb4e9efcc94842b167ad01305dc7f245b1332.
Code snapshot: c9a8ab2ab6451f4201e622b90edd2b2fe21dafddea531b541093415432df09f6.
Branch: codex/m0r-takeover. Report committed separately; final delivery SHA supplied by coordinator.

## Changes

Replace buffered drain and unbounded queues with two raw pipe readers sharing a locked output budget. POSIX descriptors are nonblocking; raw reads preserve short output. Exact budget is not truncation until one actual excess byte is observed. EOF and leader completion are both required; inherited pipes remain subject to the same wall deadline. Stop/readers and execution exceptions are handled in finally, with bounded joins and unbuffered pipe closure. Native Windows polls PeekNamedPipe availability and reads at most the available byte count (one reader per pipe), avoiding synchronous read cancellation races. Native Windows remains untested.

Linux tracks observed descendant identities/ancestry via /proc, including descendants that enter another process group. POSIX ps metadata is a fallback. Termination sends group and observed descendant signals, reaps the leader, and checks observed identities for exit/zombie state. Denied group signals never count as confirmed. If ancestry inspection is unavailable, required-tree execution is rejected before launch as unsupported. This is observed process tracking, not an OS sandbox or proof against arbitrary adversarial fork/reparent races; M2 execution isolation remains unimplemented.

Restore permitted unit-test naming: tests/unit/test_m0_review1_regressions.py preserves all eight previous tests. Add tests/unit/test_m0_takeover.py covering exited leader/inherited pipe deadline, retained short output, bounded finite flood, escaped-session descendant cleanup. Parser repair from Hermes retained.

## Validation on Linux/Python 3.12

All commands run from implementation root, using frozen uv dev dependencies. Test subprocess environment whitelisted without injected Git credentials.

- python -m pytest tests/unit -q: exit 0, 98 passed, 0 failed/skipped.
- python -m pytest -q: exit 0, 194 passed, 0 failed/skipped.
- python -m pytest <external-contract>/tests/protected/test_m0_acceptance.py <external-contract>/tests/protected/test_m0r_acceptance.py -q: exit 0, 72 passed (57 + 15), 0 failed/skipped.
- ruff check src tests scripts: exit 0.
- ruff format --check src tests scripts: exit 0 (rerun after final formatting).
- python scripts/check_specs.py: exit 0, 6 schemas validated.

Native macOS and Windows have not been run by this implementer; simulated pipe behavior is not native-platform evidence. Fresh final Reviewer must verify the final exact candidate, cumulative allowed paths/1800-line budget, previous/new failure probes and report binding. Original M0 rejection and review history remain unchanged; no main merge performed.
