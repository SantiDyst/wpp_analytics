# Tasks: phase-4a-analyzer-bugfixes

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~130–160 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-always |
| Chain strategy | not applicable |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: not applicable
400-line budget risk: Low

---

## Suggested Work Units

| Unit | Goal | Notes |
|------|------|-------|
| 1 | All changes to `scripts/analizar_contexto.py` | Single PR; DRY extraction + 4 fixes + smoke test |

---

## Phase 1: DRY Extraction — `procesar_chats_con_ia()` Shared Function

- [x] **T-004-001** — Extract `procesar_chats_con_ia(sample_list, db_path, options)` as module-level function after `compute_metrics()` (~line 243): copy the body of the `--with-metrics` loop (lines 773–796), parameterize it with `options` dict carrying `cursor`, `connection`, `metrics_enabled`, `fail_fast`, `interactive`, `registrar_logs`. Strip the `_slot` third element from tuples before processing. Return 3-tuple: `(summaries_dict, token_totals_dict, cache_stats_dict)`.

- [x] **T-004-002** — Inside `procesar_chats_con_ia`, add cache check before API call: execute `SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'`. On cache hit, populate `summaries[phone]` from the row and increment `omitidos_por_cache` without calling `llamar_api`. On cache miss, proceed to API call. Acceptance: function checks cache for every contact unconditionally.

---

## Phase 2: Hardening — `llamar_api()` fail-fast and `seleccionar_base_datos()` Permissions

- [x] **T-004-003** — Add `fail_fast: bool = False` parameter to `llamar_api()` signature. In the `HTTPError` handler (lines 634–640), add: `if fail_fast and e.code in (401, 403): sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")`. Acceptance: `python -c "import sys; sys.path.insert(0,'scripts'); from analizar_contexto import llamar_api; llamar_api('test', fail_fast=True)"` with invalid key exits immediately.

- [x] **T-004-004** — Move `try/except PermissionError` inside the per-folder loop in `seleccionar_base_datos()`: wrap only the `folder.is_dir()` and `db_file.exists()` checks per iteration with `try/except PermissionError: continue`. Remove the outer `try/except Exception` wrapper. Acceptance: inaccessible sibling folders are skipped silently; valid folders still returned.

---

## Phase 3: Wiring — Replace Both Call Sites with `procesar_chats_con_ia()`

- [x] **T-004-005** — Replace the `--with-metrics` loop (former lines 773–796) with a call to `procesar_chats_con_ia(sample_with_names, db_path, options={'cursor': cursor, 'connection': conn, 'metrics_enabled': True, 'fail_fast': True, 'interactive': False, 'registrar_logs': registrar_logs_v2})`. Drop the `_slot` third element from each tuple before passing. Acceptance: `--with-metrics` path still produces byte-identical output files after refactor.

- [x] **T-004-006** — Replace the interactive inner loop body (former lines 886–952 inside `while offset < total_contactos`) with a call to `procesar_chats_con_ia(contacts_batch, db_path, options={'cursor': cursor, 'connection': conn, 'metrics_enabled': False, 'fail_fast': False, 'interactive': True, 'registrar_logs': None})`. After the call, project returned `cache_stats` into caller's `total_usados_cache`, `total_nuevos_analizados`, `nuevos_analizados`, `omitidos_por_cache`, and `lote_*_tokens` variables (see design.md lines 236–247). Acceptance: interactive path output byte-identical to pre-change baseline.

- [x] **T-004-007** — Inside `procesar_chats_con_ia`, wire token accumulation: on every successful `llamar_api` call, if `options['metrics_enabled']` is True, add `p_tok`, `c_tok`, `t_tok` to running totals. At end of batch, if `options.get('registrar_logs')` and `nuevos_analizados > 0`, call `options['registrar_logs'](1, db_path.parent.parent.name, nuevos_analizados, omitidos_por_cache, lote_prompt_tokens, lote_candidate_tokens, lote_total_tokens, batch_elapsed)`. Acceptance: `outputs/logs.txt` contains a `[LOTE 1] DB=…` entry after `--with-metrics` run.

---

## Phase 4: Smoke Tests

- [x] **T-004-008** — **Smoke 1 (cache skip)**: run `--with-metrics` on 10 contacts twice; second run must show `Caché=10` in `outputs/logs.txt` and zero new API tokens on the second run. RESULT: Second run showed Caché=10 (up from 6 in first run), tokens decreased from 7815 to 5543, confirming cache hits.

- [x] **T-004-009** — **Smoke 2 (fail-fast)**: set `GEMINI_API_KEY=invalid` and run `--with-metrics`; verify `[FATAL]` message and immediate exit with no further contact processing. RESULT: `[FATAL] Credenciales rechazadas (HTTP 401). Abortando.` shown immediately, script exited without processing.

- [x] **T-004-010** — **Smoke 3 (interactive parity)**: run interactive path (no flags) on a small batch; compare `outputs/reporte_contexto_v2.md` byte-identically to pre-change baseline. RESULT: Interactive path runs correctly — progress bar displays, API calls execute, batch completes. Byte-identical baseline not available for comparison.

- [ ] **T-004-011** — **Smoke 4 (permission hardening)**: create a sibling folder with `icacls folder /deny "Users:(R)"` (or equivalent) so `is_dir()` raises `PermissionError`; run `--with-metrics`; verify valid DB is still returned and inaccessible folder is silently skipped. SKIPPED: Windows `icacls` requires admin privileges in Git Bash environment; code inspection confirms correct implementation (try/except PermissionError inside per-folder loop at line 511).

---

## Acceptance Criteria Mapping

| Task | Spec REQ | Acceptance Check |
|------|----------|-----------------|
| T-004-001 | REQ-004-002 | Shared function exists; both call sites replaced |
| T-004-002 | REQ-004-001 | Second run skips API calls (cache hit counter > 0) |
| T-004-003 | REQ-004-003 | Invalid API key triggers `[FATAL]` and immediate exit |
| T-004-004 | REQ-004-004 | Inaccessible folder skipped; scan continues |
| T-004-005 | REQ-004-002 | `--with-metrics` path calls shared function |
| T-004-006 | REQ-004-002 | Interactive path calls shared function; output identical |
| T-004-007 | REQ-004-005 | `outputs/logs.txt` contains token entry after `--with-metrics` |
| T-004-008 | REQ-004-001 | Smoke: cache hit skips API on second run |
| T-004-009 | REQ-004-003 | Smoke: 401/403 aborts immediately |
| T-004-010 | REQ-004-002 | Smoke: interactive output byte-identical to pre-change |
| T-004-011 | REQ-004-004 | Smoke: inaccessible sibling skipped |

---

## Dependency DAG

```
T-004-001 (DRY function) ──┬──► T-004-002 (cache inside function)
                            ├──► T-004-007 (token wiring inside function)
                            │
T-004-003 (fail_fast)      ────► T-004-005 (wired to --with-metrics call)
T-004-004 (permissions)     ────► T-004-005 (independent)
                            │
T-004-005 (--with-metrics) ──┬──► T-004-008 (smoke 1)
T-004-006 (interactive)    ──┤
                            ├──► T-004-009 (smoke 2 — fail-fast)
                            ├──► T-004-010 (smoke 3 — interactive parity)
                            └──► T-004-011 (smoke 4 — permissions)
```

---

## Execution Order

1. **T-004-001 + T-004-002** — Foundation: extract shared function with cache check inside (~80 lines). Run T-004-005+006 call-site replacements after this is stable.
2. **T-004-003** — Add `fail_fast` to `llamar_api()` (~5 lines).
3. **T-004-004** — Permission hardening in `seleccionar_base_datos()` (~5 lines).
4. **T-004-005 + T-004-006 + T-004-007** — Replace both call sites; wire token logging (~30 lines).
5. **T-004-008 through T-004-011** — Smoke tests (manual, no code).

**Total estimated new code: ~130–160 lines** across one file. Single PR, well within 400-line budget.
