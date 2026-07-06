# Exploration: phase-4-analyzer-feedback-fixes

## Executive Summary

This exploration examines 7 feedback items against `analizar_contexto.py` V2. One is a confirmed data-loss bug (cache check missing in `--with-metrics` path), three are missing features (fail-fast auth errors, master context generation, token logging in the new path), two are refactors (DRY extraction, prompt field reduction), and one is a low-risk hardening (permission error handling). The DRY refactor is foundational — it unblocks items 1, 5, and 7. Item 7 (Master Context) has significant non-obvious complexity around sample size, API failure recovery, and interaction with Phase 3 taxonomy.

---

## Per-Issue Analysis

### Issue 1 — Bug Crítico de Caché (Missing DB lookup in `--with-metrics`)

**Classification**: Bug | **Severity**: Critical | **Complexity**: Small

**Code location**: `scripts/analizar_contexto.py` lines 773–796 (the `--with-metrics` LLM loop).

**Description**: The `--with-metrics` branch calls `llamar_api()` for every sampled contact without first checking `conversation_summaries` for an existing cached profile. This means:
- Resume after interruption is broken: the script ignores previously saved results and re-calls the API.
- If interrupted mid-run, the in-memory `summaries` dict is empty → `compilar_reporte_local()` reads from DB and finds no entries → output contains `*Sin resumen disponible.*`.

**Interactive branch comparison** (lines 903–918) — does it correctly:
```python
cursor.execute(
    "SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'",
    (phone,)
)
row = cursor.fetchone()
if row:
    omitidos_por_cache += 1
    total_usados_cache += 1
    continue  # ← skipped in --with-metrics path
```

**Fix approach**: Add the same `SELECT` cache check at the top of the `--with-metrics` loop, with an else-branch that skips to `mostrar_progreso` without calling `llamar_api`.

**Risk**: None. Straightforward additive check.

---

### Issue 2 — Violación DRY (Duplicated Processing Loop)

**Classification**: Refactor | **Severity**: Medium | **Complexity**: Medium

**Code location**: Two separate loops:
- `--with-metrics` path: lines 773–796 (LLM call + SQLite write, no token accumulation, no logging).
- Interactive path: lines 886–986 (full batch loop with token counting, `registrar_logs_v2`, confirmation prompts, etc.).

**Description**: The core sequence `extraer_muestra_contacto → llamar_api → remove_think_tags → SQLite INSERT OR REPLACE → mostrar_progreso` appears in both branches with slight variations. The `--with-metrics` variant lacks token tracking and logging entirely.

**Proposed extraction**: A single `procesar_chats_con_ia(sample_list, db_path, cursor, ...)` function that:
- Accepts a list of `(phone, name)` tuples.
- Optionally accumulates token counters if provided.
- Optionally calls `registrar_logs_v2` if metrics are present.
- Returns `(summaries dict, token totals)`.

**Dependency note**: This refactor is **foundational** — items 1, 5, and 7 all benefit or depend on a clean, single processing function. The cache bug (issue 1) would be fixed inside this function. Token logging (issue 5) would be wired up here. Master context aggregation (issue 7) would consume the collected profiles from this function's return.

**Risk**: Medium. Extracting a shared function requires careful handling of closure variables (cursor, db_path, connection state). The two call sites have subtly different pre-processing (stratified sample vs random shuffle). Test manually with both paths after refactor.

---

### Issue 3 — Carencia de Fail-Fast (Auth Error Handling)

**Classification**: Feature/Bug | **Severity**: Medium | **Complexity**: Small

**Code location**: `llamar_api()` lines 634–640.

**Description**: When `llamar_api()` receives an HTTP 401 or 403, it prints an error and returns `(None, 0, 0, 0, 0)`. The calling loop (both paths) continues iterating over remaining contacts. For a credential rejection error (bad API key, revoked token), continuing wastes API calls and produces a run where every contact fails.

**Fix approach**: Add a `fail_fast` parameter to `llamar_api` (default `False` for backward compat). When `True` and HTTP status is 401 or 403, call `sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")` instead of returning None.

**Risk**: Low. `sys.exit` is safe in a batch script context. The parameter keeps backward compatibility.

---

### Issue 4 — Riesgo de Permisos en Exploración de Archivos

**Classification**: Bug/Hardening | **Severity**: Low | **Complexity**: Small

**Code location**: `seleccionar_base_datos()` lines 374–385.

**Description**: The outer `try/except Exception` at line 376 wraps the entire directory scan. However, a permission error on a single subfolder (`folder.is_dir()` or `db_file.exists()`) could theoretically throw before the inner checks complete. The current `except Exception as e` at line 383 catches this globally and returns `None`.

**Fix approach**: Move the `try/except` inside the loop, per-folder, so one permission-denied folder doesn't abort the entire scan:
```python
for folder in base_dir.parent.iterdir():
    try:
        if folder.is_dir() and folder.name != 'wpp_analytics':
            db_file = folder / 'database' / 'whatsapp.sqlite'
            if db_file.exists():
                rutas_validas.append((folder.name, db_file))
    except PermissionError:
        continue  # skip inaccessible folders, keep scanning
```

**Risk**: Very low. This is defensive hardening with no behavioral change for正常工作 paths.

---

### Issue 5 — Omisión de Logueo de Tokens (Missing `registrar_logs_v2` in `--with-metrics`)

**Classification**: Bug | **Severity**: Medium | **Complexity**: Small

**Code location**: `--with-metrics` branch, lines 773–819 (no token accumulation, no logging).

**Description**: The `--with-metrics` path does not accumulate `prompt_tokens`, `candidate_tokens`, or `total_tokens` from `llamar_api()` calls, and never invokes `registrar_logs_v2()`. The interactive path does this correctly at line 971. Without logging, there is no audit trail for token consumption in the new path.

**Fix approach**: Once the DRY extraction (issue 2) is done, add token accumulation and a call to `registrar_logs_v2` at the end of the `--with-metrics` branch. Alternatively, accumulate inline tokens (trivial addition).

**Risk**: Low. Token values are already returned by `llamar_api`; wiring them up is straightforward.

---

### Issue 6 — Refinamiento del Prompt (Commercial Focus + Token Savings)

**Classification**: Refactor | **Severity**: Medium | **Complexity**: Small

**Code location**: `llamar_api()` lines 538–550 (`is_individual=True` prompt), lines 563–570 (batch prompt).

**Description**: The current prompt extracts:
1. Categoría Ocupacional detallada
2. Allegados y Círculo Social
3. Temas Principales (3 topics)
4. Dinámica Relacional

Feedback requires removing "Categoría Ocupacional detallada" and "Allegados", keeping only:
- **Vínculo Comercial**: Clasificar en (Cliente, Proveedor, Empleado, Familiar, Spam, Otro)
- **Temas Clave**: Palabras clave precisas de la interacción

The removed fields increase token cost and risk of alucinaciones without B2B value. This is critical for Phase 3 taxonomy compatibility.

**Prompt change** (individual path example):
```
# BEFORE
1. Categoría Ocupacional: Clasifica al contacto en [Empresario/Emprendedor], [Estudiante], [Desempleado], [Personal] u [Otro/Indet.]...
2. Allegados y Círculo Social: Identifica nombres de terceros mencionados...
3. Temas Principales: Los 3 asuntos o tópicos más recurrentes...
4. Dinámica Relacional: Define el tipo de relación...

# AFTER
1. Vínculo Comercial: Clasifica al contacto en [Cliente], [Proveedor], [Empleado], [Familiar], [Spam], [Otro].
2. Temas Clave: Palabras clave precisas que representen la interacción (máximo 5).
```

**Risk**: Low. This only changes what the LLM extracts. The stored summary format in `conversation_summaries` will change, but this is the intended effect. Verify that `compilar_reporte_local()` and `dual_output_writer()` handle the new format correctly (they just write whatever is stored, so no code change needed there).

---

### Issue 7 — Generación del Contexto Maestro del Negocio

**Classification**: Feature | **Severity**: High (strategic value) | **Complexity**: Large

**Code location**: No existing implementation. Would be added after the LLM loop in `--with-metrics`.

**Description**: After processing all contacts in a sample, make a final API call that synthesizes all individual profiles into a "Master Business Context" (Resumen Ejecutivo). This output is prepended to the Markdown report.

**Key questions the propose phase must answer**:
1. **Input to master call**: Should it consume the raw `summaries` dict (structured text per contact) or a compact aggregation (all commercial-link labels + all topic keywords)?
2. **Sample size risk**: If processing 300 contacts (30% of 1000), the master call receives 300 individual summaries. This could exceed context window and inflate costs. Should there be a tier-level summary first, then master call on tier summaries?
3. **API failure recovery**: If the master call fails (timeout, 500, etc.), should the individual results still be persisted? Should there be a retry?
4. **Caching**: Should the master context be stored in `conversation_summaries` with a special `period='master'`? This would enable resume.
5. **Phase 3 interaction**: The taxonomy from Phase 2/3 may define the label set for "Vínculo Comercial". The master context prompt must use the same taxonomy labels. This creates a coupling risk if Phase 3 is not finalized.

**Non-obvious risk — taxonomy coupling**: Issue 6 changes the prompt to use specific commercial-link labels. Issue 7's master call must reference the same label taxonomy. If Phase 3 defines this taxonomy in a YAML file, the master call logic must read that file. Currently `buscar_datos.py` has hardcoded taxonomy; Phase 2 was supposed to externalize this to YAML. If Phase 3 is delayed, issue 7 cannot be fully specified.

**Risk**: Medium-High. The master call is a new API call with no existing error handling pattern for a "final aggregation" step. Design must specify failure behavior explicitly.

---

## Dependency Map

```
Issue 2 (DRY refactor)  ──────┬──► Issue 1 (cache check fix)
                               ├──► Issue 5 (token logging)
                               └──► Issue 7 (master context aggregation)
                                    │
                                    └──► Issue 6 (prompt fields)
                                             (master call uses same labels)

Issue 3 (fail-fast)       ────► standalone, no dependents

Issue 4 (permissions)     ────► standalone, no dependents
```

**Blocking relationship**: Issue 2 is the critical path. All of 1, 5, and 7 are simpler to implement once the processing loop is deduplicated. Issue 6 (prompt) is independent but feeds into issue 7's label vocabulary.

---

## Scope Decision

**Recommended split**: Two coherent changes.

### phase-4a — Bugfixes + Hardening (small, self-contained)
- Issue 1: Cache check in `--with-metrics`
- Issue 3: Fail-fast on auth errors
- Issue 4: Permission error handling per-folder
- Issue 5: Token logging in `--with-metrics`

**Rationale**: These are surgical fixes that don't require architectural decisions. They can be smoke-tested in one session. Estimated review footprint: ~100 lines.

### phase-4b — Contexto Maestro + Prompt Refinamiento (medium, design needed)
- Issue 6: Prompt field reduction (low-risk text change)
- Issue 7: Master Business Context generation (new feature requiring design)

**Rationale**: Issue 7 has significant design complexity (sample size, API failure, caching, Phase 3 coupling). Issue 6 is simple but must be sequenced before issue 7 since the master call uses the same label vocabulary.

**Alternative**: Single `phase-4` change with issues 1+3+4+5+6 as tasks and issue 7 as a separate design track. Given the review budget of 800 lines, a single PR could fit but would be at the high end.

---

## Non-Obvious Risks

1. **Phase 3 taxonomy coupling (Issue 7)**: The "Vínculo Comercial" label set (Cliente, Proveedor, etc.) is referenced by both issue 6 and issue 7. If Phase 3 changes this taxonomy to YAML-externalized values, the master call prompt must be updated to read from that file. This coupling is not mentioned in the feedback.

2. **Sample size pressure on master call (Issue 7)**: A 30% sample of 1000 contacts = 300 contacts. If the master call receives all 300 individual summaries as input, this may exceed context windows and inflate costs significantly. The design needs to specify whether a two-pass approach (contact → tier summary → master) is needed.

3. **API failure on final call (Issue 7)**: If the master call fails after all individual profiles are already persisted to SQLite, the system is in an inconsistent state (individual results exist but master summary is missing). The design must specify retry logic or at minimum a graceful degradation (individual results still usable without master context).

4. **Schema touch (Issue 1)**: The fix adds a SELECT query before the LLM call in `--with-metrics`. This adds one round-trip per contact in the sample. At 300 contacts, this is 300 extra micro-queries. Negligible overhead, but worth noting.

5. **Prompt version compatibility**: Changing the prompt (issue 6) means stored summaries use a different format from previous runs. `compilar_reporte_local()` and `dual_output_writer()` don't parse the summary content — they just write it — so no code change needed there. However, any future code that assumes the old 4-field format will break.

---

## Open Questions for Propose Phase

1. **phase-4 split**: Does the user want a single coherent change or the 4a/4b split? The scope decision section recommends split for manageability.

2. **Issue 7 sample strategy**: Should the master call receive raw per-contact summaries, or a two-pass aggregation (contacts → tier summaries → master)? This affects API cost and complexity.

3. **Issue 7 failure handling**: If the master API call fails, should: (a) raise and abort, (b) retry once, or (c) log warning and continue with individual results only?

4. **Issue 7 persistence**: Should the master context be stored in `conversation_summaries` with `period='master'` for cache/resume, or only written to the output files?

5. **Phase 3 timeline**: Is Phase 3 (taxonomy YAML externalization) expected to land before or after these fixes? This affects whether issue 7 should hardcode the commercial-link labels or read them from a config file.

6. **Fail-fast scope**: Should fail-fast apply to all `--with-metrics` runs, or only when the `--with-metrics` flag is combined with `--auto` (if such a flag exists)?

---

## Affected Files

| File | Why Affected |
|---|---|
| `scripts/analizar_contexto.py` | All 7 issues touch this file directly. Issues 1, 2, 3, 4, 5, 6, 7 all require changes here. |
| `outputs/contexto_{ts}.md` | Issue 7 prepends master context header. Issue 6 changes the per-contact body format. |
| `outputs/contexto_{ts}.json` | Issue 7 may add a `master_context` field. |
| `outputs/logs.txt` | Issue 5 enables logging for `--with-metrics` runs. |
| `conversation_summaries` SQLite table | Issue 7 may add a `period='master'` row. Issues 1, 5 don't change schema. |

---

## Severity Summary

| Issue | Class | Severity | Complexity | Blocks |
|---|---|---|---|---|
| 1. Cache bug in `--with-metrics` | Bug | Critical | Small | — |
| 2. DRY violation | Refactor | Medium | Medium | 1, 5, 7 |
| 3. No fail-fast on auth errors | Feature/Bug | Medium | Small | — |
| 4. Permission error handling | Bug/Hardening | Low | Small | — |
| 5. Missing token logging | Bug | Medium | Small | — |
| 6. Prompt field reduction | Refactor | Medium | Small | 7 |
| 7. Master Business Context | Feature | High | Large | — |
