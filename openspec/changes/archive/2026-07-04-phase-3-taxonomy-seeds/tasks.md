# Tasks: phase-3-taxonomy-seeds

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~165–415 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Author YAML Seeds

- [ ] **T-001** Author `taxonomias_seed/salud.yaml` — 6 top-level categories: `TURNOS`, `RECETAS`, `RESULTADOS_ESTUDIOS`, `COBERTURA`, `FACTURACION`, `ATENCION_PACIENTE`. Each subcategory 2–6 tags (median ~3). Descriptions in Spanish ≤ 100 chars. UPPER_SNAKE_CASE throughout. Maps to REQ-001, REQ-002, REQ-003.
- [ ] **T-002** Author `taxonomias_seed/educacion.yaml` — 7 top-level categories: `INSCRIPCIONES`, `DOCENTES`, `LICENCIAS_ARTICULO`, `ESTUDIANTES`, `PADRES`, `INSTITUCION`, `PAGOS`. Note: `LICENCIAS_ARTICULO/ARTICULO_FAMILIAR` has 2 tags. Each subcategory 2–6 tags. Descriptions in Spanish ≤ 100 chars. Maps to REQ-001, REQ-002, REQ-004.
- [ ] **T-003** Author `taxonomias_seed/retail.yaml` — 7 top-level categories: `PRODUCTOS`, `VENTAS`, `PRESUPUESTOS`, `STOCK`, `CLIENTES`, `PAGOS`, `DEVOLUCIONES`. Note: `CLIENTES/ALTA` has 2 tags. Each subcategory 2–6 tags. Descriptions in Spanish ≤ 100 chars. Maps to REQ-001, REQ-002, REQ-005.
- [ ] **T-004** Author `taxonomias_seed/general.yaml` — Exactly 4–5 top-level categories from the approved set: `CONSULTAS`, `UBICACION_ACCESO`, `QUEJAS_RECLAMOS`, `FUERA_DE_AMBITO`, `PRECIOS_HORARIOS`. Each subcategory 2–6 tags. Descriptions in Spanish ≤ 100 chars. Maps to REQ-001, REQ-002, REQ-006.
- [ ] **T-005** Author `taxonomias_seed/personal.yaml` — Action-verb-led categories: `COMUNICACION_DIRECTA`, `COMPARTIR`, `SOLICITUDES`, `EXPRESION`. Subcategory names are chat actions (e.g., `COORDINAR_PLAN`, `RECORDATORIO`, `COMPARTIR_ARCHIVO`, `PEDIR_OPINION`). No theme names (no `FAMILIA`, `TRABAJO`, `SALUD_PERSONAL`). Each subcategory 2–6 tags. Descriptions in Spanish ≤ 100 chars. Maps to REQ-001, REQ-002, REQ-007.

## Phase 2: README Update

- [ ] **T-006** Replace `taxonomias_seed/README.md` — Update the file list to exactly the 5 new files: `salud.yaml`, `educacion.yaml`, `retail.yaml`, `general.yaml`, `personal.yaml`. Remove `servicios_profesionales.yaml`. Preserve the "Convención de nombres" paragraph. Maps to REQ-008.

## Phase 3: Validation

- [ ] **T-007** Structural validation — Run `yaml.safe_load` on all 5 new YAMLs; confirm each parses without exception. Verify each has exactly `{domain, description, categories}` at root. Confirm every subcategory has 2–6 tags. Confirm all `description` fields are Spanish and ≤ 100 chars. Confirm all keys are UPPER_SNAKE_CASE. Confirm `general.yaml` has 4–5 categories. Confirm `personal.yaml` subcategory names are action verbs (no theme names). Run the pre-commit one-liner from the design doc.
- [ ] **T-008** Confirm untouched files — Verify `taxonomias_seed/medical_licenses.yaml` is byte-identical to its Phase 2 state. Verify no files under `outputs/` were created or modified.

## Dependencies

- T-001 through T-005 are independent — can be authored in any order or in parallel.
- T-006 can start as soon as the list of new files is known (T-001–T-005 are running).
- T-007 depends on T-001 through T-005 being complete.
- T-008 depends on T-001 through T-007 being complete.

## Order of Execution

1. T-001, T-002, T-003, T-004, T-005 (in any order — YAML authoring, no interdependencies)
2. T-006 (README update — replace stale list with 5 new file names)
3. T-007 (structural validation — all YAMLs must exist)
4. T-008 (confirm untouched files — final gate)
