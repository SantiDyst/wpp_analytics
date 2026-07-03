# SDD Spec: taxonomy-yaml

## Purpose

Phase 2 extracts the hardcoded taxonomy string from `scripts/buscar_datos.py` into an external YAML file, enabling manual taxonomy edits without code changes. The `load_taxonomy(client_name)` function loads the client-specific YAML at runtime with a hardcoded fallback to preserve existing behavior. The LLM prompt contract is unchanged.

---

## Requirement: YAML Seed File Exists

**REQ-001**

The repository SHALL contain `taxonomias_seed/medical_licenses.yaml` encoding the full 3-level taxonomy currently hardcoded in `scripts/buscar_datos.py` lines 21–31. The file SHALL be valid YAML and SHALL contain every category, subcategory, and tag present in the hardcoded `TAXONOMIA` string.

---

## Requirement: Per-Client Taxonomy Output Exists

**REQ-002**

When the seed bootstrap is performed (manual step or documented script invocation), the system SHALL produce `outputs/taxonomia_<client>_v1.yaml` where `<client>` is the value returned by `seleccionar_db()` (currently `auto_wpp`). The output file SHALL be byte-equivalent to the seed file for Phase 2 (no delta).

---

## Requirement: load_taxonomy(client_name) Function

**REQ-003**

`scripts/buscar_datos.py` SHALL expose a `load_taxonomy(client_name)` function with the following behavior:

- The function SHALL construct the path `outputs/taxonomia_<sanitized_client>_v1.yaml` where `<sanitized_client>` is the sanitized client name.
- If the file exists, is non-empty, is valid YAML, and `pyyaml` is importable, the function SHALL load and return the taxonomy.
- If the file is missing, empty, malformed YAML, or `pyyaml` is unavailable, the function SHALL fall back to the hardcoded `TAXONOMIA` string and log a warning to stderr.
- The function SHALL return a string.

---

## Requirement: Prompt Format Preserved

**REQ-004**

When `load_taxonomy()` returns from a successful YAML load, the returned string SHALL be byte-equivalent (after normalization) to the original hardcoded `TAXONOMIA` value with respect to:
1. Same category headings (e.g., `LICENCIAS_MEDICAS`, `INFORMACION_AGENTE`, `CONSULTAS_VARIAS`)
2. Same subcategory headings (e.g., `SOLICITUD_TURNO`, `SEGUIMIENTO_Y_ESTADO`)
3. Same tag names (e.g., `SOL_TURNO_NUEVO`, `SOL_TURNO_REPROGRAMAR`)
4. Same ` | ` separator between sibling tags within a subcategory
5. Same indentation structure (2-space indent for subcategory lines under category, 2-space indent for tag lists)

---

## Requirement: Integration in modo_semantic()

**REQ-005**

The `modo_semantic()` function in `scripts/buscar_datos.py` SHALL call `load_taxonomy(nombre_db)` when building the LLM prompt (specifically when `classify=True`), replacing the direct reference to the `TAXONOMIA` constant. The result SHALL be injected at the same position in the prompt string with no change to surrounding prompt text.

---

## Requirement: pyyaml Documented as Required

**REQ-006**

The project documentation (README.md or equivalent installation/setup document) SHALL list `pyyaml` as a required dependency for Phase 2 and beyond, with the install command `pip install pyyaml`. Installation without `pyyaml` SHALL not break the script, but the YAML loading path will not activate and a runtime warning SHALL be logged.

---

## Requirement: Filename Sanitization

**REQ-007**

If `<client>` contains any character not in the set `[A-Za-z0-9_-]`, `load_taxonomy()` SHALL replace each such character with a single underscore (`_`) before constructing the file path. The sanitization SHALL be applied consistently on every call.

---

## Scenarios

#### Scenario: YAML loads successfully

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` exists, is non-empty, and contains valid YAML matching the seed schema
- **WHEN** `load_taxonomy("auto_wpp")` is called
- **THEN** the function returns a string formatted identically to the original hardcoded `TAXONOMIA` value
- **AND** no warning is logged to stderr

#### Scenario: YAML file is missing

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` does not exist
- **WHEN** `load_taxonomy("auto_wpp")` is called
- **THEN** the function returns the hardcoded `TAXONOMIA` string
- **AND** a warning is logged to stderr indicating the file was not found and fallback was used

#### Scenario: YAML file is malformed

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` exists but contains invalid YAML syntax
- **WHEN** `load_taxonomy("auto_wpp")` is called
- **THEN** the function returns the hardcoded `TAXONOMIA` string
- **AND** a warning is logged to stderr indicating YAML parsing failed and fallback was used

#### Scenario: pyyaml is not installed

- **GIVEN** `pyyaml` cannot be imported
- **WHEN** `load_taxonomy("auto_wpp")` is called
- **THEN** the function returns the hardcoded `TAXONOMIA` string
- **AND** a warning is logged to stderr indicating pyyaml is unavailable and fallback was used

#### Scenario: Client name contains invalid filename characters

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` exists and is valid
- **WHEN** `load_taxonomy("auto_wpp test")` is called (client name contains a space)
- **THEN** the function sanitizes the name to `auto_wpp_test` before constructing the path
- **AND** the function returns the taxonomy string from `outputs/taxonomia_auto_wpp_test_v1.yaml`

#### Scenario: modo_semantic uses load_taxonomy with classify=True

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` exists and is valid
- **WHEN** `modo_semantic(db_path, "consulta", 10, classify=True)` is called
- **THEN** the LLM prompt contains the taxonomy string returned by `load_taxonomy("auto_wpp")` at the same position where `TAXONOMIA` was previously injected
- **AND** the prompt format is unchanged except that the taxonomy source is now the loaded YAML

#### Scenario: modo_semantic uses load_taxonomy with classify=False

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` exists and is valid
- **WHEN** `modo_semantic(db_path, "consulta", 10, classify=False)` is called
- **THEN** the LLM prompt contains no taxonomy string
- **AND** the behavior is identical to the original implementation

#### Scenario: YAML file is empty

- **GIVEN** `outputs/taxonomia_auto_wpp_v1.yaml` exists but is empty (zero bytes)
- **WHEN** `load_taxonomy("auto_wpp")` is called
- **THEN** the function returns the hardcoded `TAXONOMIA` string
- **AND** a warning is logged to stderr indicating the file was empty and fallback was used

---

## Constraints / Non-Goals

Phase 2 is explicitly bounded. The following are **out of scope** and MUST NOT be implemented in this phase:

- **Versioning**: No v2, v3, or rollback of taxonomy versions. The `v1` suffix on output filenames is a label only.
- **Multi-taxonomy**: No support for multiple taxonomy files per client or per business line.
- **Seed generation from `perfil_cliente_*.json`**: No automated seed creation from contact profiling data.
- **`taxonomy_corrections` table**: No database table for tracking user-corrected taxonomy assignments.
- **Changes to `analizar_contexto.py`**: That script is not modified by this phase.
- **Changes to the LLM prompt content**: The taxonomy string injected into the prompt is unchanged; only its source changes.

---

## Verification

The implementer (`sdd-apply`) and verifier (`sdd-verify`) SHALL prove each requirement is met through the following manual steps. No automated test runner exists; all verification is manual.

### REQ-001 — YAML seed file exists

1. Open `taxonomias_seed/medical_licenses.yaml` in a text editor.
2. Confirm it is valid YAML.
3. Confirm it contains all three top-level categories: `LICENCIAS_MEDICAS`, `INFORMACION_AGENTE`, `CONSULTAS_VARIAS`.
4. Confirm every subcategory and tag from the hardcoded `TAXONOMIA` (lines 21–31 of `buscar_datos.py`) is present.

### REQ-002 — Per-client taxonomy output

1. Confirm `outputs/taxonomia_auto_wpp_v1.yaml` exists.
2. Confirm it is byte-equivalent to the seed file for Phase 2.

### REQ-003 — load_taxonomy function

1. Open a Python REPL in the project root.
2. Import `load_taxonomy` from `scripts.buscar_datos`.
3. Call `load_taxonomy("auto_wpp")` with the output file present and valid — confirm it returns a string and logs no warning.
4. Rename `outputs/taxonomia_auto_wpp_v1.yaml` to a temporary name.
5. Call `load_taxonomy("auto_wpp")` again — confirm it returns the hardcoded string and logs a warning to stderr.
6. Restore the file.
7. Corrupt the file by writing `not: valid: yaml` — call `load_taxonomy("auto_wpp")` — confirm fallback and warning.

### REQ-004 — Prompt format preserved

1. In the Python REPL, compare the string returned by `load_taxonomy("auto_wpp")` (with valid YAML) to the hardcoded `TAXONOMIA` constant.
2. Confirm category headings, subcategory headings, tag names, ` | ` separators, and indentation all match.

### REQ-005 — modo_semantic integration

1. Run `python scripts/buscar_datos.py --help` and confirm the script accepts `--mode semantic --classify --query "..."`.
2. Run the script against the real database with `--mode semantic --classify --query "turno médico"` (or any query that triggers classification).
3. Confirm the output is produced and the LLM prompt is sent without error (inspect logs for any taxonomy-related warning).

### REQ-006 — pyyaml documented

1. Open README.md (or equivalent).
2. Confirm `pyyaml` is listed as a required dependency with `pip install pyyaml`.

### REQ-007 — Filename sanitization

1. In the Python REPL, call `load_taxonomy("auto_wpp test!@#")`.
2. Confirm the function does not raise an exception.
3. Confirm the warning indicates fallback (since `outputs/taxonomia_auto_wpp_test___v1.yaml` will not exist).

---

## File Layout

```
openspec/changes/phase-2-taxonomy-yaml/
├── exploration.md
├── proposal.md
├── tasks.md
└── specs/
    └── taxonomy-yaml/
        └── spec.md          ← this file
```
