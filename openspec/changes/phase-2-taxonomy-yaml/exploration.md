# Exploration: phase-2-taxonomy-yaml

## Current State

### Taxonomy Location and Format

The taxonomy is a **plain multiline string** (not a Python dict or list) at `scripts/buscar_datos.py:21-31`:

```python
TAXONOMIA = """
LICENCIAS_MEDICAS
  SOLICITUD_TURNO: SOL_TURNO_NUEVO | SOL_TURNO_REPROGRAMAR | SOL_TURNO_INFO_REQUISITOS
  SEGUIMIENTO_Y_ESTADO: SEG_TURNO_MEDICO_NO_CONTACTA | SEG_ACTA_NO_GENERADA | SEG_DEMORA_GENERAL
  RECEPCION_ACTA: REC_ACTA_NO_RECIBIDA | REC_ACTA_SOLICITAR_REENVIO | REC_ACTA_PROBLEMAS_ACCESO
  CORRECCION_ACTA: CORR_ACTA_FECHAS_DIAS | CORR_ACTA_DATOS_PERSONALES | CORR_ACTA_ARTICULO_TIPO_LICENCIA | CORR_ACTA_CRITERIO_MEDICO
  REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA: REQ_PROC_DOCUMENTACION_GENERAL | REQ_PROC_MODALIDAD_PRESENCIAL_ONLINE | REQ_PROC_LICENCIA_ESPECIFICA | REQ_PROC_ALTA_LABORAL
  PROBLEMAS_EN_GESTION: PROB_GEST_LICENCIA_DENEGADA | PROB_GEST_SITUACION_IRREGULAR | PROB_GEST_ERROR_PLATAFORMA
INFORMACION_AGENTE: INFO_AGENTE_ALTA_NUEVO_REGISTRO | INFO_AGENTE_ACTUALIZACION_DATOS
CONSULTAS_VARIAS: CONS_VARIAS_GENERAL | CONS_VARIAS_QUEJA_RECLAMO | CONS_VARIAS_FUERA_DE_AMBITO
"""
```

This is a 3-level hierarchy:
- **Level 1** (Category): `LICENCIAS_MEDICAS`, `INFORMACION_AGENTE`, `CONSULTAS_VARIAS`
- **Level 2** (Subcategory): `SOLICITUD_TURNO`, `SEGUIMIENTO_Y_ESTADO`, etc.
- **Level 3** (Tags): Pipe-delimited values inside each subcategory

### How the Taxonomy Is Consumed

Only **2 usages** exist in the entire codebase (confirmed via grep across all `.py` files):

1. **`scripts/buscar_datos.py:261`** — Injected as a raw string into the LLM prompt inside `modo_semantic()` when `classify=True`:
   ```python
   f"{TAXONOMIA}\n"
   "Indica la ruta taxonómica exacta (ej. LICENCIAS_MEDICAS > RECEPCION_ACTA > REC_ACTA_NO_RECIBIDA).\n"
   ```
2. **`scripts/buscar_datos.py:21`** — The variable declaration itself.

**No other script references the taxonomy.** `analizar_contexto.py` does not use it (it does contact profiling, not classification). `clean_db.py` does not touch it.

### Existing Data Flow

```
analizar_contexto.py  →  writes  →  perfil_cliente_<db>_<fecha>.json  (per PLAN_PRODUCTO.md, not yet built)
buscar_datos.py       →  reads   →  DB + hardcoded TAXONOMIA  →  LLM classification
```

### No Existing Versioning or Multi-Taxonomy

No `taxonomias_seed/` content exists. No `taxonomy_corrections` table exists. No per-client taxonomy files exist.

---

## Affected Areas

- `scripts/buscar_datos.py` — Core change: extract `TAXONOMIA`, add YAML loader, keep fallback
- `scripts/analizar_contexto.py` — Read-only consumer: may need to write the initial taxonomy file (Phase 1 seed), but NOT modified in this phase
- `taxonomias_seed/` — Target directory for seed taxonomy file(s) to be created in this phase
- `outputs/` — Target directory for client-specific taxonomy file(s) (`taxonomia_<client>_v<n>.yaml`)
- No impact to `clean_db.py` or any other script

---

## Approaches

### Approach A — Minimal Viable (Recommended)

Extract the hardcoded string to a YAML file. Implement a `load_taxonomy()` function that:
1. Tries to load `taxonomia_<client>_v1.yaml` from `outputs/`
2. Falls back to the hardcoded `TAXONOMIA` string if the file doesn't exist
3. Does NOT implement versioning, multi-taxonomy, feedback loop, or seed taxonomy generation

**Schema** (simple and close to current format):
```yaml
# taxonomias_seed/medical_licenses.yaml
domain: LICENCIAS_MEDICAS
description: Taxonomía para licencias médicas de empleados públicos
categories:
  LICENCIAS_MEDICAS:
    SOLICITUD_TURNO:
      - SOL_TURNO_NUEVO
      - SOL_TURNO_REPROGRAMAR
      - SOL_TURNO_INFO_REQUISITOS
    SEGUIMIENTO_Y_ESTADO:
      - SEG_TURNO_MEDICO_NO_CONTACTA
      - SEG_ACTA_NO_GENERADA
      - SEG_DEMORA_GENERAL
    # ... etc
  INFORMACION_AGENTE:
    INFO_AGENTE_ALTA_NUEVO_REGISTRO:
      - INFO_AGENTE_ALTA_NUEVO_REGISTRO
    INFO_AGENTE_ACTUALIZACION_DATOS:
      - INFO_AGENTE_ACTUALIZACION_DATOS
  CONSULTAS_VARIAS:
    CONS_VARIAS_GENERAL:
      - CONS_VARIAS_GENERAL
    CONS_VARIAS_QUEJA_RECLAMO:
      - CONS_VARIAS_QUEJA_RECLAMO
    CONS_VARIAS_FUERA_DE_AMBITO:
      - CONS_VARIAS_FUERA_DE_AMBITO
```

- Pros: Low risk, single change, backwards compatible, no over-engineering
- Cons: Doesn't deliver the full PLAN_PRODUCTO.md Fase 2 ambition
- Effort: Low

### Approach B — Full PLAN_PRODUCTO.md Fase 2

Implement everything from the spec: versioning (v1, v2...), multi-taxonomy per client, seed taxonomy generation from `perfil_cliente_*.json`, `taxonomy_corrections` table, rollback support.

- Pros: Matches the full spec ambition
- Cons: Over-engineering for a 1-client project, high risk of scope creep, large PR, breaks the "keep it focused" user intent
- Effort: High

### Approach C — Intermediate (Staged YAML + Seed)

Same as Approach A but ALSO create the seed taxonomy file and document the versioning/multi-taxonomy schema design for future phases.

- Pros: Sets up Phase 3 properly, still minimal scope
- Cons: Slightly more than strictly necessary
- Effort: Low-Medium

---

## Recommendation

**Approach A** (Minimal Viable) is the correct scope for Phase 2.

The user explicitly picked this change to keep it focused. Adding versioning, multi-taxonomy, and feedback loops now is over-engineering for `auto_wpp` being the sole client. The hardcoded fallback ensures zero regression risk.

**Specifically, Phase 2 should:**
1. Create `taxonomias_seed/medical_licenses.yaml` from current hardcoded taxonomy
2. Add `load_taxonomy(client_name)` function in `buscar_datos.py` with `pyyaml` + fallback to hardcoded string
3. Convert YAML to the plain string format expected by the LLM prompt (preserving existing prompt logic)
4. Create the initial `outputs/taxonomia_auto_wpp_v1.yaml` from the seed

**Defer to Phase 3:**
- Seed taxonomy generation from `perfil_cliente_*.json` (requires Fase 1 to exist)
- Versioning & rollback
- Multi-taxonomy per business/line
- `taxonomy_corrections` table

---

## Risks

1. **pyyaml dependency**: Listed as optional. If not installed, the fallback to hardcoded string works — but this should be documented clearly so the user knows to `pip install pyyaml`.
2. **YAML schema rigidity**: Once users start editing the YAML, changing the schema in future phases may require migration. A flat or semi-structured schema is easier to evolve than deeply nested.
3. **No validation**: The YAML loader should validate that the loaded taxonomy is non-empty; otherwise fall back silently. If the YAML file is corrupted, the fallback must save the user.
4. **No test coverage**: No test framework exists. Manual verification only. Changes must be verified by running `buscar_datos.py --mode semantic --query "..." --classify` against the real DB.
5. **Single-client assumption baked in**: The current `seleccionar_db()` returns `nombre_db` which can serve as the client key, but if future clients have spaces or special chars in their names, the filename may need sanitization.

---

## Next Steps

- `sdd-propose` — Formalize scope, approach, and rollback plan
- `sdd-spec` — Write delta spec with requirements and scenarios
- `sdd-design` — Define YAML schema, loader function signature, file naming conventions
- `sdd-tasks` — Break into implementable tasks
