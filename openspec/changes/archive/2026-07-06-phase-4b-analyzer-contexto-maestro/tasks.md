# Tasks: phase-4b-analyzer-contexto-maestro

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150–190 |
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
| 1 | All changes to `scripts/analizar_contexto.py` | Single PR; prompt updates + helpers + master call wiring + smoke tests |

---

## Phase 1: Prompt Reduction — 2-Field Extraction

- [x] **T-005-001** — Add `LABELS` constant at module level: `LABELS = ["Cliente", "Proveedor", "Empleado", "Familiar", "Spam", "Otro"]` with inline comment `# TODO: Read from taxonomy YAML when Phase 3 lands`. Acceptance: constant exists and is importable.

- [x] **T-005-002** — Update individual-path prompt in `llamar_api()` (current lines 538–550): replace the 4-field instruction with 2-field instruction: (1) `Vínculo Comercial: Clasifica al contacto en uno de estos 6 valores: [{', '.join(LABELS)}]`; (2) `Temas Clave: Hasta 5 palabras clave precisas que representen la interacción`. Keep the return format as `*   **Vínculo Comercial:** [valor]\n*   **Temas Clave:** [palabra1, palabra2, …]`. Acceptance: prompt string no longer contains `Categoría Ocupacional` or `Allegados`.

- [x] **T-005-003** — Update batch-path prompt in `llamar_api()` (current lines 563–570) with the same 2-field instruction. Acceptance: both prompt strings are identical in their 2-field instruction; batch still uses `#### {contact_label}` headers per contact.

---

## Phase 2: Aggregation Helpers — `parse_label()`, `extract_temas()`, `aggregate_for_master()`

- [x] **T-005-004** — Add `parse_label(summary: str) -> str` helper: use `re.search(r"V[ií]nculo Comercial[:*\s]+([A-Za-zÁÉÍÓÚáéíóú]+)", summary or "")` to extract the label; return matched label if in `LABELS`, else `"Otro"`. Acceptance: `parse_label("*   **Vínculo Comercial:** Cliente\n*   **Temas Clave:** pedido")` returns `"Cliente"`.

- [x] **T-005-005** — Add `extract_temas(summary: str) -> str | None` helper: iterate lines, strip leading `*` and whitespace, match `temas clave` (case-insensitive), return substring after first colon trimmed; return `None` if no match or value is empty/whitespace. Acceptance: `extract_temas("*   **Temas Clave:** pedido, entrega, factura")` returns `"pedido, entrega, factura"`.

- [x] **T-005-006** — Add `aggregate_for_master(summaries: dict) -> tuple[dict, str]`: group `summaries.items()` by `parse_label()`; for each label sample `min(10, len(items))` using `random.sample`; for each sampled contact call `extract_temas()` and append `f"  - {phone}: {temas}"` to the block; build block as `f"=== {label} ({len(items)} contactos, muestreo {len(sample)}) ==="` followed by topic lines; return `(labels_distribution dict, master_input string)`. Acceptance: with ≤60 input contacts, `master_input` has ≤60 lines; `labels_distribution` keys sum to number of non-None summaries.

---

## Phase 3: Master Call — `master_call_with_retry()` and `is_recent()`

- [x] **T-005-007** — Add `MASTER_SYNTHESIS_PROMPT` constant and `MasterCallEmptyResponse` exception class. Implement `master_call_with_retry(master_input: str) -> str | None`: build prompt from `MASTER_SYNTHESIS_PROMPT.format(master_input=master_input)`; attempt `llamar_api(prompt, is_individual=False, fail_fast=False)` up to 2 times; detect empty/whitespace response as failure and raise `MasterCallEmptyResponse`; return `None` after second exhausted attempt with `[WARN]` print. Acceptance: two consecutive empty responses produce exactly one `[WARN]` line; one success returns text.

- [x] **T-005-008** — Add `is_recent(updated_at: str, hours: int = 24) -> bool`: parse `updated_at[:19]` with `%Y-%m-%d %H:%M:%S` and attach `tzinfo=dt.timezone.utc`; compare against `dt.datetime.now(dt.timezone.utc)`; return `age < timedelta(hours=hours)`. Acceptance: a row timestamp 3 hours ago returns `True`; a row 30 hours ago returns `False`.

---

## Phase 4: Wiring — Master Call into `--with-metrics` Post-Batch Flow

- [x] **T-005-009** — After `procesar_chats_con_ia()` returns and before `dual_output_writer()`: (a) execute `SELECT summary, updated_at FROM conversation_summaries WHERE contact_phone = '__MAESTRO__' AND period = 'master'`; (b) if row exists and `is_recent(row[1], hours=24)`, reuse stored text and print `[INFO] Master context reutilizado de {timestamp} (<24h).`; (c) otherwise call `aggregate_for_master(summaries)` then `master_call_with_retry(master_input)`; (d) on success execute `INSERT OR REPLACE INTO conversation_summaries (contact_phone, period, summary, updated_at) VALUES ('__MAESTRO__', 'master', ?, CURRENT_TIMESTAMP)` and commit; (e) build `master_meta` dict with `generated_at` and `labels_distribution`. Move `conn.close()` to after the master call UPSERT. Acceptance: master context appears in output files; `conversation_summaries` contains `__MAESTRO__` row after first run.

- [x] **T-005-010** — Update `dual_output_writer()` signature to accept `master_context: dict | None = None` kwarg. When `master_context` is non-None, prepend YAML front-matter `master_context:` block to Markdown output (with `generated_at`, `labels_distribution`, and `summary` sub-keys). Add `master_context` top-level key to JSON output. Acceptance: Markdown output contains `master_context:` block under `---` delimiters; JSON contains `"master_context": { … }`.

- [x] **T-005-011** — Update `compilar_reporte_local()` to prepend YAML front-matter with `master_context:` block to Markdown output when `master_context` is non-None. The `__MAESTRO__` row uses `period='master'` and is filtered out by the existing `WHERE period = 'profile'` clause, so this function reads no new rows. Acceptance: standalone `compilar_reporte_local()` call (no `--with-metrics`) still works; if called with master context it writes the header.

---

## Phase 5: Smoke Tests

- [x] **T-005-012** — **Smoke 1 (prompt + YAML)**: run `--with-metrics` on 50 contacts; verify every per-contact summary has exactly 2 bullets (`**Vínculo Comercial:**` + `**Temas Clave:**`); verify Markdown output begins with `master_context:` block inside YAML front-matter; verify `outputs/contexto_{ts}.json` has `master_context` top-level field.

- [x] **T-005-013** — **Smoke 2 (sample cap)**: run on 200-contact sample; verify master call input ≤ 60 lines by checking `len(master_input.splitlines()) <= 60`; verify `labels_distribution` sums to total non-None summaries.

- [x] **T-005-014** — **Smoke 3 (resume)**: run `--with-metrics` twice within minutes; second run prints `[INFO] Master context reutilizado de … (<24h).`; verify `run2_total_tokens - run1_total_tokens <= 1000` (per-contact non-determinism buffer; master call tokens ~2-3k, so a reused master adds 0).

- [x] **T-005-015** — **Smoke 4 (master failure)**: monkey-patch `llamar_api` to raise `HTTPError` for the master call only; verify `[WARN] Master synthesis call failed after retry. Individual results remain available.` prints exactly once; per-contact output is intact; YAML `master_context:` block is absent.

---

## Acceptance Criteria Mapping

| Task | Spec REQ | Acceptance Check |
|------|----------|-----------------|
| T-005-001 | REQ-005-001 | `LABELS` constant exists; TODO comment present |
| T-005-002 | REQ-005-001 | Individual-path prompt has exactly 2 fields; no `Categoría Ocupacional` |
| T-005-003 | REQ-005-001 | Batch-path prompt identical; `####` headers preserved |
| T-005-004 | REQ-005-002 | `parse_label()` returns correct label or `"Otro"` |
| T-005-005 | REQ-005-002 | `extract_temas()` returns comma string or `None` |
| T-005-006 | REQ-005-002 | `aggregate_for_master()` returns ≤60-line string; distribution sums correctly |
| T-005-007 | REQ-005-003, REQ-005-004 | `master_call_with_retry()` retries once; `[WARN]` prints once on double-failure |
| T-005-008 | REQ-005-005 | `is_recent()` returns `True` for 3h-old row, `False` for 30h-old |
| T-005-009 | REQ-005-003, REQ-005-005 | `__MAESTRO__` row written; resume check skips API call on re-run |
| T-005-010 | REQ-005-003 | Markdown has `master_context:` YAML block; JSON has top-level field |
| T-005-011 | REQ-005-003 | `compilar_reporte_local()` writes YAML header when master context provided |
| T-005-012 | REQ-005-001, REQ-005-003 | Smoke: 2-field summaries; YAML + JSON contain master block |
| T-005-013 | REQ-005-002 | Smoke: master input ≤60 lines; distribution sums to total |
| T-005-014 | REQ-005-005 | Smoke: second run reuses cached master context |
| T-005-015 | REQ-005-004 | Smoke: forced failure logs warning; per-contact output intact |

---

## Dependency DAG

```
T-005-001 (LABELS constant) ──┬──► T-005-002 (individual prompt)
                              └──► T-005-003 (batch prompt)
                                    │
T-005-002, T-005-003               │
      │                            │
      └──────┬──► T-005-004 (parse_label)
             ├──► T-005-005 (extract_temas)
             └──► T-005-006 (aggregate_for_master)
                   │
T-005-007 (master_call_with_retry) ───► T-005-009 (master call wiring)
T-005-008 (is_recent)            ───► T-005-009 (master call wiring)
                                        │
T-005-009 (master wiring) ─────────────┴──► T-005-010 (dual_output_writer update)
                                        │
T-005-010 (dual_output_writer) ────────────► T-005-011 (compilar_reporte_local update)
                                              │
T-005-010, T-005-011 ─────────────────────────┴──► T-005-012 (smoke 1: prompt + YAML)
                                                    ├──► T-005-013 (smoke 2: sample cap)
                                                    ├──► T-005-014 (smoke 3: resume)
                                                    └──► T-005-015 (smoke 4: failure)
```

---

## Execution Order

1. **T-005-001 + T-005-002 + T-005-003** — Add `LABELS` constant and update both prompts (~20 lines). These are the foundation for everything that follows.
2. **T-005-004 + T-005-005 + T-005-006** — Add the three aggregation helpers (~55 lines). Pure functions with no side effects; independently testable.
3. **T-005-007 + T-005-008** — Add `master_call_with_retry()` and `is_recent()` (~45 lines). Independent of the helpers.
4. **T-005-009** — Wire master call into `--with-metrics` branch (~35 lines). This is the main integration point.
5. **T-005-010 + T-005-011** — Extend output writer signatures (~15 lines). Independent of the master call logic.
6. **T-005-012 through T-005-015** — Smoke tests (manual, no code).

**Total estimated new code: ~150–190 lines** across one file. Single PR, well within 400-line budget and 800-line review budget.
