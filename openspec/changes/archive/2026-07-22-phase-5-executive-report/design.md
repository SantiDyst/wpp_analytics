# Design: phase-5-executive-report

## Context

The current `analizar_contexto.py` writes three artifacts: a flat JSON data dump, a per-contact Markdown with one table row per sampled contact, and a legacy `reporte_contexto_v2.md` that re-iterates the same profiles by reading `conversation_summaries`. The architecture directive (`arquitectura_y_flujo_agil.md`) requires replacing this with a 3-output split: **Data Lake JSON** (machine-readable, consumed by Phase 3 RAG/taxonomy), **Executive MD** (human-readable, dense, no per-contact tables), **Logs** (audit, unchanged). Phase-4b introduced `master_context` as a 350-word executive synthesis parked in the YAML front-matter; phase-5 promotes that synthesis to the body of the MD and adds four structured sections that mirror the manual reference report.

This change supersedes the MD-output portion of phase-4b (`aggregate_for_master`, `MASTER_SYNTHESIS_PROMPT`, `dual_output_writer` MD branch, `compilar_reporte_local`). The JSON shape, master-call resume logic, and per-contact 2-field LLM prompt are unchanged.

## Goals / Non-Goals

| In | Out |
|---|---|
| Drop `reporte_contexto_v2.md` generation | Per-contact 2-field LLM prompt (phase-4b, unchanged) |
| Replace MD body with 4-section executive report | Master-call retry/empty-body logic (phase-4b, unchanged) |
| Enrich master-call input with raw conversation snippets | New test framework — manual smoke only |
| Keep JSON data-lake shape stable; add `master_sections` + `conversation_snippet` | Phase-3 YAML taxonomy integration (still TODO) |
| Remove `compilar_reporte_local` | Interactive batch-mode report (line 1295) — same removal applies |

## Architecture Decisions

### Decision: Re-extract conversation snippets from the open cursor inside `aggregate_for_master()`

**Choice**: `aggregate_for_master()` accepts the live `cursor` and re-runs `extraer_muestra_contacto(cursor, phone, name)` for each sampled contact, then joins the per-contact `Temas Clave` (from the stored summary) with the first ~12 chat lines of the extracted conversation.

**Alternatives**: (a) Cache snippets in memory during `procesar_chats_con_ia()` and thread them through the return tuple. Rejected: requires changing the shared helper signature and forces a 4th return value on every caller (interactive batch doesn't need it). (b) Persist raw snippets to `conversation_summaries.summary_raw`. Rejected: bloats the SQLite table with duplicated conversation text and pollutes the JSON payload shape. (c) Open a second SQLite connection just for the master call. Rejected: directly violates Fix 5 (B) — one connection per run.

**Rationale**: The `--with-metrics` branch keeps `conn`/`cursor` open until line 1161 (`conn.close()`); the master call happens at line 1145, before close. Re-extraction costs one indexed SELECT per sampled contact (~90 SELECTs of a few rows each) and zero new connections.

### Decision: Drop per-label sample from 10 → 6 to compensate for richer payload

**Choice**: `random.sample(items, min(6, len(items)))` (was 10).

**Rationale**: 6 contacts × 6 labels × ~15 lines of profile + chat snippet ≈ 540 lines worst case vs. the prior 60-line cap. Six per label still gives 30-50 keywords per label — statistically sufficient to identify dominant themes. The trade-off (fewer contacts sampled per label) is acceptable because each sampled contact now carries raw chat context, not just 5 keywords.

### Decision: Parse the master response into a 4-key dict before the MD writer runs

**Choice**: `master_call_with_retry()` returns `dict[str, str] | None` with keys `contexto_general`, `tematicas`, `dudas`, `propuesta_taxonomia`. The MD writer consumes the dict, not the raw text.

**Alternatives**: Return raw markdown; let the writer split on `## 1.` … `## 4.`. Rejected: parser logic ends up duplicated inside the MD writer, and a malformed header (the LLM renames a section) makes the writer fail silently. A dict enforces the contract at the API boundary.

**Rationale**: A single parsing helper in `master_call_with_retry()` is testable in isolation; the MD writer becomes a thin formatter. Bonus: the JSON payload's `master_context.sections` field is the dict itself — zero transformation needed for the data-lake consumer.

### Decision: `compilar_reporte_local()` is deleted entirely

**Choice**: Remove the function (lines 949-1007), the `report_path` module-level variable (line 31), the call site in the `--with-metrics` branch (lines 1190-1197), the call site in the interactive path (line 1295), and the final print that references `report_path.name` (line 1340).

**Rationale**: The function does one thing — re-emit `conversation_summaries` as a per-contact Markdown. The new `contexto_*.md` already contains everything `compilar_reporte_local` would write, plus the executive synthesis. Keeping it produces a duplicate artifact (architectural no-no per the directive).

### Decision: New `logs.txt` line for master-call token accounting

**Choice**: Add `[MASTER]` line after `master_call_with_retry()` completes, with prompt/candidate/total tokens + elapsed seconds.

**Rationale**: Phase-4b flagged this as a future enhancement ("a future enhancement could add a `[MASTER]` line, but phase-4b keeps the change scope tight"). Phase-5 picks it up so the master-call cost is auditable. The format matches the existing `[LOTE N]` line style.

## Data Flow

```
  --with-metrics branch (lines 1062-1199)
       │
       │ stratified sample → procesar_chats_con_ia() → summaries {phone: 2-field md}
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ aggregate_for_master(summaries, cursor, db_path)                │
  │                                                                 │
  │   grouped = defaultdict(list) by parse_label(summary)           │
  │   for label, items in grouped:                                  │
  │       sample = random.sample(items, min(6, |items|))            │
  │       for phone, summary in sample:                             │
  │           temas = extract_temas(summary)                        │
  │           snippet = extraer_muestra_contacto(cursor, phone, …)  │
  │                    .splitlines()[-12:]   # last 12 chat lines    │
  │           emit "- {phone} | Temas: {temas} | Snippet: …"        │
  │   return distribution, master_input_string                     │
  └─────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ master_call_with_retry(master_input) → dict | None              │
  │                                                                 │
  │   prompt = MASTER_SYNTHESIS_PROMPT.format(master_input=…)      │
  │   text = llamar_api(prompt, raw_prompt=True, fail_fast=False)   │
  │   text = remove_think_tags(text)                                │
  │   sections = _parse_master_sections(text)                       │
  │   # splits on "## 1.", "## 2.", "## 3.", "## 4."                │
  │   if any section missing → return None (degrades gracefully)    │
  │   return {"contexto_general": …, "tematicas": …, …}             │
  └─────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ Persistence + log                                               │
  │   UPSERT __MAESTRO__ row with JSON-encoded sections dict        │
  │   registrar_logs_v3("MASTER", db_name, prompt_tokens, …)        │
  └─────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │ dual_output_writer(sample, metrics, summaries, db_name, ts,     │
  │                     output_dir, stratification, total_dataset,  │
  │                     master_sections={…4 keys…},                 │
  │                     labels_distribution={…})                    │
  │                                                                 │
  │   JSON: contacts[].conversation_snippet (truncated, 200 chars)  │
  │         + master_context.sections = {4-key dict}                │
  │   MD:   YAML front-matter (master_context block + summary|)     │
  │         ## 1. Contexto General del Entorno                       │
  │         ## 2. Temáticas o Categorías Más Comunes                │
  │         ## 3. Dudas o Consultas Frecuentes                       │
  │         ## 4. Propuesta de Taxonomía                              │
  │   NO per-contact tables. NO legacy reporte_contexto_v2.md.      │
  └─────────────────────────────────────────────────────────────────┘
```

## 1. New Output Contracts

### `contexto_{ts}.json` shape

Fields kept (unchanged): `generated_at`, `db_name`, `total_contacts`, `sampled_contacts`, `stratification`, `contacts[].phone/name/metrics/profile_summary`.

Fields added:
- `master_context.sections: {contexto_general, tematicas, dudas, propuesta_taxonomia}` — the four parsed sections.
- `master_context.generated_at`, `master_context.labels_distribution` — unchanged from phase-4b.
- `contacts[].conversation_snippet: str` — last ~200 chars of the per-contact extracted conversation, for Phase-3 RAG consumption. Added to the per-contact dict so downstream taxonomy/RAG tools have raw chat context without re-querying SQLite.

```json
{
  "generated_at": "2026-07-07T14:32:11",
  "db_name": "auto_wpp",
  "total_contacts": 300,
  "sampled_contacts": 90,
  "stratification": { "5491115551234": "high", … },
  "master_context": {
    "generated_at": "2026-07-07T14:32:11",
    "labels_distribution": { "Cliente": 20, "Proveedor": 15, … },
    "sections": {
      "contexto_general": "El negocio opera como comercializador mayorista de …",
      "tematicas": "1. Pedidos y entregas (45 menciones)…",
      "dudas": "- ¿Cuál es el plazo de entrega para …?",
      "propuesta_taxonomia": "- Operación comercial\n  - Pedidos…"
    }
  },
  "contacts": [
    {
      "phone": "5491115551234",
      "name": "Juan",
      "metrics": { "total_messages": 42, … },
      "profile_summary": "*   **Vínculo Comercial:** Cliente\n*   **Temas Clave:** …",
      "conversation_snippet": "Cliente: Hola, necesito un pedido…"
    }
  ]
}
```

### `contexto_{ts}.md` shape

YAML front-matter (same shape as phase-4b, `master_context:` block kept) + exactly four `## N.` sections, no per-contact tables:

```markdown
---
date: 2026-07-07
title: Reporte Ejecutivo de Análisis de Contexto
db_name: auto_wpp
sample_size: 90
tier_method: quantile (P33/P66 inclusive)
master_context:
  generated_at: 2026-07-07T14:32:11
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
    El negocio opera como comercializador mayorista de …  [mirrored from contexto_general]
---

## 1. Contexto General del Entorno

<contenido devuelto por MASTER_SYNTHESIS_PROMPT, sección 1>

## 2. Temáticas o Categorías Más Comunes

<contenido, sección 2>

## 3. Dudas o Consultas Frecuentes

<contenido, sección 3>

## 4. Propuesta de Taxonomía

<contenido, sección 4 — árbol jerárquico, máx 3 niveles>
```

### `logs.txt`

No change to existing `[LOTE N]` lines. **New line** appended after the master call completes (success or fail-and-skip):

```
[2026-07-07 14:32:11] [MASTER] DB=auto_wpp | Tokens Entrada=3200 | Tokens Salida=1100 | Total Tokens=4300 | Tiempo=8.42s
```

Master-call failure path emits:

```
[2026-07-07 14:32:11] [MASTER] DB=auto_wpp | STATUS=failed | Tiempo=4.10s
```

## 2. Removal of Legacy Output

| Item | Lines | Action |
|---|---|---|
| `report_path = output_dir / 'reporte_contexto_v2.md'` | 31 | Delete |
| `def compilar_reporte_local(...)` | 949-1007 | Delete entirely |
| `--with-metrics` call: `compilar_reporte_local(db_path, master_context={…})` | 1190-1197 | Delete; replace with new `escribir_reporte_ejecutivo(...)` call (see §5) |
| Interactive-batch call: `compilar_reporte_local(db_path)` | 1295 | Delete |
| `[INFO] Reporte legacy (reporte_contexto_v2.md) también actualizado.` | 1189 | Delete |
| `print(f" Reporte unificado disponible en: {report_path.name}")` | 1340 | Replace with `print(f" Reporte ejecutivo: contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}.md")` (ts needs hoisting; see §8) |

Imports: `re` stays (used by `parse_label`, `extract_temas`, `remove_think_tags`). No imports become unused after the deletion.

## 3. `aggregate_for_master()` Redesign

```python
def aggregate_for_master(
    summaries: dict,
    cursor: sqlite3.Cursor,
) -> tuple[dict, str]:
    """Build rich master-call input: per-label profile + raw chat snippet.

    Returns (labels_distribution, master_input_string).
      - labels_distribution: {"Cliente": 20, "Proveedor": 15, ...}
      - master_input_string: ≤ ~600 lines, 6 contacts sampled per label,
        each contact gets its stored `Temas Clave` plus the last ~12
        chat lines extracted from the open cursor.
    """
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for phone, summary in summaries.items():
        if not summary:
            continue
        label = parse_label(summary)
        grouped[label].append((phone, summary))

    distribution = {label: len(items) for label, items in grouped.items()}

    blocks = []
    for label, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        sample = random.sample(items, min(6, len(items)))
        contact_lines = []
        for phone, summary in sample:
            temas = extract_temas(summary) or "(sin temas)"
            # Re-extract from the live cursor; same helper used by the
            # per-contact loop, so the snippet format is consistent.
            muestra = extraer_muestra_contacto(cursor, phone, _name_lookup(phone))
            snippet_lines = (muestra or "").splitlines()[-12:]   # last 12 chat lines
            snippet = " | ".join(snippet_lines)[:600]           # hard cap
            contact_lines.append(
                f"  - {phone}\n    Temas: {temas}\n    Snippet: {snippet}"
            )
        header = f"=== {label} ({len(items)} contactos, muestreo {len(sample)}) ==="
        blocks.append(header + "\n" + "\n".join(contact_lines))

    return distribution, "\n\n".join(blocks)
```

`_name_lookup(phone)` is a small inline closure passed by the caller (or a dict hoisted from the `--with-metrics` branch where `phone_to_name` is already built at line 1093).

**Trade-off**: Master-call input token count grows from ~6k worst case to ~30-40k worst case. With `max_tokens=4096` for the master call (already configured in `llamar_api` for `is_individual=False`/`raw_prompt=True`), the OUTPUT budget is unchanged; the INPUT budget grows. For `gemini-2.5-flash` (1M context) and MiniMax-M3 (≥128k context) this is comfortably inside the window. Per-run cost rises by ~$0.01-0.03 on the master call — acceptable given the qualitative jump in synthesis quality.

## 4. New `MASTER_SYNTHESIS_PROMPT`

The prompt must elicit four sections with parseable Markdown headers. Exact text (the apply phase copies this verbatim into `MASTER_SYNTHESIS_PROMPT`):

```python
MASTER_SYNTHESIS_PROMPT = (
    "Eres un analista senior de inteligencia comercial B2B. Recibirás una "
    "muestra estratificada de conversaciones reales de WhatsApp, agrupadas "
    "por Vínculo Comercial. Cada contacto incluye Temas Clave (resumidos por "
    "IA) y un fragmento crudo de su conversación.\n\n"
    "Produce un Reporte Ejecutivo estructurado en EXACTAMENTE cuatro secciones, "
    "cada una iniciando con su encabezado Markdown en una línea propia. "
    "Respeta los encabezados al pie de la letra (sin renombrar):\n\n"
    "## 1. Contexto General del Entorno\n"
    "[2-3 párrafos: qué hace el negocio, cómo opera, canales principales, "
    "volumen relativo por tipo de vínculo. Tono ejecutivo, sin relleno.]\n\n"
    "## 2. Temáticas o Categorías Más Comunes\n"
    "[Lista priorizada de 5-8 patrones transversales de conversación con "
    "frecuencia relativa estimada. Cada ítem: '- <tema> (<N> contactos)' "
    "seguido de una línea de evidencia del snippet.]\n\n"
    "## 3. Dudas o Consultas Frecuentes\n"
    "[Lista de 5-10 preguntas reales o implícitas que los usuarios hacen. "
    "Esta sección es insumo directo para chatbots. Formato: '- ¿<pregunta>?' "
    "seguido de una línea de contexto breve.]\n\n"
    "## 4. Propuesta de Taxonomía\n"
    "[Árbol jerárquico Markdown con guiones. Máximo 3 niveles de "
    "profundidad. Cada categoría hoja debe tener 2-3 ejemplos reales "
    "derivados de los snippets. Formato:\n"
    "  - <Categoría nivel 1>\n"
    "    - <Subcategoría nivel 2>\n"
    "      - <Tema nivel 3>: ejemplo1, ejemplo2]\n\n"
    "Restricciones:\n"
    "- Idioma: español.\n"
    "- Tono: ejecutivo, denso, sin disclaimers ni frases de cortesía.\n"
    "- Longitud total: 500-800 palabras. Si te quedas corto, profundiza; "
    "si te excedes, recorta las evidencias a una línea cada una.\n"
    "- NO inventes datos. Cita solo lo respaldado por los snippets.\n"
    "- NO incluyas secciones adicionales fuera de las cuatro.\n\n"
    "Muestra de contactos:\n{master_input}"
)
```

## 5. MD Writer Redesign (`escribir_reporte_ejecutivo`)

```python
def escribir_reporte_ejecutivo(
    master_sections: dict[str, str],
    db_name: str,
    sample_size: int,
    ts: time.struct_time,
    labels_distribution: dict[str, int],
    output_dir: Path,
) -> Path:
    """Write contexto_{ts}.md: YAML front-matter + 4 executive sections.

    Returns the output Path. Does not raise on missing section — emits a
    placeholder line for each missing key.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}"
    md_path = output_dir / f"{stem}.md"

    date_str = time.strftime("%Y-%m-%d", ts)
    contexto = master_sections.get("contexto_general", "")

    front_matter = [
        "---",
        f"date: {date_str}",
        "title: Reporte Ejecutivo de Análisis de Contexto",
        f"db_name: {db_name}",
        f"sample_size: {sample_size}",
        "tier_method: quantile (P33/P66 inclusive)",
        "master_context:",
        f"  generated_at: {time.strftime('%Y-%m-%dT%H:%M:%S', ts)}",
        f"  database: {db_name}",
        f"  sample_size: {sample_size}",
        "  labels_distribution:",
    ]
    for label, count in labels_distribution.items():
        front_matter.append(f"    {label}: {count}")
    front_matter.append("  summary: |")
    for line in contexto.splitlines() or ["(sección no generada)"]:
        front_matter.append(f"    {line}")
    front_matter.append("---")
    front_matter.append("")

    body = [
        "## 1. Contexto General del Entorno",
        "",
        master_sections.get("contexto_general", "*No disponible.*"),
        "",
        "## 2. Temáticas o Categorías Más Comunes",
        "",
        master_sections.get("tematicas", "*No disponible.*"),
        "",
        "## 3. Dudas o Consultas Frecuentes",
        "",
        master_sections.get("dudas", "*No disponible.*"),
        "",
        "## 4. Propuesta de Taxonomía",
        "",
        master_sections.get("propuesta_taxonomia", "*No disponible.*"),
        "",
    ]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(front_matter + body))
    return md_path
```

## 6. Master Call Response Parsing

**Recommendation: option (a) — return a `dict[str, str]`**.

`master_call_with_retry()` returns `dict[str, str] | None`. Internal `_parse_master_sections(text: str) -> dict[str, str]` splits the raw text on the markers `## 1.`, `## 2.`, `## 3.`, `## 4.`, normalizes the keys to the four canonical names (`contexto_general`, `tematicas`, `dudas`, `propuesta_taxonomia`), and returns the dict. If any of the four markers is missing, the function returns `None` and the master block degrades to a single-line note in the MD front-matter (`master_context.summary: "(master call incomplete: missing section 3 — Dudas)"`).

**Justification**: The MD writer becomes a thin formatter (§5); the JSON payload's `master_context.sections` is the dict directly. Parsing is testable in isolation. A rename or reordering by the LLM surfaces as a hard failure at parse time, not as a silently-broken MD body.

## 7. `dual_output_writer()` Changes

| Change | Detail |
|---|---|
| Add kwarg `master_sections: dict[str, str] | None = None` | Replaces `master_context={"summary": master_text or "", …}` |
| Keep kwarg `master_context: dict | None = None` | Backward-compat: when caller passes the old shape, MD writer degrades gracefully (renders only YAML block, no body) |
| MD body | Replace the per-contact loop (lines 503-531) with the four-section body from `master_sections` |
| JSON `master_context.sections` | Emit the dict |
| JSON `contacts[].conversation_snippet` | New field; populated if `sample_for_output` includes it. Caller (main) populates this list by reusing `extraer_muestra_contacto` once per contact and truncating to 200 chars. |

## 8. Main Flow Integration (`--with-metrics` branch)

Replace lines 1188-1198 with:

```python
        # 8a. MD writer (replaces compilar_reporte_local)
        escribir_reporte_ejecutivo(
            master_sections=master_sections or {},
            db_name=db_name,
            sample_size=len(sample_phones),
            ts=ts,
            labels_distribution=master_meta.get("labels_distribution", {}),
            output_dir=args.output_dir,
        )

        # 8b. JSON writer (unchanged signature, extended payload)
        json_path, _md_path = dual_output_writer(
            sample_for_output, metrics, summaries, db_name, ts, args.output_dir,
            stratification=stratification_map,
            total_dataset_size=len(todos_contactos),
            master_sections=master_sections,
            master_context={
                "summary": (master_sections or {}).get("contexto_general", ""),
                "generated_at": master_meta.get("generated_at", ""),
                "labels_distribution": master_meta.get("labels_distribution", {}),
            },
        )
        print(f"[INFO] Salida JSON: {json_path.name}")
        print(f"[INFO] Reporte ejecutivo: contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}.md")
        print("[INFO] Proceso completado.")
        return
```

`master_sections` is the new variable name in main; assign it from `master_call_with_retry`'s dict return at line 1145. The cursor/connection lifecycle at lines 1154-1161 stays — re-extraction inside `aggregate_for_master` runs against the still-open cursor.

Interactive path (line 1295): delete the `compilar_reporte_local(db_path)` call. The interactive menu does not produce an MD file by design.

## 9. Backward Compatibility

| Artifact | Status | Notes |
|---|---|---|
| `outputs/reporte_contexto_v2.md` files written by previous runs | Historical, untouched | Users keep them on disk; new runs no longer write this path |
| `outputs/contexto_*.md` (old per-contact-table format) | Historical, untouched | Same — files on disk remain valid |
| `outputs/contexto_*.md` (new format) | Generated from this version onward | Format change is BREAKING for any downstream consumer that parsed the per-contact tables |
| `outputs/contexto_*.json` (old shape) | Historical, untouched | New runs add `master_context.sections` and `conversation_snippet`; missing keys in old files mean "phase-5 has not run on this DB yet" |
| `conversation_summaries` schema | Unchanged | `__MAESTRO__` row continues to exist; its `summary` column now holds a JSON-encoded dict `{contexto_general, tematicas, …}` instead of a 350-word string |
| `logs.txt` format | Extended | Old `[LOTE N]` lines parse unchanged; new `[MASTER]` lines are additive |

**Migration note for users** (changelog entry, no code action): "The MD report format changed in phase-5. Old `contexto_*.md` files used per-contact tables; new files use a four-section executive report. Old files remain on disk and are still readable. If you have a downstream tool that parses per-contact tables from `contexto_*.md`, migrate it to consume `contexto_*.json` instead."

## File Changes

| File | Action | Description |
|---|---|---|
| `scripts/analizar_contexto.py` | Modify | Rewrite `MASTER_SYNTHESIS_PROMPT`, `master_call_with_retry`, `aggregate_for_master`, `dual_output_writer` (MD branch); delete `compilar_reporte_local`, the `report_path` module var, the 4 call sites, and 2 print lines; add `escribir_reporte_ejecutivo`, `_parse_master_sections`, `registrar_logs_v3` (master-call log); extend `--with-metrics` branch to compute `conversation_snippet` per contact and call the new MD writer |
| `outputs/contexto_{ts}.md` | Format change | Body changes from per-contact tables to 4-section executive report |
| `outputs/contexto_{ts}.json` | Schema addition | New fields: `master_context.sections`, `contacts[].conversation_snippet` |
| `outputs/logs.txt` | Format addition | New `[MASTER]` lines |
| `conversation_summaries.__MAESTRO__.summary` | Format change | Stored value is now a JSON dict (was a 350-word string). Resume path checks `is_recent()` then deserializes via `json.loads`; if deserialization fails, treats the row as stale and re-invokes the master call |
| `outputs/reporte_contexto_v2.md` | Stop writing | No new files; existing files untouched on disk |

## Testing Strategy

No test framework. Manual smoke only. The architecture directive explicitly skips `/sdd-verify` and `/sdd-archive` (human-in-the-loop review after visual inspection).

| Layer | What to Test | Approach |
|---|---|---|
| Smoke | Full `--with-metrics` run on a real DB | `python scripts/analizar_contexto.py --with-metrics --db TU_DB --sample-size 0.30` |
| Visual | MD has 4 sections, no per-contact tables, executive tone, taxonomy tree ≤3 levels | Open `outputs/contexto_{ts}.md`; verify the YAML front-matter carries the `master_context:` block AND the body has exactly `## 1.` … `## 4.` headings with non-empty content |
| Visual | JSON has `master_context.sections` (4-key dict) and `contacts[].conversation_snippet` | Open `outputs/contexto_{ts}.json`; grep `"sections"` and `"conversation_snippet"` |
| Visual | Legacy file absent | Confirm `outputs/reporte_contexto_v2.md` was NOT created or modified this run |
| Functional | Resume works across format change | Run twice in succession; verify the second run prints `[INFO] Master context reutilizado…` and the `__MAESTRO__` row deserializes correctly (if deserialization fails, `[INFO]` should NOT print and the master call should re-invoke) |
| Functional | Failure path | Temporarily monkey-patch `llamar_api` to return `("", 0, 0, 0, 0)`; verify `[WARN] Master synthesis call failed after retry…` prints once, the MD body shows `*No disponible.*` for each section, and the JSON's `master_context.sections` is `null` |

## Migration / Rollout

No data migration. The first run after the change will:
1. Detect any existing `__MAESTRO__` row from phase-4b (where `summary` was a 350-word string).
2. Attempt `json.loads(summary)` → fails.
3. Fall through to a fresh master call.
4. Overwrite the row with a JSON-encoded dict.

**Rollback**: revert `scripts/analizar_contexto.py` to the phase-4b commit. The new `master_context.sections` and `conversation_snippet` fields are additive — older code that ignores unknown JSON keys continues to work. The `escribir_reporte_ejecutivo` function and the 4-section MD body disappear with the revert; old `contexto_*.md` files written post-rollback revert to the per-contact-table format.

## Open Questions

- **Cursor availability across the master-call → MD-write gap**: confirmed by reading lines 1078-1161 that `conn`/`cursor` are open throughout the `--with-metrics` branch's master-call section. No gap to close.
- **`_name_lookup` plumbing**: the new `aggregate_for_master(summaries, cursor)` signature drops the `name` dimension. The caller in main (line 1143) needs to pass `phone_to_name` as a third arg so `extraer_muestra_contacto` can build `contact_label`. Final signature: `aggregate_for_master(summaries, cursor, phone_to_name)`. The orchestrator's prompt did not call this out explicitly; flagged here for the apply phase.
- **JSON serialization of the `__MAESTRO__` row**: phase-4b stored `master_text` (str). Phase-5 stores `json.dumps(master_sections, ensure_ascii=False)`. The apply phase must NOT use `str(master_sections)` — that produces Python repr, not valid JSON.

## Acceptance Criteria

| Requirement | Design mapping | Acceptance check |
|---|---|---|
| 4-section executive MD | `escribir_reporte_ejecutivo` writes `## 1.` … `## 4.` from `master_sections` dict | Smoke: open the MD, count headings = 4 |
| Rich master input | `aggregate_for_master` re-extracts snippets via open cursor | Smoke: master call input has both `Temas:` and `Snippet:` fields per contact (grep `Snippet:` in `__MAESTRO__` row or temporarily print `master_input`) |
| No per-contact tables in MD | `dual_output_writer` MD branch emits only the 4 sections | Smoke: `grep -c "### #" outputs/contexto_*.md` returns 0 |
| `reporte_contexto_v2.md` not generated | `compilar_reporte_local` deleted; `report_path` deleted; call sites deleted | Smoke: `ls outputs/reporte_contexto_v2.md` returns "No such file" (or shows an unchanged timestamp from a prior run) |
| JSON `master_context.sections` populated | `dual_output_writer` writes the dict | Smoke: `jq .master_context.sections outputs/contexto_*.json` shows 4 keys |
| JSON `conversation_snippet` per contact | main loop re-extracts once per contact, truncates to 200 chars | Smoke: `jq '.contacts[0].conversation_snippet' outputs/contexto_*.json` shows non-empty string |
| Logs `[MASTER]` line | `registrar_logs_v3("MASTER", …)` after master call | Smoke: `tail -1 outputs/logs.txt` shows `[MASTER]` line |
| Master-call resume works across format change | `_parse_master_sections` + `json.loads` on cached row; fall through to fresh call on parse error | Functional: run twice; second run prints `[INFO] Master context reutilizado…` and `__MAESTRO__` row remains a JSON dict |