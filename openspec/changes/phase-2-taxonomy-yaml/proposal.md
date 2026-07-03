# SDD Proposal: phase-2-taxonomy-yaml

## Intent

Extract the hardcoded taxonomy string from `buscar_datos.py` into a versioned YAML file and load it at runtime, while preserving the existing LLM prompt contract and backwards compatibility via a hardcoded fallback.

## Scope

**In scope:**
- Create `taxonomias_seed/medical_licenses.yaml` encoding the current 3-level taxonomy hierarchy
- Add `load_taxonomy(client_name)` in `buscar_datos.py` that reads `outputs/taxonomia_<client>_v1.yaml`
- Convert the loaded YAML back to the plain string format the LLM prompt expects (preserving the exact structure injected at line 261)
- Create the initial `outputs/taxonomia_auto_wpp_v1.yaml` from the seed
- Document `pyyaml` as a required (not optional) dependency

**Out of scope (deferred to Phase 3):**
- Versioning, rollback, or v2+ files
- Multi-taxonomy per business line or client
- Seed taxonomy generation from `perfil_cliente_*.json`
- `taxonomy_corrections` feedback table
- Changes to `analizar_contexto.py` or any other script

## Approach

**Approach A — Minimal Viable (chosen)**

A single change to `buscar_datos.py`:
1. Define `load_taxonomy(client_name)` that attempts to load `outputs/taxonomia_<client>_v1.yaml` via `pyyaml`
2. If the file is missing or `pyyaml` is unavailable, fall back to the existing hardcoded `TAXONOMIA` string
3. `load_taxonomy` returns the taxonomy as a plain multiline string in the exact format currently injected into the LLM prompt
4. `modo_semantic()` calls `load_taxonomy(nombre_db)` instead of referencing `TAXONOMIA` directly
5. No changes to the LLM prompt content, no changes to the DB schema, no changes to `analizar_contexto.py`

The seed file `taxonomias_seed/medical_licenses.yaml` encodes the current hierarchy as:
```yaml
domain: LICENCIAS_MEDICAS
description: Taxonomía para licencias médicas de empleados públicos
categories:
  LICENCIAS_MEDICAS:
    SOLICITUD_TURNO:
      - SOL_TURNO_NUEVO
      - SOL_TURNO_REPROGRAMAR
      - SOL_TURNO_INFO_REQUISITOS
    ...
```

The initial client output file `outputs/taxonomia_auto_wpp_v1.yaml` is a copy of the seed (no delta at this stage).

## Affected Areas

| File/Dir | Change |
|---|---|
| `scripts/buscar_datos.py` | Add `load_taxonomy()`, replace `TAXONOMIA` reference with `load_taxonomy(nombre_db)` |
| `taxonomias_seed/medical_licenses.yaml` | **Create** — seed taxonomy |
| `outputs/taxonomia_auto_wpp_v1.yaml` | **Create** — initial client taxonomy (copy of seed) |
| `requirements.txt` (or equivalent) | Add `pyyaml` as required |

No changes to `analizar_contexto.py`, `clean_db.py`, or any other script.

## Risks

1. **pyyaml dependency not installed** — The fallback to hardcoded `TAXONOMIA` handles this at runtime, but the user must install `pyyaml` for the YAML path to activate. This is documented explicitly.
2. **YAML file corrupted or empty** — `load_taxonomy` must validate non-empty output and fall back to `TAXONOMIA` on any parse error.
3. **Filename sanitization** — `nombre_db` from `seleccionar_db()` is used directly in the output filename. Future clients with spaces or special chars in their DB folder name will produce invalid filenames; this is accepted for Phase 2.
4. **No test coverage** — Manual verification via `python scripts/buscar_datos.py --mode semantic --query "..." --classify` against the real DB is the only verification path.
5. **Schema lock-in** — Once users edit `outputs/taxonomia_auto_wpp_v1.yaml`, changing the YAML schema in a future phase will require a migration step.

## Rollback Plan

Rollback is trivial: revert `buscar_datos.py` to the previous version that references the hardcoded `TAXONOMIA` string. The YAML files are additive and do not need to be removed. `pip uninstall pyyaml` does not break anything since the fallback activates when the import fails.

## Why This Approach

**Approach A over B (Full PLAN_PRODUCTO.md Fase 2):** The full Phase 2 spec calls for versioning, multi-taxonomy, seed generation from `perfil_cliente_*.json`, and a `taxonomy_corrections` table. This is over-engineering for a single-client project (`auto_wpp`). The user explicitly requested this change to stay focused. A large PR with versioning and feedback loops introduces unnecessary risk and complexity before the core extraction value is even validated.

**Approach A over C (Intermediate — Staged YAML + Seed):** Approach C would also document the versioning/multi-taxonomy schema for future phases. That design work belongs in `sdd-design` or `sdd-spec`, not in the Phase 2 implementation. Phase 2 should deliver working code; design documentation for Phase 3 is out of scope here.

**Approach A is correct because:** The taxonomy is a plain multiline string with exactly 2 usages (declaration + LLM injection). The change surface is small, backwards-compatible by construction, and delivers the stated intent — externalize the taxonomy to a YAML file — without speculative complexity.
