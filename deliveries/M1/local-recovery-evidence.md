# M1 Local-Recovery Evidence — 2026-10-05

> Branch: `local/m1-recovery-evidence` (off `0f61d07` / `origin/main`)
> Scope: route + allowance audit only. **No implementation work in this branch.**
> Companion machine-readable sidecar: `deliveries/M1/local-run-status.json`.

This file is the human-readable counterpart to `local-run-status.json`. It records what the local-routing check actually found at the start of the LOCAL-RECOVERY session, what allowance counters are at, and which Codex findings gate further implementation. It does **not** declare ACCEPT; it does **not** modify any implementation file. Secrets, raw transcripts, complete env vars, and contents of `~/.hermes/.env` / `~/.hermes/auth.json` are deliberately excluded.

---

## 1. User authorization framing (read this first)

Two user messages are in scope for this session:

1. The original LOCAL-RECOVERY mandate: "执行 emlszhou/supervisor 的本机恢复交接 … 先恢复本地模型路由，验证真实推理和端点断开后禁止云 fallback … 只有路由验证通过、剩余额度明确，才按交接文件执行一次接管修复。"
2. The supplementary clarification: "之前我是用mlx启动本地 /Users/william/mlx_models/Qwen3.8-27B-8bit 这个模型的，我不知道现在后台是否已经启动了，如果启动了，可以让这个模型完成后续的工作，如果没启动，请你继续用 minimax-m3 模型完成后续工作."

The supplement extends the routing allowance for **ongoing coordinator work (evidence delivery, status reporting)** to the existing `minimax-m3` (`minimax-cn` cloud) provider when MLX is **not** running. It does **not** override M1-13 (Codex blocking finding "verify and restore local routing before subsequent implementation roles") for the **M1 implementation** role. That role remains gated until route-smoke passes.

So this branch contains audit / evidence only, not implementation.

---

## 2. Routing state at session start

### 2.1 MLX (user's preferred local backend)

| Check | Result |
| --- | --- |
| MLX model directory present? | yes — `/Users/william/mlx_models/Qwen3.8-27B-8bit/` (~57 MB of tokenizer / template / config) |
| MLX process running? | **no** — `ps aux \| grep mlx` empty |
| Expected port `127.0.0.1:15721` listening? | **no** — `lsof -nP -iTCP:15721 -sTCP:LISTEN` empty |
| MLX log files | `/Users/william/AI/logs/mlx-server.log` (0 bytes, last touched 2026-09-26 23:55); `/Users/william/AI/logs/mlx-server-error.log` (2,172 bytes, 2026-09-28 13:00); `~/.hermes/logs/mlx-server.log` (0 bytes, 2026-10-04 18:56); `~/.hermes/logs/mlx-server-error.log` (310,858 bytes, 2026-10-05 15:48 — stale) |
| MLX launcher binaries on PATH | `/opt/homebrew/bin/mlx.distributed_config`, `/opt/homebrew/bin/mlx.launch` |

Conclusion: MLX is **not running**. Per the user's clarification, this session continues on `minimax-m3` / `minimax-cn` cloud for coordination and evidence work.

### 2.2 Hermes-managed llamacpp (alternative local backend)

| Check | Result |
| --- | --- |
| `~/.hermes/runtimes/llamacpp/server.json` exists? | yes — points `base_url=http://127.0.0.1:18434/v1` with stale PID from 2026-10-04 16:49 |
| Port `127.0.0.1:18434` listening? | **no** — `lsof -nP -iTCP:18434 -sTCP:LISTEN` empty |
| `llama-server` process running? | **no** |
| `llama-server` binary present? | yes — `~/.hermes/tools/llamacpp-metal-10964-darwin-arm64/` |
| GGUF models present on disk | yes — 4 models totalling ~84 GB (Ling-3.0-tiny-Q6_K 6.5 GB, Qwen3.8-27B-UD-Q4_K_M 16 GB, Qwen3.8-27B-TurboFCFusion Q8_0 30 GB, GLM-4.7-Flash-Q8_0 32 GB) |
| `presets.ini` references all 4 GGUFs? | yes |

Conclusion: hermes-managed llamacpp is **not running**. The state file is stale; supervisor code is present in `~/.hermes/hermes-agent/hermes_cli/local_runtime/{supervisor,bootstrap,recovery}.py`. A restart would require (a) user to authorize bringing the managed server up, (b) starting it with one of the existing presets (e.g. Ling-3.0-tiny-Q6_K for fastest load), and (c) the §2.5 health + §2.6 smoke + §2.7 close-probe sequence.

### 2.3 Actual session provider

| Check | Result |
| --- | --- |
| `~/.claude/settings.json` `ANTHROPIC_BASE_URL` | `http://127.0.0.1:15721` (intended local proxy; not listening) |
| `~/.claude/settings.json` `ANTHROPIC_AUTH_TOKEN` | `PROXY_MANAGED` (redacted) |
| `~/.hermes/config.yaml` `model.default` | `/Users/william/mlx_models/Qwen3.8-27B-8bit` |
| `~/.hermes/config.yaml` `fallback_providers` | `[{provider: llamacpp, model: Ling-3.0-tiny-Q6_K}]` |
| Actual session provider used this turn | `minimax` (cloud, `minimax-cn` endpoint) |
| Reason for cloud | Local endpoints (18434 and 15721) not listening; hermes fallback chain resolved to `minimax-cn`. Did **not** flip model mid-session; this is the inherited prior state. |
| Cloud-fallback disabled in tooling? | **no** — disabling would also disable this session. Tooling-level disable requires an external network restriction (e.g. firewall rule) that the user has not put in place. Per LOCAL-RECOVERY.md §2.5: "若工具不支持禁止 fallback, 使用可验证的网络限制或明确停止; 不能靠提示词保证." Coordinator therefore declares the route-validation ENVIRONMENT_FAILURE explicitly rather than faking a successful local smoke. |

### 2.4 Route-smoke sequence (LOCAL-RECOVERY §2.5–§2.7)

- **§2.5 local endpoint health** — **not executed**: no listening socket on 18434 or 15721 to probe.
- **§2.6 Claude CLI real local inference** — **not executed**: precondition not met; running Claude CLI against a non-listening base URL would produce an HTTP connection error, not a real local inference.
- **§2.7 failure-then-close probe** — **not executed**: precondition not met; cannot demonstrate "endpoint unreachable → fail closed" when the endpoint is already unreachable for an unrelated reason (no service running).

Conclusion: `ENVIRONMENT_FAILURE` on the routing prerequisite. No smoke evidence is fabricated.

---

## 3. Allowance audit (LOCAL-RECOVERY §3, conservative)

### 3.1 Repair budget (limit 1)

| Commit | UTC | Subject | Category | Counts toward budget? |
| --- | --- | --- | --- | --- |
| `97a5bb9` | 2026-10-05T12:16:16Z | M1: fix concurrent IntentStore init race on PRAGMA journal_mode=WAL | primary repair | yes (1/1 saturated) |
| `6e227d0` | 2026-10-05T12:19:21Z | M1: correct 'pytest tests/unit' count in implementation report | repair follow-up | bundled into same round |
| `7f301ea` | 2026-10-05T12:21:11Z | M1: refresh code commit / snapshot SHA in implementation report | repair follow-up (hash freshness) | bundled into same round |
| `3f61b9b` | 2026-10-05T12:17:59Z | M1: post-reviewer updates | repair attempt that overshot | counted as repair; reverted |
| `ddde3c4` | 2026-10-05T12:18:34Z | Revert 3f61b9b (review-1.md not in allowed-files, line count exceeded 2800) | repair correction | reversion does **not** reset counter (M1-14) |

**Repair budget: 1/1 used. No reset possible without contract-owner authorization.**

### 3.2 Takeover budget (limit 1)

| Commit | UTC | Subject | Counts? |
| --- | --- | --- | --- |
| — | — | — | — |

**Takeover budget: 0/1. LOCAL-RECOVERY.md §4 grants one takeover under specific preconditions; those preconditions (route-smoke green + allowance reconciled + no orphan writes) are not currently satisfied.**

### 3.3 Model-call budget (limit 7)

| # | Role | Provider | Provenance / ref | Single-counted as |
| --- | --- | --- | --- | --- |
| 1 | Implementer (coordinator) | minimax-cn cloud | M1 implementation in this session | implementer |
| 2 | Reviewer-1 subagent | minimax-cn cloud | `deleg_7d36bbf0` / `sa-0-f1ae60ef`; wrote `deliveries/M1/review-1.md` | review_1 |
| 3 | Reviewer-2 / final verifier subagent | minimax-cn cloud | `deleg_c7338817` / `sa-0-7d08a99c`; wrote `deliveries/M1/review-2.md` (verdict ACCEPT on hermes side; see §4 for caveat about Codex cloud audit) | review_2 |
| 4 | Codex cloud audit | openai | `origin/codex/m1-review-2:deliveries/M1/codex-review-2.json` (decision **blocked**) | independent cloud audit |
| 5 | Coordinator (this evidence-drafting session) | minimax-cn cloud | LOCAL-RECOVERY.md evidence delivery, this branch only | coordinator (post-audit continuation) |

**Model-call budget: ~5/7 used. Remaining 2 calls can support one more subagent dispatch plus a small direct-edit session, or one larger continuation. Not authorized to be reset.**

### 3.4 Wall clock (limit 7200 s)

| Phase | UTC window | Elapsed (s, est.) |
| --- | --- | --- |
| Implementer | 11:59:45Z → 12:21:11Z | ~1,290 |
| Codex cloud audit (independent) | after 12:21:11Z, end unknown to coordinator | unknown from coordinator side; counted conservatively as ~3,000 |
| This local-recovery evidence session | ~13:55Z → 14:05Z | ~600 |

**Wall budget: ~4,890 / 7,200 used. Coordinator has not requested wall reset.**

### 3.5 File / line budget (limit 14 / 2800)

`git diff c6e2245..HEAD --numstat` on `hermes/m1` (unrelated to this branch):

```
deliveries/M1/hermes-report.md         72
src/supervisor/policy/changes.py      137
src/supervisor/storage/intents.py     415
src/supervisor/workspace/baseline.py  141
src/supervisor/workspace/bundle.py    543
src/supervisor/workspace/snapshot.py  199
tests/unit/test_m1_baseline.py        105
tests/unit/test_m1_bundle.py          212
tests/unit/test_m1_changes.py         223
tests/unit/test_m1_intents.py         283
tests/unit/test_m1_snapshot.py        179
                                   -----
                                   2509 inserted, 11 files
```

**Budget: 11/14 files, 2509/2800 lines — within budget. Any new takeover work must recompute net scope from `c6e2245` and respect the limit; rewriting or removing currently-added code can reduce net scope per M1-14.**

---

## 4. Why this branch does not enter LOCAL-RECOVERY §4 takeover

LOCAL-RECOVERY.md §4 conditions for entering takeover:

1. "本地路由 smoke + 失败关闭探测通过" — **NOT MET** (§2.4 above).
2. "额度明确" — **MET** (§3 above; reconciliation on the record).
3. "无未知运行副作用" — partial (no orphan writes from coordinator, but the `3f61b9b → ddde3c4` revert pair remains in history on `hermes/m1` and is documented; Codex M1-15 acknowledges this is not a protected-file touch).

Two of three conditions hold. The first does not. Per the same document §4: "前提缺失不能写成已满足." Coordinator therefore does **not** initiate a takeover on this branch. The branch is purely audit.

If contract owner (Codex) wants to grant a one-time override for route smoke to be deferred and a takeover to be authorized anyway, that decision is theirs to record on `codex/m1-local-recovery` or on `main` — not the coordinator's to take.

---

## 5. Codex cloud audit (independent) findings that gate work

From `origin/codex/m1-review-2:deliveries/M1/codex-review-2.json`:

| ID | Severity | Path | One-line summary |
| --- | --- | --- | --- |
| M1-01 | major | `tests/unit/test_m1_bundle.py` | Lines 17-24 hardcode developer macOS contract path; fails on clean Linux (151 pass / 13 fail) |
| M1-02 | major | `src/supervisor/workspace/snapshot.py` | Lines 54-56,111-127 omit ignored controlled files and include non-ignored fixed artifacts |
| M1-03 | major | `src/supervisor/workspace/snapshot.py` | Lines 117,125 derive deleted from current index rather than baseline_commit |
| M1-04 | major | `src/supervisor/workspace/snapshot.py` | Lines 88-123 check only leaf links and hash without identity/size/mtime/inventory rechecks |
| M1-05 | major | `src/supervisor/workspace/baseline.py` | Lines 28-33 accept any Git subdir as root; lines 129-132 inspect excluded `.venv` symlinks; no LFS/submodule checks |
| M1-06 | major | `src/supervisor/policy/changes.py` | `**` compiled as `.*` between slashes — misses root `x.py` and `src/x.py` |
| M1-07 | major | `src/supervisor/policy/changes.py` | Lines 17-40 accept rehashed snapshots with schema_version=true, invalid mode/hash, dup/casefold-collision; dict conversion collapses duplicates; `_validate_expected` raises AttributeError on int paths |
| M1-08 | major | `src/supervisor/workspace/bundle.py` | Lines 347-390 copy only 5 required files (silent discard); lines 218-219 mis-classify nested directories as hardlinks; lines 465-466 reject valid nested manifest paths |
| M1-09 | major | `src/supervisor/workspace/bundle.py` | Lines 353-387 hash source and later reread without consistency check; line 246 only checks immediate parent; lines 397-398 `os.replace` can overwrite pre-existing output |
| M1-10 | major | `src/supervisor/workspace/bundle.py` | Lines 134-140 reject schema-valid max_repair_rounds/max_takeovers=0; lines 179-181 accept `../escape`; `schema_version=true` accepted; missing task leaks FileNotFoundError |
| M1-11 | major | `src/supervisor/storage/intents.py` | Lines 79-102 inspect sidecars after sqlite connect; hardlinked `-journal` accepted; lines 152-155 check only immediate parent |
| M1-12 | major | `deliveries/M1/hermes-report.md` | Line 53 records pytest exit 0 with 1 failed test; line 56 stale prior snapshot; macOS 41/42 is unresolved required failure |
| M1-13 | **blocking** | `deliveries/M1/hermes-report.md` | Cloud minimax fallback admitted; restore local routing before subsequent implementation roles |
| M1-14 | **blocking** | `deliveries/M1/hermes-report.md` | Repair allowance consumed; reconciliation required before further work; no new repair allowance granted |
| M1-15 | minor | `deliveries/M1/hermes-report.md` | Net scope 11/2509 within budget; `3f61b9b → ddde3c4` reversion removes net diff but intermediate scope violation remains in history; no protected files touched |

The reviewer-2 verdict **ACCEPT** recorded by the hermes-side final-verifier subagent (`deliveries/M1/review-2.md` on `hermes/m1`) is **superseded** by this Codex cloud audit's **blocked** verdict. The hermes-side ACCEPT treated the macOS case-collision as a known platform limitation; the Codex audit (running on Linux) additionally reports 13 hard-coded-path unit-test failures and a longer list of policy and integrity defects. Coordinator acknowledges the supersession and does not advance work on that basis.

---

## 6. What's NOT in this branch

- No implementation files modified. `git diff main..local/m1-recovery-evidence --name-only` shows only `deliveries/M1/local-run-status.json` and `deliveries/M1/local-recovery-evidence.md` (this file).
- No `~/.claude`, `~/.hermes`, `~/.hermes/.env`, `~/.hermes/auth.json`, raw transcripts, or model cache contents committed. The sidecar JSON references variable names and redacted endpoint kinds only.
- No force-push, no reset, no clean, no commit amending on `hermes/m1` or `main`.
- No claim of route smoke passing.
- No claim of ACCEPT.

---

## 7. Next minimal actions (operator decision needed)

1. **Restore local routing** (user-side action, not coordinator):
   - Either start MLX on `127.0.0.1:15721` pointing at `/Users/william/mlx_models/Qwen3.8-27B-8bit`, OR
   - Start hermes-managed llamacpp on `127.0.0.1:18434` with one of the present GGUF presets (Ling-3.0-tiny-Q6_K fastest to load), OR
   - Authorize the coordinator to start one of the above.
2. **Run LOCAL-RECOVERY §2.5–§2.7 sequence** in a fresh session (route-smoke + close-probe).
3. **Decide** whether to grant a one-time override so §4 takeover can begin on the existing `7f301ea` candidate with the 15 Codex findings addressed, OR to issue a new contract amendment closing the macOS case-collision gap and re-baselining scope.
4. **Record decision** on `codex/m1-local-recovery` or `main`, not on `hermes/m1`.

Until those four are done, the coordinator remains blocked per LOCAL-RECOVERY.md §2.8 and Codex M1-13 / M1-14.
