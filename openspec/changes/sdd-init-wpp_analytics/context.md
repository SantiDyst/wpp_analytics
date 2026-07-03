# SDD Init Context — wpp_analytics

**Detected**: 2026-07-03
**Execution Mode**: interactive
**Artifact Store**: openspec (mode: openspec)
**Delivery Strategy**: single-pr-default
**Review Budget**: 800 lines
**Strict TDD**: false

## Stack

| Component | Value |
|---|---|
| Language | Python 3.14.0 |
| Interpreter | C:\Python314\python.exe |
| Stdlib modules | sqlite3, urllib, json, argparse, re, pathlib, time, random, sys |
| Optional deps | rich (UI), pyyaml (configs), flask (dashboard) |
| Scripts | scripts/analizar_contexto.py, scripts/buscar_datos.py, scripts/clean_db.py |
| API | Gemini via urllib (GEMINI_API_KEY) or OpenAI/MiniMax-compatible (sk-* keys) |
| Config | .env with GEMINI_API_KEY (gitignored) |
| Project lang | Spanish (docs); English for code/identifiers/comments |

## Project Structure

```
scripts/           — 3 executables
  analizar_contexto.py  — batch contact profiling pipeline
  buscar_datos.py       — keyword + semantic search
  clean_db.py           — removes AI think blocks from saved profiles
docs/             — 5 reference docs (analytics, propuesta, sql_features, skills, reporte)
outputs/          — generated artifacts (logs.txt, reporte_contexto_v2.md) — gitignored
taxonomias_seed/  — YAML taxonomy seeds per industry (empty, Phase 3)
skills/            — whatsapp_assistant/ packaging (empty, Phase 5)
tests/             — automated tests (empty placeholder)
99_archivo/        — deprecated/historical — do not touch
```

## Conventions (from PLAN_PRODUCTO.md, analizar_contexto.py, buscar_datos.py)

- **Encoding**: Force UTF-8 on stdout/stderr at top of each script (`sys.stdout.reconfigure(encoding='utf-8')`).
- **API compatibility**: `sk-*` keys → OpenAI/MiniMax (`https://api.minimax.io/v1/chat/completions`, model `MiniMax-M3`); other keys → Google Gemini (`gemini-2.5-flash` default).
- **Cleanup**: `remove_think_tags()` strips `<think>...</think>` and `<think>...` blocks from LLM responses before saving to DB.
- **Reports**: Always with YAML front-matter (`---`, `date:`, `title:`).
- **DB path**: Scans sibling Desktop folders for `database/whatsapp.sqlite`; supports multi-DB interactive selection.
- **Taxonomy**: Currently hardcoded string in `buscar_datos.py`; Phase 2 migrates to external YAML.
- **Stdlib-first**: Scripts work with stdlib only; rich/pyyaml/flask are optional enhancements.
- **Caching**: Profile results cached in SQLite table `conversation_summaries` keyed by (contact_phone, period).

## OpenSpec Layout

```
openspec/
├── config.yaml            ← Project SDD config
├── specs/                 ← Main specs (source of truth)
└── changes/
    └── archive/           ← Completed changes
```

## Risks

- `strict_tdd: false` — all verification must be manual until pytest is added
- `tests/` directory is empty placeholder; future work needs test scaffold
- `taxonomias_seed/` and `skills/` directories are empty stubs
- GEMINI_API_KEY in .env (gitignored) — no other secrets management
- Python 3.14 is very recent; some packages may lack compatibility

## Next Step

Run `sdd-explore` to scope the first change.
