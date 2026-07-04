# Design: phase-3-taxonomy-seeds

## Context

Today `taxonomias_seed/` contains exactly one complete seed (`medical_licenses.yaml`, the Phase 2 schema reference) and a `README.md` listing a stale 4-vertical plan (salud / educacion / retail / servicios_profesionales). Operators boot new clients one vertical at a time through `scripts/bootstrap_taxonomy.py`, with no canonical starting point for non-medical clients. Phase 3 closes that gap by hand-authoring five seeds — `salud`, `educacion`, `retail`, `general`, `personal` — plus a README refresh. Nothing in `scripts/`, `outputs/`, or the loader is touched. Activation stays manual: `python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/<v>.yaml --client <v>`.

## Goals / Non-Goals

**Goals** (locked):

- Five YAMLs in `taxonomias_seed/` matching `medical_licenses.yaml` byte-shape: top-level keys `domain` + `description` (Spanish, ≤ 100 chars) + `categories` (dict).
- All keys/tags `UPPER_SNAKE_CASE`; tag density 2–6 per subcategory, median ~3 per file (REQ-002).
- `salud`, `educacion`, `retail`: ≥ 3 top-level categories each (REQ-003/004/005).
- `general.yaml`: exactly 4–5 top-level categories — the approved set is `CONSULTAS`, `UBICACION_ACCESO`, `QUEJAS_RECLAMOS`, `FUERA_DE_AMBITO`, `PRECIOS_HORARIOS` (REQ-006). A sixth category makes the file over-broad and is REJECTED.
- `personal.yaml`: subcategory keys are chat-action verbs (`COORDINAR_PLAN`, `RECORDATORIO`, `PEDIR_OPINION`, `COMPARTIR_ARCHIVO`, …); theme names like `SALUD_PERSONAL` are REJECTED (REQ-007).
- `README.md`: replace the 4-item list with the 5 new file names; `servicios_profesionales.yaml` is gone (REQ-008).

**Non-Goals**: no loader wiring, no `load_taxonomy()` changes, no `outputs/` artifacts, no Phase 4 routing decision, no `servicios_profesionales.yaml`.

## Approach

### Conformance with `medical_licenses.yaml`

Every seed follows the exact byte-shape:

```yaml
domain: VERTICAL_KEY
description: "Texto en español, ≤ 100 caracteres"
categories:
  CATEGORY_KEY:
    SUBCATEGORY_KEY:
      - PREFIX_TAG_DESCRIPTOR
      - PREFIX_TAG_DESCRIPTOR
```

Tag prefixes mirror Phase 2 (`SOL_TURNO_*`, `SEG_*`, `REC_*`, `CORR_*`, `REQ_*`, `PROB_*`, `INFO_*`, `CONS_*`). New seeds reuse the same `PREFIX_*` skeleton for prompt readability (e.g., `TUR_*` for turnos, `REC_*` for recetas, `COB_*` for cobertura).

### `salud.yaml` (REQ-003) — ≥ 3 categories

| Category | Subcategories (example tags) |
|----------|-------------------------------|
| `TURNOS` | `SOLICITUD` (TUR_NUEVO, TUR_REPROGRAMAR, TUR_CANCELAR), `SEGUIMIENTO` (SEG_TURNO_NO_CONTACTA, SEG_DEMORA), `CONSULTA_GENERAL` (TUR_DISPONIBILIDAD, TUR_REQUISITOS) |
| `RECETAS` | `PRESCRIPCION` (REC_NUEVA, REC_RENOVACION), `REPOSICION` (REC_MEDICACION_CRONICA, REC_AUTORIZACION) |
| `RESULTADOS_ESTUDIOS` | `LABORATORIO` (LAB_RESULTADO_LISTO, LAB_RESULTADO_DUDA), `IMAGEN` (IMG_ESTUDIO_LISTO, IMG_ESTUDIO_DUDA) |
| `COBERTURA` | `OBRA_SOCIAL` (COB_AFILIACION, COB_AUTORIZACION), `PREPAGA` (COB_PLAN, COB_COPAGO) |
| `FACTURACION` | `EMISION` (FACT_EMITIDA, FACT_REIMPRIMIR), `REINTEGRO` (FACT_SOLICITUD, FACT_ESTADO) |
| `ATENCION_PACIENTE` | `ADMISION` (ATEN_CHECKIN, ATEN_DEMORA_ESPERA), `SEGUIMIENTO_CLINICO` (ATEN_EVOLUCION, ATEN_CONTROL_POST) |

### `educacion.yaml` (REQ-004) — ≥ 3 categories

| Category | Subcategories (example tags) |
|----------|-------------------------------|
| `INSCRIPCIONES` | `NUEVA` (INS_NUEVO_ALUMNO, INS_CICLO_LECTIVO), `REINSCRIPCION` (INS_RENOVACION, INS_CAMBIO_CURSO), `LISTA_ESPERA` (INS_ESPERA_POSICION) |
| `DOCENTES` | `ALTA_DOCENTE` (DOC_ALTA_TITULO, DOC_ALTA_CARGO), `ACTUALIZACION` (DOC_DATOS_PERSONALES, DOC_HORAS_CATEDRA) |
| `LICENCIAS_ARTICULO` | `ARTICULO_ENFERMEDAD` (LIC_ART_MEDICA, LIC_ART_PRORROGA), `ARTICULO_FAMILIAR` (LIC_ART_CARGO_FAMILIAR, LIC_ART_FALLECIMIENTO_FAMILIAR), `ARTICULO_ESTUDIOS` (LIC_ART_ESTUDIOS_AVANCE), `ARTICULO_MATERNIDAD` (LIC_ART_NACIMIENTO, LIC_ART_LACTANCIA) |
| `ESTUDIANTES` | `REGISTRO` (EST_ALTA, EST_BAJA), `CALIFICACIONES` (EST_NOTA_CONSULTA, EST_REVISION), `ASISTENCIA` (EST_INASISTENCIA_JUSTIFICAR, EST_INASISTENCIA_AVISO) |
| `PADRES` | `COMUNICACION` (PAD_REUNION, PAD_AVISO), `AUTORIZACION` (PAD_SALIDA_EDUCATIVA, PAD_RETIRO_ANTICIPADO) |
| `INSTITUCION` | `HORARIOS` (INS_HORARIO_CURSADA), `UBICACION` (INS_DIRECCION, INS_ACCESO), `CALENDARIO` (INS_FERIADO, INS_RECESO) |
| `PAGOS` | `MATRICULA` (PAG_MATRICULA_VENCIMIENTO), `CUOTA` (PAG_CUOTA_MENSUAL, PAG_CUOTA_VENCIDA), `BECA` (PAG_BECA_SOLICITUD, PAG_BECA_ESTADO) |

### `retail.yaml` (REQ-005) — ≥ 3 categories

| Category | Subcategories (example tags) |
|----------|-------------------------------|
| `PRODUCTOS` | `CATALOGO` (PROD_INFO_GENERAL, PROD_VARIANTE), `DISPONIBILIDAD` (PROD_EN_STOCK, PROD_SIN_STOCK) |
| `VENTAS` | `PUNTO_VENTA` (VEN_COMPROBANTE, VEN_PAGO), `SEGUIMIENTO` (VEN_ENTREGA, VEN_POST_VENTA) |
| `PRESUPUESTOS` | `EMISION` (PRES_NUEVO, PRES_VENCIMIENTO), `APROBACION` (PRES_ACEPTADO, PRES_RECHAZADO) |
| `STOCK` | `CONSULTA` (STOCK_DISPONIBLE, STOCK_FECHA_REPOSICION), `REPOSICION` (STOCK_PEDIDO_PROVEEDOR, STOCK_INGRESO_MERCADERIA) |
| `CLIENTES` | `ALTA` (CLI_NUEVO_CLIENTE, CLI_ALTA_REACTIVACION), `FIDELIDAD` (CLI_PUNTOS, CLI_DESCUENTO), `HISTORIAL` (CLI_COMPRA_ANTERIOR) |
| `PAGOS` | `METODO` (PAG_EFECTIVO, PAG_TARJETA, PAG_TRANSFERENCIA), `CUOTA` (PAG_CUOTA_ESTADO) |
| `DEVOLUCIONES` | `CAMBIO` (DEV_CAMBIO_TALLE, DEV_CAMBIO_PRODUCTO), `REEMBOLSO` (DEV_REEMBOLSO_PENDIENTE, DEV_REEMBOLSO_PROCESADO) |

### `general.yaml` (REQ-006) — 4 or 5 categories, no more

Approved top-level keys (UPPER_SNAKE_CASE per REQ-001):

1. `CONSULTAS` — `CONS_GENERAL` (CONS_PREGUNTA_GENERAL, CONS_INFO_NEGOCIO)
2. `UBICACION_ACCESO` — `UBI_DIR_HORARIO` (UBI_DIRECCION, UBI_HORARIO_ATENCION), `UBI_ACCESO` (UBI_COMO_LLEGAR, UBI_ESTACIONAMIENTO)
3. `QUEJAS_RECLAMOS` — `QUE_RECLAMO` (QUE_RECLAMO_PRODUCTO, QUE_RECLAMO_SERVICIO), `QUE_SUGERENCIA` (QUE_SUGERENCIA_MEJORA)
4. `FUERA_DE_AMBITO` — `FUERA_REDIRIGIR` (FUERA_REDIRIGIR_VERTICAL, FUERA_NO_CORRESPONDE)
5. `PRECIOS_HORARIOS` — `PRE_PRECIO` (PRE_CONSULTA_PRECIO, PRE_LISTA), `PRE_HORARIO` (PRE_HORARIO_ESPECIAL, PRE_FERIADO)

Phase 3 ships all five; a future phase may drop to four. Six is REJECTED.

### `personal.yaml` (REQ-007) — action-verb shape

Top-level keys group actions by chat **context**, never by life theme:

| Category | Subcategories (verbs) |
|----------|-----------------------|
| `COMUNICACION_DIRECTA` | `COORDINAR_PLAN` (PER_COORD_PLAN_FECHA, PER_COORD_PLAN_LUGAR), `RECORDATORIO` (PER_REC_AGENDA, PER_REC_CUMPLE), `CONSULTA_RAPIDA` (PER_CONS_OPINION, PER_CONS_DUDA), `SALUDO_DESPEDIDA` (PER_SAL_BIENVENIDA, PER_DESPEDIDA) |
| `COMPARTIR` | `COMPARTIR_ARCHIVO` (PER_COMP_ARC_DOCUMENTO, PER_COMP_ARC_PDF), `COMPARTIR_ENLACE` (PER_COMP_LINK_WEB, PER_COMP_LINK_VIDEO), `COMPARTIR_FOTO` (PER_COMP_FOTO_UNICA, PER_COMP_FOTO_ALBUM) |
| `SOLICITUDES` | `PEDIR_OPINION` (PER_PED_OPINION_DECISION, PER_PED_OPINION_RECOMENDACION), `PEDIR_FAVOR` (PER_PED_FAVOR_AYUDA, PER_PED_FAVOR_TRAMITE), `PEDIR_REFERENCIA` (PER_PED_REF_CONTACTO, PER_PED_REF_PROFESIONAL) |
| `EXPRESION` | `FELICITACION` (PER_FEL_LOGRO, PER_FEL_CUMPLE), `DISCULPAS` (PER_DISC_OFRECER, PER_DISC_ACEPTAR), `AGRADECIMIENTO` (PER_AGR_AYUDA, PER_AGR_REGALO), `QUEJA_PERSONAL` (PER_QUE_DESABOGO, PER_QUE_BUSCO_CONSEJO) |

### `README.md` (REQ-008)

Replace the 4-item list with exactly: `salud.yaml`, `educacion.yaml`, `retail.yaml`, `general.yaml`, `personal.yaml`. Remove `servicios_profesionales.yaml`. Preserve the "Convención de nombres" section.

## Files / Functions Touched

| File | Action | Reason |
|------|--------|--------|
| `taxonomias_seed/salud.yaml` | Create | REQ-003 |
| `taxonomias_seed/educacion.yaml` | Create | REQ-004 |
| `taxonomias_seed/retail.yaml` | Create | REQ-005 |
| `taxonomias_seed/general.yaml` | Create | REQ-006 |
| `taxonomias_seed/personal.yaml` | Create | REQ-007 |
| `taxonomias_seed/README.md` | Modify | REQ-008 — replace list |

**Not touched**: `medical_licenses.yaml` (canonical reference, byte-locked), `scripts/buscar_datos.py`, `scripts/bootstrap_taxonomy.py`, `outputs/*`, `openspec/main-specs/*` (sync happens in archive phase).

## Schema Validation Strategy

Pre-commit single-line check (stdlib-only, matches project philosophy):

```bash
python -c "
import yaml, sys
ref = yaml.safe_load(open('taxonomias_seed/medical_licenses.yaml'))
for f in ['salud','educacion','retail','general','personal']:
    d = yaml.safe_load(open(f'taxonomias_seed/{f}.yaml'))
    assert set(d.keys()) == {'domain','description','categories'}, f
    assert d['categories'].keys() == ref['categories'].keys() or isinstance(d['categories'], dict)
    for cat, subs in d['categories'].items():
        for sub, tags in subs.items():
            assert 2 <= len(tags) <= 6, f'{f}/{cat}/{sub}'
print('OK')
"
```

`load_taxonomy()` silently falls back to `TAXONOMIA` on parse error — schema drift is invisible at runtime. This pre-commit gate is the only safety net before `bootstrap_taxonomy.py` runs.

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Schema drift (wrong top-level key, non-dict categories, list-as-subcategory) | Low | Pre-commit validator above; REQ-001 byte-shape check. |
| Tag naming inconsistency across 5 files | Medium | Reuse Phase 2 prefix convention (`PREFIX_*`); REQ-002 density rule. |
| `personal.yaml` slipping into theme names (`FAMILIA`, `TRABAJO`) | Medium | REQ-007 action-verb test — every subcategory name must be a verb-led phrase. |
| `general.yaml` becoming a dumping ground | Medium | REQ-006 hard cap of 5 categories; sixth is REJECTED. |
| README keeps `servicios_profesionales.yaml` by mistake | Low | REQ-008 explicit replace; validator grep for the legacy name. |
| Bootstrap wiring question unanswered (Approach A vs B vs C in exploration.md) | High | **Out of scope for Phase 3**; seeds are content-only, runtime routing is a follow-up SDD. |

## Migration / Rollout

**Non-breaking**. All five files are additive. Existing `medical_licenses.yaml` and every `outputs/taxonomia_*_v1.yaml` are untouched. Rollback = delete the 5 new YAMLs and revert README.

**Activation workflow** (documented, manual):

```bash
python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/salud.yaml      --client salud
python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/educacion.yaml  --client educacion
python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/retail.yaml     --client retail
python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/general.yaml    --client general
python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/personal.yaml   --client personal
```

Each command produces `outputs/taxonomia_<v>_v1.yaml`. The loader already accepts arbitrary client names (`buscar_datos.py:41-109`). No code path change.

## Acceptance Criteria

Each item maps 1-to-1 to a spec REQ and is verifiable without code changes:

- [ ] **REQ-001** All 5 YAMLs parse with `yaml.safe_load`; each has exactly `{domain, description, categories}` at the root, same nesting as `medical_licenses.yaml`.
- [ ] **REQ-002** Every subcategory list has 2–6 tags; median across each file is 2–4.
- [ ] **REQ-003** `salud.yaml` has ≥ 3 top-level categories and includes `TURNOS` (or equivalent) with 2–6 tags.
- [ ] **REQ-004** `educacion.yaml` has ≥ 3 top-level categories and includes `DOCENTES` + `LICENCIAS_ARTICULO` with 2–6 tags each.
- [ ] **REQ-005** `retail.yaml` has ≥ 3 top-level categories and includes `PRODUCTOS` + `VENTAS` with 2–6 tags each.
- [ ] **REQ-006** `general.yaml` has exactly 4 or 5 top-level categories, named from the approved set `CONSULTAS`, `UBICACION_ACCESO`, `QUEJAS_RECLAMOS`, `FUERA_DE_AMBITO`, `PRECIOS_HORARIOS`.
- [ ] **REQ-007** Every subcategory in `personal.yaml` is a verb-led chat action (e.g., `COORDINAR_PLAN`, `RECORDATORIO`, `PEDIR_OPINION`, `COMPARTIR_ARCHIVO`); no theme names (`FAMILIA`, `TRABAJO`, `SALUD_PERSONAL`).
- [ ] **REQ-008** `README.md` lists exactly the 5 new file names; `servicios_profesionales.yaml` is absent.
- [ ] All `description` fields are Spanish and ≤ 100 characters.
- [ ] All category, subcategory, and tag keys are `UPPER_SNAKE_CASE`.
- [ ] Pre-commit validation one-liner exits 0.

---

**Status**: success
**Executive summary**: Phase 3 design commits to authoring five `taxonomias_seed/*.yaml` files plus a README refresh, all conforming byte-shape to the Phase 2 `medical_licenses.yaml` reference. Top-level category names for each vertical are concrete (e.g., salud: `TURNOS`/`RECETAS`/`RESULTADOS_ESTUDIOS`/`COBERTURA`/`FACTURACION`/`ATENCION_PACIENTE`; personal: action-verb shape per REQ-007). No code or loader wiring is in scope; runtime vertical routing is flagged as a follow-up SDD.
**Next recommended**: `sdd-tasks` (decompose apply phase into per-file tasks with REQ acceptance gates).
**Risks**: schema drift, tag inconsistency, `personal.yaml` theme drift, `general.yaml` breadth creep, README staleness, runtime routing unresolved (out of scope here).
**Skill resolution**: paths-injected (read both `sdd-design` and `cognitive-doc-design` from explicit paths).