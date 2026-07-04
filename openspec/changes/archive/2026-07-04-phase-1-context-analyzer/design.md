# Design: phase-1-context-analyzer

## Context

`scripts/analizar_contexto.py` currently samples contacts via `random.shuffle(todos_contactos)` at line 425 and writes only `outputs/reporte_contexto_v2.md`. No per-contact numeric metrics exist, and natural groupings (light vs. heavy chatters) are ignored — random shuffle plus sequential 50-contact batches (`analizar_contexto.py:440-442`) means early batches can over- or under-represent any tier of relationship. Phase 1 adds four additive capabilities — volume-tier stratified sampling, an inline base-metrics pass, dual JSON+Markdown output, and an opt-in `--with-metrics` flag — without altering the interactive menu, the `conversation_summaries` cache schema, or any existing function signature. Phase 2 (already archived taxonomy work) builds on this foundation; this design is the prerequisite.

## Goals / Non-Goals

**Goals** (locked, not renegotiable):

| Goal | Detail |
|---|---|
| Tiers | 3 quantile-based tiers (Low / Mid / High); thresholds P33 and P66 computed at runtime from current dataset |
| Allocation | Proportional per tier, **minimum 1 per non-empty tier**; sum of sample ≤ `floor(0.30 * N)` (strict budget, no overflow) |
| Sample size | **30% of total contacts** per run, **no floor** on total |
| Output | `outputs/contexto_{YYYYMMDD}_{HHMMSS}.json` and `.md` (same stem, different extension); Markdown begins with YAML front-matter |
| CLI | `--with-metrics` required to activate metrics pass; default off |
| Stack | Python 3.14 stdlib only — no pandas / numpy / scipy |

**Non-Goals**: changes to `scripts/buscar_datos.py`, Flask dashboard, or skill packaging; multi-dimensional stratification (volume + recency + media); any SQLite schema migration.

## Approach

### Data flow

```
[contacts table]                          [messages table]
       │                                          │
       │ SELECT phone, name                       │ SELECT … GROUP BY contact_phone
       ▼                                          ▼
obtener_todos_los_contactos()  ──► counts dict ──► statistics.quantiles() → (P33, P66)
                                              │                              │
                                              ▼                              ▼
                                    assign_tier() → {low, mid, high} → stratified_sample()
                                                                              │
                              ┌── --with-metrics? ────────────────────────────┤
                              ▼ YES                                            ▼ NO
                       compute_metrics()                              random.shuffle path
                       → metrics dict {phone: …}                       (existing behavior)
                              │                                            │
                              └────────────────┬───────────────────────────┘
                                               ▼
                                per-contact LLM loop (unchanged: extraer_muestra_contacto → llamar_api → conversation_summaries)
                                               │
                                               ▼
                                    dual_output_writer()
                                    ├── contexto_{ts}.json  (machine-readable)
                                    └── contexto_{ts}.md    (YAML front-matter)
```

### SQL queries

**Q1 — aggregation** (drives both tier thresholds and most metrics):

```sql
SELECT contact_phone,
       COUNT(*)                                                 AS total_messages,
       SUM(CASE WHEN mime_type IS NOT NULL AND mime_type != ''
                THEN 1 ELSE 0 END)                              AS media_count,
       SUM(from_me)                                             AS from_me_count,
       MIN(timestamp)                                           AS first_ts,
       MAX(timestamp)                                           AS last_ts
FROM messages
GROUP BY contact_phone;
```

**Q2 — distinct media types per contact** (only when `--with-metrics` is set):

```sql
SELECT contact_phone, mime_type
FROM messages
WHERE mime_type IS NOT NULL AND mime_type != ''
GROUP BY contact_phone, mime_type;
```

Python groups rows into `{phone: {mime_type, …}}` via `dict.setdefault`.

**Q3 — sampling**: no SQL — selection runs in Python over the in-memory tier buckets using `random.shuffle` within each tier. The aggregation above already produced all `(phone, count)` rows we need; no second pass is required to choose contacts.

### Tier computation algorithm

SQLite has no `NTILE` window function. The stdlib `statistics.quantiles` (Python 3.8+, available in 3.14) is deterministic and dependency-free.

```python
counts = {phone: n for phone, n in cursor.execute(Q1)}
import statistics
q = statistics.quantiles(list(counts.values()) or [0], n=3, method="inclusive")
p33, p66 = q[0], q[1]

def assign_tier(n: int) -> str:
    if n < p33:  return "low"
    if n <= p66: return "mid"   # P33 inclusive per spec ("Contact on exact boundary")
    return "high"
```

Thresholds are recomputed every run (spec: "Quantiles recalculated per run"); never persisted. N=0 collapses all contacts into "mid".

### Allocation algorithm

Strict-budget allocation: the sum of selected samples never exceeds `floor(0.30 * N)`. The algorithm seeds each non-empty tier at 1 (so every observed tier is represented), then distributes the remaining budget proportionally to tier sizes via `int(0.30 * |tier|) - 1` per tier. A final trim step protects the strict-budget invariant when many small tiers would otherwise push the total over budget.

```python
N       = sum(len(b) for b in tiers.values() if b)   # total non-empty contacts
N_tiers = sum(1 for b in tiers.values() if b)        # non-empty tier count
budget  = max(int(0.30 * N), N_tiers)                # strict 30%, floor = 1 per non-empty tier

# Seed: 1 per non-empty tier
desired = {name: 1 for name, b in tiers.items() if b}
# Distribute remaining budget proportionally to tier sizes
for name, bucket in tiers.items():
    if not bucket:
        continue
    extra = int(0.30 * len(bucket)) - 1
    if extra > 0:
        desired[name] += extra

# Strict-budget trim: if sum > budget (rare; only when many tiny tiers),
# take from the largest tier(s), never dropping any non-empty tier below 1.
total = sum(desired.values())
if total > budget:
    overflow = total - budget
    for name in sorted(desired, key=lambda k: -len(tiers[k])):
        if overflow <= 0:
            break
        can_give = desired[name] - 1
        give = min(can_give, overflow)
        desired[name] -= give
        overflow -= give

sample = []
for name, bucket in tiers.items():
    random.shuffle(bucket)
    take  = min(desired.get(name, 0), len(bucket))
    sample.extend(bucket[:take])
```

**Spec scenario trace — "Proportional split reflects population"** (300 contacts: Low=150, Mid=90, High=60; budget=90):
- `N=300`, `N_tiers=3`, `budget = max(90, 3) = 90`.
- Seed: `{low: 1, mid: 1, high: 1}`.
- Extras: low gets `int(0.30 * 150) - 1 = 44`; mid gets `int(0.30 * 90) - 1 = 26`; high gets `int(0.30 * 60) - 1 = 17`.
- No trim (sum=90 = budget).
- Final: `low=45, mid=27, high=18`, sum=90. ✓ matches strict-budget spec.

**Spec scenario trace — "Small tier boosted to floor"** (100 contacts: Low=90, Mid=8, High=2; budget=30):
- `N=100`, `N_tiers=3`, `budget = max(30, 3) = 30`.
- Seed: `{low: 1, mid: 1, high: 1}`.
- Extras: low gets `int(0.30 * 90) - 1 = 26`; mid gets `int(0.30 * 8) - 1 = 1`; high gets `max(0, int(0.30 * 2) - 1) = 0`.
- No trim (sum=30 = budget).
- Final: `low=27, mid=2, high=1`, sum=30 (strict budget). ✓ matches strict-budget spec.

**Spec scenario trace — "Small database with floor interaction"** (10 contacts: Low=3, Mid=3, High=4; budget=3):
- `N=10`, `N_tiers=3`, `budget = max(3, 3) = 3`.
- Seed: `{low: 1, mid: 1, high: 1}`.
- Extras: low gets `max(0, int(0.30 * 3) - 1) = 0`; mid gets `0`; high gets `max(0, int(0.30 * 4) - 1) = 0`.
- No trim (sum=3 = budget).
- Final: `low=1, mid=1, high=1`, sum=3 (within budget). ✓ matches strict-budget spec.

Edge cases (per spec):
- `|tier| == 0` → skip tier entirely (excluded from `desired`, `N`, and `N_tiers`).
- Trim step never drops a non-empty tier below 1; if every tier is "tiny" (|tier| ≤ 3) the seed itself already saturates `budget = N_tiers` and the trim is a no-op.
- Trim step only fires when many small non-empty tiers collectively exceed budget — empirically rare for real datasets but guaranteed-safe for the strict-budget invariant.

### Metrics pass

Sits between sampling and the per-contact LLM loop, runs **only** when `--with-metrics` is set. Q1 supplies `total_messages`, `media_count`, `from_me_count`, `first_ts`, `last_ts`; Q2 fills `media_types`. Derived in Python:

```python
multimedia_pct = media_count / total * 100         # 0.0 when total == 0
from_me_pct     = from_me_count / total * 100
first_message   = first_ts[:10]                     # ISO slice (buscar_datos.py:250)
last_message    = last_ts[:10]
```

**NULL handling** (spec explicit):
- `mime_type IS NULL` → excluded from numerator **and** from `media_types`.
- `mime_type = ''` (empty string) → same exclusion; treated as non-multimedia.
- Denominator always `total_messages` (never NULL because `COUNT(*)`).
- Empty contact (`total_messages == 0`) → `multimedia_pct = 0.0`, `from_me_pct = 0.0`, `first_message = last_message = None`.

Metrics live in a `{phone: dict}` in memory only — **never** written to SQLite. They are consumed by `dual_output_writer()` for both JSON and Markdown.

### Dual output writer

```python
def dual_output_writer(sample, metrics, summaries, db_name, ts):
    stem      = f"contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}"
    json_path = output_dir / f"{stem}.json"
    md_path   = output_dir / f"{stem}.md"

    # JSON: dict → json.dump(payload, fp, ensure_ascii=False, indent=2)
    # payload matches exploration.md §3A: {generated_at, db_name,
    #   total_contacts, sampled_contacts, stratification,
    #   contacts: [{phone, name, metrics, profile_summary}, …]}

    # MD: YAML front-matter (`---`, `date:`, `title:`, `db_name:`,
    #   `sample_size:`, `tier_method:`, `tier_thresholds:`),
    #   then one `### #{idx} - {name} ({phone})` block per contact;
    #   each block ends with a metrics table when metrics is present.
```

Both files written with `encoding='utf-8'`. The legacy `reporte_contexto_v2.md` is still produced when `--with-metrics` is **absent**, preserving today's contract.

### CLI surface

Modeled on `buscar_datos.py:384-393`. Interactive menu is preserved as the default branch via `len(sys.argv) == 1`.

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--with-metrics` | `store_true` | off | Activate metrics pass + dual JSON/MD output |
| `--db NAME` | str | `None` | Skip interactive DB-selection prompt |
| `--sample-size` | float | `0.30` | Override 30% allocation ratio |
| `--output-dir` | path | `outputs/` | Override output directory |
| `--help` | built-in | — | Usage |

Argparse is added **additively**; it never replaces the menu. The menu (mode 1 = batches of 50 with confirmation; mode 2 = auto-all) is reached only when no flag is passed.

### Backward compatibility

| Invocation | Resulting behavior |
|---|---|
| `python scripts/analizar_contexto.py` | **Identical** to today: interactive menu, `random.shuffle`, single `reporte_contexto_v2.md` |
| `python scripts/analizar_contexto.py --db auto_wpp` | Skips DB prompt; rest identical |
| `python scripts/analizar_contexto.py --with-metrics [--db …]` | **New path**: stratified sampling + metrics + dual JSON/MD output |

No existing function (`obtener_todos_los_contactos`, `extraer_muestra_contacto`, `llamar_api`, `compilar_reporte_local`) is renamed, re-signed, or has its body altered. New helpers are purely additive.

## Files / Functions Touched

| File | Status | Notes |
|---|---|---|
| `scripts/analizar_contexto.py` | modified | Add `argparse`, `statistics`, `sys` imports; add UTF-8 stdout reconfigure (mirror `buscar_datos.py:21-24`); new helpers `compute_tier_thresholds`, `assign_tier`, `stratified_sample`, `compute_metrics`, `dual_output_writer`, `parse_args`; branch `main()` on `len(sys.argv)`. Existing functions **unchanged**. |
| `outputs/contexto_{ts}.json` | new | Written by `dual_output_writer` when `--with-metrics` is set. |
| `outputs/contexto_{ts}.md` | new | Same condition; YAML front-matter. |
| `outputs/reporte_contexto_v2.md` | unchanged | Still produced by `compilar_reporte_local()` whenever flag is absent. |
| `outputs/logs.txt` | unchanged | `registrar_logs_v2()` is untouched. |
| `conversation_summaries` table | unchanged | No migration; same `INSERT OR REPLACE` writes. |
| `scripts/buscar_datos.py` | unchanged | Reference only (argparse + UTF-8 patterns). |
| `scripts/clean_db.py` | unchanged | Reference only (YAML front-matter shape). |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Q1/Q2 scan cost on large DBs | Medium | Omitting `--with-metrics` skips both queries; existing cache path used |
| NULL / empty `mime_type` skews multimedia % | Low | Explicit `IS NOT NULL AND != ''` predicate; covered by three spec scenarios |
| Argparse replacing interactive menu | Low | `len(sys.argv) == 1` early-return preserves menu; argparse only runs when flags present |
| Windows console encoding for JSON / MD | Medium | Mirror `buscar_datos.py:21-24` `sys.stdout.reconfigure(encoding='utf-8')` at top of file; both files written with `encoding='utf-8'` |
| `statistics.quantiles` on degenerate input (N=0) | Low | `or [0]` fallback; all contacts collapse to "mid", allocation still works |
| Many small non-empty tiers pushing sum over budget | Low | Strict-budget trim step takes from largest tier first, never below 1; only fires when ≥ 4 non-empty tiers are all ≤ 3 contacts (empirically rare) |
| Date-range formatting for non-ISO timestamps | Low | `buscar_datos.py:250` confirms ISO format; if assertion fails, `str[:10]` raises and surfaces the bug rather than silently producing garbage |

## Migration / Rollout

No migration. Validation is **behavioral** (no test framework available per `openspec/config.yaml:8`).

**Smoke 1 — interactive parity**:
```
python scripts/analizar_contexto.py
```
Confirm: menu appears, mode 1/2 prompt works, `outputs/reporte_contexto_v2.md` is rewritten, **no JSON file** appears in `outputs/`.

**Smoke 2 — new path**:
```
python scripts/analizar_contexto.py --with-metrics --db auto_wpp
```
Confirm:
1. P33 and P66 thresholds are printed (or logged).
2. Sample size ≈ 30% of total contacts (within ±1).
3. Each non-empty tier contributes ≥ 2 contacts (unless budget forced skip — see spec "Small DB" scenario).
4. Both `outputs/contexto_{ts}.json` and `.md` exist and are non-empty.
5. `json.load` on the JSON parses; the MD starts with `---` and contains `date:` and `title:`.

**Smoke 3 — backward compatibility**: any prior shell script that invokes `python scripts/analizar_contexto.py` continues to behave exactly as before.

Rollback = revert `scripts/analizar_contexto.py`. No DB migration, no dependency change.

## Open Decisions

None. Both previously-open items are resolved:
- **`--quick` semantics** → flag and capability dropped entirely; default behavior is the only "no metrics" mode.
- **Allocation spec discrepancy** → algorithm updated to strict-budget (min 1 per non-empty tier, sum ≤ `floor(0.30 * N)`); all three spec scenarios now produce results that respect the 30% budget exactly.

## Acceptance Criteria

| Spec REQ | Design mapping | Acceptance check |
|---|---|---|
| Quantile Threshold Computation | `compute_tier_thresholds` via `statistics.quantiles(n=3)` | Run twice after adding messages; thresholds differ |
| Tier Assignment | `assign_tier` with `n <= p66` → mid | Boundary `n == P33` → mid |
| Proportional Allocation | `int(0.30 * \|tier\|) - 1` per non-empty tier (added to seed of 1) | Sum of extras ≤ `floor(0.30 * N) - N_tiers` |
| Minimum Per-Tier Representation | Seed `{name: 1 for name, b in tiers.items() if b}` | Every non-empty tier contributes ≥ 1 contact |
| Strict 30% Budget | `budget = max(int(0.30 * N), N_tiers)` + trim step | "Low=90, Mid=8, High=2" → low=27, mid=2, high=1, sum=30 |
| Sample Size 30% of Total | `int(0.30 * N)`, no floor; trim protects invariant | N=10 (Low=3, Mid=3, High=4) → sample=3 (low=1, mid=1, high=1) |
| Total Message Count | Q1 `COUNT(*)` | N=0 → `total_messages=0` |
| Multimedia % NULL handling | Q1 `CASE WHEN mime_type IS NOT NULL AND != ''` | Empty-string rows excluded from numerator |
| From-Me % | Q1 `SUM(from_me)` | 80/200 → 40.0 |
| Distinct Media Types | Q2 + Python `setdefault` | Duplicates collapse to set |
| Date Range | Q1 MIN/MAX + `[:10]` slice | Single-msg contact → first == last |
| JSON Output File | `dual_output_writer` JSON branch | Filename matches `contexto_\d{8}_\d{6}\.json` |
| Markdown + YAML Front-Matter | `dual_output_writer` MD branch | First lines `---`, `date:`, `title:`, `---` |
| Same Data in Both Formats | Single source dict | `contacts[i].metrics.total_messages` == MD-rendered cell |
| Default Skips Metrics | `len(sys.argv)==1` early-return | No JSON file produced |
| `--with-metrics` Activates Pass | argparse branch | Q1+Q2 executed before LLM loop |