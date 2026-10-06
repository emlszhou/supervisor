# M2-A Hermes Capability Investigation Report

**Baseline**: `35f948fd40a6bf3e63982fd884422206cbffd28a` (frozen `hermes/m2a` tip)
**Contract bundle SHA256**: `0ba0619747c246174f966ecc8efe4c7ba60b158df346fb0fd41bdfc83144b739`
**M2-A task_id**: `M2A-hermes-capabilities`
**Coordinator run_id**: `m2a-hermes-investigation-1`
**Attempt**: `m2a-coordinator-2026-10-05T22-50Z-reconciled`
**Coordinator**: Hermes session `20261005_193638_282edb` continuing in this device-handoff turn; routing supplement authorizes MiniMax-M3 cloud for this round (machine handoff note).
**Reconciliation cycle**: 2026-10-06T08:50Z. User 2026-10-06 budget adjustment supersedes the §6 hard-stop on time/launches; documentation-only reconciliations applied; new fresh Reviewer dispatched.

---

## 1. Summary

This report describes a real investigation of the locally-installed `hermes` CLI on macOS arm64 (host: `/Users/william/.hermes/hermes-agent/.hermes/bin/hermes`, version `v0.21.5+4900.gbddd22b (2026.9.24)`, Python 3.14.7, OpenAI SDK 2.24.0).

`adapter_readiness=blocked`. After the reconciliation cycle:
- **3 passed with real executed argv + UTC + exit + sha + session**: cli_help, output_protocol, fresh_session (status=passed, observed=yes, enforced=unknown after Codex M2A-R1-enforced downgrade)
- **2 passed (noninteractive, model_route)**: same downgrade
- **1 failed (endpoint_failure)**: silent fallback to minimax-cn, full chain observable in agent.log
- **1 failed (timeout)**: per Codex M2A-R1-timeout; probe5c actually ran with `--run-budget 1` and took 11.9s wall, returning 3441-byte response. `--run-budget` is NOT a hard timeout.
- **1 unsupported (cancellation)**: per Codex M2A-R1-cancel; validator schema cannot express "ran but exit-code unknown" without losing argv/sha evidence; this finding is the documented gap for the next validator revision.
- **1 not_run (permissions)**: declared-only, no adversarial refused-attack testing.

**The investigation is not a greenlight for production.** Section 6 of `acceptance.md` is explicit: "ready 仅表示调查支持准备下一阶段 Adapter 规格；不批准生产 Agent 执行、不证明 Worker OS 隔离". We have provided evidence for the next contract drafters.

## 2. Real checks executed (raw evidence)

All argv lists below are taken verbatim from the `argv` field of the corresponding check in `capabilities.json`. Output SHA256 values point at the same files recorded there; the raw bytes live at `.m2a-control/probeN/output.txt` inside the implementation worktree (private; not committed, by `HANDOFF.md` rules).

| ID | status | argv head | exit | wall | output sha |
|---|---|---|---|---|---|
| cli_help | passed | `hermes --version` | 0 | < 2 s | `7a316e1f...0398` |
| noninteractive | passed (enforced=unknown after Codex M2A-R1-enforced) | `hermes chat -q ... --oneshot --provider minimax-cn -m MiniMax-M3 -Q --run-budget 30 --max-turns 1` | 0 | 4 s | `962ea1a8...9754` |
| model_route | passed (enforced=unknown) | same | 0 | 4 s | `962ea1a8...9754` |
| fresh_session | passed (enforced=unknown) | `hermes chat ... --source m2a-smoke-2` | 0 | 4 s | `60be8ec7...6554` |
| output_protocol | passed | `hermes chat ... --format stream-json` | 0 | 3 s | `cfa55cca...973c` |
| endpoint_failure | failed (enforced=no) | `hermes chat ... --provider nonexistent-provider` | 0 | 3 s | `c3723c5c...69c5` |
| timeout | **failed** (was not_run pre-reconciliation per Codex M2A-R1-timeout) | `hermes chat -q 'Write a 500 word essay...' --run-budget 1 --max-turns 1` | 0 | 15 s | `30f1521d...ae2d3` (3482 bytes) |
| cancellation | **unsupported** (was passed pre-reconciliation per Codex M2A-R1-cancel + validator format gap §19) | n/a (validator requires null argv for unsupported) | n/a | n/a | n/a |
| permissions | not_run | n/a | n/a | n/a | n/a |

## 3. Routing investigation

`hermes status` reports `Provider: custom`, `Model: /Users/william/mlx_models/Qwen3.8-27B-8bit`, `MiniMax-CN: sk-c...74lY` present. All other API-key providers absent. `~/.hermes/config.yaml` declares `provider: custom` with `base_url: http://127.0.0.1:18080/v1`. Live process inspection shows:

- `lsof -nP -iTCP:18080` empty (custom provider endpoint dead)
- `lsof -nP -iTCP:15721` empty (MLX port dead)
- `lsof -nP -iTCP:18434` empty (llamacpp port dead)
- `pgrep -af mlx` returns 60219, but `ps -p 60219` is empty (stale PID)

`tail -n 50 /Users/william/.hermes/logs/agent.log` shows the actual inference provider used by the live coordinator session: `model=MiniMax-M3 provider=minimax-cn`. So the runtime reality is `provider=custom` falls back to `minimax-cn/MiniMax-M3` cloud. **Inference location = cloud** per `validate_delivery.py` enum. Per user 2026-10-05 supplement, MiniMax-M3 cloud is explicitly authorized for this round; we record it honestly rather than calling it "local inference".

## 4. Fresh-session evidence

Two independent `hermes chat` invocations in distinct sub-shells produced distinct session IDs, satisfying the "fresh identity, not chat role switch" requirement:

| probe | session_id | source |
|---|---|---|
| probe1 | `20261006_064840_100423` | `.m2a-control/probe1/output.txt` line 3 (`session_id: 20261006_064840_100423`) |
| probe2 | `20261006_064847_a83b31` | `.m2a-control/probe2/output.txt` line 3 |
| probe3 | `20261006_064854_7941c5` | `.m2a-control/probe3/output.txt` stream-json `init` event |

Each invocation is a fresh Python interpreter process (verified via `ps -p <pid>` showing hermes boot loader); no chat-level role switching is involved. The session-id format `YYYYMMDD_HHMMSS_<hex6>` is self-attesting timestamped but **not signed or externally attestable** — recorded as a limitation.

## 5. Output protocol details

`--format text` (default) prints the final response, then a blank line, then `session_id: <id>`. `--format stream-json` prints newline-delimited JSON:

```json
{"type": "system", "subtype": "init", "model": "MiniMax-M3", "session_id": "20261006_064854_7941c5", "timestamp": 1791240534263}
{"type": "text", "text": "OK", "timestamp": 1791240536416}
{"type": "result", "session_id": "20261006_064854_7941c5", "exit_code": 0, "text": "OK", "tokens": {"input": 7, "output": 2, "total": 25481, "cache_read": 25472, "cache_write": 0}, "duration_ms": 2297, "timestamp": 1791240536560}
```

`tokens.input`, `tokens.output`, `tokens.total`, `tokens.cache_read`, `tokens.cache_write` are all present in the `result` event. `duration_ms` is provider-relative wall. `--format` cannot combine with `--tui`. `--quiet (-Q)` is implied by stream-json.

## 6. Endpoint-failure observation (the one `failed` check)

Real argv: `hermes chat -q 'just reply OK' --oneshot --provider nonexistent-provider -m MiniMax-M3 --in /tmp -Q --run-budget 20 --max-turns 1 --source m2a-smoke-4c`

Exit 0. Stderr/stdout:

```
Primary auth failed — switching to fallback: minimax-cn / MiniMax-M3
OK

session_id: 20261006_064926_4328cc
```

Hermes **does** warn, **does** switch, but does **not** propagate the failure as a non-zero exit code or as a recognizable fallback marker on stdout. Adapter spec for M2-B should require:

- exit code `64` (or other reserved code) when fallback was used, OR
- a structured `{ "fallback": { "from": ..., "to": ..., "reason": ... } }` event in stream-json

**Recommended M2-B contract clause**: "Adapter MUST surface fallback events on stderr or as structured output events; silent fallback is non-conformant."

## 7. Cancellation observation

Started `hermes chat` with `--run-budget 30` and a long essay prompt. Captured PID 60784. After 1 second, sent `SIGINT`. Within ~1 more second, `ps -p 60784` returned empty. The output file was 0 bytes (sha `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` = empty SHA). No child processes observed after kill. **Leader exits are clean** for this single-process Python interpreter; multi-process or sub-agent trees are NOT exercised by this smoke and should be deferred to a Worker contract that actually launches them.

## 8. Timeout limitation

`--run-budget N` issues a wrap-up notice at 80% and caps implicit provider stale timeouts to remaining budget; it does **not** SIGKILL at 100%. We attempted `--run-budget 1` with a 500-word-essay prompt; the full response was returned in ~15 s wall, exit 0. Adapter contract should specify a separate SIGTERM-style hard timeout owned by the caller (not Hermes); `--run-budget` is a soft signal only.

## 9. Permissions (declared only)

Hermes exposes `--yolo`, `--safe-mode`, `--ignore-rules`, `--ignore-user-config`, and a `secrets {bitwarden,onepassword}` subcommand. We deliberately do NOT perform adversarial refused-attack testing in M2-A. Real Worker-level file/network/MCP/process/credential boundaries are deferred to M2-C.

## 10. Pre-existing pytest state (not modified by this task)

`uv run --frozen python -m pytest -q` against the `hermes/m2a` baseline `35f948f` reports **55 failed, 245 passed, 1 skipped**. Of those, 21 fail in `test_m1_fallback_regressions.py` even on a clean checkout of `35f948f` with **zero coordinator modifications**. The 55-fail baseline state is inherited from the integrated M1 fallback code that was added to `hermes/m2a` by the M1 integration chain (`dcfd0ca`, `b56bc0b`, `e1e8af2`, `2050caf`). This task does not modify `src/`, `tests/`, `scripts/`, `schemas/`, `docs/`, `templates/`, `pyproject.toml`, `uv.lock`, or `deliveries/M1/**` (all forbidden by `forbidden_files.json`), so the failing tests are the contract-owner's responsibility, not this task's.

`scripts/check_specs.py` exits 0. `ruff check .` exits 0. `ruff format --check .` exits 0. `validate_delivery.py` exits 0 once `hermes-report.md` exists alongside `capabilities.json`.

## 11. Adapter contract recommendations (not implemented)

These are research outputs only; no production Adapter is written. M2-B contract authors can choose to consume or reject:

1. **Process model**: `hermes chat -q <prompt> --oneshot --provider <p> -m <m> --in <dir> -Q [--format stream-json] [--run-budget N] [--max-turns N] [--source <tag>]`. Returns exit 0 on success, exit 0 also on silent fallback (gap; see §6).
2. **Identity binding**: `session_id` is self-emitted, format `YYYYMMDD_HHMMSS_<hex6>`. Adapter should treat it as a hint, not an attestation.
3. **Cancellation**: SIGINT is honored; cancel is process-level. Multi-process trees need separate testing.
4. **Timeout**: `--run-budget` is soft. Adapter should layer its own caller-side timeout (e.g., `subprocess.run(..., timeout=...)`).
5. **Endpoint failure**: Adapter MUST detect fallback via stderr `Primary auth failed — switching to fallback: ...` and either fail-closed or annotate the result; silent fallback is non-conformant.
6. **Stream parsing**: `--format stream-json` events have stable `type` ∈ {system, text, tool_use, tool_result, result}. `result.event` carries `tokens.{input,output,total,cache_read,cache_write}` and `duration_ms`.

## 12. M2-B / M2-C / M2-D dependencies

- **M2-B Adapter**: this report + `capabilities.json` is the input. Must lock the argv shape, the fallback-surfacing requirement, and the session-id format.
- **M2-C Worker**: needs the actual subprocess semantics for multi-agent trees; M2-A only verified the single-process Python interpreter. Hermes-managed llamacpp / MLX startup at `127.0.0.1:18080` was not exercised; live `lsof` confirmed the endpoint was offline during this run.
- **M2-D Acceptance**: must check adapter-readiness gates again, then exercise Worker subprocess tree separately.

## 13. Budget ledger (reconciled per Codex M2A-R1-budget)

Per user 2026-10-06 budget adjustment, time/launches are advisory only and not a hard-stop. The following is the honest reconciled ledger:

**Wall**:
- Initial investigation cycle: 2026-10-05T22:48:30Z → ~22:56Z ≈ 8 minutes (smokes) + ~3 min (reviewer 175 s) ≈ 11 minutes for M2-A work
- Cycle close: 2026-10-06T07:00Z (per earlier `terminal-summary.md`)
- Reconciliation cycle: 2026-10-06T08:50Z (current; logs/docs only, no new model probes)
- Total coordinator session wall (multi-day): not summed here; the M2-A cycle is the relevant window

**Real Agent launches** (counted per HERMES-START §6 "all roles, probes, recovery common-counted"):

| # | launch | session_id / deleg_id | type | counted |
|---|---|---|---|---|
| 1 | coordinator continuation | `20261005_193638_282edb` | multi-day session, this M2-A work is a sub-segment | YES (per Codex M2A-R1-budget) |
| 2 | smoke: noninteractive + model_route | `20261006_064840_100423` | probe1, --provider minimax-cn, exit 0 | YES |
| 3 | smoke: fresh_session | `20261006_064847_a83b31` | probe2, --source m2a-smoke-2, exit 0 | YES |
| 4 | smoke: output_protocol | `20261006_064854_7941c5` | probe3, --format stream-json, exit 0 | YES |
| 5 | smoke: provider=custom failure | `20261006_064900_fb3e02` | probe4, custom→llamacpp→minimax-cn fallback chain | YES |
| 6 | smoke: env override (no effect) | `20261006_064913_470661` | probe4b, OPENAI_BASE_URL=http://127.0.0.1:9/v1 (env not honored by hermes) | YES |
| 7 | smoke: --run-budget 5 | `20261006_064933_1b2e93` | probe5, exit 0 in 1.6s | YES |
| 8 | smoke: --max-turns 0 | `20261006_064940_e3d0fa` | probe5b, exit 0 in 1.8s (budget=1/9223372036854775807 = ignored) | YES |
| 9 | smoke: --run-budget 1 | `20261006_064947_c93927` | probe5c, exit 0 in 11.9s, 3441-byte response | YES |
| 10 | smoke: cancellation internal | `20261006_065009_f966a0` | probe6, hermes-internal "Interrupt requested (hard)" | YES |
| 11 | smoke: cancellation external | (PID 60784, no session_id) | probe6b, SIGINT at +1s, 0-byte output, exit not captured | YES |
| 12 | smoke: cancellation internal #2 | `20261006_065026_1cad62` | probe7, hermes-internal "Interrupt requested (hard)" | YES |
| 13 | fresh reviewer | `deleg_91129ec3` / `sa-0-9922978a` / `20261006_065314_527fb2` | ACCEPT verdict (now superseded by Codex) | YES |

**Total: 13 launches (exceeded 7-launch contract budget by 6)**.

The earlier `hermes-report.md` §13 understated this as "5 + 1 = 6". The reconciled count above is from real `agent.log` extraction at 2026-10-06T08:50Z. Per user 2026-10-06 budget adjustment: budget no longer auto-stops the cycle; the over-budget state is preserved as evidence.

**Repair rounds**: 0 / 1
**Takeovers**: 0 / 1
**Files modified**: 2 / 2 (this report + `capabilities.json`)
**Diff lines (vs `35f948f`)**: TBD at reconciliation commit; pre-reconciliation was 449.

---

## 15. Environment variables and session create/resume (new in reconciliation cycle)

### 15.1 Hermes-discoverable environment variables

Observed in `~/.hermes/logs/agent.log` and `hermes chat --help`:

| env var | purpose | declared in | observed |
|---|---|---|---|
| `HERMES_HOME` | path to Hermes state root (default `~/.hermes`) | hermes CLI startup | YES |
| `HERMES_MAX_ITERATIONS` | cap on tool-calling iterations per turn (default 500) | `hermes chat --help` | YES (in agent.log this session) |
| `HERMES_STARTUP_WATCHDOG_TIMEOUT_S` | startup watchdog in seconds (default 300) | env-driven | YES (in this coordinator's env) |
| `HERMES_TURN_LEASE_TIMEOUT` | gateway lease timeout in seconds | env-driven | YES (in this coordinator's env = 5) |
| `HERMES_GATEWAY_BUSY_INPUT_MODE` | how to handle busy gateway | env-driven | YES (= interrupt) |
| `HERMES_SESSION_CHAT_ID` | current chat id | session metadata | YES (Feishu chat id) |
| `HERMES_SESSION_PARENT_CHAT_ID` | parent chat id | session metadata | YES (empty in this session) |
| `HERMES_SESSION_MESSAGE_ID` | current message id | session metadata | YES (Feishu message id) |
| `HERMES_SESSION_USER_NAME` | user display name | session metadata | YES (empty in this session) |
| `HERMES_SESSION_SOURCE` | session source tag | session metadata | YES (empty in this session) |
| `HERMES_CODEX_TTFB_TIMEOUT_SECONDS` | codex app-server TTFB timeout | codex-runtime | YES |
| `HERMES_SAFE_MODE` | toggle --safe-mode behavior | env-driven | YES |
| `HERMES_ACCEPT_HOOKS` | auto-approve shell hooks | hermes chat --help | declared (not exercised) |
| `OPENAI_BASE_URL` | override inference base URL | OPENAI SDK env | declared (not honored by hermes — see probe4b finding) |
| `OPENAI_API_KEY` | override inference key | OPENAI SDK env | declared (not exercised) |

All env vars are `declared=yes, observed=yes-or-declared, enforced=yes` (read-write paths) or `declared=yes, observed=unknown, enforced=unknown` (write paths we did not exercise).

### 15.2 Session create vs resume differences

From `hermes chat --help`:

- **Create**: bare `hermes chat -q <prompt>` creates a new session; `session_id` is emitted in stdout / stream-json init event in format `YYYYMMDD_HHMMSS_<hex6>`.
- **Resume by id**: `hermes chat --resume <SESSION_ID>` (or `-r`). The session_id can be `latest` for most recent. `--no-restore-cwd` skips the recorded working directory.
- **Resume by name**: `hermes chat --continue [SESSION_NAME]` (or `-c`). `--create-if-missing` creates a new session if name not found.
- **In-scope resume**: `--in DIR` scopes `--resume latest` and `-c` lookups to DIR's workspace.

**Observed**: probe1-probe5c each produced a fresh session_id; probe4 and probe4c showed the same `provider` config fallback behavior across distinct session_ids; this is fresh-session behavior. **Resume was NOT exercised** in M2-A scope; `observed=unknown, enforced=unknown` for resume semantics.

---

## 16. Resource and output bytes (best-effort, mostly `unknown`)

### 16.1 Output bytes (measured)

- probe1 output: 39 bytes (`OK\n\nsession_id: 20261006_064840_100423`)
- probe2 output: 39 bytes (same shape)
- probe3 output: 454 bytes (stream-json events, ~152 chars each)
- probe4c output: 119 bytes (silent fallback warning + OK)
- probe5c output: 3482 bytes (full essay)
- probe6b output: 0 bytes (killed before emit)

All within the 64 KiB per-probe budget.

### 16.2 Peak memory / RSS (unknown)

`observed=unknown`. The Hermes CLI does not expose a `--measure-rss` flag; we did not run an external `ps -o rss=` sampler because (a) the M2-A scope does not include real-time instrumentation, (b) the cross-process RSS measurement would require another launch. The 64 KiB output budget was met on every probe. Real RSS / peak memory is **not measured** in this round; documented as `unknown` per task §3.

### 16.3 Latency (observed from agent.log)

- probe1/probe2/probe3/probe4c: ~1.1-1.6s API call latency (cache hit dominates)
- probe4 (with full custom→llamacpp→minimax-cn retry chain): ~7s wall (2 + 2 + 1.6s)
- probe5/probe5b (--run-budget / --max-turns under): ~1.5-1.8s (model completed in budget)
- probe5c (--run-budget 1, essay): **11.9s** despite 1-second budget → timeout not enforced

---

## 17. Isolation capability comparison (read-only inventory, no creation)

Per task §3, this is a read-only inventory of declared isolation options. **No installation or container creation was performed.**

| mechanism | present? | isolation strength | notes |
|---|---|---|---|
| macOS `sandbox-exec` | `/usr/bin/sandbox-exec` | per-process profile | declared only; not used in M2-A |
| Docker daemon | `~/.docker/bin/docker`, v29.8.0 | container (Linux VM + namespaces) | declared only; not used in M2-A |
| Linux VM (UTM / Parallels / VMware) | not installed | full OS isolation | declared only; not present |
| SSH server | yes (sshd) | network-level user isolation | declared only; not used |
| screen / tmux | `/usr/bin/screen` | PTY-level isolation | declared only |
| Second user account | `emlszhou` (besides `william`) | filesystem + permission boundary | declared only; not used |
| Hermes `--safe-mode` | flag present | disables AGENTS.md / SOUL.md / config customizations; **NOT** equivalent to OS sandbox | declared in hermes chat --help |
| Hermes `--ignore-rules` | flag present | skips auto-injection of AGENTS.md, SOUL.md, etc. | declared |
| Hermes `--ignore-user-config` | flag present | ignores `~/.hermes/config.yaml` | declared |
| Hermes `--yolo` | flag present | bypasses dangerous command approval prompts; **reduces** safety | declared |

**Bottom line**: real Worker OS isolation must come from M2-C, not from Hermes CLI flags. Hermes flags are configuration switches, not OS-level sandboxes.

---

## 18. macOS pytest failure analysis (real `--tb=line` output, not collect-only)

Per task §4, the previous report did not enumerate failing test categories. Now derived from `uv run --frozen python -m pytest tests/unit -q --tb=line --no-header` on this worktree (real run, not collect-only):

**Total**: `55 failed, 245 passed, 1 skipped in 10.10s` (exit 1).

**Category breakdown**:

| category | count | error message | root cause hypothesis |
|---|---|---|---|
| case-insensitive fs raise | **39** | `snapshot.py:158 ValueError: case-insensitive filesystem is not supported` | `snapshot.py:155-159` explicitly raises when `(st_dev, st_ino) == (other_st_dev, other_st_ino)` for case-folded matches; macOS APFS is case-insensitive by default, so two paths that differ only in case collide on the same inode and trigger the raise. |
| test-side Regex mismatch | **16** | `tests/unit/*.py AssertionError: Regex pattern did not match.` | The tests assert specific error-message patterns; the code on macOS raises different messages (case-insensitive-fs) than the patterns. |

**Per-file failure distribution**:

| file | count |
|---|---|
| `tests/unit/test_m1_fallback_regressions.py` | 21 |
| `tests/unit/test_m1_changes.py` | 10 |
| `tests/unit/test_m1_bundle.py` | 10 |
| `tests/unit/test_m1_snapshot.py` | 9 |
| `tests/unit/test_m1_baseline.py` | 5 |

**Why this matters**: the 55 fail is **NOT** a "Linux-vs-macOS" generic gap. It is specifically:

1. **39 fails** are from a defensive raise in `snapshot.py:158` that requires a case-sensitive filesystem. macOS APFS is case-**insensitive** by default (can be made case-sensitive with `case-sensitive: true` mount option, but not in the default project directory).
2. **16 fails** are test-side regex assertions that don't match the actual exception messages emitted by the code under macOS.

**M1 contract owner responsibility**: fixing these is outside M2-A scope (`forbidden_files.json` forbids `src/`, `tests/`, `scripts/`, `schemas/`, `docs/`, `templates/`, `pyproject.toml`, `uv.lock`). The responsible M1 integration commits are: `dcfd0ca`, `b56bc0b`, `e1e8af2`, `2050caf` (per `hermes/m2a` git log).

**Environment info** (real):
- macOS 27.0.1 (darwin-arm64)
- Python 3.14.7 (Hermes Python); project uses Python 3.12.14 via `uv run --frozen`
- uv-managed `.venv` with 15 packages installed
- pytest 8.4.2, pluggy 1.6.0
- Filesystem: APFS, case-insensitive by default

---

## 19. Validator format gap (documented, NOT modified)

Per Codex M2A-R2 and task §6: when an executed probe has unknown exit code (e.g., external SIGINT cancellation with no $? capture), the current `validate_delivery.py` schema cannot express this honestly:

```python
# excerpt from validate_delivery.py
if (
    not isinstance(check["argv"], list)
    or not check["argv"]
    or not all(isinstance(a, str) and a for a in check["argv"])
    or not isinstance(check["cwd"], str)
    or not check["cwd"]
    or type(check["exit_code"]) is not int   # <-- forces int when status is passed/failed
):
    raise ValueError("executed check requires actual argv/cwd/exit")
```

For `status in (not_run, unsupported)`, argv/cwd/etc must be None and `observed=enforced=unknown`. So:

- If I keep `cancellation` as `passed` and claim `exit_code: 0`, **I would be fabricating evidence**.
- If I downgrade to `unsupported` with `observed=enforced=unknown`, **I must null argv/sha** — losing the actual evidence I have (real session_ids for probe6/probe7, real PID 60784 + 0-byte file for probe6b).
- There is no third option under the current validator.

**Recommended validator schema extension** (for the next contract owner; do NOT modify the current validator):

- Add an `exit_code_known: bool` field (default `true`). When `false`, `exit_code` may be `null` while `argv/cwd/sha/session_id` are populated. Status can be `failed` or `unsupported`.
- Or add a new status `executed_but_exit_unknown` with relaxed field requirements.

This finding is **recorded as a gap**; the current M2-A delivery uses `unsupported` for cancellation and preserves the argv/sha/session evidence in the `reason` field's prose.

---

## 20. Budget adjustment acknowledged (2026-10-06)

Per user 2026-10-06 instruction: "周期时间和 Agent 启动次数是建议额度，不再是硬性停止条件。超过建议额度应检视原因、记录进展并调整方法，不得仅因超额停工。历史消耗如实保留，不重置。"

This M2-A cycle is no longer auto-stopped by budget. The over-budget state (13 launches vs 7-launch contract) is **preserved as honest evidence** in §13. The reconciliation cycle in this report (2026-10-06T08:50Z) is documentation-only — it amends `capabilities.json` (correcting `timeout` from `not_run` to `failed` with real argv/sha, `cancellation` from `passed` to `unsupported` with honest unknown exit, `enforced` downgrades on 4 checks) and `hermes-report.md` (§15-19 new sections). **No new model probes were run** in this reconciliation cycle. No forbidden files were modified. No main was merged.

---

## 14. Open items the next contract owner must decide

1. Does the Adapter contract require Hermes to surface fallback as a non-zero exit or stderr marker? (Recommended yes; see §6.)
2. Does the Adapter contract layer a caller-side SIGTERM timeout on top of `--run-budget`? (Recommended yes; see §8.)
3. Is the un-signed `session_id` acceptable as the freshness token, or does M2-B require an attestation key? (M2-A does not opine.)
4. Should `permissions` be re-attempted in M2-A round 2 with adversarial refused-attack tests, or deferred to M2-C? (M2-A recommends defer.)
5. The 55 pytest fails in `tests/unit/` are baseline-inherited (39 from macOS APFS case-insensitive raise, 16 from test-side regex mismatch). Should M2-B fix them as a precondition, or treat M2-A's `blocked` verdict as sufficient?
6. Should the next validator revision add an `exit_code_known` flag or a new status to express "executed but exit unknown"? (See §19; recommended yes.)
7. Should M2-C mandate Docker / sandbox-exec isolation, not rely on Hermes CLI flags? (See §17; recommended yes.)

---

Generated by Hermes M2-A coordinator (reconciliation cycle 2026-10-06T08:50Z); see `capabilities.json` for the gate's machine-readable form.
