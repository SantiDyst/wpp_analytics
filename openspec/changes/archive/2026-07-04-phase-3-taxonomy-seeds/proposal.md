# Proposal: phase-3-taxonomy-seeds

## Intent

Seed taxonomies for 5 industry verticals (`salud`, `educacion`, `retail`, `general`, `personal`) as hand-authored YAML files in `taxonomias_seed/`, enabling Phase 4 wiring to runtime without manual bootstrap per new client. Today's manual taxonomy creation is one-vertical-at-a-time with no canonical starting point; Phase 2 delivered one seed (`medical_licenses.yaml`); Phase 3 generalizes that pattern.

## Scope

### In Scope

- `taxonomias_seed/salud.yaml` — Health vertical: turnos, recetas, cobertura, resultados, facturación, atención paciente.
- `taxonomias_seed/educacion.yaml` — Education vertical: inscripciones, docentes, estudiantes, padres, institución, pagos, licencias artículo.
- `taxonomias_seed/retail.yaml` — Retail vertical: productos, ventas, presupuestos, stock, clientes, pagos, devoluciones.
- `taxonomias_seed/general.yaml` — Cross-cutting fallback: horarios, consulta precio, atención cliente, productos servicios, gestión cuenta.
- `taxonomias_seed/personal.yaml` — Individual/social: planes, fotos, chats grupales, vida diaria, celebraciones.
- Canonical schema reference: `taxonomias_seed/medical_licenses.yaml` (Phase 2, unchanged).
- Activation workflow: `python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/<vertical>.yaml --client <client>` (manual, non-breaking).

### Out of Scope

- Any code changes in `scripts/` or elsewhere.
- Modifications to `load_taxonomy()` or `buscar_datos.py`.
- Wiring seed → runtime behavior (Phase 4 vertical routing decision).
- Changes to `outputs/` files.
- Modifications to `taxonomias_seed/README.md` (flagged as open question below).
- Authoring `servicios_profesionales.yaml` (not requested).

## Capabilities

> Contract with `sdd-spec`. No spec-level capabilities are introduced or modified — Phase 3 delivers only seed data files. The canonical schema is already locked by Phase 2.

### New Capabilities
*(None — seed files only; no new system capabilities)*

### Modified Capabilities
*(None — no existing capability requirements change)*

## Approach

Hand-author 5 YAML files matching the Phase 2 locked schema exactly:

```yaml
domain: UPPER_SNAKE_CASE
description: "Spanish text ≤ 100 chars"
categories:
  CATEGORY_KEY:
    SUBCATEGORY_KEY:
      - TAG_KEY
      - TAG_KEY
```

**Tag density target**: 2–6 tags per subcategory (median ~3), consistent with `medical_licenses.yaml` benchmark (range 1–4, median 3). Subcategories with a single tag equal to their name render in collapsed form — acceptable but lower discriminative power.

**Tag naming convention**: `PREFIX_TAG_DESCRIPTOR` (e.g., `SOL_TURNO_NUEVO`), matching Phase 2 prefix pattern.

**Activation**: Operator runs `bootstrap_taxonomy.py --seed taxonomias_seed/salud.yaml --client salud` once per vertical. The loader already supports arbitrary client names with no code changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `taxonomias_seed/salud.yaml` | New | Health vertical seed |
| `taxonomias_seed/educacion.yaml` | New | Education vertical seed |
| `taxonomias_seed/retail.yaml` | New | Retail vertical seed |
| `taxonomias_seed/general.yaml` | New | Cross-cutting fallback seed |
| `taxonomias_seed/personal.yaml` | New | Individual/social seed |
| `taxonomias_seed/medical_licenses.yaml` | Unchanged | Canonical schema reference |
| `scripts/buscar_datos.py` | Unchanged | No code changes |
| `scripts/bootstrap_taxonomy.py` | Unchanged | CLI unchanged |
| `outputs/` | Unchanged | Runtime concern; gitignored |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Schema drift (invalid YAML structure) | Low | All files validated with `yaml.safe_load` in spec; `load_taxonomy()` silently falls back to `TAXONOMIA` on parse error |
| Tag naming inconsistency across seeds | Medium | Follow Phase 2 prefix convention; spec defines `UPPER_SNAKE_CASE` |
| `personal.yaml` shape mismatch | Medium | Open question #2 — resolve before spec |
| `general.yaml` becomes a dumping ground | Medium | Open question #3 — cap at 4–5 categories |
| README still lists old verticals | Low | Open question #4 — user decides |

## Rollback Plan

YAML files are additive and purely lexical. To revert: delete the 5 new seed files. No code rollback needed. The `medical_licenses.yaml` seed and all `outputs/` files are unaffected.

## Dependencies

- `scripts/bootstrap_taxonomy.py` must remain functional (no code changes in Phase 3, but the script's existing `--seed` and `--client` flags are the activation mechanism).
- `pyyaml` must be installed for `bootstrap_taxonomy.py` to run (already documented in `LEEME.md`).

## Success Criteria

- [ ] All 5 YAMLs parse with `yaml.safe_load` (no syntax errors).
- [ ] Each YAML matches the canonical schema (same key shape, same nesting depth as `medical_licenses.yaml`).
- [ ] Each of `salud`, `educacion`, `retail` YAMLs has ≥ 3 top-level categories; each subcategory has ≥ 2 tags.
- [ ] `general.yaml` and `personal.yaml` each have ≥ 3 top-level categories; each subcategory has ≥ 2 tags.
- [ ] `description` field in Spanish, concise (≤ 100 chars).
- [ ] Tag density comparable to `medical_licenses.yaml` (1–7 tags per subcategory, median ~3).
- [ ] All tag keys and category/subcategory keys are `UPPER_SNAKE_CASE`.

## Open Questions

1. **Tag density target** — `medical_licenses.yaml` averages ~3 tags/subcategory (range 1–4). Recommend: **2–6 tags per subcategory, target median ~3**. Accept higher only for subcategories covering genuinely diverse workflows. Confirm or adjust.

2. **`personal.yaml` shape** — Should subcategories be themed (familia, trabajo, salud_personal, ocio) rather than workflow-step oriented? Exploration recommends theme-oriented; confirm.

3. **`general.yaml` coverage breadth** — How many categories (4–5 recommended) and subcategories to avoid becoming a dumping ground? Confirm the 4–5 category cap.

4. **`taxonomias_seed/README.md` update** — The README currently lists old verticals (salud/educacion/retail/servicios_profesionales). Options: (a) replace the list, (b) add a separate Phase 3 section, (c) leave unchanged. Recommend (a) or (b) before Phase 4 wiring.

---

**Status**: success  
**Executive summary**: Author 5 hand-crafted YAML seed taxonomies for salud, educacion, retail, general, and personal verticals in `taxonomias_seed/`, matching the Phase 2 schema locked in `medical_licenses.yaml`. No code changes; no runtime wiring; activation is manual bootstrap per vertical via the existing CLI. Four open questions need user input before spec.  
**Next recommended**: spec  
**Risks**: Schema drift, tag inconsistency, `personal.yaml` shape mismatch, README staleness  
**Skill resolution**: none
