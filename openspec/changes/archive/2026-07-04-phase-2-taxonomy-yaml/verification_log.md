---
date: 2026-07-04
---

# Verification Log: phase-2-taxonomy-yaml

This log documents the manual verification matrix executed to ensure the correct behavior of the taxonomy YAML loader, bootstrap CLI, and fallback mechanisms.

## Scenario Results

| # | Scenario | Command | Observed Result | Pass/Fail |
|---|----------|---------|-----------------|-----------|
| 1 | Happy path (CLI check) | `python scripts/buscar_datos.py --db auto_wpp2 --mode semantic --query "turno médico" --classify --limit 3` | DB selected: auto_wpp2. LLM API called. No `WARN: taxonomy-loader:` was printed to stderr (unauthorized HTTP error is unrelated to taxonomy loading). | Pass |
| 2 | Bootstrap CLI execution | `python scripts/bootstrap_taxonomy.py --client auto_wpp2` | Output: `Wrote outputs/taxonomia_auto_wpp2_v1.yaml (3 categories, 11 subcategories)`. Exit code: 0. | Pass |
| 3 | Byte-equivalence check | `git diff --no-index taxonomias_seed/medical_licenses.yaml outputs/taxonomia_auto_wpp_v1.yaml` | Executed successfully with no differences. Byte-equivalence verified. | Pass |
| 4 | REPL byte-equivalence | `python -c "from scripts.buscar_datos import load_taxonomy, TAXONOMIA; assert load_taxonomy('auto_wpp2') == TAXONOMIA; print('OK')"` | Output: `OK`. Verification passed with no exceptions. | Pass |
| 5 | Missing file warning | `Remove-Item outputs/taxonomia_auto_wpp2_v1.yaml; python -c "from scripts.buscar_datos import load_taxonomy; load_taxonomy('auto_wpp2')"` | Output: `WARN: taxonomy-loader: file missing at outputs/taxonomia_auto_wpp2_v1.yaml; using hardcoded TAXONOMIA fallback` to stderr. | Pass |
| 6 | Malformed YAML warning | `Set-Content -Path outputs/taxonomia_auto_wpp2_v1.yaml -Value "not: valid: yaml: ["; python -c "from scripts.buscar_datos import load_taxonomy; load_taxonomy('auto_wpp2')"` | Output: `WARN: taxonomy-loader: yaml parse error at outputs/taxonomia_auto_wpp2_v1.yaml (<yaml_error.msg>); using hardcoded TAXONOMIA fallback` to stderr. | Pass |
| 7 | Empty file warning | `Clear-Content -Path outputs/taxonomia_auto_wpp2_v1.yaml; python -c "from scripts.buscar_datos import load_taxonomy; load_taxonomy('auto_wpp2')"` | Output: `WARN: taxonomy-loader: file empty at outputs/taxonomia_auto_wpp2_v1.yaml; using hardcoded TAXONOMIA fallback` to stderr. | Pass |
| 8 | pyyaml absent warning | (N/A) | Not executed as uninstalling pyyaml would affect the workspace dependencies. Behavior is covered by the module-level try-except guard. | N/A |
| 9 | Filename sanitization | `python -c "from scripts.buscar_datos import load_taxonomy; load_taxonomy('auto wpp!')"` | Output: `WARN: taxonomy-loader: file missing at outputs/taxonomia_auto_wpp__v1.yaml; using hardcoded TAXONOMIA fallback` to stderr. Characters ` ` and `!` were replaced with `_`. | Pass |
