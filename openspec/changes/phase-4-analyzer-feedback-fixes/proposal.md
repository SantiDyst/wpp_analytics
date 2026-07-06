# Proposal: phase-4-analyzer-feedback-fixes

## Intent

This change addresses seven feedback items collected after the first production run of `analizar_contexto.py`. The work resolves one confirmed data-loss bug (cache check missing in `--with-metrics`), adds missing operational hardening (fail-fast auth, per-folder permissions), enables token audit logging in the new path, trims the LLM prompt to reduce cost and alucinaciones, and introduces a new Master Business Context synthesis call. The work is split into two sub-changes to keep each PR scannable under the 800-line review budget.

---

## Scope Decision

**Split into two sub-changes**, aligned with the `ask-always` delivery strategy and the exploration's dependency map:

| Sub-change | Issues | Rationale |
|---|---|---|
| `phase-4a-analyzer-bugfixes` | 1 (cache), 3 (fail-fast), 4 (permissions), 5 (token logging) | Surgical fixes; no architectural decisions; ~100 lines |
| `phase-4b-analyzer-contexto-maestro` | 6 (prompt), 7 (master context) | Prompt text is simple; master call is design-heavy |

A single 800+ line PR would trigger an ask under `ask-always`. Splitting keeps each PR autonomous and reviewable in one session. Issue 2 (DRY refactor) is the foundation for phase-4a and is implemented as part of that sub-change's scope.

---

## Scope: phase-4a-analyzer-bugfixes

### In Scope
- Issue 1: Add `SELECT` cache check at top of `--with-metrics` loop before calling `llamar_api()`
- Issue 2: Extract shared `procesar_chats_con_ia()` function — consolidates both processing paths; issue 1 fix lives inside this function
- Issue 3: Add `fail_fast` parameter to `llamar_api()`; raise `sys.exit` on HTTP 401/403 when `True`
- Issue 4: Move `try/except PermissionError` inside the per-folder loop in `seleccionar_base_datos()`
- Issue 5: Wire token accumulation + `registrar_logs_v2()` into `--with-metrics` path after DRY extraction

### Out of Scope
- Prompt field changes (issue 6) — phase-4b
- Master Business Context generation (issue 7) — phase-4b
- Phase 3 taxonomy YAML externalization

### Non-Goals
- Comprehensive test suite (strict_tdd is off; smoke-test by running both paths manually)
- Changes to `compilar_reporte_local()` or `dual_output_writer()` — they are format-agnostic

---

## Scope: phase-4b-analyzer-contexto-maestro

### In Scope
- Issue 6: Reduce prompt fields — remove "Categoría Ocupacional detallada" and "Allegados y Círculo Social"; keep only "Vínculo Comercial" (6 labels) and "Temas Clave" (max 5 keywords)
- Issue 7: After processing all contacts, make a final synthesis API call producing "Contexto Maestro del Negocio"; prepend as YAML-front-matter header in Markdown report; store in SQLite with `period='master'`

### Out of Scope
- Phase 3 taxonomy YAML integration — hardcode 6-label set with TODO note
- Multi-DB aggregation (master call operates on single database at a time)

---

## Approach

### phase-4a — Bugfixes + Hardening

**DRY extraction (issue 2)**: Create `procesar_chats_con_ia(sample_list, db_path, cursor, connection, options)` that:
- Accepts `(phone, name)` tuples
- Optionally accepts token accumulator dicts and a `metrics_enabled` flag
- Conditionally calls `registrar_logs_v2()` when metrics are on
- Returns `(summaries dict, token totals dict)`

**Cache fix (issue 1)**: Inside `procesar_chats_con_ia`, check `conversation_summaries` for `period='profile'` before calling `llamar_api()`. Skip to next contact on cache hit.

**Fail-fast (issue 3)**: Add `fail_fast: bool = False` to `llamar_api()`. On HTTP 401/403 with `fail_fast=True`, call `sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")`. The `--with-metrics` call site passes `fail_fast=True`.

**Permission hardening (issue 4)**: Move `try/except PermissionError` inside the per-folder loop in `seleccionar_base_datos()`, catching and skipping individual inaccessible folders.

**Token logging (issue 5)**: After DRY extraction, `--with-metrics` path passes token accumulators and `metrics_enabled=True`; function calls `registrar_logs_v2()` at end of batch.

### phase-4b — Prompt Refinement + Master Context

**Prompt change (issue 6)**: In `llamar_api()` individual-path prompt (lines 538–550) and batch-path prompt (lines 563–570), replace 4-field extraction with 2-field extraction:
```
1. Vínculo Comercial: Clasifica al contacto en [Cliente], [Proveedor], [Empleado], [Familiar], [Spam], [Otro].
2. Temas Clave: Palabras clave precisas que representen la interacción (máximo 5).
```
Hardcode the 6-label set. Add TODO comment: `# TODO: Read from taxonomy YAML when Phase 3 lands`

**Master call (issue 7)**:
1. After `procesar_chats_con_ia()` returns, build compact input for master call: group contacts by Vínculo Comercial label; sample max 10 per label (or all if fewer); concatenate per-contact topic keywords into aggregated list.
2. Make one API call with a synthesis prompt asking for an executive summary of the business context.
3. On API failure: retry once; if still fails, log warning and continue — individual results remain usable.
4. Write master context as YAML front-matter header in Markdown output.
5. Store in SQLite with `period='master'` and `contact_phone='__MAESTRO__'` for resume capability.

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `scripts/analizar_contexto.py` | Modified | All 7 issues touch this file; DRY extraction (issue 2) is the structural change |
| `outputs/contexto_{ts}.md` | Modified | phase-4b prepends master context header; per-contact body changes format |
| `outputs/contexto_{ts}.json` | Modified | phase-4b may add `master_context` field |
| `outputs/logs.txt` | Modified | phase-4a enables token logging for `--with-metrics` runs |
| `conversation_summaries` SQLite | Modified | phase-4b adds `period='master'` row; phase-4a fixes cache reads |

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Phase 3 taxonomy coupling (issue 6→7 label set) | Medium | Master call prompt uses hardcoded labels; if Phase 3 changes taxonomy, master call output becomes inconsistent | Hardcode 6-label set with TODO; orchestrator defers YAML integration to Phase 3 |
| Sample size pressure on master call (issue 7) | Medium | 30% of 1000 contacts = 300 summaries; exceeds context windows and inflates cost | Two-pass: group by label → sample max 10 per label → master call on ~60 condensed inputs |
| API failure after individual results persisted (issue 7) | Low-Medium | Inconsistent state: individual profiles saved but master missing | Retry-once then graceful degradation; individual results remain usable |
| DRY extraction introduces subtle behavioral change | Low | Closure variable handling differs between two call sites | Manual smoke test on both `--with-metrics` and interactive paths after refactor |
| Prompt version breaks downstream consumers | Low | Stored summary format changes from 4 fields to 2; downstream parsers assume old format | Add TODO comment; `compilar_reporte_local()` is format-agnostic (writes raw text) |

---

## Rollback Plan

### phase-4a
- Revert `scripts/analizar_contexto.py` to pre-change commit — the DRY extraction and all four issues are contained in this file.
- If `--with-metrics` path regresses, the original duplicated loop at lines 773–796 can be restored from git.
- Token logs already written to `outputs/logs.txt` are append-only; no data loss on rollback.

### phase-4b
- Revert prompt string changes in `llamar_api()` to restore original 4-field extraction.
- Delete any `period='master'` rows from `conversation_summaries` via: `DELETE FROM conversation_summaries WHERE period='master'`.
- Existing Markdown/JSON outputs are not modified in place; new outputs reflect the new format. No migration needed.

---

## Dependencies

- Phase 2 (taxonomy YAML externalization) is not required for these changes, but phase-4b includes a TODO noting that the 6-label hardcode should be replaced when Phase 3 lands.
- No new external packages. All changes use stdlib only (sqlite3, urllib, sys, pathlib).
- GEMINI_API_KEY (or compatible sk-* key) must be present in `.env`.

---

## Success Criteria

### phase-4a
- [ ] `--with-metrics` run interrupted mid-batch resumes without re-calling API for cached contacts
- [ ] HTTP 401/403 causes immediate abort with `[FATAL]` message in `--with-metrics` path
- [ ] `seleccionar_base_datos()` skips inaccessible folders without aborting scan
- [ ] Token counts appear in `outputs/logs.txt` after `--with-metrics` run completes
- [ ] Interactive path produces identical output before and after DRY extraction (smoke test)

### phase-4b
- [ ] Per-contact summary format uses exactly 2 fields: Vínculo Comercial + Temas Clave
- [ ] Master context header appears at top of Markdown report after successful `--with-metrics` run
- [ ] Master context stored in SQLite with `period='master'`
- [ ] Master call fails gracefully: retry once, then log warning; individual results remain in output
- [ ] TODO comment present in code noting hardcoded label set awaiting Phase 3 YAML

---

## Open Questions (Proposed Defaults — Orchestrator Surfaces to User)

| # | Question | Proposed Default |
|---|---|---|
| 1 | Confirm split into phase-4a/4b? | YES — split; phase-4a ships fast, phase-4b gets design runway |
| 2 | Master call input: raw summaries or two-pass aggregation? | Two-pass: group by Vínculo label → sample max 10 per label → master call on ~60 condensed inputs |
| 3 | Master call failure: abort, retry, or degrade? | Retry once, then log warning and continue with individual results |
| 4 | Master context persistence: SQLite `period='master'` or output-only? | Store in SQLite for resume capability; also write to output files |
| 5 | Phase 3 timeline: hardcode labels or read from YAML? | Hardcode 6-label set NOW with TODO comment; Phase 3 replaces with YAML read |
| 6 | Fail-fast scope: all `--with-metrics` runs or only combined with `--auto`? | All `--with-metrics` runs; no flag dependency needed |

---

## Spec Directory Structure Decision

**Choice**: Sibling change directories.

Each sub-change was created as a standalone sibling change directory (matching the archive convention of `YYYY-MM-DD-{change-name}/`), not as nested subdirectories under the umbrella `phase-4-analyzer-feedback-fixes/` folder:

```
openspec/changes/phase-4a-analyzer-bugfixes/spec.md   ← 5 REQs, 11 scenarios
openspec/changes/phase-4b-analyzer-contexto-maestro/spec.md  ← 5 REQs, 13 scenarios
```

**Rationale**: The archive structure (`openspec/changes/archive/YYYY-MM-DD-{phase}/`) shows each phase/change is a top-level sibling. Treating `phase-4a` and `phase-4b` as independent sibling changes (rather than nested under the umbrella) is the most consistent approach. The umbrella `phase-4-analyzer-feedback-fixes/` folder retains `exploration.md` and `proposal.md` as shared context documents.
