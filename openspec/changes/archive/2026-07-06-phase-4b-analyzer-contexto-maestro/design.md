# Design: phase-4b-analyzer-contexto-maestro

## Context

Phase 4a closes five surgical fixes to `scripts/analizar_contexto.py` and lands a new shared `procesar_chats_con_ia()` (see `phase-4a design.md`). Phase 4b rides on top: it changes the per-contact LLM prompt to extract a 2-field B2B-focused profile, and adds a new "Master Business Context" synthesis call after the per-contact batch. The master call is the highest-leverage output for a B2B user: instead of reading 90 individual profiles, the user opens `outputs/contexto_{ts}.md` and sees a YAML-front-matter block summarizing the whole business relationship landscape.

The two changes are coupled: the master call's input aggregation groups contacts by the `Vínculo Comercial` label produced by the per-contact prompt. If the prompt is 4-field (today), the master call has no label to group by. Hence the order in the spec: prompt reduction (Issue 6) ships in the same change as the master call (Issue 7).

The 6-label taxonomy (`Cliente`, `Proveedor`, `Empleado`, `Familiar`, `Spam`, `Otro`) is hardcoded with a `# TODO` comment for Phase 3 YAML integration. Master call input is two-pass: group by label → sample ≤ 10 per label → concatenate `Temas Clave` keywords. This caps the master call input at ~60 condensed lines (6 labels × 10 samples) regardless of sample size, keeping it inside the LLM's context window and the project's per-call cost budget. Master call failure is graceful: retry once, then log a `[WARN]` and continue — individual per-contact results remain usable.

## Goals / Non-Goals

**Goals** (locked):

| Goal | Detail |
|---|---|
| 2-field prompt | Per-contact LLM extracts exactly `Vínculo Comercial` (one of 6 labels) + `Temas Clave` (≤ 5 keywords) |
| Master synthesis | One post-batch API call produces an executive business context from the per-contact summaries |
| Two-pass input | Group by `Vínculo Comercial` label → sample ≤ 10 per label → concatenate `Temas Clave` keywords; input ≤ 60 condensed lines |
| YAML front-matter | Master context prepended to Markdown output as `--- … ---` block |
| SQLite resume | Master context stored in `conversation_summaries` with `contact_phone='__MAESTRO__'`, `period='master'`; reused if `updated_at` within 24 h |
| Graceful failure | Master call retries once on failure; on second failure, logs `[WARN]` and continues — individual results unaffected |

**Non-Goals**: Phase 3 taxonomy YAML integration (TODO marker only), multi-DB master aggregation, switching to a different LLM provider, persisting master context to a separate table.

## Architecture Decisions

### Decision: Two-pass aggregation, not a single-pass "feed the model everything"

**Choice**: Group contacts by `Vínculo Comercial` label, sample ≤ 10 per label, then concatenate `Temas Clave` keywords. Master call receives ~60 condensed lines, not 300 full per-contact summaries.
**Alternatives considered**:
- Feed the model the full `summaries` dict (every per-contact Markdown block). Rejected: at 300 contacts, the input is ~12-30k tokens of structured Markdown; the LLM's effective context window is small enough that truncation or loss-of-detail is likely, and per-call cost is 5-10× the two-pass version.
- Two-stage tier summary (per-contact → per-tier synthesis → master). Rejected: doubles the API calls (one per tier). The "label group → sample 10" approach is a single master call.
**Rationale**: A 6-label × 10-sample grid is the smallest structure that captures the per-label topic distribution. Sampling 10 per label gives 30-50 keywords per label, enough to identify the dominant themes without overwhelming the model.

### Decision: Hardcode the 6-label taxonomy with a TODO comment

**Choice**: Inline `LABELS = ["Cliente", "Proveedor", "Empleado", "Familiar", "Spam", "Otro"]` in `scripts/analizar_contexto.py`; comment `# TODO: Read from taxonomy YAML when Phase 3 lands` adjacent.
**Alternatives considered**:
- Read from `taxonomias_seed/` (Phase 2 already creates this directory). Rejected: Phase 3's externalization is not finalized; coupling to a moving YAML schema risks master call output becoming inconsistent if the YAML changes.
- Hardcode without a TODO. Rejected: the user explicitly raised Phase 3 coupling as a concern; a TODO makes the temporary state visible.
**Rationale**: The label set is small, stable, and not expected to change inside phase-4b. The TODO is the explicit hand-off marker for the next phase.

### Decision: Retry exactly once, then degrade gracefully

**Choice**: Wrap the master `llamar_api` call in a `try/except` block; on any exception, retry once with the same arguments; on the second failure, log `[WARN] Master synthesis call failed after retry. Individual results remain available.` and set `master_context = None`.
**Alternatives considered**:
- No retry — single call. Rejected: HTTP 500 / 503 from upstream is a transient class of failure worth a second try.
- Exponential backoff (3+ retries). Rejected: the script is batch-mode and 30-60s of additional wait is not worth the small additional success rate.
**Rationale**: One retry covers transient blips without extending the worst-case runtime. Graceful degradation means the run still produces all individual profiles.

### Decision: 24-hour resume window

**Choice**: Reuse a stored `period='master'` row if its `updated_at` is within 24 hours of the current run; otherwise make a fresh API call and overwrite.
**Alternatives considered**:
- Indefinite reuse. Rejected: business context drifts; a 7-day-old synthesis may be stale.
- Per-run invalidation. Rejected: defeats the resume purpose — the user explicitly wants to skip the master call if they re-run within the same workday.
**Rationale**: 24 hours covers "I ran the script this morning, then again after lunch." Anything older and the user is intentionally asking for a fresh synthesis.

### Decision: Master call uses `fail_fast=False`

**Choice**: The master call's `llamar_api` invocation passes `fail_fast=False` even when the `--with-metrics` path uses `fail_fast=True` for per-contact calls.
**Rationale**: The master call is post-batch and wrapped in its own retry logic. If it fails, we want the retry path to take over, not `sys.exit` to abort the run. Per-contact calls keep `fail_fast=True` so a bad key aborts before we burn quota on a doomed master call.

## Data Flow

```
  --with-metrics branch (lines 723-820)
       │
       │ stratified sample (lines 731-767)
       ▼
  procesar_chats_con_ia(...)               ← phase-4a shared function
       │  with reduced 2-field prompt
       │  returns summaries {phone: 2-field Markdown}
       ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ Master call aggregation                                      │
  │                                                              │
  │  summaries.items()                                           │
  │     │ parse "Vínculo Comercial: <label>" from each summary   │
  │     ▼                                                        │
  │  grouped_by_label = defaultdict(list)                        │
  │  for phone, summary in summaries.items():                    │
  │      label = parse_label(summary)                            │
  │      grouped_by_label[label].append((phone, summary))        │
  │                                                              │
  │  compact_inputs = []                                          │
  │  for label, contacts in grouped_by_label.items():            │
  │      sample = random.sample(contacts, min(10, len(contacts)))│
  │      topic_lines = [s['temas'] for _, s in sample]           │
  │      header = f"=== {label} ({len(contacts)} contactos, "    │
  │                f"muestreo {len(sample)}) ==="                │
  │      compact_inputs.append(header + "\n" + "\n".join(topic_lines))
  │                                                              │
  │  master_input = "\n\n".join(compact_inputs)                  │
  │  (≤ 60 lines, ≤ ~6k tokens)                                  │
  └──────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ Resume check                                                 │
  │                                                              │
  │  cursor.execute("SELECT summary, updated_at FROM             │
  │      conversation_summaries WHERE contact_phone='__MAESTRO__'│
  │      AND period='master'")                                   │
  │  if row and is_recent(row['updated_at'], hours=24):          │
  │      master_text = row['summary']                            │
  │  else:                                                       │
  │      master_text = master_call_with_retry(master_input)      │
  │      UPSERT __MAESTRO__ row with master_text                 │
  └──────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ Output writers (unchanged signatures, master_text added)     │
  │                                                              │
  │  dual_output_writer(                                          │
  │      sample, metrics, summaries, db_name, ts,                │
  │      stratification=…,                                        │
  │      total_dataset_size=…,                                    │
  │      master_context={                                         │
  │          'text': master_text or '',                          │
  │          'generated_at': ISO 8601,                            │
  │          'labels_distribution': {label: count, …},            │
  │      }                                                       │
  │  )                                                           │
  │                                                              │
  │  compilar_reporte_local(db_path)   ← unchanged; reads only   │
  │                                      period='profile' rows    │
  └──────────────────────────────────────────────────────────────┘
```

## File Changes

| File | Action | Description |
|---|---|---|
| `scripts/analizar_contexto.py` | Modify | Replace the per-contact prompt in `llamar_api()` at lines 538-550 (individual) and 563-570 (batch) with the 2-field prompt; add a `LABELS` constant and `# TODO` comment; add `parse_label()`, `extract_temas()` (**BLOCKER-2** helper, defined in this design), `aggregate_for_master()`, `master_call_with_retry()` (**CRITICAL-2** with empty-response handling), `is_recent()` (**CRITICAL-3** UTC-only) helpers; insert master call step in `--with-metrics` branch between line 799 (end of `procesar_chats_con_ia`) and the `dual_output_writer` call at line 810; extend `dual_output_writer` signature with `master_context` kwarg |
| `outputs/contexto_{ts}.md` | Modified | YAML front-matter grows a `master_context:` block; same body otherwise |
| `outputs/contexto_{ts}.json` | Modified | Top-level `master_context` field added (text, generated_at, labels_distribution) |
| `conversation_summaries` table | Modified | New row pattern: `('__MAESTRO__', 'master', '<text>', CURRENT_TIMESTAMP)` |

## Interfaces / Contracts

### Reduced prompt (both individual and batch paths)

```text
# TODO: Read from taxonomy YAML when Phase 3 lands.
# Hardcoded for now: Cliente | Proveedor | Empleado | Familiar | Spam | Otro.
LABELS = ["Cliente", "Proveedor", "Empleado", "Familiar", "Spam", "Otro"]

# Individual-path prompt (replaces lines 538-550):
instrucciones = (
    "Analiza la siguiente conversación de WhatsApp entre 'Nosotros' "
    "(Usuario Principal) y un 'Cliente/Contacto' e identifica:\n"
    "1. Vínculo Comercial: Clasifica al contacto en uno de estos 6 valores: "
    f"[{', '.join(LABELS)}].\n"
    "2. Temas Clave: Hasta 5 palabras clave precisas que representen la "
    "interacción.\n\n"
    "Devuelve la respuesta en este formato Markdown:\n"
    "*   **Vínculo Comercial:** [uno de los 6 valores]\n"
    "*   **Temas Clave:** [palabra1, palabra2, palabra3, palabra4, palabra5]\n\n"
    f"Conversación:\n{prompt}"
)

# Batch-path prompt (replaces lines 563-571): same 2-field instruction
# applied "por contacto" with "usando títulos #### para cada sección".
```

The batch prompt text changes identically; the per-contact wrapper is unchanged (`#### {contact_label}`). The interactive batch path (lines 886-986 in the original; now inside the shared function) inherits the same prompt.

### `parse_label(summary: str) -> str`

```python
def parse_label(summary: str) -> str:
    """Extract the Vínculo Comercial label from a per-contact summary.

    Returns the matched label, or 'Otro' if no label is found.
    Format expected: '*   **Vínculo Comercial:** Cliente' or equivalent.
    """
    import re
    match = re.search(r"V[ií]nculo Comercial[:*\s]+([A-Za-zÁÉÍÓÚáéíóú]+)", summary or "")
    if match:
        candidate = match.group(1).strip()
        if candidate in LABELS:
            return candidate
    return "Otro"
```

### `extract_temas(summary: str) -> str | None`

> **BLOCKER-2 fix**: the previous draft referenced `extract_temas(summary)` inside `aggregate_for_master()` (line 214) but never declared the helper. The function is defined here alongside `parse_label()` because both are pure parsers of the per-contact Markdown produced by the reduced prompt.

```python
def extract_temas(summary: str) -> str | None:
    """Extract the 'Temas Clave:' line content from a per-contact summary.

    Returns the comma-separated keyword list (already trimmed) or None if
    the line is missing or empty. The expected line format is:

        *   **Temas Clave:** pedido, entrega, factura, pago, devolucion

    Behavioural contract:
      - Walks the summary line-by-line.
      - Matches any line that starts (after optional bullets/asterisks) with
        "Temas Clave:" (case-insensitive accent-tolerant: "Témas Cláve:" also
        accepted via a normalized comparison).
      - Returns the substring after the first colon, `.strip()`-ed.
      - Returns None if no matching line is found OR if the matched value is
        empty/whitespace (e.g. "Temas Clave:   ").
    """
    for line in (summary or "").splitlines():
        stripped = line.lstrip().lstrip('*').strip()
        if stripped.lower().startswith("temas clave"):
            # Find the colon, return whatever comes after it trimmed.
            _, _, after = stripped.partition(":")
            value = after.strip()
            return value if value else None
    return None
```

**Where it is called**: exclusively inside `aggregate_for_master()` (see Interfaces section below), once per sampled `(phone, summary)` per label. The result is appended as one bullet line to the master call's compact input. The apply phase must not call it from anywhere else; it is a private parser coupled to the prompt's `*   **Temas Clave:** …` format.

### `aggregate_for_master(summaries: dict) -> tuple[dict, str]`

```python
def aggregate_for_master(summaries: dict) -> tuple[dict, str]:
    """Group summaries by Vínculo Comercial label, sample up to 10 per label,
    and build a compact input string for the master synthesis call.

    Returns (labels_distribution, master_input_string):
      - labels_distribution: {"Cliente": 20, "Proveedor": 15, ...}
      - master_input_string: ≤ 60 lines, one block per non-empty label
    """
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for phone, summary in summaries.items():
        if not summary:
            continue
        label = parse_label(summary)
        grouped[label].append((phone, summary))

    distribution = {label: len(items) for label, items in grouped.items()}

    compact = []
    for label, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        sample = random.sample(items, min(10, len(items)))
        topic_lines = []
        for phone, summary in sample:
            temas = extract_temas(summary)   # parses "Temas Clave: …" line
            if temas:
                topic_lines.append(f"  - {phone}: {temas}")
        header = f"=== {label} ({len(items)} contactos, muestreo {len(sample)}) ==="
        compact.append(header + "\n" + "\n".join(topic_lines))

    return distribution, "\n\n".join(compact)
```

**Budget cap**: `len(grouped) ≤ 6` labels × `min(10, |label|)` samples × 1 line per sample. Worst case is 6 × 10 = 60 lines. Empty labels are skipped (the `if topic_lines` filter inside the inner loop handles groups where extraction yielded no parseable topics).

**Edge cases**:
- All-spam group (`Spam: 30 contacts`): the sample of 10 is taken; master call still receives a `Spam` block. Acceptable — confirms the script flagged the noise.
- Empty summaries dict (all `None`): `master_input_string` is `""`; the master call is **skipped** (no point asking the LLM to summarize nothing). Master context is `None`; output omits the YAML block.
- One contact per label: `min(10, 1) = 1`; that one contact is taken as-is.

### `master_call_with_retry(master_input: str) -> str | None`

```python
MASTER_SYNTHESIS_PROMPT = (
    "Eres un analista de relaciones comerciales B2B. A continuación recibirás "
    "una muestra de contactos agrupados por Vínculo Comercial y sus Temas Clave. "
    "Genera un 'Contexto Maestro del Negocio' en prosa ejecutiva (máximo 350 palabras) "
    "que incluya:\n"
    "  1. Composición de la cartera de contactos por tipo de vínculo.\n"
    "  2. Los 3-5 temas dominantes que articulan la operatoria comercial.\n"
    "  3. Riesgos comerciales detectados (Spam, dependencias, desequilibrios).\n"
    "  4. Una recomendación priorizada de 1-2 líneas de acción.\n\n"
    "Muestra agregada:\n{master_input}"
)

class MasterCallEmptyResponse(ValueError):
    """Raised when the API returns HTTP 200 with an empty/whitespace body.
    Surfaces a non-recoverable-as-success case to the retry layer below."""
    pass


def master_call_with_retry(master_input: str) -> str | None:
    """Returns master text or None after exhausted retries.

    CRITICAL-2 fix: the previous draft only triggered a retry on `Exception`.
    A successful HTTP 200 with an empty body returns normally but is not a
    usable synthesis. We now treat empty/whitespace text as a failure and
    route it through the same retry path that handles network/HTTP errors.
    """
    prompt = MASTER_SYNTHESIS_PROMPT.format(master_input=master_input)

    for attempt in (1, 2):
        try:
            text, *_ = llamar_api(prompt, is_individual=False, fail_fast=False)
            if not text or not text.strip():
                # CRITICAL-2: explicit empty-body detection. Without this,
                # an HTTP 200 + empty JSON would pass as "success" and we'd
                # persist a `__MAESTRO__` row with `summary=''`.
                raise MasterCallEmptyResponse("Empty response from master call")
            return remove_think_tags(text)
        except (Exception, MasterCallEmptyResponse):
            if attempt == 2:
                print("[WARN] Master synthesis call failed after retry. "
                      "Individual results remain available.")
                return None
            # else: fall through to the next iteration (the retry).
    return None  # unreachable; the loop returns explicitly on attempt == 2
```

The `fail_fast=False` is critical: even when the `--with-metrics` branch's per-contact calls use `fail_fast=True`, the master call must **not** abort the run. It has its own retry; on second failure it degrades gracefully. The `MasterCallEmptyResponse` exception is scoped to this function — it is not raised elsewhere and is caught by the same `except` that catches HTTP/connection failures, so the retry path treats it identically.

### `is_recent(updated_at: str, hours: int = 24) -> bool`

```python
def is_recent(updated_at: str, hours: int = 24) -> bool:
    """True if the SQLite CURRENT_TIMESTAMP string is within `hours` of now (UTC).

    CRITICAL-3 fix: the previous draft compared `dt.datetime.now()` (local
    time) against a SQLite `CURRENT_TIMESTAMP` value (UTC). On a UTC-3
    deployment, that 3-hour offset caused a 1-hour-old row to appear 4 hours
    old and the resume window to silently shrink. We now force both sides to
    UTC.
    """
    if not updated_at:
        return False
    try:
        import datetime as dt
        # SQLite CURRENT_TIMESTAMP format is 'YYYY-MM-DD HH:MM:SS' in UTC.
        # Attach tzinfo=utc explicitly so the arithmetic below cannot drift
        # to local time.
        stored = dt.datetime.strptime(updated_at[:19], "%Y-%m-%d %H:%M:%S")
        stored = stored.replace(tzinfo=dt.timezone.utc)
        now = dt.datetime.now(dt.timezone.utc)
        age = now - stored
        return age < dt.timedelta(hours=hours)
    except ValueError:
        return False
```

**Timezone assumption (documented as a known limitation — see Open Questions)**: This function assumes `CURRENT_TIMESTAMP` in the `conversation_summaries` table is in UTC. The `CREATE TABLE` statement at lines 855-863 uses the SQLite default for `CURRENT_TIMESTAMP`, which is documented to return UTC. The apply phase must NOT change the table to use a local-time default; doing so would break the resume window in mixed-timezone deployments. If a future migration changes the column to `DEFAULT (datetime('now', 'localtime'))`, this function must be updated to also parse with a local timezone.

### Master call invocation (in `--with-metrics` branch)

Inserted between `procesar_chats_con_ia()` returning and the `dual_output_writer()` call (current line 810):

```python
# 7. Master Business Context — synthesis call (phase-4b)
master_text: str | None = None
master_meta: dict = {}
if summaries:
    # 7a. Resume check
    cursor.execute(
        "SELECT summary, updated_at FROM conversation_summaries "
        "WHERE contact_phone = '__MAESTRO__' AND period = 'master'"
    )
    cached = cursor.fetchone()
    if cached and cached[1] and is_recent(cached[1], hours=24):
        print(f"[INFO] Master context reutilizado de {cached[1]} (<24h).")
        master_text = cached[0]
    else:
        # 7b. Aggregate and synthesize
        distribution, master_input = aggregate_for_master(summaries)
        if master_input:
            master_text = master_call_with_retry(master_input)
            if master_text:
                cursor.execute("""
                    INSERT OR REPLACE INTO conversation_summaries
                        (contact_phone, period, summary, updated_at)
                    VALUES ('__MAESTRO__', 'master', ?, CURRENT_TIMESTAMP)
                """, (master_text,))
                conn.commit()
        master_meta = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", ts),
            "labels_distribution": distribution if master_text else {},
        }
    conn.close()
```

The `conn.close()` is moved to AFTER the master call writes the `__MAESTRO__` row (was at line 799). `ts` is the same timestamp used for output filenames.

### `dual_output_writer()` — extended signature

```python
def dual_output_writer(
    sample, metrics, summaries, db_name, ts, output_dir,
    stratification=None, total_dataset_size=None,
    master_context: dict | None = None,   # ← new
):
```

`master_context` keys:
- `text: str` — the master synthesis body (empty if not generated).
- `generated_at: str` — ISO 8601.
- `labels_distribution: dict[str, int]` — e.g. `{"Cliente": 20, "Proveedor": 15, …}`.

### Markdown YAML front-matter

The new `master_context` block is appended **inside** the existing front-matter:

```yaml
---
date: 2026-07-06
title: Reporte de Analisis de Contexto
db_name: auto_wpp
sample_size: 90
tier_method: quantile (P33/P66 inclusive)
master_context:
  generated_at: 2026-07-06T14:32:11
  database: auto_wpp
  sample_size: 90
  labels_distribution:
    Cliente: 20
    Proveedor: 15
    Empleado: 5
    Familiar: 8
    Spam: 12
    Otro: 30
  summary: |
    La cartera de contactos se compone principalmente de clientes comerciales…
---
```

When `master_context` is `None` (failed call, or empty summaries), the `master_context:` block is **omitted** entirely. Downstream parsers must treat the field as optional.

**Parsing hint for downstream readers** (e.g. a future dashboard): the YAML block is delimited by the first and second `---` lines; within it, `master_context` is a sub-mapping. Standard YAML libraries (`yaml.safe_load`) handle it without special config.

### JSON payload

The top-level payload gains one field:

```json
{
  "generated_at": "2026-07-06T14:32:11",
  "db_name": "auto_wpp",
  "total_contacts": 300,
  "sampled_contacts": 90,
  "stratification": { … },
  "master_context": {
    "text": "La cartera de contactos…",
    "generated_at": "2026-07-06T14:32:11",
    "labels_distribution": { "Cliente": 20, "Proveedor": 15, … }
  },
  "contacts": [ … ]
}
```

When the master call is skipped/failed, the field is `null` (not omitted) so the JSON schema is stable.

## Backward Compatibility

| Caller / consumer | Today | After | Compatible? |
|---|---|---|---|
| `--with-metrics` invocation | Outputs `contexto_{ts}.{json,md}` with no master block | Same files, with `master_context` block in YAML / top-level field in JSON | **Yes** — adds a field, doesn't remove anything. |
| `compilar_reporte_local(db_path)` | Reads only `period='profile'` rows | Same | **Yes** — the new `__MAESTRO__` row uses `period='master'`, not `'profile'`, and is filtered out by the existing `WHERE cs.period = 'profile'` clause (line 655). |
| Downstream YAML/JSON parsers | Expects specific front-matter keys | New `master_context` sub-mapping | **Compatible** if parsers ignore unknown keys; document `master_context` as optional. |
| Interactive path (no `--with-metrics`) | Unchanged | Unchanged | **Yes** — master call only runs in `--with-metrics` branch. |
| `procesar_chats_con_ia()` (phase-4a) | Returns `summaries` and `token_totals` | Same | **Yes** — phase-4b is a consumer, not a modifier. |
| `llamar_api()` per-contact calls | 4-field prompt | 2-field prompt | **Behavior change** — intentional, scoped to per-contact summaries. The new prompt produces 2-field Markdown; existing stored summaries (4-field) remain readable but are no longer regenerated. |

## Migration

No data migration. The new `period='master'` row is created on first run and reused for 24 hours.

**Rollback procedure** (per `proposal.md`):
1. Revert `scripts/analizar_contexto.py` to the pre-change commit.
2. Clean up the master row: `sqlite3 outputs/.../whatsapp.sqlite "DELETE FROM conversation_summaries WHERE period='master';"` (or skip — the row is invisible to `compilar_reporte_local` and ignored by `dual_output_writer` after the prompt change reverts).

## Observability

| Surface | New line | When |
|---|---|---|
| stdout | `[INFO] Master context reutilizado de 2026-07-06 13:45:02 (<24h).` | `--with-metrics` re-run within 24 h skips the API call |
| stdout | `[WARN] Master synthesis call failed after retry. Individual results remain available.` | Master call fails twice in a row |
| `outputs/logs.txt` | (no new line — master call tokens are not logged separately; they roll up into the per-batch `[LOTE 1]` line via `metrics_enabled=True`) | n/a |

No new metrics. The master call's tokens ARE counted by the `--with-metrics` path's existing accumulation loop, but they appear in the per-batch `[LOTE 1]` line, not as a separate entry. A future enhancement could add a `[MASTER]` line, but phase-4b keeps the change scope tight.

## Performance

- **Per-contact prompt**: 2 fields vs. 4 fields. The trimmed prompt is ~30% shorter in input tokens, ~40% shorter in output tokens. Across 90 contacts, this saves an estimated 1.5-2k input tokens and 2-3k output tokens per run.
- **Master call input**: capped at 60 lines (~6k tokens worst case). One additional API call per run (skipped on resume). Master call `max_tokens` is 2048 (uses the same `is_individual=False` default), with `temperature=0.1`.
- **Resume check**: one `SELECT summary, updated_at FROM conversation_summaries WHERE contact_phone='__MAESTRO__' AND period='master'`. Single query, sub-millisecond.
- **Aggregation**: `O(N)` over summaries dict (parse + group + sample). Random sampling is 10 items per group — negligible.
- **No extra API calls on resume**: the 24-hour cache eliminates the master call on same-day reruns.

## Security

- **No new auth surface**: master call uses the same `api_key` (GEMINI or sk-* compatible) and the same `llamar_api()` transport. No new headers, no new tokens.
- **No new SQL injection**: the `__MAESTRO__` literal is a hardcoded string passed to a parameterized `?` placeholder. The `period='master'` and `period='profile'` are hardcoded in all `WHERE` clauses.
- **No new PII exposure**: the master call input is already a downstream aggregate of per-contact data the script has read; it doesn't introduce a new data source.
- **Prompt injection**: the user-controlled part of the master prompt is `master_input` (the aggregated `Temas Clave` keywords). The model is instructed to ignore instructions inside the input ("…los 3-5 temas dominantes…"); this is best-effort, but the worst-case outcome is a slightly off-topic synthesis, not a data exfiltration (the API endpoint doesn't accept new instructions to forward data).

## Open Questions

None of the items below block implementation; they are known limitations and
follow-ups that the apply phase should be aware of:

- **Timezone assumption (CRITICAL-3 follow-up)**: `is_recent()` and the
  resume window rely on `CURRENT_TIMESTAMP` returning UTC. If a future
  schema change switches the column to `datetime('now', 'localtime')`,
  `is_recent()` will need a matching parser update. The current code is
  correct for the existing schema (default `CURRENT_TIMESTAMP` is UTC per
  SQLite docs); this is documented in the `is_recent` docstring.
- **Master call input format**: two-pass aggregation (group by label → sample 10 per label) — resolved.
- **Failure handling**: retry once, then warn-and-continue — resolved.
- **Persistence**: SQLite `__MAESTRO__` row with `period='master'` — resolved.
- **Resume window**: 24 hours — resolved.
- **Phase 3 timeline**: hardcode labels with TODO comment — resolved.
- **Provider-specific empty-body semantics**: some LLM providers return
  HTTP 200 with an empty `choices[0].message.content` string when the
  prompt is rejected by an upstream filter (content moderation, safety
  block). The CRITICAL-2 fix routes this case through the retry path; if
  the second attempt also returns empty, the run proceeds without a
  master block, exactly as if the call had raised an exception. No
  telemetry is sent to a separate channel — the `[WARN]` line is the only
  signal. A future enhancement could add a counter to the per-batch log
  line.

## Testing Strategy

No test framework available. Smoke testing per phase-1 pattern. All four runs use `--with-metrics` against a real local database.

| # | Command | Expected outcome |
|---|---|---|
| 1 | `python scripts/analizar_contexto.py --with-metrics --db <test_db> --sample-size 0.50` (50 contacts) | Each per-contact summary contains exactly two bullets: `**Vínculo Comercial:**` and `**Temas Clave:**`. The Markdown output begins with a `master_context:` block in the YAML front-matter. The `outputs/contexto_{ts}.md` file shows the master synthesis below the YAML block. |
| 2 | Run the same command on a 200-contact sample | Master call input is sampled (≤ 10 per label) — verify by adding a temporary `print(f"DEBUG: master_input has {len(master_input.split(chr(10)))} lines")` before the master call. Must be ≤ 60 lines. |
| 3 | Run the same command twice in succession (within minutes) | Second run prints `[INFO] Master context reutilizado de <timestamp> (<24h).` and `outputs/logs.txt` shows no new master-call tokens (the per-contact tokens still roll up into the second `[LOTE 1]` line because the master call happens AFTER the per-contact loop and shares the `metrics_enabled=True` accumulation). Acceptance: `run2_total_tokens - run1_total_tokens <= 1000`. The +1000 buffer covers per-contact LLM non-determinism (the per-contact batch alone can vary by ±5% between runs); the master call itself is ~2-3k tokens, so an INVOKED master call on run 2 would push the delta well past 1000. A run-2 delta in the −500..+1000 range confirms the master call was reused, not invoked. |
| 4 | Temporarily monkey-patch `llamar_api` to raise `urllib.error.HTTPError` for the master call (e.g. by setting `args.fail_fast=False` and breaking the URL); then run | `[WARN] Master synthesis call failed after retry. Individual results remain available.` is printed; `outputs/contexto_{ts}.md` is still produced; per-contact summaries are intact; the `master_context:` block in YAML is **absent** (or has empty `summary:`); `outputs/contexto_{ts}.json` has `master_context: null`. |

For test 3, exact token equality is a strong check but brittle to network jitter — accept "no NEW master call tokens" (the per-contact tokens may differ by ±5% between runs, but the master call tokens should be exactly zero on the second run). Easiest: read the run #1 `[LOTE 1]` line, run #2 `[LOTE 1]` line, and verify `run2_total_tokens <= run1_total_tokens + 1000` (the +1000 buffer covers per-contact LLM non-determinism). Master call is ~2-3k tokens; if it's invoked, the second run's total exceeds the first by a wide margin.

### Additional Edge Cases

The four smoke tests above cover the happy path and one failure path. The gate review flagged three boundary cases that the apply phase must verify with targeted asserts (no extra fixtures; reuse the test database from Smoke 1 and a monkey-patch helper for the API).

| # | Case | Expected behavior | What proves it |
|---|---|---|---|
| E1 | All contacts land in the same `Vínculo Comercial` label (e.g. 50 contacts all classified as `Cliente`) | `aggregate_for_master()` produces a single label group. `random.sample(items, min(10, len(items)))` returns exactly 10 contacts. The master input has ONE `=== Cliente (50 contactos, muestreo 10) ===` block, 10 topic bullets, ≤ 11 lines. The master call is invoked once. `labels_distribution = {"Cliente": 50}`. | Monkey-patch `llamar_api` to record its prompts; verify the master call's prompt contains exactly one `=== ` block. Run on a 50-contact test DB and confirm `outputs/contexto_{ts}.md` `master_context.labels_distribution == {"Cliente": 50}`. |
| E2 | Empty response on the FIRST master call (HTTP 200 with `choices[0].message.content == ""`) | CRITICAL-2 fix path: `master_call_with_retry` raises `MasterCallEmptyResponse`, falls into the second iteration, invokes the API again. If the retry returns non-empty text, that text is returned. If the retry ALSO returns empty, the function returns `None`, the `[WARN]` line prints exactly once, and the YAML `master_context:` block is absent. Two API calls total in the failure case. | Monkey-patch `llamar_api` to return `("", 0, 0, 0, 0)` on the first call and a valid synthesis on the second. Verify `outputs/contexto_{ts}.md` has the master block. Then monkey-patch to return `("", 0, 0, 0, 0)` on BOTH calls; verify `[WARN]` prints once, no master block, and the `__MAESTRO__` SQLite row is NOT written. |
| E3 | SQLite write failure for `period='master'` (e.g. disk full, schema locked mid-run by another process) | The `INSERT OR REPLACE` raises `sqlite3.OperationalError` after the master call succeeded. The function catches it, prints `[WARN] No se pudo persistir el contexto maestro en SQLite. La síntesis se mantiene en memoria para esta corrida.`, and the in-memory `master_text` is still passed to `dual_output_writer` for the YAML/JSON output. The next run will re-invoke the master call (no row was persisted). | Inject a side effect into the SQLite connection that raises `OperationalError("database is locked")` on the next `cursor.execute`; run `--with-metrics`; verify the output files contain the master block AND `[WARN] No se pudo persistir…` prints. Then re-run the command — the second run must invoke the master call again (no `__MAESTRO__` row exists). |

## Acceptance Criteria

| Spec REQ | Design mapping | Acceptance check |
|---|---|---|
| REQ-005-001 Reduced prompt | `LABELS` constant + 2-field `instrucciones` text in `llamar_api`; `# TODO` comment present | Smoke 1: every per-contact summary has 2 bullets; `LABELS` constant visible in source |
| REQ-005-002 Aggregation | `aggregate_for_master()` with `defaultdict`, `random.sample(min(10, n))` | Smoke 2: master input has ≤ 60 lines; `labels_distribution` in YAML sums to `len(summaries)` |
| REQ-005-003 Synthesis + persistence | `master_call_with_retry()` + `INSERT OR REPLACE` for `__MAESTRO__` row | Smoke 1: `outputs/contexto_{ts}.md` has `master_context:` block; `outputs/contexto_{ts}.json` has `master_context` field; `SELECT * FROM conversation_summaries WHERE contact_phone='__MAESTRO__'` returns 1 row |
| REQ-005-004 Failure handling | `try/except` wrapping the master call, single retry, `print("[WARN]…")` | Smoke 4: forced failure prints `[WARN]` exactly once; per-contact output intact |
| REQ-005-005 Resume | `is_recent(updated_at, hours=24)` check before `master_call_with_retry` | Smoke 3: second run prints `[INFO] Master context reutilizado…` and skips API call (verifiable via token count) |
