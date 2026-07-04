# SDD Tasks: phase-2-taxonomy-yaml

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150–200 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | N/A |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: N/A
400-line budget risk: Low

## Tasks Checklist

- [x] **T-001** — Create seed YAML file (`taxonomias_seed/medical_licenses.yaml`)
- [x] **T-002** — Document pyyaml dependency in `LEEME.md`
- [x] **T-003** — Implement `load_taxonomy(client_name)` function with fallback paths
- [x] **T-004** — Wire `load_taxonomy()` into `modo_semantic()`
- [x] **T-005** — Implement `bootstrap_taxonomy.py` CLI
- [x] **T-006** — Run bootstrap to materialize per-client taxonomy
- [x] **T-007** — Execute manual verification matrix
- [x] **T-008** — Final review and cleanup (diff footprint, TAXONOMIA refs, gitignore note)

### Suggested Work Units

| Unit | Goal | PR | Notes |
|------|------|----|-------|
| 1 | Seed YAML + LEEME.md doc | PR 1 | Foundation; can be reviewed independently |
| 2 | load_taxonomy() + modo_semantic integration | PR 1 | Core implementation; same commit |
| 3 | bootstrap_taxonomy.py CLI | PR 1 | Bootstrap tool; same commit |
| 4 | Generated output + verification log | PR 1 | Artifacts + test evidence; same commit |

Rollback: revert commits in reverse order. The hardcoded `TAXONOMIA` constant is the safety net.

---

## Phase 1: Foundation

### T-001 — Create seed YAML file

**Create `taxonomias_seed/medical_licenses.yaml`** encoding the full 3-level taxonomy from `scripts/buscar_datos.py` lines 21–31 using the schema locked in `design.md` §2 (Option L: nested dict of lists with `domain` and `description` at top level). The file must contain all 3 categories, all 9 subcategories, and all tags from the hardcoded `TAXONOMIA` constant.

**File:** `taxonomias_seed/medical_licenses.yaml` (new)
**REQ:** REQ-001
**Verification:**
```powershell
python -c "import yaml; data=yaml.safe_load(open('taxonomias_seed/medical_licenses.yaml')); print(data['categories']['LICENCIAS_MEDICAS']['SOLICITUD_TURNO'])"
```
Expected: `['SOL_TURNO_NUEVO', 'SOL_TURNO_REPROGRAMAR', 'SOL_TURNO_INFO_REQUISITOS']`
**Dependency:** — (T-001 starts)
**Effort:** Small

---

### T-002 — Document pyyaml dependency in LEEME.md

**Add `pip install pyyaml` to the "Requisitos Previos" section** of `LEEME.md`, inserting after the existing item 3 (API key). Use the wording from `design.md` §9: a brief Spanish note that the dependency enables taxonomy loading but the script works without it via fallback.

**File:** `LEEME.md` (modified)
**REQ:** REQ-006
**Verification:** Read `LEEME.md` and confirm a line matching `pip install pyyaml` appears under Requisitos Previos.
**Dependency:** T-001
**Effort:** Small

---

## Phase 2: Core Implementation

### T-003 — Implement `load_taxonomy(client_name)` function

**Add to `scripts/buscar_datos.py`** near the top (after `TAXONOMIA` constant):

1. **Module-level pyyaml guard** (after line 10 imports):
   ```python
   try:
       import yaml
   except ImportError:
       yaml = None
   _HAS_YAML = yaml is not None
   _yaml_warned = False
   ```

2. **`load_taxonomy(client_name: str) -> str`** function implementing the locked contract from `design.md` §3:
   - Step 1 — Sanitize: `safe = re.sub(r"[^A-Za-z0-9_-]", "_", client_name)` (REQ-007).
   - Step 2 — Check pyyaml: if `_HAS_YAML` is False, log `WARN: taxonomy-loader: pyyaml not installed; using hardcoded TAXONOMIA fallback` to stderr (once per process via `_yaml_warned` guard) and return `TAXONOMIA`.
   - Step 3 — Build path: `path = base_dir / 'outputs' / f'taxonomia_{safe}_v1.yaml'`.
   - Step 4 — File check: if `not path.exists()` or `path.stat().st_size == 0`, log `WARN: taxonomy-loader: file missing at {path}; using hardcoded TAXONOMIA fallback` and return `TAXONOMIA`.
   - Step 5 — Parse: `yaml.safe_load(path.read_text(encoding='utf-8'))`. Catch `yaml.YAMLError` → warn + fallback. If result is None or not a dict → warn + fallback.
   - Step 6 — Validate: must contain key `categories` whose value is a dict. Otherwise warn + fallback.
   - Step 7 — Render: walk `data['categories']` using the per-category decision rule from `design.md` §4. Return the result wrapped with leading+trailing `\n` for byte-equivalence with `TAXONOMIA`.

3. **Render algorithm** (`design.md` §4): per-category decision rule — collapsed form when every subcategory has exactly one tag that equals the subcategory name; hierarchical form otherwise.

**Files:** `scripts/buscar_datos.py` (modified)
**REQ:** REQ-003, REQ-004, REQ-007
**Verification:**
```powershell
python -c "import sys; sys.path.insert(0,'scripts'); from buscar_datos import load_taxonomy, TAXONOMIA; result = load_taxonomy('auto_wpp'); print('Match:', result == TAXONOMIA); print('Has newlines:', result.startswith(chr(10)) and result.endswith(chr(10)))"
```
Expected: `Match: True`, `Has newlines: True`
**Dependency:** T-001 (seed file not required for T-003 itself, but T-005 generates the file T-003 reads)
**Effort:** Medium

---

### T-004 — Wire `load_taxonomy()` into `modo_semantic()`

**Modify `modo_semantic()` in `scripts/buscar_datos.py`** at lines 256–263:

```python
taxonomy_text = load_taxonomy(nombre_db) if classify else ""
# ...
if classify:
    instrucciones_extra = (
        "Además, clasifica cada coincidencia encontrada según la siguiente taxonomía del dominio "
        "(Reconocimientos Médicos - licencias para empleados públicos):\n\n"
        f"{taxonomy_text}\n"
        "Indica la ruta taxonómica exacta (ej. LICENCIAS_MEDICAS > RECEPCION_ACTA > REC_ACTA_NO_RECIBIDA).\n"
    )
```

The call is hoisted above the `if classify:` block and guarded by `if classify else ""` so no file I/O occurs when `classify=False`. The `nombre_db` variable is in scope from `main()`.

**Files:** `scripts/buscar_datos.py` (modified)
**REQ:** REQ-005
**Verification:**
```powershell
python scripts/buscar_datos.py --db auto_wpp --mode semantic --query "turno médico" --classify --limit 3 2>&1 | Select-String "WARN"
```
Expected: No `WARN: taxonomy-loader:` lines in stderr when the taxonomy file is present.
**Dependency:** T-003
**Effort:** Small

---

## Phase 3: Bootstrap

### T-005 — Implement `bootstrap_taxonomy.py` CLI

**Create `scripts/bootstrap_taxonomy.py`** as a standalone one-shot CLI:

- argparse: `--seed` (default `taxonomias_seed/medical_licenses.yaml`), `--client` (default `auto_wpp`), `--output-dir` (default `outputs/`).
- Load the seed with `yaml.safe_load`, validate `categories` key exists.
- Sanitize client name the same way `load_taxonomy` does (REQ-007).
- Write `outputs/taxonomia_<sanitized_client>_v1.yaml` (byte-equivalent to seed for v1 — no metadata enrichment).
- Create `outputs/` directory if it doesn't exist.
- Print summary line to stdout on success: `Wrote outputs/taxonomia_<client>_v1.yaml (N categories, M subcategories)`.
- Exit non-zero on any error with a stderr message.

**Files:** `scripts/bootstrap_taxonomy.py` (new)
**REQ:** REQ-002
**Verification:**
```powershell
python scripts/bootstrap_taxonomy.py
if ($?) { echo "Exit code: $LASTEXITCODE"; Test-Path "outputs/taxonomia_auto_wpp_v1.yaml" }
```
Expected: Exit code 0, `True`.
```powershell
python -c "import yaml; yaml.safe_load(open('outputs/taxonomia_auto_wpp_v1.yaml'))" 2>$null; if ($LASTEXITCODE -eq 0) { echo "Valid YAML" }
```
Expected: `Valid YAML`
**Dependency:** T-001, T-003
**Effort:** Small

---

### T-006 — Run bootstrap to materialize per-client taxonomy

**Run `python scripts/bootstrap_taxonomy.py`** to produce `outputs/taxonomia_auto_wpp_v1.yaml`. No code changes — just the execution step.

**Files:** `outputs/taxonomia_auto_wpp_v1.yaml` (generated, new)
**REQ:** REQ-002
**Verification:**
```powershell
$diff = Compare-Object -Path "taxonomias_seed/medical_licenses.yaml" -Path "outputs/taxonomia_auto_wpp_v1.yaml"
if ($diff -eq $null) { echo "Files are identical" } else { echo "DIFF: $diff" }
```
Expected: `Files are identical`
**Dependency:** T-005
**Effort:** Small

---

## Phase 4: Verification

### T-007 — Manual verification matrix

**Execute each scenario from `design.md` §8** and document results in `openspec/changes/phase-2-taxonomy-yaml/verification_log.md`:

| Step | Scenario | Command | Expected |
|------|----------|---------|----------|
| 1 | Happy path | `python scripts/buscar_datos.py --db auto_wpp --mode semantic --query "turno médico" --classify --limit 3` | Output produced; no `WARN: taxonomy-loader:` in stderr |
| 2 | Bootstrap | `python scripts/bootstrap_taxonomy.py` | Exit 0; file exists |
| 3 | Byte-equivalence | `diff taxonomias_seed/medical_licenses.yaml outputs/taxonomia_auto_wpp_v1.yaml` | No diff |
| 4 | REPL check | `python -c "from scripts.buscar_datos import load_taxonomy, TAXONOMIA; assert load_taxonomy('auto_wpp') == TAXONOMIA; print('OK')"` | `OK` printed |
| 5 | Missing file | `Remove-Item outputs/taxonomia_auto_wpp_v1.yaml`; re-run step 1 | `WARN: taxonomy-loader: file missing ...` in stderr; output still produced |
| 6 | Malformed YAML | Write `not: valid: yaml` to `outputs/taxonomia_auto_wpp_v1.yaml``; re-run step 1 | `WARN: taxonomy-loader: yaml parse error ...` in stderr |
| 7 | Empty file | `Set-Content outputs/taxonomia_auto_wpp_v1.yaml -NoNewline`; re-run step 1 | `WARN: taxonomy-loader: file empty ...` in stderr |
| 8 | pyyaml absent | (skip — would require uninstall; note in log) | — |
| 9 | Filename sanitization | `python -c "from scripts.buscar_datos import load_taxonomy; print(load_taxonomy('auto wpp!'))"` | No exception; `WARN: taxonomy-loader: file missing at outputs/taxonomia_auto_wpp__v1.yaml ...` |

Create `verification_log.md` at `openspec/changes/phase-2-taxonomy-yaml/verification_log.md` with a table of command + observed output for each step.

**Files:** `openspec/changes/phase-2-taxonomy-yaml/verification_log.md` (new, not committed)
**REQ:** REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-007
**Verification:** `verification_log.md` exists with at least 5 of 9 steps documented.
**Dependency:** T-001 through T-006
**Effort:** Small

---

### T-008 — Final review and cleanup

**Perform the following checks:**

1. Confirm no stray `TAXONOMIA` references remain in `modo_semantic()` body (lines 247–299). The only references should be: (a) the constant declaration at line 21, and (b) the fallback inside `load_taxonomy()`.

2. Confirm `TAXONOMIA` constant is still present at lines 21–31 (it is the fallback).

3. Run `git diff --stat` to see the changed-line footprint.

4. Confirm `verification_log.md` is in `.gitignore` or noted as uncommitted (it lives in the change directory, not in the project root).

**Files:** all modified files
**REQ:** All (consistency check)
**Verification:**
```powershell
git diff --stat
git diff scripts/buscar_datos.py | Select-String "TAXONOMIA"
```
Expected: Diff touches only the expected files. `TAXONOMIA` appears only in the declaration, the `load_taxonomy` fallback, and the f-string is replaced with `taxonomy_text`.
**Dependency:** T-001 through T-007
**Effort:** Small

---

## Dependency Graph

```
T-001 ─┬─> T-002
       ├─> T-003 ─> T-004
       └─> T-005 ─> T-006
             └────────────────> T-007 ─> T-008
```

DAG: T-001 (no deps) → T-002, T-003, T-005 all depend on T-001 → T-004 depends on T-003 → T-006 depends on T-005 → T-007 depends on all → T-008 depends on all.
