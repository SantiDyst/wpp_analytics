# Design: phase-2-taxonomy-yaml

## 1. Module / File Layout

```
wpp_analytics/
├── taxonomias_seed/
│   ├── README.md                       (existing — untouched)
│   └── medical_licenses.yaml           (new — seed taxonomy, edited manually)
├── outputs/
│   ├── logs.txt                        (existing)
│   ├── reporte_contexto_v2.md          (existing)
│   └── taxonomia_auto_wpp_v1.yaml      (new — generated, byte-equivalent to seed in v1)
├── scripts/
│   ├── analizar_contexto.py            (existing — untouched, does NOT consume taxonomy)
│   ├── buscar_datos.py                 (modified — gains `load_taxonomy()` + pyyaml import)
│   ├── bootstrap_taxonomy.py           (new — one-shot CLI to write client output from seed)
│   └── clean_db.py                     (existing — untouched)
└── LEEME.md                            (modified — adds `pip install pyyaml` to Requisitos)
```

| File | Action | Role |
|------|--------|------|
| `taxonomias_seed/medical_licenses.yaml` | Create | Source-of-truth seed; manually edited. Stores the 3-level hierarchy as nested YAML. |
| `outputs/taxonomia_auto_wpp_v1.yaml` | Create | Generated per-client output. Read by `load_taxonomy()`. v1 is a copy of the seed. |
| `scripts/buscar_datos.py` | Modify | Adds module-level `try import yaml`, defines `load_taxonomy(client_name)`, replaces the `TAXONOMIA` reference in `modo_semantic()` at line 261. Keeps `TAXONOMIA` constant as the fallback. |
| `scripts/bootstrap_taxonomy.py` | Create | One-shot CLI: reads the seed, writes `outputs/taxonomia_<client>_v1.yaml`. Run manually, not at runtime. |
| `LEEME.md` | Modify | Adds `pyyaml` to Requisitos Previos. (Spanish `LEEME.md` is the project README; English `README.md` does not exist at the project root.) |

**Bootstrap is an explicit CLI script** (`Option A`). Lazy bootstrap (`Option B`) is rejected because the spec REQ-002 phrases it as "When the seed bootstrap is performed (manual step or documented script invocation)" — explicit, one-shot, deterministic. `Option C` adds both paths without value.

## 2. YAML Schema

**Decision: Option L (nested dict of lists)** with `domain` and `description` metadata at the top level.

**Why Option L over Option S**: Option S (`CATEGORY > SUB: "tag1 | tag2"`) flattens to a format that mirrors the rendered string and would couple the YAML representation to a specific rendering style. Option L separates concerns: the YAML captures the *data model* (categories → subcategories → tags), and the renderer decides the textual form. This makes the data easier to inspect, diff, and migrate in Phase 3.

**YAML seed (`taxonomias_seed/medical_licenses.yaml`)** — full content, locked:

```yaml
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
    RECEPCION_ACTA:
      - REC_ACTA_NO_RECIBIDA
      - REC_ACTA_SOLICITAR_REENVIO
      - REC_ACTA_PROBLEMAS_ACCESO
    CORRECCION_ACTA:
      - CORR_ACTA_FECHAS_DIAS
      - CORR_ACTA_DATOS_PERSONALES
      - CORR_ACTA_ARTICULO_TIPO_LICENCIA
      - CORR_ACTA_CRITERIO_MEDICO
    REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA:
      - REQ_PROC_DOCUMENTACION_GENERAL
      - REQ_PROC_MODALIDAD_PRESENCIAL_ONLINE
      - REQ_PROC_LICENCIA_ESPECIFICA
      - REQ_PROC_ALTA_LABORAL
    PROBLEMAS_EN_GESTION:
      - PROB_GEST_LICENCIA_DENEGADA
      - PROB_GEST_SITUACION_IRREGULAR
      - PROB_GEST_ERROR_PLATAFORMA
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

**Schema invariants** (validated by `load_taxonomy` before rendering):
1. Top level MUST be a `dict` with key `categories` mapping to a `dict`.
2. Each category value MUST be a `dict` of subcategory keys.
3. Each subcategory value MUST be a non-empty `list` of non-empty strings.

**Generated output (`outputs/taxonomia_auto_wpp_v1.yaml`)** — **decision: byte-equivalent to the seed for v1**.

**Why not auto-enrich with `version` / `generated_at` / `client`**: REQ-002 explicitly says "byte-equivalent to the seed file for Phase 2 (no delta)". Auto-enrichment forces the bootstrap script to know a metadata schema, breaks diffability against the seed (the seed IS the canonical source), and is premature — Phase 3 versioning will define its own metadata envelope. Keeping v1 as a pure copy makes "did the bootstrap work?" trivially verifiable with `diff`.

```yaml
# This file is byte-equivalent to taxonomias_seed/medical_licenses.yaml at v1.
# Do not edit directly — edit the seed and re-run scripts/bootstrap_taxonomy.py.
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
    RECEPCION_ACTA:
      - REC_ACTA_NO_RECIBIDA
      - REC_ACTA_SOLICITAR_REENVIO
      - REC_ACTA_PROBLEMAS_ACCESO
    CORRECCION_ACTA:
      - CORR_ACTA_FECHAS_DIAS
      - CORR_ACTA_DATOS_PERSONALES
      - CORR_ACTA_ARTICULO_TIPO_LICENCIA
      - CORR_ACTA_CRITERIO_MEDICO
    REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA:
      - REQ_PROC_DOCUMENTACION_GENERAL
      - REQ_PROC_MODALIDAD_PRESENCIAL_ONLINE
      - REQ_PROC_LICENCIA_ESPECIFICA
      - REQ_PROC_ALTA_LABORAL
    PROBLEMAS_EN_GESTION:
      - PROB_GEST_LICENCIA_DENEGADA
      - PROB_GEST_SITUACION_IRREGULAR
      - PROB_GEST_ERROR_PLATAFORMA
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

## 3. `load_taxonomy(client_name)` Contract

**Signature** (locked):

```python
def load_taxonomy(client_name: str) -> str: ...
```

**Behavior** (locked, in order — first failure short-circuits to fallback):

1. **Sanitize**: `safe = re.sub(r"[^A-Za-z0-9_-]", "_", client_name)`.
2. **Check pyyaml**: use module-level flag `_HAS_YAML = (yaml is not None)` set at import time. If `False`, log `WARN: pyyaml not installed; using hardcoded TAXONOMIA fallback` to stderr (ONCE per process, guarded by `_yaml_warned`) and return `TAXONOMIA`.
3. **Build path**: `path = base_dir / 'outputs' / f'taxonomia_{safe}_v1.yaml'`. `base_dir` is the existing module-level variable.
4. **File check**: if `not path.exists()` or `path.stat().st_size == 0`, log `WARN: taxonomy file missing or empty at {path}; using hardcoded TAXONOMIA fallback` and return `TAXONOMIA`.
5. **Parse**: `data = yaml.safe_load(path.read_text(encoding='utf-8'))`. Catch `yaml.YAMLError` → log `WARN: failed to parse YAML at {path}: {exc}; using hardcoded TAXONOMIA fallback` and return `TAXONOMIA`. If `data` is `None` or not a `dict` → log `WARN: YAML at {path} did not yield a mapping; using hardcoded TAXONOMIA fallback` and return `TAXONOMIA`.
6. **Validate**: must contain key `categories` whose value is a `dict`. Any structural failure → log `WARN: taxonomy YAML at {path} has invalid structure (<reason>); using hardcoded TAXONOMIA fallback` and return `TAXONOMIA`.
7. **Render**: walk `data['categories']` per the algorithm in §4 and return the resulting string. Never raises.

The function is total: any path returns a `str` or raises only on programmer error (which we guard against).

## 4. Render Algorithm

Locked algorithm. The hardcoded `TAXONOMIA` constant at `scripts/buscar_datos.py:21-31` has **non-uniform formatting**: `LICENCIAS_MEDICAS` is hierarchical (category on its own line, subcategories indented 2 spaces), but `INFORMACION_AGENTE` and `CONSULTAS_VARIAS` are collapsed onto single lines (`CATEGORY: SUB | SUB`). The renderer must reproduce this exact asymmetry to satisfy REQ-004.

**Per-category decision rule** (deterministic, no special-cases in code):

- **Hierarchical form** — emit when a category has subcategories whose tag set is NOT just `[subcategory_name]`. The category name goes on its own line; each subcategory is rendered as `  SUB: TAG1 | TAG2 | ...` on the next line (2-space indent).
- **Collapsed form** — emit when **every** subcategory in a category has exactly one tag AND that tag's name equals the subcategory's name. The category line is `CATEGORY: SUB1 | SUB2 | ...` with no indent.

This rule fits both `LICENCIAS_MEDICAS` (hierarchical, subcats have multi-tag lists) and `INFORMACION_AGENTE` / `CONSULTAS_VARIAS` (collapsed, subcats are degenerate single-tag lists).

**Sketch** (illustrative, not the implementation):

```python
def _render_category(cat_name: str, subcats: dict) -> str:
    # Decide form
    collapsed = all(
        isinstance(tags, list) and len(tags) == 1 and tags[0] == sub_name
        for sub_name, tags in subcats.items()
    )
    if collapsed:
        return f"{cat_name}: {' | '.join(subcats.keys())}"
    # Hierarchical
    lines = [cat_name]
    for sub_name, tags in subcats.items():
        lines.append(f"  {sub_name}: {' | '.join(tags)}")
    return "\n".join(lines)

def _render(data: dict) -> str:
    parts = [_render_category(cat, subs) for cat, subs in data['categories'].items()]
    # Original literal has leading and trailing newline (triple-quoted string spans lines 21-31).
    return "\n" + "\n".join(parts) + "\n"
```

**Exact byte target** the renderer must produce (locked, copy of original `TAXONOMIA` literal):

```
\nLICENCIAS_MEDICAS\n  SOLICITUD_TURNO: SOL_TURNO_NUEVO | SOL_TURNO_REPROGRAMAR | SOL_TURNO_INFO_REQUISITOS\n  SEGUIMIENTO_Y_ESTADO: SEG_TURNO_MEDICO_NO_CONTACTA | SEG_ACTA_NO_GENERADA | SEG_DEMORA_GENERAL\n  RECEPCION_ACTA: REC_ACTA_NO_RECIBIDA | REC_ACTA_SOLICITAR_REENVIO | REC_ACTA_PROBLEMAS_ACCESO\n  CORRECCION_ACTA: CORR_ACTA_FECHAS_DIAS | CORR_ACTA_DATOS_PERSONALES | CORR_ACTA_ARTICULO_TIPO_LICENCIA | CORR_ACTA_CRITERIO_MEDICO\n  REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA: REQ_PROC_DOCUMENTACION_GENERAL | REQ_PROC_MODALIDAD_PRESENCIAL_ONLINE | REQ_PROC_LICENCIA_ESPECIFICA | REQ_PROC_ALTA_LABORAL\n  PROBLEMAS_EN_GESTION: PROB_GEST_LICENCIA_DENEGADA | PROB_GEST_SITUACION_IRREGULAR | PROB_GEST_ERROR_PLATAFORMA\nINFORMACION_AGENTE: INFO_AGENTE_ALTA_NUEVO_REGISTRO | INFO_AGENTE_ACTUALIZACION_DATOS\nCONSULTAS_VARIAS: CONS_VARIAS_GENERAL | CONS_VARIAS_QUEJA_RECLAMO | CONS_VARIAS_FUERA_DE_AMBITO\n
```

Verifier at §8 step 5 will compare `load_taxonomy("auto_wpp")` to this literal character-by-character.

## 5. Integration in `modo_semantic()`

**Diff at `scripts/buscar_datos.py` line 247-263** — the only behavior change inside the function:

```diff
 def modo_semantic(db_path, query, limit, classify):
     print(f"\n[INFO] Búsqueda SEMANTIC: '{query}' (límite contactos: {limit})")
     contactos = pre_filtrar_semantic(db_path, query, limit)
     ...
+    taxonomy_text = load_taxonomy(nombre_db) if classify else ""
     ...
     instrucciones_extra = ""
     if classify:
         instrucciones_extra = (
             "Además, clasifica cada coincidencia encontrada según la siguiente taxonomía del dominio "
             "(Reconocimientos Médicos - licencias para empleados públicos):\n\n"
-            f"{TAXONOMIA}\n"
+            f"{taxonomy_text}\n"
             "Indica la ruta taxonómica exacta (ej. LICENCIAS_MEDICAS > RECEPCION_ACTA > REC_ACTA_NO_RECIBIDA).\n"
         )
```

**Notes**:
- The call is hoisted **above** the `if classify:` block and guarded by `if classify else ""` so we don't read the file when classification is disabled (REQ-005 scenario: classify=False → no taxonomy in prompt, no file I/O).
- `nombre_db` is sourced from `seleccionar_db(args.db)` in `main()`; for Phase 2 this is always `"auto_wpp"`.
- Module-level import at the top of `buscar_datos.py`:

```python
try:
    import yaml
except ImportError:
    yaml = None
_HAS_YAML = yaml is not None
_yaml_warned = False
```

The `TAXONOMIA` constant stays in place — it is now the fallback, not the primary source.

## 6. Bootstrap Mechanism

**Decision: Option A — standalone CLI `scripts/bootstrap_taxonomy.py`**, run once by the developer.

**Why not Option B (lazy bootstrap)**: adds a write-path inside `load_taxonomy`, which is read-only by contract. Mixing read and write complicates error handling (what if the directory doesn't exist? what if write permission is denied during a search call?). Spec REQ-002 treats bootstrap as an explicit, manual step.

**Why not Option C (both)**: doubles the code surface for no Phase 2 benefit. Phase 3 will revisit the bootstrap strategy when multi-client support arrives.

**CLI sketch** (illustrative, not the implementation):

```python
# scripts/bootstrap_taxonomy.py
"""Read taxonomias_seed/medical_licenses.yaml and write outputs/taxonomia_<client>_v1.yaml.

Usage:
    python scripts/bootstrap_taxonomy.py
    python scripts/bootstrap_taxonomy.py --seed taxonomias_seed/medical_licenses.yaml --client auto_wpp
"""
```

- Default args: `--seed taxonomias_seed/medical_licenses.yaml`, `--client auto_wpp`.
- Reads the seed with `yaml.safe_load`, validates it has a `categories` key, writes the file to `outputs/taxonomia_<sanitized>_v1.yaml`.
- Exits non-zero on any failure (missing seed, invalid YAML, write error) with a stderr message.
- Does **not** modify `TAXONOMIA` or call `load_taxonomy`. Pure file copy semantics for v1.

## 7. Error Handling & Observability

**Stderr warning format** (locked, grep-able, single-line):

```
WARN: taxonomy-loader: <human-readable cause>; using hardcoded TAXONOMIA fallback
```

Prefix `WARN:` (uppercase, colon) + `taxonomy-loader:` namespace + cause + fallback clause. Examples:

```
WARN: taxonomy-loader: pyyaml not installed; using hardcoded TAXONOMIA fallback
WARN: taxonomy-loader: file missing at outputs/taxonomia_auto_wpp_v1.yaml; using hardcoded TAXONOMIA fallback
WARN: taxonomy-loader: file empty at outputs/taxonomia_auto_wpp_v1.yaml; using hardcoded TAXONOMIA fallback
WARN: taxonomy-loader: yaml parse error at outputs/taxonomia_auto_wpp_v1.yaml (<yaml_error.msg>); using hardcoded TAXONOMIA fallback
WARN: taxonomy-loader: invalid structure at outputs/taxonomia_auto_wpp_v1.yaml (missing 'categories' key); using hardcoded TAXONOMIA fallback
```

**Invariants**:
- `load_taxonomy` never raises to its caller.
- The pyyaml-missing warning is logged at most once per process (guarded by `_yaml_warned`).
- All other warnings are logged per-call (file may appear/disappear between calls).
- Success path (file present, valid, rendered) is **silent** — no log. Phase 3 may add a `--verbose` flag.

## 8. Testing Strategy

No test framework exists. All verification is manual. Steps for `sdd-apply` and `sdd-verify`:

| # | Step | Expected |
|---|------|----------|
| 1 | `python scripts/buscar_datos.py --db auto_wpp --mode semantic --query "turno médico" --classify --limit 10` | LLM prompt is sent; output is produced; **no** `WARN: taxonomy-loader:` line in stderr. |
| 2 | `python scripts/bootstrap_taxonomy.py` | Exits 0; `outputs/taxonomia_auto_wpp_v1.yaml` exists. |
| 3 | `diff taxonomias_seed/medical_licenses.yaml outputs/taxonomia_auto_wpp_v1.yaml` | No diff (byte-equivalent per REQ-002). |
| 4 | REPL byte-equivalence check: `assert load_taxonomy("auto_wpp") == TAXONOMIA` | No exception. |
| 5 | Indentation/separator check (optional): regex-match `load_taxonomy("auto_wpp")` for `^  [A-Z_]+: ` and ` \\| ` substrings | All present. |
| 6 | Delete `outputs/taxonomia_auto_wpp_v1.yaml`, re-run step 1 | `WARN: taxonomy-loader: file missing at outputs/taxonomia_auto_wpp_v1.yaml; ...` on stderr; output still produced (fallback active). |
| 7 | Restore the file, then write `not: valid: yaml` into it, re-run step 1 | `WARN: taxonomy-loader: yaml parse error ...` on stderr; output still produced. |
| 8 | Truncate the file to 0 bytes (`> outputs/taxonomia_auto_wpp_v1.yaml`), re-run step 1 | `WARN: taxonomy-loader: file empty ...` on stderr; output still produced. |
| 9 | `pip uninstall -y pyyaml`, re-run step 1 | `WARN: taxonomy-loader: pyyaml not installed ...` on stderr; output still produced. |
| 10 | In REPL: `load_taxonomy("auto wpp test!")` | No exception; `WARN: taxonomy-loader: file missing at outputs/taxonomia_auto_wpp_test__v1.yaml; ...` (REQ-007 sanitization: space and `!` both replaced with `_`). |

## 9. Documentation Updates

The project has no English `README.md` at the root — the user-facing README is **`LEEME.md`** (Spanish, "read me"). REQ-006 says "README.md or equivalent installation/setup document", so `LEEME.md` is the equivalent.

**Addition to `LEEME.md`** under `Requisitos Previos` (after the existing numbered list, item 3):

```markdown
3.  Una clave de API de **Google Gemini** o compatible (MiniMax, OpenAI).
4.  Dependencia adicional para taxonomía: `pip install pyyaml`. Si no está instalada,
    `buscar_datos.py --classify` sigue funcionando pero usa la taxonomía hardcodeada
    de respaldo y emite un aviso por stderr.
```

**Addition to `taxonomias_seed/README.md`** is **not** required — that README documents future seed files by industry, and `medical_licenses.yaml` is a new entry that fits the existing `salud.yaml` pattern (the existing README mentions `salud.yaml` as a future filename; `medical_licenses.yaml` is the actual name locked by the proposal, an inconsistency that sdd-tasks may resolve).

## 10. Out of Scope (recap from spec)

Locked out per spec:

- **Versioning**: no v2/v3/rollback. The `_v1` suffix is a label only.
- **Multi-taxonomy**: no per-business-line or per-domain taxonomy switching.
- **Seed generation from `perfil_cliente_*.json`**: seed is hand-authored.
- **`taxonomy_corrections` table**: no DB feedback loop.
- **`analizar_contexto.py` changes**: not modified.
- **LLM prompt content**: unchanged except the source of the taxonomy string.

---

## Surprises / Spec-vs-code findings

1. **Non-uniform formatting in the original `TAXONOMIA` literal**: `LICENCIAS_MEDICAS` is hierarchical (6 indented subcategory lines); `INFORMACION_AGENTE` and `CONSULTAS_VARIAS` are collapsed (`CATEGORY: SUB1 | SUB2`). The spec assumes a single format and the proposal's example schema didn't flag this. The render algorithm (§4) reproduces the exact asymmetry via a deterministic per-category decision rule — no special-cases in code.

2. **The original `TAXONOMIA` literal starts and ends with `\n`** because it is a triple-quoted string spanning lines 21-31. The render algorithm must wrap the joined parts with `\n` on both sides to match byte-for-byte (REQ-004). This is easy to miss.

3. **The current `modo_semantic()` call site has `classify = args.classify or True`** (line 322), which means `classify` is **always truthy** regardless of the flag. The REQ-005 scenario "modo_semantic uses load_taxonomy with classify=False" therefore cannot be observed via the current CLI. The design still hoists `load_taxonomy` behind a `classify` guard to keep the contract clean, but a verifier should note this latent bug — it lives outside the scope of Phase 2.

4. **No `requirements.txt` exists**. The proposal mentions adding one, but the project uses a `.env`-only config and no `pip install -r` workflow. Documenting `pip install pyyaml` in `LEEME.md` is the correct alternative. sdd-tasks should not invent a `requirements.txt`.