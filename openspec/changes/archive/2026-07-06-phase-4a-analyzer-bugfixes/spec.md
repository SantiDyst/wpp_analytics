# Delta for analyzer-bugfixes

## Purpose

Phase 4a addresses five surgical feedback items from the first production run of `analizar_contexto.py`. All five changes are contained in `scripts/analizar_contexto.py`. The changes are: missing cache check in `--with-metrics` (data-loss bug), DRY extraction of the duplicated processing loop, fail-fast auth error handling, per-folder permission error hardening, and token logging in the `--with-metrics` path.

**What existing behavior this modifies**: The `--with-metrics` processing loop (lines 773–796) is replaced by a call to the new shared `procesar_chats_con_ia()` function; `seleccionar_base_datos()` moves its exception handling inside the per-folder loop; `llamar_api()` gains a `fail_fast` parameter.

---

## ADDED Requirements

### Requirement: REQ-004-001 — Cache Check Before API Call in `--with-metrics`

The system SHALL query `conversation_summaries` for an existing `period='profile'` row before calling `llamar_api()` in the `--with-metrics` processing path. If a cached row exists, the system SHALL skip the API call and increment the cache-skip counter.

#### Scenario: Cache hit skips API call

- GIVEN a contact `+5491112345678` exists in `conversation_summaries` with `period='profile'`
- WHEN the `--with-metrics` processing loop reaches that contact
- THEN the system executes `SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'`
- AND finds a non-null row
- AND skips the call to `llamar_api()`
- AND increments `omitidos_por_cache` and `total_usados_cache`

#### Scenario: Cache miss proceeds to API call

- GIVEN a contact `+5491112345678` has no row in `conversation_summaries` with `period='profile'`
- WHEN the `--with-metrics` processing loop reaches that contact
- THEN the `SELECT` returns `None`
- AND the system calls `llamar_api()` normally
- AND the result is written to `conversation_summaries`

---

### Requirement: REQ-004-002 — DRY Consolidation of Processing Loops

The system SHALL provide a single shared function `procesar_chats_con_ia(sample_list, db_path, options)` that consolidates the two previously separate processing loops. The `options` dict MUST carry `cursor`, `connection`, `metrics_enabled`, `fail_fast`, `interactive`, and `registrar_logs` keys. The function MUST return a 3-tuple `(summaries_dict, token_totals_dict, cache_stats_dict)` where `cache_stats_dict` carries `nuevos_analizados` and `omitidos_por_cache` counts.

#### Scenario: `--with-metrics` path calls shared function with token accumulation

- GIVEN `--with-metrics` is active and a sample of 10 contacts is selected
- WHEN the processing loop calls `procesar_chats_con_ia(sample_list, db_path, options)` with `options['cursor']`, `options['connection']`, `options['metrics_enabled']=True`, `options['fail_fast']=True`, `options['registrar_logs']=registrar_logs_v2`
- THEN the function iterates over all contacts in `sample_list`
- AND accumulates `prompt_tokens`, `candidate_tokens`, and `total_tokens` from each `llamar_api()` call
- AND calls `registrar_logs_v2()` once at batch completion with accumulated token totals

#### Scenario: Interactive path calls shared function without token accumulation

- GIVEN the interactive path is active (no `--with-metrics` flag)
- WHEN the existing confirmation loop calls `procesar_chats_con_ia(sample_list, db_path, options)` with `options['cursor']`, `options['connection']`, `options['metrics_enabled']=False`, `options['fail_fast']=False`, `options['interactive']=True`, `options['registrar_logs']=None`
- THEN the function iterates over contacts with user confirmation prompts
- AND does NOT call `registrar_logs_v2()`
- AND returns `(summaries_dict, token_totals_dict)` with zeroed token counts

---

### Requirement: REQ-004-003 — Fail-Fast on HTTP 401/403

The function `llamar_api()` SHALL accept a `fail_fast: bool = False` parameter. When `fail_fast=True` and the HTTP response status is 401 or 403, the function SHALL call `sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")` instead of returning `(None, 0, 0, 0, 0)`.

#### Scenario: HTTP 401 triggers fail-fast abort

- GIVEN `llamar_api()` is called with `fail_fast=True` and the API returns HTTP 401
- WHEN the function detects the 401 status code
- THEN it writes `sys.exit("[FATAL] Credenciales rechazadas (HTTP 401). Abortando.")`
- AND the Python process terminates immediately

#### Scenario: HTTP 403 triggers fail-fast abort

- GIVEN `llamar_api()` is called with `fail_fast=True` and the API returns HTTP 403
- WHEN the function detects the 403 status code
- THEN it writes `sys.exit("[FATAL] Credenciales rechazadas (HTTP 403). Abortando.")`
- AND the Python process terminates immediately

#### Scenario: HTTP 401 does not abort when fail_fast=False (default)

- GIVEN `llamar_api()` is called with `fail_fast=False` (default) and the API returns HTTP 401
- WHEN the function detects the 401 status code
- THEN it prints an error message
- AND returns `(None, 0, 0, 0, 0)` without calling `sys.exit()`

---

### Requirement: REQ-004-004 — Per-Folder Permission Error Handling

The function `seleccionar_base_datos()` SHALL catch `PermissionError` inside the per-folder iteration loop and continue scanning remaining folders without aborting the entire scan. A single inaccessible folder MUST NOT prevent processing of subsequent valid folders.

#### Scenario: Inaccessible folder is skipped without aborting scan

- GIVEN `seleccionar_base_datos()` is scanning `Desktop/wpp_analytics/` siblings
- AND one subfolder `Desktop/inaccessible/` raises `PermissionError` on `folder.is_dir()` or `db_file.exists()`
- WHEN the exception is raised inside the loop
- THEN the exception is caught with `except PermissionError: continue`
- AND the scan proceeds to the next folder
- AND the function returns valid `(folder_name, db_path)` tuples for all accessible folders

#### Scenario: All folders inaccessible triggers graceful empty return

- GIVEN all subfolders in `Desktop/` raise `PermissionError`
- WHEN the scan loop exhausts all entries
- THEN the function returns an empty list `rutas_validas = []`
- AND the calling code handles the empty list appropriately (prompts user or exits)

---

### Requirement: REQ-004-005 — Token Logging for `--with-metrics`

After `procesar_chats_con_ia()` completes a batch with `metrics_enabled=True`, the system SHALL call `registrar_logs_v2()` with the accumulated `prompt_tokens`, `candidate_tokens`, and `total_tokens` values from the batch.

#### Scenario: Token totals logged after successful batch

- GIVEN a `--with-metrics` run processes 10 contacts
- AND each contact's `llamar_api()` call returns non-zero token counts
- WHEN the batch completes
- THEN `registrar_logs_v2()` is called once with the accumulated totals
- AND the `outputs/logs.txt` file contains an entry with the correct accumulated token values

#### Scenario: Zero tokens logged when all calls fail

- GIVEN a `--with-metrics` run where all `llamar_api()` calls return `(None, 0, 0, 0, 0)` due to API errors
- WHEN the batch completes
- THEN `registrar_logs_v2()` is called with `prompt_tokens=0`, `candidate_tokens=0`, `total_tokens=0`
- AND the `outputs/logs.txt` file reflects zero consumption for that run

---

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

---

## Coverage

| Requirement | Happy Path | Edge Case |
|-------------|------------|-----------|
| REQ-004-001 Cache check | Cache hit skips API | Cache miss proceeds |
| REQ-004-002 DRY extraction | Shared function called correctly | Both paths (metrics on/off) work identically |
| REQ-004-003 Fail-fast | 401/403 aborts immediately | fail_fast=False returns normally |
| REQ-004-004 Permissions | Accessible folders processed | Inaccessible skipped; all-inaccessible returns empty |
| REQ-004-005 Token logging | Tokens accumulated and logged | Zero tokens logged on all-fail batch |
