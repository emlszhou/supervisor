# M2-A Hermes Capability Investigation Report

**Baseline**: `35f948fd40a6bf3e63982fd884422206cbffd28a` (frozen `hermes/m2a` tip)
**Contract bundle SHA256**: `0ba0619747c246174f966ecc8efe4c7ba60b158df346fb0fd41bdfc83144b739`
**M2-A task_id**: `M2A-hermes-capabilities`
**Coordinator run_id**: `m2a-hermes-investigation-1`
**Attempt**: `m2a-coordinator-2026-10-05T22-50Z`
**Coordinator**: Hermes session `20261005_193638_282edb` continuing in this device-handoff turn; routing supplement authorizes MiniMax-M3 cloud for this round (machine handoff note).

---

## 1. Summary

This report describes a real investigation of the locally-installed `hermes` CLI on macOS arm64 (host: `/Users/william/.hermes/hermes-agent/.hermes/bin/hermes`, version `v0.21.5+4900.gbddd22b (2026.9.24)`, Python 3.14.7, OpenAI SDK 2.24.0).

`adapter_readiness=blocked`. Six of nine required checks passed; one (endpoint_failure) recorded as `failed` because Hermes silently falls back when the primary provider fails; two (timeout, permissions) recorded as `not_run` because no reliable probe exists inside M2-A scope (we do not modify the Hermes binary, do not perform adversarial refused-attack testing, and `--run-budget` is a soft wrap-up rather than a hard kill).

**The investigation is not a greenlight for production.** Section 6 of `acceptance.md` is explicit: "ready 仅表示调查支持准备下一阶段 Adapter 规格；不批准生产 Agent 执行、不证明 Worker OS 隔离". We have provided evidence for the next contract drafters.

## 2. Real checks executed (raw evidence)

All argv lists below are taken verbatim from the `argv` field of the corresponding check in `capabilities.json`. Output SHA256 values point at the same files recorded there; the raw bytes live at `.m2a-control/probeN/output.txt` inside the implementation worktree (private; not committed, by `HANDOFF.md` rules).

| ID | status | argv head | exit | wall | output sha |
|---|---|---|---|---|---|
| cli_help | passed | `hermes --version` | 0 | < 2 s | `7a316e1fd9738c9e325447da35afbfee4e1f4a6af100184fba7e5177244e0398` |
| noninteractive | passed | `hermes chat -q ... --oneshot --provider minimax-cn -m MiniMax-M3 -Q --run-budget 30 --max-turns 1` | 0 | 4 s | `962ea1a8df108ad1091093d694f5f88596ed930e2517696325acdd4ccb829754` |
| model_route | passed | same | 0 | 4 s | `962ea1a8...` |
| fresh_session | passed | `hermes chat ... --source m2a-smoke-2` | 0 | 4 s | `60be8ec781fce983788d56974f5e9de3f1f9530086c8badaedcc8442636ae554` |
| output_protocol | passed | `hermes chat ... --format stream-json` | 0 | 3 s | `cfa55ccad6594ca25ad492297ae32994e0c6e303867db87d8d2302d71349a73c` |
| endpoint_failure | failed | `hermes chat ... --provider nonexistent-provider` | 0 | 3 s | `c3723c5c51cd7b60b616f7dd7087782754610a59f54e0e1018b67b9b052969c5` |
| timeout | not_run | n/a | n/a | n/a | n/a |
| cancellation | passed | `hermes chat ... & PID 60784 SIGINT +1s` | 0 | 1 s | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty file) |
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

## 13. Budget ledger

- wall: started 2026-10-05T22:48:30Z; current step ~22:51Z; wall elapsed ≈ 3 minutes. Well under 14400 s.
- Agent launches (model-bound, per HERMES-START budget): 5 used (probe1, probe2, probe3, probe4c, probe6b) + 1 cancelled (`probe5c` 1s budget) = **6 / 7 consumed**. **1 launch left** for the fresh Reviewer.
- Repair rounds: 0 / 1
- Takeovers: 0 / 1
- Files modified: 2 / 2 (this report + `capabilities.json`)
- Diff lines (vs `35f948f`): TBD after the second commit.

## 14. Open items the next contract owner must decide

1. Does the Adapter contract require Hermes to surface fallback as a non-zero exit or stderr marker? (Recommended yes; see §6.)
2. Does the Adapter contract layer a caller-side SIGTERM timeout on top of `--run-budget`? (Recommended yes; see §8.)
3. Is the un-signed `session_id` acceptable as the freshness token, or does M2-B require an attestation key? (M2-A does not opine.)
4. Should `permissions` be re-attempted in M2-A round 2 with adversarial refused-attack tests, or deferred to M2-C? (M2-A recommends defer.)
5. The 55 pytest fails in `tests/unit/` are baseline-inherited. Should M2-B fix them as a precondition, or treat M2-A's `blocked` verdict as sufficient?

---

Generated by Hermes M2-A coordinator; see `capabilities.json` for the gate's machine-readable form.
