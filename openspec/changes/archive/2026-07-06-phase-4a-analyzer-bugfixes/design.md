# Design: phase-4a-analyzer-bugfixes

## Context

`scripts/analizar_contexto.py` carries two parallel processing loops for the per-contact LLM pass. The `--with-metrics` branch (lines 773-796) and the interactive branch (lines 903-952) duplicate the same core sequence: `extraer_muestra_contacto` → `llamar_api` → `remove_think_tags` → `INSERT OR REPLACE` → `mostrar_progreso`. The two loops drifted: the `--with-metrics` variant omits the cache check (line 911-918), omits token accumulation, and never calls `registrar_logs_v2` (the interactive path does at line 971). This causes a data-loss bug on resume (Issue 1) and a missing audit trail (Issue 5). The two outer issues — fail-fast on 401/403 (Issue 3) and per-folder `PermissionError` handling (Issue 4) — are independent hardening that can land in the same change.

Phase 4a extracts a single `procesar_chats_con_ia()` that consolidates both loops, with an `options` dict that toggles token accumulation, fail-fast, and the user-confirmation prompt. This refactor (Issue 2) is the foundation: Issues 1 and 5 are fixed **inside** the new function, so the `--with-metrics` path inherits the cache check and the token log for free.

This design covers only `scripts/analizar_contexto.py`. `outputs/contexto_{ts}.{json,md}` and the `conversation_summaries` schema are unchanged. The new `__MAESTRO__` row from phase-4b is NOT yet written here.

## Goals / Non-Goals

**Goals** (locked):

| Goal | Detail |
|---|---|
| DRY consolidation | One `procesar_chats_con_ia()` consumed by both branches; both branches produce identical per-contact SQLite rows and `summaries` dict shapes |
| Cache check parity | `--with-metrics` and interactive paths both check `conversation_summaries` before calling the API; resume works for either path |
| Fail-fast on auth | `llamar_api(fail_fast=True)` calls `sys.exit("[FATAL] …")` on HTTP 401/403; `fail_fast=False` preserves today's print-and-return-`(None, 0, 0, 0, 0)` contract |
| Token audit | `--with-metrics` accumulates `prompt_tokens` / `candidate_tokens` / `total_tokens` and writes one `registrar_logs_v2` line per batch |
| Permission hardening | `seleccionar_base_datos()` skips a single inaccessible folder instead of aborting the whole scan |

**Non-Goals**: prompt field changes (phase-4b), master context synthesis (phase-4b), Phase 3 taxonomy YAML, new CLI flags, any schema migration.

## Architecture Decisions

### Decision: Single shared function with an `options` dict, not a class hierarchy

**Choice**: Extract `procesar_chats_con_ia(sample_list, db_path, options)` as a module-level function; the per-branch behavior, plus the SQLite handles, are encoded in `options`. This resolves the **BLOCKER-1** signature mismatch flagged by the gate review: the earlier draft declared 5 positional parameters (`sample_list, db_path, cursor, connection, options`) while the spec wording (REQ-004-002) and the actual call sites only need 3. Threading `cursor` and `connection` through the `options` dict keeps the call sites simple (`procesar_chats_con_ia(sample_list, db_path, options)`) and aligns the implementation with the spec.
**Alternatives considered**:
- Strategy class with `MetricsStrategy` / `InteractiveStrategy` subclasses — overkill for a 60-line loop.
- Pass `procesar_chats_con_ia` itself as a parameter to a higher-order function — adds a wrapper without removing the duplication.
- 5-parameter signature (the previously proposed signature) — rejected: it forces both call sites to thread 5 args and has no real readability benefit over a single `options` dict that bundles the SQLite handles with the behavior flags.
**Rationale**: A plain function with a small `options` dict matches the existing imperative style of the file (no OOP anywhere in the module). Bundling `cursor`/`connection` inside the dict also lets us add cache-stat return values cleanly (see CRITICAL-1 fix below) without growing the parameter list further. The dict has at most seven keys; explicit keyword args would be cleaner for Python 3.14, but a dict keeps the `options['registrar_logs'] = registrar_logs_v2` callback injection readable and lets the interactive path pass `None`.

### Decision: Cache check lives inside the function, not at call sites

**Choice**: The `SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'` check happens unconditionally for every contact inside `procesar_chats_con_ia`.
**Alternatives considered**: Have each call site do the check first and pass a "skip" flag. Rejected because the interactive path already does the check inline (line 911-918) and we are removing the duplication — splitting the check back out re-duplicates it.
**Rationale**: Issue 1 was a direct consequence of the `--with-metrics` loop forgetting this check. Putting the check inside the new function guarantees the fix is permanent: any future caller automatically benefits.

### Decision: `fail_fast` defaults to `False`

**Choice**: `llamar_api(prompt, current_report=None, is_individual=False, fail_fast=False)`.
**Rationale**: The interactive path is the default in batch mode and has no flag to flip `fail_fast=True`; defaulting off keeps its behavior bit-identical to today. The `--with-metrics` call site opts in explicitly. Any third-party caller importing `llamar_api` from this module is unaffected.

### Decision: `PermissionError` caught per-folder, not the whole scan

**Choice**: Move the `try/except` block from outside the `for folder in base_dir.parent.iterdir():` loop to inside it. The outer `try/except Exception` becomes a no-op for normal cases and remains as a last-resort safety net.
**Rationale**: `PermissionError` is the only realistic I/O failure here (the iteration itself does not require read access on the children). Per-folder `continue` is the minimum surface-area fix.

## Data Flow

```
                main() — branch on '--with-metrics' in sys.argv
                   │
       ┌───────────┴──────────────┐
       ▼ YES                      ▼ NO
   --with-metrics                interactive menu
       │                              │
       │ stratified sample            │ random.shuffle
       │ (lines 731-767)              │ (line 871)
       │                              │ opens conn/cursor
       │ opens conn/cursor            │ (lines 900-901)
       │ (lines 739-740)              │
       ▼                              ▼
   procesar_chats_con_ia(        procesar_chats_con_ia(
       sample_list,                  sample_list,
       db_path,                      db_path,
       options={                     options={
         'cursor': cursor,             'cursor': cursor,
         'connection': conn,           'connection': conn,
         'metrics_enabled': True,      'metrics_enabled': False,
         'fail_fast': True,            'fail_fast': False,
         'interactive': False,         'interactive': True,
         'registrar_logs':             'registrar_logs':
           registrar_logs_v2,            None,
       })                              })
       │                              │
       └──────────────┬───────────────┘
                      ▼
        for (phone, name) in sample_list:
            cache = SELECT summary … WHERE contact_phone=? AND period='profile'
            if cache:
                summaries[phone] = cache[0]    # populate from cache, no API call
                omitidos_por_cache += 1
                continue
            muestra = extraer_muestra_contacto(db_path, phone, name)
            if not muestra: continue
            text, p_tok, c_tok, t_tok, elapsed = llamar_api(
                muestra,
                is_individual=True,
                fail_fast=options['fail_fast'],    # abort on 401/403 if True
            )
            if text:
                clean = remove_think_tags(text)
                summaries[phone] = clean
                INSERT OR REPLACE conversation_summaries
                accumulate p_tok / c_tok / t_tok
                nuevos_analizados += 1
                if options['interactive']:
                    mostrar_progreso(...)
                    time.sleep(0.5)
            else:
                summaries[phone] = None
                if options['interactive']:
                    print(f"[WARN] No se pudo analizar {contact_label}.")

        cache_stats = {
            'nuevos_analizados': nuevos_analizados,
            'omitidos_por_cache': omitidos_por_cache,
        }

        # End of batch: if metrics enabled, log the per-batch token line.
        # Interactive path does NOT log here — its caller retains the legacy
        # registrar_logs_v2 call (line 971 in the unmodified flow).
        if options['metrics_enabled'] and options.get('registrar_logs') \
                and nuevos_analizados > 0:
            options['registrar_logs'](
                1, db_path.parent.parent.name,
                cache_stats['nuevos_analizados'],
                cache_stats['omitidos_por_cache'],
                lote_prompt_tokens, lote_candidate_tokens, lote_total_tokens,
                time.time() - batch_start,
            )

        return summaries, token_totals, cache_stats

   # Caller (main) after the function returns:

   --with-metrics branch             interactive branch
       │                                  │
       │ summaries, token_totals,         │ summaries, token_totals,
       │ cache_stats = ...                │ cache_stats = ...
       ▼                                  ▼
   total_usados_cache +=            total_usados_cache +=
       cache_stats['omitidos_por_cache']    cache_stats['omitidos_por_cache']
   dual_output_writer(              compilar_reporte_local(db_path)
       sample, metrics,             legacy [LOTE N] registrar_logs_v2
       summaries, …                 call at line 971 (uses
   )                                cache_stats['nuevos_analizados']
   compilar_reporte_local(db_path)  and cache_stats['omitidos_por_cache'])
                                   continues with menu / next batch
```

The two branches converge on the same `summaries` dict shape (`{phone: str | None}`) and the same SQLite row, so `dual_output_writer()` and `compilar_reporte_local()` work without modification.

## File Changes

| File | Action | Description |
|---|---|---|
| `scripts/analizar_contexto.py` | Modify | Add `procesar_chats_con_ia(sample_list, db_path, options)` after `compute_metrics()` (around line 243); replace the `--with-metrics` loop (lines 773-796) with a call passing `options={'cursor': cursor, 'connection': conn, 'metrics_enabled': True, 'fail_fast': True, 'registrar_logs': registrar_logs_v2}`; replace the interactive inner loop (lines 903-952) with a call passing `options={'cursor': cursor, 'connection': conn, 'metrics_enabled': False, 'fail_fast': False, 'interactive': True, 'registrar_logs': None}` — caller updates `total_usados_cache` from the returned `cache_stats['omitidos_por_cache']` (resolves **CRITICAL-1**); move the `try/except` inside the per-folder loop in `seleccionar_base_datos()` (lines 374-385); add `fail_fast: bool = False` to `llamar_api()` (line 518) and the `sys.exit` branch in the `HTTPError` handler (line 634) |
| `outputs/contexto_{ts}.{json,md}` | Unchanged | The writer already accepts `summaries` populated from cache. |
| `outputs/logs.txt` | Append | `--with-metrics` runs now produce a `[LOTE 1] DB=…` line. |
| `conversation_summaries` table | Unchanged | No migration. |

## Interfaces / Contracts

### `procesar_chats_con_ia()`

```python
def procesar_chats_con_ia(
    sample_list: list[tuple[str, str]],   # [(phone, name), ...]
    db_path: Path,
    options: dict,                         # see below — also carries cursor/connection
) -> tuple[dict, dict, dict]:              # (summaries, token_totals, cache_stats)
```

**Why the SQLite handles live inside `options` (BLOCKER-1 fix)**: The spec (REQ-004-002) and both call sites only need three arguments (`sample_list`, `db_path`, plus the per-branch `options`). Threading `cursor` and `connection` as separate positional args is rejected because (a) it bloats the call sites with two SQLite handles that are conceptually part of the run-scoped state, and (b) it leaves no room to grow the contract for cache stats (CRITICAL-1 fix) without an awkward 6-arg signature. The function uses `options['cursor']` and `options['connection']` exactly as it would use the previously proposed positional args.

**Parameters**:
- `sample_list`: list of `(phone, name)` tuples. The `_slot` third element used by `--with-metrics` today is stripped by the caller before invoking the function.
- `db_path`: passed through to `extraer_muestra_contacto` (which opens its own short-lived connection).
- `options` keys:
  - `cursor: sqlite3.Cursor` — the SQLite handle opened by the caller; the function reuses it for the cache `SELECT` and the `INSERT OR REPLACE`. Required.
  - `connection: sqlite3.Connection` — the SQLite connection opened by the caller; the function calls `conn.commit()` once at end of batch. Required.
  - `metrics_enabled: bool` — when `True`, accumulate tokens and (if `registrar_logs` is provided) call it once at end of batch with `lote_num=1`.
  - `fail_fast: bool` — forwarded to `llamar_api()`. `True` in `--with-metrics`, `False` in interactive.
  - `interactive: bool` — when `True`, show `mostrar_progreso` and the `[WARN]` line on API failure; when `False`, the caller (i.e. `dual_output_writer`) handles missing summaries.
  - `registrar_logs: callable | None` — when set AND `metrics_enabled` is `True`, called once at end of batch with positional args matching `registrar_logs_v2`'s signature (lote_num, db_name, analizados, de_cache, prompt_tokens, candidate_tokens, total_tokens, tiempo_segundos). `db_name` is `db_path.parent.parent.name`.

**Returns** (3-tuple):
- `summaries: dict[str, str | None]` — phone → cleaned summary text (or `None` on extraction failure / API error).
- `token_totals: dict[str, int | float]` — `{"prompt_tokens": int, "candidate_tokens": int, "total_tokens": int, "elapsed_seconds": float}`. Interactive path ignores this; `--with-metrics` passes it to `dual_output_writer` and the optional logger.
- `cache_stats: dict[str, int]` — `{"nuevos_analizados": int, "omitidos_por_cache": int}`. **This is the CRITICAL-1 fix**: the function previously returned only a 2-tuple and the interactive caller's `total_usados_cache` global (line 884) was never updated by the shared function. The caller now reads `cache_stats['omitidos_por_cache']` and `cache_stats['nuevos_analizados']` to refresh its own counters (see call-site snippets below).

**Side effects**:
- Zero or one `SELECT` per contact on `conversation_summaries`.
- Zero or one `INSERT OR REPLACE` per contact that misses the cache.
- One `conn.commit()` after each successful `INSERT OR REPLACE` (matches the pre-change per-row commit behavior at line 789 in `--with-metrics` and line 945 in interactive; preserves the byte-identical claim for the interactive path).
- Calls `extraer_muestra_contacto` and `llamar_api` exactly once per non-cached contact.
- When `options['interactive']` is `True`, prints the progress bar and `[WARN]` lines.
- When `options['registrar_logs']` is set AND `metrics_enabled` is `True`, one call to `registrar_logs_v2` at end of batch.

**Call site — `--with-metrics` branch** (replaces lines 773-796):

```python
# After stratified sample + metrics (lines 731-770)
sample_with_names = [(p, phone_to_name.get(p, ""), None) for p in sample_phones]
summaries, token_totals, cache_stats = procesar_chats_con_ia(
    sample_with_names,
    db_path,
    options={
        'cursor': cursor,
        'connection': conn,
        'metrics_enabled': True,
        'fail_fast': True,
        'interactive': False,
        'registrar_logs': registrar_logs_v2,
    },
)
# `cache_stats['nuevos_analizados']` and `cache_stats['omitidos_por_cache']` are
# already passed to registrar_logs_v2 inside the function when metrics_enabled=True.
# No caller-side counter update is needed in this branch.
```

**Call site — interactive branch** (replaces the inner loop at lines 903-952):

```python
# Inside the per-lote `while offset < total_contactos` loop (line 886+),
# after `conn = sqlite3.connect(db_path); cursor = conn.cursor()` (lines 900-901):
contacts_batch = todos_contactos[offset : limite_lote]   # [(phone, name), ...]
summaries, _token_totals, cache_stats = procesar_chats_con_ia(
    contacts_batch,
    db_path,
    options={
        'cursor': cursor,
        'connection': conn,
        'metrics_enabled': False,
        'fail_fast': False,
        'interactive': True,
        'registrar_logs': None,
    },
)
# CRITICAL-1 fix: project the per-batch cache stats into the run-level globals
# the interactive summary block at lines 988-1003 reads. Without this, the
# "Perfiles recuperados de caché local: 0" line would be wrong on resumed runs.
total_usados_cache     += cache_stats['omitidos_por_cache']
total_nuevos_analizados += cache_stats['nuevos_analizados']
# Legacy registrar_logs_v2 call stays at line 971 (byte-identical to pre-change
# behavior) and now reads `nuevos_analizados`/`omitidos_por_cache` from the
# shared function's returned cache_stats instead of local counters.
nuevos_analizados      = cache_stats['nuevos_analizados']
omitidos_por_cache     = cache_stats['omitidos_por_cache']
lote_prompt_tokens     = _token_totals['prompt_tokens']
lote_candidate_tokens  = _token_totals['candidate_tokens']
lote_total_tokens      = _token_totals['total_tokens']
```

The five lines that copy fields from `_token_totals` and `cache_stats` back into the local `nuevos_analizados`/`omitidos_por_cache`/`lote_*_tokens` variables are the **minimal** change to the interactive loop body: the rest of the per-batch block (the line 971 `registrar_logs_v2` call, the per-batch `print(f"--- Estadísticas del Lote …")` block, the lote_size increment, and the user-confirmation prompt) is left exactly as it was. Net interactive diff: replace ~50 lines of inner-loop body with one `procesar_chats_con_ia` call plus the 8-line projection above.

### `llamar_api()` — signature change

```python
def llamar_api(prompt, current_report=None, is_individual=False, fail_fast: bool = False):
```

The `HTTPError` handler at lines 634-640 gains a `sys.exit` branch:

```python
except urllib.error.HTTPError as e:
    if fail_fast and e.code in (401, 403):
        sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")
    print(f"\n[ERROR] Error HTTP de la API: {e.code} - {e.reason}")
    try:
        print("Detalles del error:", e.read().decode('utf-8'))
    except Exception:
        pass
    return None, 0, 0, 0, 0
```

**Provider-specific status codes (warning note)**: The spec lists 401/403 because those are the auth-rejected codes emitted by OpenAI-compatible endpoints. Gemini's `generateContent` endpoint uses **HTTP 400** with a `INVALID_API_KEY` payload for the same condition. The `e.code in (401, 403)` check covers the OpenAI-compatible path; the apply phase must smoke-test against the actual deployment (whichever provider `.env` points to) and widen the set to `(400, 401, 403)` if a 400 is observed on a bad key. The failure mode is still abort; only the exact status code is provider-specific. Comment in source: `# test against actual deployment; widen to 400 if needed`.

### `seleccionar_base_datos()` — permission hardening (BEFORE/AFTER)

```python
# BEFORE (lines 374-385)
def seleccionar_base_datos(db_name=None):
    rutas_validas = []
    try:
        for folder in base_dir.parent.iterdir():
            if folder.is_dir() and folder.name != 'wpp_analytics':
                db_file = folder / 'database' / 'whatsapp.sqlite'
                if db_file.exists():
                    rutas_validas.append((folder.name, db_file))
    except Exception as e:
        print(f"[ERROR] No se pudo escanear el Escritorio en busca de bases de datos: {str(e)}")
        return None
```

```python
# AFTER
def seleccionar_base_datos(db_name=None):
    rutas_validas = []
    for folder in base_dir.parent.iterdir():
        try:
            if folder.is_dir() and folder.name != 'wpp_analytics':
                db_file = folder / 'database' / 'whatsapp.sqlite'
                if db_file.exists():
                    rutas_validas.append((folder.name, db_file))
        except PermissionError:
            continue   # skip inaccessible folder, keep scanning siblings

    if not rutas_validas:
        print("[ERROR] No se encontró ninguna base de datos de WhatsApp en el Escritorio.")
        print("Asegúrate de que tus carpetas de WhatsApp tengan el archivo 'database/whatsapp.sqlite' sincronizado.")
        return None
    # ... rest unchanged (--db override, single-DB auto-pick, multi-DB prompt)
```

The broad `except Exception` is removed because the only realistic I/O failure on a directory scan is `PermissionError`; any other `OSError` (e.g. parent deleted mid-scan) will surface to the caller and abort, which is the desired behavior — never return a partial list silently.

## Token Logging Wiring (Issue 5)

Inside `procesar_chats_con_ia`, on every successful `llamar_api` call:

```python
p_tok, c_tok, t_tok, _elapsed = (...,)
if options['metrics_enabled']:
    lote_prompt_tokens   += p_tok
    lote_candidate_tokens += c_tok
    lote_total_tokens     += t_tok
```

At end of batch:

```python
if options['metrics_enabled']:
    batch_elapsed = time.time() - batch_start
    if options.get('registrar_logs') and nuevos_analizados > 0:
        options['registrar_logs'](
            1,                              # lote_num
            db_path.parent.parent.name,     # db_name
            nuevos_analizados,
            omitidos_por_cache,
            lote_prompt_tokens,
            lote_candidate_tokens,
            lote_total_tokens,
            batch_elapsed,
        )
```

The `--with-metrics` call site passes `options['registrar_logs'] = registrar_logs_v2`. The interactive call site passes `options['registrar_logs'] = None`; the existing per-batch `registrar_logs_v2` call at line 971 stays exactly where it is (interactive keeps its own legacy logging).

## Backward Compatibility

| Caller | Today | After | Compatible? |
|---|---|---|---|
| `python scripts/analizar_contexto.py` (interactive) | Lines 886-986 loop, registers logs at line 971 | Loop body replaced by call to `procesar_chats_con_ia(... interactive=True)`, legacy `registrar_logs_v2` call kept at line 971. The 6-arg `options` dict carries the SQLite handles; the function returns `cache_stats` which the caller projects into `total_usados_cache` and `total_nuevos_analizados` (see Interfaces §Call site — interactive). | **Yes — byte-identical**: the per-contact `SELECT`/API call/`INSERT OR REPLACE`/`mostrar_progreso`/`time.sleep` sequence is unchanged; the `[LOTE N]` line written at line 971 uses the same `nuevos_analizados`/`omitidos_por_cache` values it did before (now sourced from the function's return). The interactive path gains **nothing** observable. The only file touched is `scripts/analizar_contexto.py`; the interactive summary block at lines 988-1003 still reads `total_nuevos_analizados` and `total_usados_cache` as it did before. |
| `python scripts/analizar_contexto.py --with-metrics --db NAME` | Loop at lines 773-796, no cache check, no token log | Loop replaced by call passing `options={'metrics_enabled': True, 'fail_fast': True, 'registrar_logs': registrar_logs_v2, 'cursor': cursor, 'connection': conn}` | **Behavior change — intentional**. The new cache check is the Issue 1 fix; the new token log is the Issue 5 fix. Output format (`contexto_{ts}.json` + `.md`) is unchanged. The `summaries` shape consumed by `dual_output_writer` is preserved. |
| Imports of `llamar_api` from other scripts | `llamar_api(prompt, current_report=None, is_individual=False)` | `llamar_api(prompt, current_report=None, is_individual=False, fail_fast=False)` | **Yes** — `fail_fast` is a new optional kwarg with a default that preserves the existing return contract. |
| `compilar_reporte_local(db_path)` | Reads `conversation_summaries` directly | Same | **Yes** — no call site changes. |
| `dual_output_writer(...)` | Consumes `summaries` dict | Same | **Yes** — `summaries` shape is preserved. |

## Migration

No data migration. The cache check reads rows that already exist; the `INSERT OR REPLACE` overwrites with new content; the schema is unchanged.

**Rollback procedure** (per `proposal.md`): revert `scripts/analizar_contexto.py` to the pre-change commit. No DB cleanup needed; any rows written by the new code use the same `(contact_phone, period='profile')` unique key as the old code.

## Observability

New log lines added by phase-4a:

| Surface | New line | When |
|---|---|---|
| stdout | `Procesando muestra estratificada: [█████-----] 50.0% (5/10)` | `--with-metrics` loop, on each contact (same as today, now driven by the shared function) |
| `outputs/logs.txt` | `[YYYY-MM-DD HH:MM:SS] [LOTE 1] DB=auto_wpp \| Analizados=10 \| Caché=0 \| Tokens Entrada=N \| Tokens Salida=N \| Total Tokens=N \| Tiempo Lote=X.XXs` | `--with-metrics`, end of batch (new — was missing) |
| stdout | `[WARN] No se pudo analizar el contacto Juan.` | Interactive path, on API failure (unchanged — moved into shared function with `interactive=True`) |

No new metrics. Token totals are the same as the interactive path, now visible for the new path.

## Performance

- **Cache check**: one `SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'` per contact. On the 1000-contact scale assumed by the proposal, 300 extra micro-queries per run. SQLite handles this in microseconds; total overhead < 50 ms. Negligible.
- **No extra API calls**: cache hits skip the API call, so wall-clock time goes **down** on resume (replacing a 1-3s API round-trip with a sub-ms SELECT).
- **Token accumulation**: four `+=` ops per contact, O(1), negligible.

## Security

No new attack surface. The `fail_fast=True` path calls `sys.exit` with a string; no untrusted input crosses the boundary. The `PermissionError` catch swallows no data — the function only continues the loop; the parent process never receives the inaccessible folder's contents. The cache check reads `summary` from a row we previously wrote ourselves; no new SQL injection surface (parameterized `?` placeholders are already used).

## Open Questions

None — all open items are resolved by the proposal defaults:
- **Fail-fast scope**: all `--with-metrics` runs (no flag dependency).
- **DRY location**: shared function, not a class.
- **Cache check location**: inside the function.
- **Token logging**: one line per batch via `registrar_logs_v2` injection.

## Testing Strategy

No test framework is available (`openspec/config.yaml:9`, `tests/README.md`). Validation is smoke testing per `phase-1 design.md §Migration/Rollout`. All four smoke tests below run against a real local database with a small sample to keep wall-clock under 5 minutes.

| # | Command | Expected outcome |
|---|---|---|
| 1 | `python scripts/analizar_contexto.py --with-metrics --db <test_db> --sample-size 0.10` (10 contacts); run twice | First run writes 10 `period='profile'` rows; second run reads them from cache — stdout shows `Caché=10` in `outputs/logs.txt`; **no second batch of API calls** (verify via `logs.txt` total tokens unchanged between runs). |
| 2 | `GEMINI_API_KEY=invalid python scripts/analizar_contexto.py --with-metrics --db <test_db> --sample-size 0.10` | Process exits with `[FATAL] Credenciales rechazadas (HTTP 401). Abortando.` and no further contacts are processed. |
| 3 | `python scripts/analizar_contexto.py` (interactive, mode 1, 50 chats) | Output `outputs/reporte_contexto_v2.md` is byte-identical to pre-change output for the same DB; interactive `[LOTE N]` line still appears in `outputs/logs.txt`. |
| 4 | Create a sibling folder with `chmod 000 database/whatsapp.sqlite` (or `icacls folder /deny "Users:(R)"` on Windows) so `is_dir()` raises `PermissionError`; then run `python scripts/analizar_contexto.py --with-metrics --db <valid_db>` | Function returns the valid DB; the inaccessible sibling is silently skipped; no `[ERROR]` printed. |

For test 2 the actual HTTP code is provider-specific — Gemini returns 400 for bad API keys, OpenAI-compatible endpoints return 401. Apply phase must confirm the live behavior and adjust the `e.code in (401, 403)` test if necessary (the failure-mode is still abort, but the exact status code may differ across providers; the spec says 401/403, so the test checks for one of those).

### Additional Edge Cases

The four smoke tests above cover the happy path. The gate review flagged three boundary cases that the apply phase must verify with targeted unit-style asserts (no extra fixtures; reuse the test database from Smoke 1).

| # | Case | Expected behavior | What proves it |
|---|---|---|---|
| E1 | `sample_list = []` (empty input, e.g. a tier that yielded 0 contacts) | Function returns `({}, zeroed-token-totals, {'nuevos_analizados': 0, 'omitidos_por_cache': 0})`. No API call. No `registrar_logs_v2` call. No commit. | Patch `llamar_api` with a sentinel `raise AssertionError("called")`; the function returns cleanly. The interactive summary block reads `total_nuevos_analizados=0` and `total_usados_cache=0`. |
| E2 | Cache hit returns empty/whitespace summary (data corruption / hand-edited row) | The function still treats the row as a cache hit: `summaries[phone] = cached_summary.strip()` (or `""` if whitespace-only). The contact is counted in `omitidos_por_cache`, **not** in `nuevos_analizados`. The cache row is NOT overwritten. The `dual_output_writer`/`compilar_reporte_local` render the contact as `*Sin resumen disponible.*` / empty profile. | Manually `INSERT OR REPLACE` a `period='profile'` row with `summary='   '` for a sampled contact, run `--with-metrics`, and confirm `logs.txt` shows `Caché+=1` (not `Analizados+=1`) and the Markdown output shows `*Sin resumen disponible.*` for that contact. |
| E3 | Caller omits `options['registrar_logs']` but passes `metrics_enabled=True` (defensive case for future refactors) | Token accumulation runs, but the per-batch `registrar_logs_v2` call is skipped. `token_totals` still reflects the accumulated values. The function does not raise. | Call `procesar_chats_con_ia(sample, db, {'cursor': cursor, 'connection': conn, 'metrics_enabled': True, 'fail_fast': True, 'interactive': False, 'registrar_logs': None})` and verify the run completes; `outputs/logs.txt` shows no new `[LOTE 1]` line. |

## Acceptance Criteria

| Spec REQ | Design mapping | Acceptance check |
|---|---|---|
| REQ-004-001 Cache check | `SELECT summary … WHERE period='profile'` at top of per-contact iteration inside `procesar_chats_con_ia` | Smoke 1: second run shows `Caché=10` and zero new API tokens |
| REQ-004-002 DRY extraction | New `procesar_chats_con_ia()` consumed by both branches with `options` dict | Both branches' `summaries` and SQLite rows are byte-identical for the same DB |
| REQ-004-003 Fail-fast | `fail_fast: bool = False` kwarg on `llamar_api`; `sys.exit` in `HTTPError` handler | Smoke 2: invalid key aborts with `[FATAL]` |
| REQ-004-004 Permission hardening | `try/except PermissionError` inside per-folder loop | Smoke 4: inaccessible sibling skipped, valid DB returned |
| REQ-004-005 Token logging | `metrics_enabled=True` triggers accumulation and `registrar_logs` callback | Smoke 1: `outputs/logs.txt` contains `[LOTE 1] DB=… | Total Tokens=…` |
