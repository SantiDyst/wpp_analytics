# Proposal: phase-1-context-analyzer

## Intent

The `analizar_contexto.py` script currently samples contacts via pure random shuffle and produces only a single Markdown report. It cannot produce per-contact numeric metrics nor stratified (representative) samples. Phase 1 adds three capabilities: volume-tier stratified sampling, an inline base-metrics pass, and dual JSON + Markdown output — all as additive, opt-in CLI additions that preserve existing behavior for users running the script interactively today.

---

## Scope

### In Scope
- Stratified sampling by message-volume tier (Low / Medium / High) with proportional allocation and a minimum of 1 contact per non-empty stratum (strict 30% budget; no floor-of-2 overflow).
- Base metrics generation: total messages, multimedia %, from-me %, distinct media types, and date range per contact — computed in a single pre-pass before LLM analysis.
- Dual output: one timestamped JSON file (machine-readable) and one Markdown file with YAML front-matter (human-readable), same base name.
- `--with-metrics` opt-in flag; default behavior preserves the existing interactive menu and single-Markdown output.

### Out of Scope
- Taxonomy changes to `buscar_datos.py` (Phase 2 — already archived).
- Changes to `scripts/buscar_datos.py`.
- Flask dashboard work.
- Skill packaging work.

---

## Capabilities

### New Capabilities

| Capability | File | Description |
|---|---|---|
| `stratified-contact-sampling` | `scripts/analizar_contexto.py` | Contacts bucketed into Low/Medium/High volume tiers; proportional allocation within strata; minimum 1 per non-empty stratum (strict 30% budget). |
| `contact-base-metrics` | `scripts/analizar_contexto.py` | Per-contact aggregates (msg count, multimedia %, from-me %, media types, date range) computed in one pre-pass before LLM loop. |
| `dual-contextual-output` | `scripts/analizar_contexto.py` | Writes `outputs/contexto_metrics_<db>_<ts>.json` and `outputs/contexto_report_<db>_<ts>.md` with YAML front-matter. |

### Modified Capabilities
None — all changes are additive; existing interactive menu, cache behavior, and `conversation_summaries` table writes are unchanged.

---

## Approach

1. **Sampling** — Single aggregation query (`SELECT contact_phone, COUNT(*) FROM messages GROUP BY contact_phone`) to build strata. CLI flags `--stratum-boundaries` (e.g. `50,200`) set tier cutoffs with smart defaults (percentile-based). Within each stratum, contacts are shuffled and sampled proportionally; minimum 1 per non-empty stratum with a strict 30% budget.
2. **Metrics** — Inline pass before LLM loop. Per-contact: `total_messages`, `multimedia_pct = COUNT(mime_type IS NOT NULL) / total * 100`, `from_me_pct`, `media_types`, `date_range`. Results stored in a `dict[phone, metrics]` passed to both JSON serializer and Markdown compiler.
3. **Output** — JSON structure mirrors the schema in `exploration.md §3A`. Markdown uses existing `compilar_reporte_local()` YAML front-matter pattern. New files replace the fixed `reporte_contexto_v2.md` naming with timestamped stems.
4. **CLI** — Use `argparse` (following `buscar_datos.py` pattern) with `--sample-size` (int, default 50), `--stratum-boundaries`, `--output-dir`, and `--with-metrics`. Existing interactive menu remains the default when no flags are given.

---

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `scripts/analizar_contexto.py` | Modified | Added: stratified sampling, metrics pre-pass, dual output, argparse, `--with-metrics` opt-in flag. |
| `scripts/buscar_datos.py` | Reference | Pattern source for argparse CLI style (`--db`, `--mode`). |
| `outputs/` | New output | JSON metrics files written here alongside existing Markdown reports. |

---

## Open Questions

- **Stratum boundaries**: Should defaults be `--stratum-boundaries 50,200` (as in exploration) or computed dynamically from dataset percentiles? User preference needed.
- **Sample size default**: 50 (current batch size) or something else?
- **Output directory**: Write to `outputs/` (current convention) or accept `--output-dir` override?

---

## Rollback / Migration Plan

All changes are additive CLI flags. Users running `python scripts/analizar_contexto.py` with no arguments get the identical interactive menu and single Markdown output they have today — no migration required. The new capabilities activate only when CLI flags are explicitly passed.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Large DB full-scan for metrics on first run | Medium | `--with-metrics` is opt-in; omitting it skips the full scan and uses the existing cache path. |
| Empty or tiny strata (e.g. 90% of contacts in "Low") | Low | Minimum 1 contact per non-empty stratum enforced in allocation logic; strict 30% budget prevents overflow. |
| Breaking interactive menu with argparse | Low | Interactive menu preserved as default when no flags given; argparse only added, never replaces menu logic. |
| `mime_type` NULL values skewing multimedia % | Low | Use `COUNT(mime_type IS NOT NULL)` in denominator; verify with null-check query before shipping. |

---

## Success Criteria

- [ ] `python scripts/analizar_contexto.py` (no flags) behaves identically to current behavior: interactive menu, single `reporte_contexto_v2.md`.
- [ ] `--sample-size 30 --stratum-boundaries 50,200` produces a stratified sample where every non-empty stratum has ≥ 1 contact and the total is ≤ `floor(0.30 * N)`.
- [ ] Base metrics JSON contains `total_messages`, `multimedia_pct`, `from_me_pct`, `media_types`, `first_message`, `last_message` per contact.
- [ ] Markdown output contains YAML front-matter (`---`, `date:`, `title:`) matching existing convention.
- [ ] No existing `conversation_summaries` cache entries are overwritten or modified by the new code path.
