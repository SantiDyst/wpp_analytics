# Exploration: phase-1-context-analyzer

## Current State

### Sampling Logic

The current sampling in `analizar_contexto.py` is **purely random** — no stratification whatsoever:

- **`scripts/analizar_contexto.py:424-425`**:
  ```python
  random.shuffle(todos_contactos)
  ```
  This is the sole sampling mechanism. All contacts are collected via `obtener_todos_los_contactos(db_path)` which does `SELECT phone, name FROM contacts` (no ordering, no filtering), then shuffled in-memory and processed sequentially in batches of 50.

- **`scripts/analizar_contexto.py:440-442`**:
  ```python
  while offset < total_contactos:
      limite_lote = min(offset + lote_size, total_contactos)
      contacts_batch = todos_contactos[offset : limite_lote]
  ```
  After shuffling, contacts are sliced into sequential batches of 50. The stratification problem is compounded: random shuffle + sequential batches means early batches may over/under-represent any natural grouping.

### Metrics / Aggregation

**No base metrics are currently generated.** The script only:
1. Calls the LLM per contact (`llamar_api()`) to produce a qualitative narrative summary per contact
2. Stores the result in `conversation_summaries` table (keyed by `contact_phone`, `period='profile'`)
3. Compiles all stored profiles into a markdown report

There is no numeric KPI computation (total chats, multimedia %, message distributions, etc.).

### Output Formats

**Current output** (`compilar_reporte_local()`, `scripts/analizar_contexto.py:323-366`):
- **Single Markdown file** (`reporte_contexto_v2.md`) with YAML front-matter (`---`, `date:`, `title:`)
- **No JSON output exists** anywhere in the script
- Report is written via `open(report_path, 'w', encoding='utf-8')` — `report_path` is a fixed path in the `outputs/` directory

The `conversation_summaries` table in SQLite is the only structured store; it stores raw LLM text per contact.

### CLI / Argument Handling

**No argparse in `analizar_contexto.py`.** The script uses an interactive menu (`input()`) to choose between:
1. Batch mode (50 contacts, manual confirmation between batches)
2. Full auto mode (process all without stopping)

There are zero command-line flags for sample size, output path, stratification, or metrics.

### DB Schema (inferred from queries)

**`messages` table** (confirmed from `extraer_muestra_contacto()` at line 120-126 and `buscar_datos.py` line 194-201):
```sql
SELECT from_me, body, media_name, mime_type 
FROM messages 
WHERE contact_phone = ? 
ORDER BY timestamp ASC
```
- `contact_phone` — foreign key to `contacts.phone`
- `from_me` — INTEGER (1 = us, 0 = contact)
- `body` — TEXT (message content, nullable)
- `media_name` — TEXT (filename of attachment, nullable)
- `mime_type` — TEXT (e.g. `image/jpeg`, `audio/ogg`, `application/pdf`)
- `timestamp` — TEXT (ISO format, confirmed from `buscar_datos.py:250`)

**`contacts` table** (confirmed from `obtener_todos_los_contactos()` at line 104):
```sql
SELECT phone, name FROM contacts
```

**`conversation_summaries` table** (confirmed from line 408-417):
```sql
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_phone TEXT NOT NULL,
    period TEXT NOT NULL,
    summary TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(contact_phone) REFERENCES contacts(phone),
    UNIQUE(contact_phone, period)
)
```

**Key for stratification**: `messages.contact_phone` links to `messages.mime_type` and `messages.timestamp` — so strata can be built from per-contact aggregates on the messages table without modifying existing schema.

---

## Affected Areas

- `scripts/analizar_contexto.py` — Core change target. Sampling, metrics, and dual output must be added here.
- `scripts/buscar_datos.py` — Pattern reference for argparse CLI style (`--db`, `--mode`, `--query`, `--limit`). Shares DB scanning logic (`seleccionar_base_datos()`) and `remove_think_tags()` utility.
- `scripts/clean_db.py` — Pattern reference for YAML front-matter report compilation. Shares the `compilar_reporte_local()` pattern (should be factored out or re-used).
- `outputs/` directory — Dual JSON + Markdown files will be written here; current `reporte_contexto_v2.md` is the only output.
- `database/` (sibling Desktop folders) — No schema change required; all needed columns (`mime_type`, `timestamp`, `from_me`, `contact_phone`) already exist.

---

## Approaches

### 1. Stratified Sampling

#### Approach 1A — Volume-Tier Stratification (Recommended)

Build strata based on **message volume tiers** (e.g., Low < 50 msgs, Medium 50-200, High > 200). Contact volume is a first-order proxy for relationship significance and is trivially computed with a single aggregation query:

```python
# Single query to build strata
cursor.execute("""
    SELECT contact_phone, COUNT(*) as msg_count
    FROM messages
    GROUP BY contact_phone
""")
```

Strata boundaries (Low/Medium/High) can be set as CLI args with smart defaults (percentiles). Within each stratum, **proportional allocation** is used: if a stratum represents 20% of contacts, ~20% of the sample comes from that stratum.

- **Pros**: Meaningful representation of light vs. heavy chat relationships; single DB round-trip; boundaries are intuitive and CLI-configurable.
- **Cons**: Volume isn't the only meaningful axis (contact type, recency, media ratio could also matter).
- **Effort**: Low-Medium

#### Approach 1B — Multi-Dimensional Stratification

Use **two or three axes simultaneously**: message volume tier + recency (last message date) + multimedia ratio. This requires more complex allocation logic and multiple aggregation queries.

- **Pros**: Most representative sample possible.
- **Cons**: Much more complex; allocation logic explodes in combinations; risk of empty strata; higher implementation and testing effort.
- **Effort**: High

#### Approach 1C — Equal Allocation with Minimum Coverage

Divide contacts into strata (by volume tier) and sample **equal numbers from each stratum**, with a minimum floor (e.g., at least 3 contacts per stratum even if it has fewer). This ensures rare types aren't drowned out.

- **Pros**: Guarantees minority groups appear in sample; simple logic.
- **Cons**: Statistically biased if population distribution matters; may over-sample light chatters.
- **Effort**: Low

### Recommendation: Approach 1A (Volume-Tier + Proportional Allocation)

Single aggregation query, proportional within strata, intuitive CLI flags (`--stratum-size`, `--stratum-boundaries`). Balances representativity with simplicity.

### 2. Base Metrics Generation

Metrics are computed **before** the LLM analysis phase, as a preliminary pass over `messages`. No new tables needed.

#### Approach 2A — Inline Metrics Pass (Recommended)

Before the main LLM loop, run a single aggregation query per stratum (or one global pass if no stratification) computing:
- `total_messages` — count per contact
- `multimedia_pct` — `COUNT(mime_type IS NOT NULL) / total * 100`
- `from_me_pct` — `SUM(from_me) / total * 100`
- `media_types` — `COUNT(DISTINCT mime_type)` per contact
- `date_range` — `MIN(timestamp)` and `MAX(timestamp)`

Return a `list[dict]` of per-contact metric dicts.

- **Pros**: Single DB pass; metrics computed once before sampling; available for both JSON and Markdown output.
- **Cons**: Slight upfront latency (but still just one `SELECT` per stratum).
- **Effort**: Low

#### Approach 2B — Streaming Metrics During Message Extraction

Compute metrics **on-the-fly** inside `extraer_muestra_contacto()`. Adds computation to the per-contact extraction loop.

- **Pros**: No separate pass needed.
- **Cons**: Duplicates the DB read (already done in `extraer_muestra_contacto()`); mixing data extraction with metrics pollutes a clean function.
- **Effort**: Low (but messy)

### Recommendation: Approach 2A (Inline Metrics Pass)

Clear separation of concerns: one pass to compute metrics, then use those metrics for stratification and output.

### 3. Dual Output (JSON + Markdown)

#### Approach 3A — Separate Files (Recommended)

Write two files to `outputs/`:
- `contexto_metrics_<db>_<timestamp>.json` — machine-readable
- `contexto_report_<db>_<timestamp>.md` — human-readable with YAML front-matter

JSON structure:
```json
{
  "generated_at": "2026-07-04T...",
  "db_name": "auto_wpp",
  "total_contacts": 123,
  "sampled_contacts": 45,
  "stratification": { "method": "volume_tier", "tiers": {...} },
  "contacts": [
    {
      "phone": "...",
      "name": "...",
      "metrics": {
        "total_messages": 312,
        "multimedia_pct": 23.4,
        "from_me_pct": 41.2,
        "media_types": ["image/jpeg", "audio/ogg"],
        "first_message": "2024-01-15",
        "last_message": "2026-06-20"
      },
      "profile_summary": "..."
    }
  ]
}
```

- **Pros**: Clean separation; JSON is fully program-readable; Markdown preserves current human-readable workflow; existing `reporte_contexto_v2.md` naming convention can be honored in the MD filename.
- **Cons**: Two files to manage.
- **Effort**: Low

#### Approach 3B — JSON with Embedded Markdown

Write a single `.json` file where each contact has a `markdown` field containing the human-readable block.

- **Pros**: Single file.
- **Cons**: Markdown inside JSON is awkward for humans reading the raw file; breaks the established `reporte_contexto_v2.md` convention.
- **Effort**: Low

#### Approach 3C — Side-by-Side Dual Extension

Write `contexto_report_<db>_<ts>.report.json` and `contexto_report_<db>_<ts>.report.md` (same stem, dual extensions).

- **Pros**: Explicitly paired.
- **Cons**: Unusual naming pattern; not used elsewhere in the project.
- **Effort**: Low

### Recommendation: Approach 3A (Separate Files)

Follows existing naming conventions (`reporte_contexto_v2.md`), keeps JSON clean for programmatic consumers, and is simplest to implement.

---

## Recommendation

**Implement Phase 1 as three orthogonal changes within the same `analizar_contexto.py` refactor:**

1. **Stratified sampling**: Approach 1A — volume-tier + proportional allocation. Add `--sample-size` and `--stratum-boundaries` CLI flags. Compute strata with a single pre-pass aggregation query.

2. **Base metrics**: Approach 2A — inline metrics pass. Compute `total_messages`, `multimedia_pct`, `from_me_pct`, `media_types`, `date_range` per contact in a single pre-pass before sampling.

3. **Dual output**: Approach 3A — separate `outputs/contexto_metrics_<db>_<ts>.json` and `outputs/contexto_report_<db>_<ts>.md` with YAML front-matter on the Markdown.

**Shared implementation notes:**
- Use `scripts/buscar_datos.py` argparse pattern as the CLI style reference
- Add `--sample-size` (int, default 50), `--stratum-boundaries` (e.g., `50,200`), `--output-dir` CLI args
- Keep `random.shuffle`-based selection within each stratum for randomness
- Metrics dict per contact is passed through to JSON output and can be referenced in Markdown
- Existing `conversation_summaries` table write (cache) behavior is unchanged
- Existing `compilar_reporte_local()` can be replaced by a new dual-output compiler

---

## Risks

1. **Large DB full-scan for metrics**: The metrics pre-pass reads `messages` for all contacts. With thousands of contacts and tens of thousands of messages each, this could be slow. Mitigation: make metrics opt-in via `--with-metrics`; omitting the flag skips the full scan and uses the existing cache path.

2. **Empty or near-empty strata**: If `--stratum-boundaries` values are too aggressive (e.g., 90% of contacts in "Low" tier), the proportional allocation may still under-represent small but important groups. Mitigation: floor of at least 2 contacts per stratum.

3. **Encoding on Windows stdout**: The project convention (`sys.stdout.reconfigure(encoding='utf-8')`) is noted in context but not present in `analizar_contexto.py` today. Should be added at the top of `main()`.

4. **Breaking the interactive menu**: Adding argparse should not break the existing interactive flow (modes 1 and 2). A `--batch` flag or positional argument can preserve the existing behavior as default.

5. **Existing `report_path` convention**: The existing `reporte_contexto_v2.md` uses a fixed name. The new output will use a timestamp-based name. The old file may still exist from previous runs. Not a bug, but worth noting.

6. **`mime_type` NULL handling**: The multimedia % calculation uses `COUNT(mime_type IS NOT NULL)`. If `mime_type` is NULL for some media rows (possible in real WhatsApp DBs), the denominator may be off. Should verify with a null-check query.

---

## Ready for Proposal

**Yes.**

The request is well-scoped: three clear capabilities (stratified sampling, base metrics, dual output) all targeting the same script (`analizar_contexto.py`). The existing codebase has all required schema columns (`messages.mime_type`, `messages.timestamp`, `messages.from_me`, `messages.contact_phone`) already populated and queried in sibling scripts.

No architectural unknowns remain. The main risk (large DB scan) is mitigable by making metrics opt-in via `--with-metrics` (omitting the flag skips the scan). The main design choice (volume-tier vs. multi-dimensional stratification) is clearly resolved in favor of the simpler approach for Phase 1.

The orchestrator should tell the user:
- Phase 1 is a refactor/addition to `analizar_contexto.py`; existing behavior (LLM profiling + SQLite cache + report compilation) is preserved
- New capabilities are additive and opt-in via CLI flags (`--sample-size`, `--stratum-boundaries`, `--output-dir`)
- Manual verification only (no test framework); delivery as a single PR is appropriate given the low-medium complexity
