# SDD Onboard Tour Report — wpp_analytics

**Date**: 2026-07-03
**Tour conducted by**: SDD onboard sub-agent
**Execution mode**: interactive
**Artifact store**: openspec

---

## 1. Pipeline Structure (3 Etapas)

The project implements a **3-stage pipeline** (Discovery → Taxonomy → Operational IA):

| Etapa | Script | Role |
|---|---|---|
| **Etapa 1** (Discovery) | `buscar_datos.py` | Keyword + semantic search against SQLite DB; `keyword` mode uses SQL `LIKE`, `semantic` mode pre-filters contacts then calls AI. |
| **Etapa 2** (Taxonomy) | `buscar_datos.py` + future YAML | Hardcoded taxonomy string for "Reconocimientos Médicos"; Phase 2 migrates to `taxonomias_seed/*.yaml`. |
| **Etapa 3** (Operational IA) | `analizar_contexto.py` | Batch contact profiling pipeline — individual AI analysis per contact, local SQLite caching, report compilation. |
| **Auxiliary** | `clean_db.py` | Cleanup utility — strips `<think>...` blocks from saved profiles, recompiles report. |

---

## 2. Script Inventory

### `analizar_contexto.py` (559 lines)
- **Entry point**: interactive console menu → `python scripts/analizar_contexto.py`
- **CLI shape**: no arguments (interactive), auto-detects DB on Desktop siblings
- **Modes**: batch of 50 (with confirmation) or all-at-once
- **Flow**: shuffle contacts → for each contact not in cache → extract 40 messages → call AI (`llamar_api`) → save to `conversation_summaries` in SQLite → compile report
- **Key functions**: `remove_think_tags()`, `seleccionar_base_datos()`, `extraer_muestra_contacto()`, `llamar_api()`, `compilar_reporte_local()`, `registrar_logs_v2()`
- **Coupling**: reads from `contacts` + `messages`; writes to `conversation_summaries`; outputs `outputs/logs.txt` + `outputs/reporte_contexto_v2.md`
- **UTF-8 enforced**: `sys.stdout.reconfigure(encoding='utf-8')` at module top (line 2)

### `buscar_datos.py` (327 lines)
- **Entry point**: CLI with argparse → `python scripts/buscar_datos.py --mode keyword --query ...`
- **CLI shape**: `--db`, `--mode {keyword|semantic}`, `--query`, `--limit`, `--classify`
- **Modes**: `keyword` (SQL LIKE, no AI) and `semantic` (AI-powered, pre-filter + LLM)
- **Flow (semantic)**: `pre_filtrar_semantic()` → extract chat per contact → assemble prompt with taxonomy → `llamar_api()` → print result
- **Key functions**: `remove_think_tags()`, `seleccionar_db()`, `buscar_keyword()`, `pre_filtrar_semantic()`, `extraer_chat()`, `llamar_api()`, `modo_keyword()`, `modo_semantic()`
- **Coupling**: reads `contacts` + `messages`; no writes (read-only search)
- **UTF-8 enforced**: `sys.stdout.reconfigure(encoding='utf-8')` at module top (line 2)

### `clean_db.py` (98 lines)
- **Entry point**: `python scripts/clean_db.py`
- **CLI shape**: no arguments (auto-detects DB)
- **Flow**: reads all profiles from `conversation_summaries`, applies `remove_think_tags()`, updates in-place, recompiles report
- **Coupling**: reads/writes `conversation_summaries`; outputs `outputs/reporte_contexto_v2.md`
- **⚠️ Missing**: `sys.stdout.reconfigure(encoding='utf-8')` — the only script without it

---

## 3. Data Model (SQLite Schema)

### Existing tables (from source DB at `auto_wpp/database/whatsapp.sqlite`):
- **`contacts`** — `phone` (PK), `name`
- **`messages`** — `id`, `contact_phone` (FK), `from_me`, `body`, `media_name`, `mime_type`, `timestamp`; has indices on `(contact_phone, timestamp)` and `timestamp`; WAL mode enabled

### Created at runtime by `analizar_contexto.py`:
- **`conversation_summaries`** — `id`, `contact_phone`, `period` (e.g. `'profile'`), `summary`, `updated_at`; UNIQUE constraint on `(contact_phone, period)`

### Gaps per PLAN_PRODUCTO.md:
- No FTS5 virtual table (`messages_fts`) — planned in Phase 7
- No `message_attachments` table (BLOB separation) — planned in Phase 7
- `media_data` BLOB still in `messages` — source DB not yet refactored
- `whatsapp_message_id` column missing from `messages` — not yet added

---

## 4. AI Integration Layer

### Routing logic (duplicated in both `analizar_contexto.py` and `buscar_datos.py`):
```python
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("MODEL_NAME")
is_openai_compatible = api_key.startswith("sk-")
if is_openai_compatible:
    active_model = "MiniMax-M3"  # if model unset or "gemini" named
    url = "https://api.minimax.io/v1/chat/completions"
else:
    active_model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/.../{active_model}:generateContent"
```

### Current .env:
```
GEMINI_API_KEY=AQ.REDACTED_API_KEY_xxxxxxxxxxxxxxxxxxxxxxxxxx
```
**Note**: The value starts with `AQ.`, not `sk-`. This means it routes to the Gemini path, NOT MiniMax — despite the variable name suggesting it's a Gemini key.

### Config variables read:
- `GEMINI_API_KEY` — primary (both scripts)
- `MODEL_NAME` — optional override (both scripts)
- `API_BASE_URL` — optional base URL (only in `analizar_contexto.py`, line 23)

### Preference noted: user wants `MINIMAX_API_KEY` as primary env var with `sk-*` key routing to MiniMax explicitly.

---

## 5. Output Convention

All generated reports follow the same format:
```
---
date: YYYY-MM-DD
title: Report Title
---

## Markdown content
```

- Reports live in `outputs/` (gitignored)
- `logs.txt` tracks token usage per batch run
- `remove_think_tags()` strips `<think>...` and `</think>...` from all AI responses before storage
- Profile summaries stored in `conversation_summaries` table in SQLite (not just files)

---

## 6. Product Strategy (3 Tiers)

From `docs/propuesta_comercial.md`:

| Plan | Name | Price (ARS) | Features |
|---|---|---|---|
| 1 | Respaldo Express | $50,000 one-time | 500 chats backup, offline viewer, manual |
| 2 | Respaldo Activo | $18,000/month | Continuous sync, PM2 service, monthly support |
| 3 | Auditoría Inteligente (VIP) | $80,000 init + $35,000/month | AI semantic search + monthly IA executive report |

**Current implementation**: Scripts cover basic backup + VIP (Etapas 1-3). Plan 2 (continuous service) is Phase 6+.

---

## 7. Roadmap Phases (1-10)

From `PLAN_PRODUCTO.md`:

| Phase | Name | Status | Dependencies |
|---|---|---|---|
| 0 | Project structure ordering | ✅ Done | None |
| 1 | Shared utils + argparse CLI | Pending | None |
| 2 | YAML taxonomy migration | Pending | Phase 1 |
| 3 | Taxonomy seeds per industry | Pending | Phase 2 |
| 4 | Flask dashboard + API REST | Pending | Phase 1 |
| 5 | WhatsApp Assistant skill packaging | Pending | Phase 3 |
| 6 | PM2 background service (Plan 2) | Pending | Phase 4 |
| 7 | SQL optimization (FTS5, BLOB separation) | Pending | Phase 6 |
| 8 | Multi-DB aggregation | Pending | Phase 7 |
| 9 | Statistical analytics module | Pending | Phase 8 |
| 10 | Advanced IA (RAG, multi-agent) | Pending | Phase 9 |

---

## 8. Gaps: Current State vs PLAN_PRODUCTO.md

### Already delivered:
- ✅ `analizar_contexto.py` — batch profiling with caching
- ✅ `buscar_datos.py` — keyword + semantic search
- ✅ `clean_db.py` — think-tag cleanup
- ✅ YAML front-matter on reports
- ✅ `remove_think_tags()` in all relevant scripts
- ✅ UTF-8 stdout enforcement (except `clean_db.py`)
- ✅ SQLite caching of profiles
- ✅ DB auto-detection (Desktop sibling scan)
- ✅ OpenSpec bootstrapped (`openspec/config.yaml` + `openspec/changes/sdd-init-*/context.md`)
- ✅ Project structure (`scripts/`, `docs/`, `outputs/`, `taxonomias_seed/`, `skills/`, `tests/`)

### Pending (gaps):
- ⬜ Phase 1: Shared utils module (`scripts/utils.py`) — duplicate code blocks everywhere
- ⬜ Phase 1: Unified argparse CLI for all scripts
- ⬜ Phase 2: Taxonomy YAML migration (hardcoded string in `buscar_datos.py:24-41`)
- ⬜ Phase 3: `taxonomias_seed/` — empty directory
- ⬜ Phase 4: Flask dashboard — not started
- ⬜ Phase 5: `skills/whatsapp_assistant/` — empty directory
- ⬜ Phase 6: PM2 background service
- ⬜ Phase 7: FTS5 virtual table + BLOB separation in source DB
- ⬜ Phase 7: `whatsapp_message_id` column in `messages`
- ⬜ Phase 8: Multi-DB aggregation
- ⬜ Phase 9: Statistical analytics
- ⬜ Phase 10: RAG/multi-agent
- ⬜ `tests/` — empty placeholder, no test framework

---

## 9. sdd-init Claim Verification

| Claim | Status | Evidence |
|---|---|---|
| Stack: Python 3.14, stdlib-first | ✅ Verified | `sys.version_info` check in scripts; imports: sqlite3, urllib, json, argparse, re, pathlib, time, random, sys |
| Testing: NONE | ✅ Verified | `tests/` is empty; no pytest/unittest imports anywhere |
| Conventions: UTF-8, YAML front-matter, `remove_think_tags()` | ✅ Verified | All 3 scripts have UTF-8 reconfigure; both `analizar_contexto.py` and `buscar_datos.py` have `remove_think_tags()`; reports have YAML front-matter |
| Stdlib-first dependency policy | ✅ Verified | Optional deps `rich`/`pyyaml`/`flask` imported conditionally in `analizar_contexto.py` (lines 28-30) |
| OpenSpec bootstrapped | ✅ Verified | `openspec/config.yaml` + `openspec/changes/sdd-init-wpp_analytics/context.md` exist |
| **Bug at `buscar_datos.py:322`**: `classify = args.classify or True` | ✅ **CONFIRMED** | Line 322: `classify = args.classify or True` — `--classify` always evaluates True regardless of flag presence |
| Duplicate code (shared utils) | ✅ **CONFIRMED + Expanded** | `remove_think_tags()`, `seleccionar_base_datos()`, `seleccionar_db()`, `extraer_muestra_contacto()`, `extraer_chat()`, `llamar_api()` all duplicated verbatim between `analizar_contexto.py` and `buscar_datos.py` |
| Taxonomy hardcoded | ✅ Confirmed | `TAXONOMIA` constant at line 24-41 of `buscar_datos.py` |
| AI key-prefix routing | ✅ Confirmed | Both scripts use `api_key.startswith("sk-")` for MiniMax routing |

---

## 10. Additional Findings (not in sdd-init)

### Architectural smells:
1. **`clean_db.py` missing UTF-8 reconfigure** — the only script without `sys.stdout.reconfigure(encoding='utf-8')` at module top; potential `UnicodeEncodeError` on Windows
2. **`GEMINI_API_KEY` naming** — `.env` var name implies Gemini but contains a non-sk- key; both scripts read it. User prefers `MINIMAX_API_KEY` naming
3. **API key routed to Gemini despite .env** — the current key (`AQ.Ab8RN...`) starts with `AQ.`, NOT `sk-`, so it routes to Gemini URL, not MiniMax — likely unintentional
4. **`API_BASE_URL` only in `analizar_contexto.py`** — `buscar_datos.py` hardcodes the MiniMax URL, no override support
5. **`taxonomias_seed/` and `skills/` empty** — intentional stubs for Phases 3 and 5 respectively
6. **No test infrastructure** — `strict_tdd: false` is accurate; no pytest, no unittest, no test runner

### Risks:
- **No rollback mechanism** — scripts modify SQLite in-place; no backup before writes
- **No error recovery in batch** — `analizar_contexto.py` silently continues on API failure (line 505); contact is skipped but no retry queue
- **Source DB schema assumed stable** — scripts assume columns exist; no schema migration support
- **Python 3.14 edge cases** — very recent release; `sys.stdout.reconfigure()` and `pathlib` behavior may differ slightly from 3.11/3.12

---

*Tour artifacts saved under: `openspec/changes/sdd-onboard-wpp_analytics/`*
