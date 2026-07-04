# Tasks: phase-1-context-analyzer

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~220–270 (additions only; existing 559-line file untouched in behavior) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | not applicable |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: not applicable
400-line budget risk: Low

---

## Suggested Work Units

| Unit | Goal | Notes |
|------|------|-------|
| 1 | All changes to `scripts/analizar_contexto.py` | Single PR; argparse + helpers + wiring; smoke tests included |

---

## Phase 1: Foundation — Argparse + UTF-8 + Interactive Menu Preservation

- [x] **T-001.1** — Add `argparse`, `statistics`, `sys` imports to `scripts/analizar_contexto.py` (near existing imports at top of file).
- [x] **T-001.2** — Add `sys.stdout.reconfigure(encoding='utf-8')` early in module (following `buscar_datos.py:21-24` pattern) to handle Windows console encoding for JSON output.
- [x] **T-001.3** — Add `parse_args()` function: `--with-metrics` (store_true), `--db` (str, default None), `--sample-size` (float, default 0.30), `--output-dir` (Path, default outputs/); mirror `buscar_datos.py` CLI style.
- [x] **T-001.4** — Wrap `main()` with `if __name__ == '__main__':` block; add `len(sys.argv) == 1` early-return guard that skips argparse and proceeds directly to existing interactive menu (preserves current behavior for zero-arg invocation).
- [x] **T-001.5** — Add `# SPEC-EXAMPLE` inline comments in the module (before each new helper) documenting the 3 worked scenarios from the design doc allocation trace: "300 contacts Low=150/Mid=90/High=60 → 45/27/18", "100 contacts Low=90/Mid=8/High=2 → 27/2/1", "10 contacts Low=3/Mid=3/High=4 → 1/1/1".

---

## Phase 2: Core Helpers — Thresholds, Tier Assignment, Stratified Sampling

- [x] **T-002.1** — Implement `compute_tier_thresholds(counts: dict[str, int]) -> tuple[float, float]`: run `statistics.quantiles(list(counts.values()) or [0], n=3, method="inclusive")`, return `(p33, p66)`. Add degenerate-input fallback (`or [0]`).
- [x] **T-002.2** — Implement `assign_tier(n: int, p33: float, p66: float) -> str`: `n < p33 → "low"`, `n <= p66 → "mid"`, else `"high"`. Verify P33-boundary contacts route to mid (per spec scenario).
- [x] **T-002.3** — Implement `stratified_sample(tiers: dict[str, list[str]], budget_ratio: float) -> list[str]`: strict-budget allocation with min-1-per-non-empty-tier and proportional extras, plus trim step that takes from largest tier first without dropping any tier below 1. Include the 3 `# SPEC-EXAMPLE` allocation traces as inline comments (design doc lines 137–156).

---

## Phase 3: Metrics Pass

- [x] **T-003.1** — Implement `compute_metrics(phones: list[str], db_path: Path) -> dict`: run Q1 (aggregation with `COUNT(*)`, `SUM(CASE WHEN mime_type IS NOT NULL AND mime_type != '' THEN 1 ELSE 0 END)`, `SUM(from_me)`, `MIN(timestamp)`, `MAX(timestamp)`) grouped by `contact_phone`; run Q2 (distinct media types) only for non-empty mime_type rows; compute `multimedia_pct`, `from_me_pct`, `first_message`/`last_message` via `[:10]` slice; return `{phone: dict}`.
- [x] **T-003.2** — Verify NULL and empty-string `mime_type` rows are excluded from multimedia numerator and from `media_types` set (per spec scenarios).

---

## Phase 4: Dual Output Writer

- [x] **T-004.1** — Implement `dual_output_writer(sample: list, metrics: dict, summaries: dict, db_name: str, ts: time.struct_time, output_dir: Path) -> None`: compute timestamped stem `contexto_{YYYYMMDD}_{HHMMSS}`; write `outputs/contexto_{ts}.json` with `json.dump(ensure_ascii=False, indent=2)` containing `{generated_at, db_name, total_contacts, sampled_contacts, stratification, contacts: [{phone, name, metrics, profile_summary}]}`; write `outputs/contexto_{ts}.md` beginning with YAML front-matter (`---`, `date:`, `title:`, `db_name:`, `sample_size:`, `tier_method:`, `tier_thresholds:`), then `### #{idx} - {name} ({phone})` blocks with metrics table per contact; both files with `encoding='utf-8'`.

---

## Phase 5: Wiring — Integration in `main()`

- [x] **T-005.1** — In `main()` argparse branch: fetch contacts via `obtener_todos_los_contactos()`, build counts dict from Q1 aggregation, compute `(p33, p66)` via `compute_tier_thresholds()`, bucket contacts into `tiers` dict via `assign_tier()`, call `stratified_sample()` with `budget_ratio` from `--sample-size`.
- [x] **T-005.2** — If `--with-metrics`: call `compute_metrics(selected_phones, db_path)` before LLM loop; pass resulting `metrics` dict and LLM `summaries` dict to `dual_output_writer()` after LLM loop completes.
- [x] **T-005.3** — If `--with-metrics` absent: behave identically to before (interactive menu → random.shuffle path → `compilar_reporte_local()` → single `reporte_contexto_v2.md`). Verify no JSON file is written.
- [x] **T-005.4** — Expose `--with-metrics`, `--db`, `--sample-size`, `--output-dir`, `--help` CLI surface; verify `python scripts/analizar_contexto.py --help` shows new flags.

---

## Phase 6: Verification — Behavioral Smoke Tests

- [x] **T-006.1** — **Smoke 1 (interactive parity)**: run `python scripts/analizar_contexto.py` with no flags; confirm interactive menu appears, mode 1/2 works, `outputs/reporte_contexto_v2.md` is rewritten, **no JSON file** appears in `outputs/`.
- [x] **T-006.2** — **Smoke 2 (new path)**: run `python scripts/analizar_contexto.py --with-metrics --db auto_wpp`; confirm (a) P33/P66 thresholds printed or logged, (b) sample size ≈ 30% of total contacts, (c) each non-empty tier contributes ≥ 1 contact, (d) both `outputs/contexto_{ts}.json` and `.md` exist and are non-empty, (e) JSON parses via `json.load`, (f) Markdown starts with `---` and contains `date:` and `title:`.
- [x] **T-006.3** — **Smoke 3 (backward compat)**: any prior shell invocation of `python scripts/analizar_contexto.py` (zero args) continues to produce identical output to pre-change baseline.

---

## Phase 7: Documentation + Cleanup

- [x] **T-007.1** — Update `outputs/.gitignore` if needed to exclude `contexto_*.json` files (if they should not be committed). — N/A: `outputs/` already in .gitignore; no changes needed.
- [ ] **T-007.2** — Add a one-paragraph note to the project CHANGELOG (or `docs/CHANGELOG.md`) recording: Phase 1 adds `--with-metrics` opt-in to `analizar_contexto.py` enabling stratified sampling by volume tier, per-contact base metrics, and dual JSON+Markdown output.

---

## Acceptance Criteria Mapping

| Task | Spec Requirement | Acceptance Check |
|------|-----------------|-----------------|
| T-001 | Argparse additive; interactive menu preserved | `python scripts/analizar_contexto.py` (no args) → menu |
| T-002.1 | Quantile thresholds computed at runtime | Run twice after adding messages; thresholds differ |
| T-002.2 | P33 boundary → mid tier | `assign_tier(17, 17, 47) → "mid"` |
| T-002.3 | Strict 30% budget; min 1 per non-empty tier | "Low=90/Mid=8/High=2" → 27/2/1; "Low=3/Mid=3/High=4" → 1/1/1 |
| T-003.1 | Total messages, multimedia %, from-me %, date range | Q1 results match spec scenarios |
| T-003.2 | NULL/empty mime_type excluded from numerator | `CASE WHEN mime_type IS NOT NULL AND mime_type != ''` in Q1 |
| T-004.1 | JSON + Markdown dual output with YAML front-matter | Files named `contexto_{ts}.json/.md`; MD starts `---`, contains `date:`, `title:` |
| T-005.2 | `--with-metrics` activates metrics pass | Q1+Q2 execute before LLM loop; JSON written |
| T-005.3 | Default skips metrics | No JSON file without `--with-metrics` |
| T-006.2 | Dual output correctness | JSON parses; MD renders; data identical across formats |

---

## Dependency DAG

```
T-001 (argparse + UTF-8 + menu guard)
  └── T-002.1 (compute_tier_thresholds) ← independent of T-001
  └── T-002.2 (assign_tier)             ← independent of T-001
  └── T-002.3 (stratified_sample)       ← depends on T-002.1, T-002.2
  └── T-003.1 (compute_metrics)        ← independent of T-001
  └── T-004.1 (dual_output_writer)      ← independent of T-001
  └── T-005 (wiring)                   ← depends on T-002.x, T-003.1, T-004.1
  └── T-006 (smoke tests)              ← depends on T-005
  └── T-007 (docs/cleanup)             ← independent, runs last
```

## Execution Order

1. **T-001** — Foundation (imports, UTF-8, argparse skeleton, menu guard). ~20 lines.
2. **T-002.1 + T-002.2** — Threshold + tier helpers. ~15 lines.
3. **T-002.3** — Stratified sample with spec-example comments. ~35 lines.
4. **T-003.1** — Metrics pass (Q1 + Q2 + derived fields). ~40 lines.
5. **T-004.1** — Dual output writer. ~50 lines.
6. **T-005** — Wire everything in `main()`. ~30 lines.
7. **T-006** — Smoke tests (manual verification). No code.
8. **T-007** — `.gitignore` + CHANGELOG note. ~10 lines.

**Total estimated new code: ~200–220 lines** (imports + helpers + wiring + comments), well within single-PR budget.
