# Exploration: phase-3-taxonomy-seeds

## Current State

### Schema confirmed identical across all files

`taxonomias_seed/medical_licenses.yaml`, `outputs/taxonomia_auto_wpp_v1.yaml`, and `outputs/taxonomia_auto_wpp2_v1.yaml` are **byte-identical**. The schema is locked by Phase 2 and imposes:

```yaml
domain: UPPER_SNAKE_CASE          # optional for load_taxonomy (not validated)
description: "Spanish text"        # optional for load_taxonomy (not validated)
categories:
  CATEGORY_KEY:                   # UPPER_SNAKE_CASE, value must be a dict
    SUBCATEGORY_KEY:              # UPPER_SNAKE_CASE, value must be a non-empty list
      - TAG_KEY                   # UPPER_SNAKE_CASE, non-empty string
      - TAG_KEY
```

**Structural invariants validated by `load_taxonomy()`** (`buscar_datos.py:77-93`):
1. Root must be a `dict` with a `categories` key whose value is a `dict`.
2. Each category value must be a `dict` (subcategories).
3. Each subcategory value must be a non-empty `list` of non-empty strings.
4. `domain` and `description` are **not validated** — they are free strings for human consumption.

The Phase 2 spec calls out an intentional asymmetry in the render algorithm:
- Hierarchical form: category on its own line, `  SUB: TAG1 | TAG2 | ...` indented 2 spaces (used when any subcategory has more than 1 tag, or the single tag differs from subcategory name).
- Collapsed form: `CATEGORY: SUB1 | SUB2 | SUB3` on one line (used when every subcategory has exactly 1 tag AND that tag name equals the subcategory name).

### Taxonomy loader path and critical gap

`load_taxonomy(client_name)` (`buscar_datos.py:41-109`) reads **only** from `outputs/taxonomia_{safe}_v1.yaml`. The `taxonomias_seed/` directory is NOT read at runtime — seeds must first be bootstrapped via `scripts/bootstrap_taxonomy.py` into the `outputs/` directory.

**CRITICAL**: There is no fallback logic for vertical selection. The system has no mechanism to route `"salud"` or `"educacion"` clients to a `general.yaml` seed. The only fallback is the hardcoded `TAXONOMIA` constant (LICENCIAS_MEDICAS). Phase 3 must address where vertical selection occurs: either (a) a naming convention in `outputs/` (e.g., `taxonomia_salud_v1.yaml`), (b) a vertical field in a client profile, or (c) a cascade of `outputs/taxonomia_{vertical}_v1.yaml` files tried by the loader. This is a **blocked** item — the 5 YAML files cannot be wired to runtime behavior without deciding this.

### `analizar_contexto.py` does not consume taxonomy

The Phase 1 design explicitly excludes `analizar_contexto.py` from taxonomy consumption. The grep found zero taxonomy references in that script. Taxonomies are consumed **only** by `buscar_datos.py` via `load_taxonomy()`.

### Existing taxonomias_seed/ contents

```
taxonomias_seed/
├── README.md                  # Lists old plan: salud/educacion/retail/servicios_profesionales
└── medical_licenses.yaml      # Phase 2 example — KEEP, DO NOT modify
```

The README plan (salud/educacion/retail/servicios_profesionales) is **superseded** by the Phase 3 plan (salud/educacion/retail/general/personal). The README should be updated in apply phase.

### Tag count benchmark

From `medical_licenses.yaml`:
| Subcategory | Tag count |
|---|---|
| SOLICITUD_TURNO | 3 |
| SEGUIMIENTO_Y_ESTADO | 3 |
| RECEPCION_ACTA | 3 |
| CORRECCION_ACTA | 4 |
| REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA | 4 |
| PROBLEMAS_EN_GESTION | 3 |
| INFO_AGENTE_ALTA_NUEVO_REGISTRO | 1 |
| INFO_AGENTE_ACTUALIZACION_DATOS | 1 |
| CONS_VARIAS_GENERAL | 1 |
| CONS_VARIAS_QUEJA_RECLAMO | 1 |
| CONS_VARIAS_FUERA_DE_AMBITO | 1 |

Range: 1–4 tags/subcategory. Median ~3. **Recommendation: 2–6 tags per subcategory** for new seeds. Subcategories with single tags that equal their name collapse to the collapsed form — this is acceptable but yields less discriminative power.

---

## Affected Areas

- `taxonomias_seed/medical_licenses.yaml` — reference schema, DO NOT modify
- `taxonomias_seed/README.md` — outdated vertical list, needs update in apply phase
- `scripts/buscar_datos.py` — `load_taxonomy()` is read-only consumer; no changes needed for seeds
- `scripts/bootstrap_taxonomy.py` — consumes seeds; CLI already supports custom `--seed` and `--client` args
- `outputs/` — where bootstrapped taxonomies live; no files yet for salud/educacion/retail/general/personal

---

## Approaches

### Approach A: Vertical-per-client naming convention

Each seed in `taxonomias_seed/` maps to a fixed client name: `salud.yaml` → `outputs/taxonomia_salud_v1.yaml`, etc. The operator selects the correct output file by running `bootstrap_taxonomy.py --client salud` for each vertical they serve. The loader reads the client-matched output.

- **Pros**: Zero code changes; leverages existing bootstrap CLI; no coupling between loader and verticals.
- **Cons**: No automatic fallback; operator must know which vertical to use per client; `general.yaml` has no special treatment.
- **Effort**: Low (apply phase — author 5 YAMLs, update README, document bootstrap workflow).

### Approach B: Vertical field in client profile

Introduce a `vertical` key in `perfil_cliente_*.json` (or a new ` verticals.yaml` mapping file) that `analizar_contexto.py` or `buscar_datos.py` reads to select the correct taxonomy file.

- **Pros**: Explicit routing; supports `general.yaml` as true fallback.
- **Cons**: Requires modifying `analizar_contexto.py` (which Phase 2 explicitly excluded from changes); adds new data artifact; more design work.
- **Effort**: High (requires spec change for a new artifact type).

### Approach C: Taxonomy loader cascade

Modify `load_taxonomy()` to try `outputs/taxonomia_{vertical}_v1.yaml` from a candidate list `[client_name, vertical_from_env, general]`. The vertical could come from a config file or the client name prefix (e.g., `auto_wpp_salud` → try `salud`).

- **Pros**: Automatic fallback to `general.yaml`; no schema changes.
- **Cons**: Mixes read and write concerns in `load_taxonomy` (violates Phase 2 design contract); still needs a source for `vertical` per client.
- **Effort**: Medium.

---

## Recommendation

**Approach A** for Phase 3. Author all 5 YAML files with the locked schema. Document the bootstrap workflow: operator runs `bootstrap_taxonomy.py --seed taxonomias_seed/salud.yaml --client salud` once per vertical, producing `outputs/taxonomia_salud_v1.yaml`. The loader already supports arbitrary client names — no code changes.

**Approach B** (vertical field) is the correct long-term answer and should be flagged as a follow-up SDD. The current `load_taxonomy` contract is read-only and must not be violated.

---

## Industry Analysis for the 5 Seeds

### salud.yaml — Health vertical

Typical subcategories for a medical practice or healthcare business:
- TURNOS (appointment scheduling, reprogramming, cancellations)
- RECETAS (prescriptions, medication refills)
- CONSULTAS (general inquiries, availability)
- COBERTURA (insurance, obra social, prepayment)
- RESULTADOS (lab results, imaging)
- FACTURACION (invoices, reimbursement, SUSS)
- ATENCION_PACIENTE (check-in, waiting times, amenities)

Target: 5–7 subcategories, 2–5 tags each.

### educacion.yaml — Education vertical

Typical subcategories for schools, teachers, institutions:
- INSCRIPCIONES (enrollment, re-enrollment, waitlists)
- DOCENTES (teacher records, certifications, licencias artículo)
- ESTUDIANTES (student records, calificaciones, asistencia)
- PADRES (parent communication, reuniones)
- INSTITUCION (school info, horarios, location)
- PAGOS (matrícula, cuotas, scholarships)
- LICENCIAS_ARTICULO (leave by article type — a specific Argentine labor context)

Target: 5–7 subcategories, 2–5 tags each.

### retail.yaml — Retail vertical

Typical subcategories for commerce, shops:
- PRODUCTOS (product info, catalog, variants)
- VENTAS (point of sale, transactions)
- PRESUPUESTOS (quotes, estimates, approval)
- STOCK (inventory, suppliers, reorder)
- CLIENTES (customer records, loyalty)
- PAGOS (payment methods, receipts)
- DEVOLUCIONES (returns, refunds)

Target: 5–7 subcategories, 2–5 tags each.

### general.yaml — Cross-cutting / fallback safety net

Used when a client doesn't fit salud/educacion/retail. Categories should be broad:
- HORARIOS_UBICACION (business hours, address, maps)
- CONSULTA_PRECIO (pricing inquiries, quotes)
- ATENCION_CLIENTE (complaints, feedback, soporte)
- PRODUCTOS_SERVICIOS (general catalog inquiries)
- GESTION_CUENTA (account changes, cancellations)

Target: 4–5 subcategories, 2–4 tags each. This is the last-resort before falling outside scope.

### personal.yaml — Individual / social use

One-to-one casual conversations, not business. Shape differs from verticals:
- PLANES (plans, activities, eventos)
- FOTOS (photo sharing, recuerdos)
- CHATS_GRUPALES (group conversations — note: this is personal social use)
- VIDA_DIARIA (daily life, salud personal, bienestar)
- CELEBRACIONES (birthdays, anniversaries, achievements)

Target: 4–5 subcategories, 2–4 tags each. Theme-oriented rather than workflow-oriented.

---

## Risks

1. **Schema drift across seeds**: If any of the 5 new YAMLs deviate from the locked schema (`categories` → dict → dict → list of strings), `load_taxonomy()` will silently fall back to `TAXONOMIA` (LICENCIAS_MEDICAS). Must be validated before use.

2. **Tag naming inconsistency**: All tags must be `UPPER_SNAKE_CASE`. The Phase 2 example prefixes tags with a subcategory abbreviation (e.g., `SOL_TURNO_NUEVO`). New seeds should follow the same convention to maintain prompt readability.

3. **Missing fallback behavior**: `general.yaml` is intended as the safety net but there is no code path that routes unknown clients to it. The system will fall back to `TAXONOMIA` (LICENCIAS_MEDICAS) instead. This is a **blocked item** that requires a design decision before apply phase can wire the seeds to runtime behavior.

4. **`taxonomias_seed/README.md` outdated**: Lists old verticals (salud/educacion/retail/servicios_profesionales). Must be updated in apply phase, but since it's in `taxonomias_seed/` (not `openspec/`), it can be updated without SDD overhead.

5. **Outputs bootstrapping not automated**: The bootstrap step is manual per vertical. If an operator serves multiple verticals, they must run `bootstrap_taxonomy.py` separately for each. Not a risk, but a workflow friction worth documenting.

---

## Ready for Proposal

**Yes**, with one blocker flagged: the fallback routing decision (where does `general.yaml` get selected when a client's vertical is unknown?) must be resolved in the `sdd-propose` phase. The 5 YAML files can be authored independently once the routing question is answered — the seeds themselves are independent of how they're selected.

The apply phase can proceed with authoring the YAMLs using Approach A (manual vertical selection) while the routing question is resolved separately.

---

## Next Steps

- `sdd-propose`: Resolve the fallback routing question. Confirm: is Approach A (manual per-client bootstrap) acceptable for Phase 3, or is a more automatic approach needed?
- `sdd-spec`: Define the 5 seed content contracts (category/subcategory/tag lists per vertical).
- `sdd-design`: Not needed — no code changes; design is locked by Phase 2.
- `sdd-apply`: Author 5 YAML files + update `taxonomias_seed/README.md` + document bootstrap workflow.
