import os
import sys
import re
import sqlite3
import json
import argparse
import statistics
import urllib.request
import urllib.error
import time
import random
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# TODO: Read from taxonomy YAML when Phase 3 lands.
# Hardcoded for now: Cliente | Proveedor | Empleado | Familiar | Spam | Otro.
LABELS = ["Cliente", "Proveedor", "Empleado", "Familiar", "Spam", "Otro"]


# Lexical triggers that signal "este caso sale del alcance del agente actual".
# Regex + human-readable label. Order matters for the .md output.
ESCALATION_PATTERNS: list[tuple[str, str]] = [
    (r"\bderivar(?:\s+a)?\b",             "Derivar a otro agente"),
    (r"\bconsulte?\s+con\b",               "Indicar 'consulte con'"),
    (r"\basesor[ií]a\b",                   "Mencionar asesoría (legal / de turno)"),
    (r"\b[ld]e\s+(des)?bloque[oó]\b",      "Bloqueo / Desbloqueo de agente"),
    (r"\bsupervisor\b|\bjefe\b",           "Escalar a supervisor / jefe"),
    (r"\bno\s+(se\s+)?pued[eo]\b",         "Límite del agente actual"),
    (r"\bm[eé]dico\s+fiscal\b",            "Pasar al médico fiscal"),
    (r"3794\d{6}",                         "Número de otra línea interna"),
]





# Handle Windows console encoding for JSON/MD output (mirrors buscar_datos.py:21-24)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# Configurar rutas locales
base_dir = Path(__file__).parent.parent
env_path = base_dir / '.env'
output_dir = base_dir / 'outputs'
output_dir.mkdir(exist_ok=True)
log_file_path = output_dir / 'logs.txt'

# Cargar API Key, Modelo y Base URL desde archivo .env si existe
api_key = ""
model_name = "gemini-2.5-flash"
api_base_url = ""

if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                if key in ('GEMINI_API_KEY', 'MINIMAX_API_KEY', 'API_KEY'):
                    api_key = val
                elif key in ('GEMINI_MODEL', 'MINIMAX_MODEL', 'MODEL_NAME'):
                    model_name = val
                elif key in ('API_BASE_URL', 'BASE_URL'):
                    api_base_url = val

# Si no hay API Key en .env, buscar en variables de entorno del sistema
if not api_key:
    api_key = os.environ.get('GEMINI_API_KEY', os.environ.get('MINIMAX_API_KEY', os.environ.get('API_KEY', '')))
if not model_name:
    model_name = os.environ.get('GEMINI_MODEL', os.environ.get('MINIMAX_MODEL', os.environ.get('MODEL_NAME', 'gemini-2.5-flash')))
if not api_base_url:
    api_base_url = os.environ.get('API_BASE_URL', os.environ.get('BASE_URL', ''))

# ---------------------------------------------------------------------------
# New helpers — Phase 1: stratified sampling + metrics + dual output
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Analizador de contexto con muestreo estratificado y métricas."
    )
    parser.add_argument(
        "--with-metrics",
        action="store_true",
        help="Activa el paso de métricas y la salida dual JSON+MD.",
    )
    parser.add_argument(
        "--db",
        dest="db_name",
        help="Nombre de la carpeta de la base de datos (ej. auto_wpp). "
        "Si se omite, se detecta automáticamente.",
    )
    parser.add_argument(
        "--sample-size",
        type=float,
        default=0.30,
        help="Fracción de contactos a muestrear (default 0.30 = 30%%).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=base_dir / "outputs",
        help="Directorio de salida (default: outputs/).",
    )
    return parser.parse_args()


def compute_tier_thresholds(counts):
    """Compute P33 and P66 quantiles from a dict of {phone: message_count}."""
    values = list(counts.values()) or [0]
    q = statistics.quantiles(values, n=3, method="inclusive")
    p33, p66 = q[0], q[1]
    return p33, p66


def assign_tier(n, p33, p66):
    """Assign a contact to a tier based on message count and quantile boundaries.
    Boundary n == P33 routes to 'mid' (per spec: 'Contact on exact boundary')."""
    if n < p33:
        return "low"
    if n <= p66:
        return "mid"
    return "high"


def stratified_sample(tiers, budget_ratio=0.30):
    """Strict-budget stratified sample with min-1-per-non-empty-tier.

    SPEC-EXAMPLE: 300 contacts — Low=150, Mid=90, High=60 → 45/27/18
        N=300, N_tiers=3, budget=max(int(0.30*300), 3)=90.
        Seed: {low:1, mid:1, high:1}.
        Extras: low=int(0.30*150)-1=44, mid=int(0.30*90)-1=26, high=int(0.30*60)-1=17.
        Sum=90=budget. Final: low=45, mid=27, high=18. ✓

    SPEC-EXAMPLE: 100 contacts — Low=90, Mid=8, High=2 → 27/2/1
        N=100, N_tiers=3, budget=max(int(0.30*100), 3)=30.
        Seed: {low:1, mid:1, high:1}.
        Extras: low=int(0.30*90)-1=26, mid=int(0.30*8)-1=1, high=max(0,int(0.30*2)-1)=0.
        Sum=30=budget. Final: low=27, mid=2, high=1. ✓

    SPEC-EXAMPLE: 10 contacts — Low=3, Mid=3, High=4 → 1/1/1
        N=10, N_tiers=3, budget=max(int(0.30*10), 3)=3.
        Seed: {low:1, mid:1, high:1}.
        Extras: all 0 (int(0.30*|tier|)-1 ≤ 0 for |tier|≤4).
        Sum=3=budget. Final: low=1, mid=1, high=1. ✓
    """
    N = sum(len(b) for b in tiers.values() if b)
    N_tiers = sum(1 for b in tiers.values() if b)
    if N == 0 or N_tiers == 0:
        return []

    budget = max(int(budget_ratio * N), N_tiers)

    # Seed: 1 per non-empty tier
    desired = {name: 1 for name, b in tiers.items() if b}

    # Distribute remaining budget proportionally to tier sizes
    for name, bucket in tiers.items():
        if not bucket:
            continue
        extra = int(budget_ratio * len(bucket)) - 1
        if extra > 0:
            desired[name] += extra

    # Strict-budget trim: take from largest tier(s) first, never below 1
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
        take = min(desired.get(name, 0), len(bucket))
        sample.extend(bucket[:take])
    return sample


def compute_metrics(cursor, contacts):
    """Run Q1 + Q2 SQL and compute per-contact base metrics.

    Q1: COUNT(*), SUM(CASE WHEN mime_type IS NOT NULL AND mime_type != ''),
        SUM(from_me), MIN(timestamp), MAX(timestamp)  — grouped by contact_phone
    Q2: DISTINCT mime_type per contact (non-NULL, non-empty).

    Returns: dict[phone, dict] with keys:
        total_messages, multimedia_pct, from_me_pct,
        first_message, last_message, media_types.
    """
    if not contacts:
        return {}

    phones = list(contacts)
    placeholders = ",".join("?" * len(phones))

    # Q1 — aggregation
    cursor.execute(f"""
        SELECT
            contact_phone,
            COUNT(*)                                                     AS total_messages,
            SUM(CASE WHEN mime_type IS NOT NULL AND mime_type != ''
                     THEN 1 ELSE 0 END)                                  AS media_count,
            SUM(from_me)                                                 AS from_me_count,
            MIN(timestamp)                                               AS first_ts,
            MAX(timestamp)                                               AS last_ts
        FROM messages
        WHERE contact_phone IN ({placeholders})
        GROUP BY contact_phone;
    """, phones)
    rows = cursor.fetchall()

    # Build base dict from Q1
    metrics = {}
    for phone, total, media_count, from_me_count, first_ts, last_ts in rows:
        first_ts_str = (first_ts[:10] if first_ts else None)
        last_ts_str = (last_ts[:10] if last_ts else None)
        multimedia_pct = (media_count / total * 100) if total > 0 else 0.0
        from_me_pct = (from_me_count / total * 100) if total > 0 else 0.0
        metrics[phone] = {
            "total_messages": total,
            "multimedia_pct": round(multimedia_pct, 2),
            "from_me_pct": round(from_me_pct, 2),
            "first_message": first_ts_str,
            "last_message": last_ts_str,
            "media_types": [],  # populated by Q2
        }

    # Q2 — distinct non-null/non-empty mime_types per contact
    cursor.execute(f"""
        SELECT contact_phone, mime_type
        FROM messages
        WHERE contact_phone IN ({placeholders})
          AND mime_type IS NOT NULL
          AND mime_type != ''
        GROUP BY contact_phone, mime_type;
    """, phones)
    for phone, mime_type in cursor.fetchall():
        if phone in metrics:
            metrics[phone]["media_types"].append(mime_type)

    # Ensure all requested contacts appear (even if 0 messages)
    for phone in phones:
        if phone not in metrics:
            metrics[phone] = {
                "total_messages": 0,
                "multimedia_pct": 0.0,
                "from_me_pct": 0.0,
                "first_message": None,
                "last_message": None,
                "media_types": [],
            }
    return metrics


def procesar_chats_con_ia(sample_list, db_path, options):
    """Shared per-contact LLM processing loop consumed by both --with-metrics and interactive paths.

    Args:
        sample_list: list of (phone, name) tuples (or 3-tuples with _slot=None for --with-metrics).
        db_path: Path to the SQLite database.
        options: dict with keys:
            - cursor: sqlite3.Cursor
            - connection: sqlite3.Connection
            - metrics_enabled: bool — when True, accumulate tokens and call registrar_logs at batch end
            - fail_fast: bool — forwarded to llamar_api(); True for --with-metrics, False for interactive
            - interactive: bool — when True, show progress bar and [WARN] lines
            - registrar_logs: callable|None — called at batch end when metrics_enabled and nuevos_analizados > 0

    Returns:
        tuple: (summaries_dict, token_totals_dict, cache_stats_dict)
            - summaries_dict: {phone: str|None} — cleaned summary or None
            - token_totals_dict: {"prompt_tokens": int, "candidate_tokens": int, "total_tokens": int, "elapsed_seconds": float}
            - cache_stats_dict: {"nuevos_analizados": int, "omitidos_por_cache": int}

    TODO Phase-3: evaluate concurrent.futures.ThreadPoolExecutor for parallel
    LLM calls. Sequential design adds ~0.5s sleep + ~2-3s API latency per contact
    (~4-5 min for 90 contacts). Concurrency would cut this proportionally, but
    rate limits on the MiniMax/Gemini providers must be validated first.
    """
    summaries = {}
    token_totals = {"prompt_tokens": 0, "candidate_tokens": 0, "total_tokens": 0, "elapsed_seconds": 0.0}
    cache_stats = {"nuevos_analizados": 0, "omitidos_por_cache": 0}
    nuevos_analizados = 0
    omitidos_por_cache = 0
    lote_prompt_tokens = 0
    lote_candidate_tokens = 0
    lote_total_tokens = 0
    batch_start = time.time()

    cursor = options["cursor"]
    connection = options["connection"]
    metrics_enabled = options.get("metrics_enabled", False)
    fail_fast = options.get("fail_fast", False)
    interactive = options.get("interactive", False)
    registrar_logs = options.get("registrar_logs")

    for idx, item in enumerate(sample_list):
        # Support both 2-tuple (phone, name) and 3-tuple (phone, name, _slot)
        if len(item) == 3:
            phone, name, _slot = item
        else:
            phone, name = item
            _slot = None

        contact_label = name if name else f"Contacto {phone[-4:]}"

        # Cache check: skip API call if profile already exists
        cursor.execute(
            "SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'",
            (phone,),
        )
        row = cursor.fetchone()
        if row:
            summaries[phone] = row[0]
            omitidos_por_cache += 1
            cache_stats["omitidos_por_cache"] = omitidos_por_cache
            mostrar_progreso(
                idx + 1, len(sample_list),
                prefijo="Progreso",
                sufijo=f"({idx+1}/{len(sample_list)}) Cache: {contact_label[:15]}",
                longitud=30,
            )
            continue

        muestra = extraer_muestra_contacto(cursor, phone, name)
        if not muestra:
            summaries[phone] = None
            print(f"\n[WARN] No se pudo analizar el contacto {contact_label} (sin mensajes válidos).")
            mostrar_progreso(
                idx + 1, len(sample_list),
                prefijo="Progreso",
                sufijo=f"({idx+1}/{len(sample_list)}) Skip: {contact_label[:15]}",
                longitud=30,
            )
            continue

        print(f"\n[LLM] {idx+1}/{len(sample_list)} Analizando: {contact_label}...", flush=True)
        resultado, p_tok, c_tok, t_tok, t_api = llamar_api(muestra, is_individual=True, fail_fast=fail_fast)

        if resultado:
            perfil_limpio = remove_think_tags(resultado)
            summaries[phone] = perfil_limpio
            cursor.execute("""
                INSERT OR REPLACE INTO conversation_summaries
                    (contact_phone, period, summary, updated_at)
                VALUES (?, 'profile', ?, CURRENT_TIMESTAMP)
            """, (phone, perfil_limpio))
            connection.commit()

            # Always accumulate tokens for the caller (interactive needs them for final summary)
            lote_prompt_tokens += p_tok
            lote_candidate_tokens += c_tok
            lote_total_tokens += t_tok

            nuevos_analizados += 1
            cache_stats["nuevos_analizados"] = nuevos_analizados

            mostrar_progreso(
                idx + 1, len(sample_list),
                prefijo="Progreso",
                sufijo=f"({idx+1}/{len(sample_list)}) OK: {contact_label[:15]}",
                longitud=30,
            )
            time.sleep(0.5)
        else:
            summaries[phone] = None
            print(f"\n[WARN] No se pudo analizar el contacto {contact_label} (API falló).")
            mostrar_progreso(
                idx + 1, len(sample_list),
                prefijo="Progreso",
                sufijo=f"({idx+1}/{len(sample_list)}) FAIL: {contact_label[:15]}",
                longitud=30,
            )

    # Token accumulation totals
    token_totals["prompt_tokens"] = lote_prompt_tokens
    token_totals["candidate_tokens"] = lote_candidate_tokens
    token_totals["total_tokens"] = lote_total_tokens

    # End-of-batch: log token totals if metrics enabled
    if metrics_enabled and registrar_logs and nuevos_analizados > 0:
        batch_elapsed = time.time() - batch_start
        registrar_logs(
            1,                              # lote_num
            db_path.parent.parent.name,     # db_name
            nuevos_analizados,
            omitidos_por_cache,
            lote_prompt_tokens,
            lote_candidate_tokens,
            lote_total_tokens,
            batch_elapsed,
        )

    return summaries, token_totals, cache_stats


def escribir_reporte_ejecutivo(
    master_sections: dict[str, str],
    db_name: str,
    sample_size: int,
    ts: time.struct_time,
    labels_distribution: dict[str, int],
    output_dir: Path,
    examples_by_category: dict[str, list[str]] | None = None,
    hourly_distribution: dict[int, int] | None = None,
    resolution_by_category: dict[str, float] | None = None,
    escalation_phrases: list[tuple[str, list[str]]] | None = None,
) -> Path:
    """Write contexto_{ts}.md: YAML front-matter + 4 executive sections + optional examples + time patterns + escalations.

    Returns the output Path. Does not raise on missing section — emits a
    placeholder line for each missing key.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}"
    md_path = output_dir / f"{stem}.md"

    date_str = time.strftime("%Y-%m-%d", ts)
    contexto = master_sections.get("contexto_general", "")

    front_matter = [
        "---",
        f"date: {date_str}",
        "title: Reporte Ejecutivo de Análisis de Contexto",
        f"db_name: {db_name}",
        f"sample_size: {sample_size}",
        "tier_method: quantile (P33/P66 inclusive)",
        "master_context:",
        f"  generated_at: {time.strftime('%Y-%m-%dT%H:%M:%S', ts)}",
        f"  database: {db_name}",
        f"  sample_size: {sample_size}",
        "  labels_distribution:",
    ]
    for label, count in labels_distribution.items():
        front_matter.append(f"    {label}: {count}")
    front_matter.append("  summary: |")
    for line in contexto.splitlines() or ["(sección no generada)"]:
        front_matter.append(f"    {line}")
    front_matter.append("---")
    front_matter.append("")

    body = [
        "## 1. Contexto General del Entorno",
        "",
        master_sections.get("contexto_general", "*No disponible.*"),
        "",
        "## 2. Temáticas o Categorías Más Comunes",
        "",
        master_sections.get("tematicas", "*No disponible.*"),
        "",
        "## 3. Dudas o Consultas Frecuentes",
        "",
        master_sections.get("dudas", "*No disponible.*"),
        "",
        "## 4. Propuesta de Taxonomía",
        "",
        master_sections.get("propuesta_taxonomia", "*No disponible.*"),
        "",
    ]

    if examples_by_category:
        body.extend(_build_examples_section(examples_by_category))

    if hourly_distribution or resolution_by_category:
        body.extend(
            _build_time_section(hourly_distribution, resolution_by_category)
        )

    if escalation_phrases:
        body.extend(_build_escalation_section(escalation_phrases))

    if master_sections.get("sentimiento"):
        body.extend(_build_sentiment_section(master_sections["sentimiento"]))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(front_matter + body))
    return md_path


def _build_examples_section(examples_by_category: dict[str, list[str]]) -> list[str]:
    """Build the 'Ejemplos de Diálogo' section body.

    Snippets are multi-line (each conversation line quoted separately).
    Returns list of markdown lines (without trailing newline).
    """
    lines = ["## 5. Ejemplos de Diálogo", ""]
    lines.append("Muestras reales de cómo los usuarios formularon consultas, agrupadas por categoría del vínculo.")
    lines.append("")
    for category in sorted(examples_by_category.keys()):
        snippets = [s for s in examples_by_category[category] if s]
        if not snippets:
            continue
        lines.append(f"### {category}")
        lines.append("")
        for snip in snippets[:3]:
            snippet_lines = [s for s in snip.splitlines() if s]
            if not snippet_lines:
                continue
            for snippet_line in snippet_lines:
                lines.append(f"> {snippet_line}")
            lines.append("")
    return lines


def compute_hourly_distribution(cursor, sample_phones: list[str]) -> dict[int, int]:
    """Aggregate message count per hour-of-day for the sampled contacts.

    Returns dict mapping hour (0-23) -> message count. Hours with no
    messages are absent from the dict; callers should treat missing as 0.
    """
    if not sample_phones:
        return {}
    placeholders = ",".join("?" * len(sample_phones))
    cursor.execute(
        f"SELECT strftime('%H', timestamp) AS hour, COUNT(*) AS n "
        f"FROM messages WHERE contact_phone IN ({placeholders}) "
        f"GROUP BY hour ORDER BY hour",
        tuple(sample_phones),
    )
    return {int(row[0]): int(row[1]) for row in cursor.fetchall()}


def compute_resolution_by_category(
    metrics: dict, phone_to_category: dict[str, str]
) -> dict[str, float]:
    """Median case duration (days) per category from first_message / last_message.

    Skips contacts with missing or unparseable timestamps.
    """
    durations_by_cat: dict[str, list[float]] = {}
    for phone, cat in phone_to_category.items():
        m = metrics.get(phone, {})
        first = m.get("first_message")
        last = m.get("last_message")
        if not first or not last:
            continue
        try:
            d1 = datetime.fromisoformat(first)
            d2 = datetime.fromisoformat(last)
            days = (d2 - d1).total_seconds() / 86400.0
        except (ValueError, TypeError):
            continue
        if days < 0:
            continue
        durations_by_cat.setdefault(cat, []).append(days)
    return {
        cat: statistics.median(durations)
        for cat, durations in durations_by_cat.items()
        if durations
    }


def extract_escalation_phrases(
    snippets_by_phone: dict[str, str],
    max_per_pattern: int = 3,
) -> list[tuple[str, list[str]]]:
    """Find examples of escalation triggers in conversation snippets.

    For each (pattern, label) in ESCALATION_PATTERNS, scan all snippets
    and return up to ``max_per_pattern`` matching lines that look like
    real chat messages. Only patterns with at least one match are returned.
    """
    results: list[tuple[str, list[str]]] = []
    compiled = [(re.compile(pat, re.IGNORECASE), label) for pat, label in ESCALATION_PATTERNS]
    for regex, label in compiled:
        matches: list[str] = []
        for snippet in snippets_by_phone.values():
            if not snippet or len(matches) >= max_per_pattern:
                continue
            for line in snippet.splitlines():
                line = line.strip()
                if not line or len(line) < 12:
                    continue
                if line.startswith("---"):
                    continue
                if regex.search(line):
                    matches.append(line)
                    break
            if len(matches) >= max_per_pattern:
                break
        if matches:
            results.append((label, matches))
    return results


def _build_time_section(
    hourly_dist: dict[int, int] | None,
    resolution_by_cat: dict[str, float] | None,
) -> list[str]:
    """Build the 'Patrones de Tiempo' section body."""
    lines = ["## 6. Patrones de Tiempo", ""]

    if hourly_dist:
        lines.append("### Distribución de mensajes por hora del día")
        lines.append("")
        total = sum(hourly_dist.values()) or 1
        peak_hour = max(hourly_dist, key=hourly_dist.get)
        lines.append(f"Hora pico: **{peak_hour:02d}:00-{peak_hour:02d}:59** "
                     f"({hourly_dist[peak_hour]} mensajes, "
                     f"{hourly_dist[peak_hour] / total * 100:.1f}% del total).")
        lines.append("")
        lines.append("| Hora | Mensajes | % |")
        lines.append("|------|----------|---|")
        for hour in range(24):
            n = hourly_dist.get(hour, 0)
            pct = (n / total) * 100
            bar = "█" * max(0, int(round(pct / 2)))
            lines.append(f"| {hour:02d}:00 | {n} | {pct:5.1f}% {bar} |")
        lines.append("")

    if resolution_by_cat:
        lines.append("### Mediana de duración del caso por categoría")
        lines.append("")
        lines.append("Mide días entre el primer y último mensaje del contacto en la muestra.")
        lines.append("")
        lines.append("| Categoría | Contactos | Mediana (días) |")
        lines.append("|-----------|-----------|----------------|")
        for cat in sorted(resolution_by_cat.keys()):
            days = resolution_by_cat[cat]
            lines.append(f"| {cat} | (ver JSON) | {days:.1f} |")
        lines.append("")

    return lines


def _build_escalation_section(
    escalations: list[tuple[str, list[str]]] | None,
) -> list[str]:
    """Build the 'Triggers de Escalación' section body.

    Each entry is a (label, matching_lines) pair produced by
    ``extract_escalation_phrases``. Empty list = section omitted.
    """
    if not escalations:
        return []
    lines = ["## 7. Triggers de Escalación", ""]
    lines.append("Frases reales que aparecen cuando un caso sale del alcance del agente actual. Útiles para que el bot sepa cuándo escalar a un humano.")
    lines.append("")
    for label, matches in escalations:
        if not matches:
            continue
        lines.append(f"### {label}")
        lines.append("")
        for match in matches:
            lines.append(f"> {match}")
        lines.append("")
    return lines


def _build_sentiment_section(sentiment_md: str | None) -> list[str]:
    """Build the 'Sentimiento por Vínculo' section body.

    The master pass already returns a formatted markdown block from the LLM;
    we just wrap it with a section header.
    """
    if not sentiment_md or not sentiment_md.strip():
        return []
    lines = ["## 8. Sentimiento por Vínculo", ""]
    lines.append("Tono emocional dominante por tipo de vínculo. Útil para que el bot ajuste el tono (empático vs. ejecutivo) según a quién está respondiendo.")
    lines.append("")
    for line in sentiment_md.splitlines():
        lines.append(line if line.strip() else "")
    return lines


def dual_output_writer(sample, metrics, summaries, db_name, ts, output_dir, stratification=None, total_dataset_size=None, master_sections: dict[str, str] | None = None, master_context: dict | None = None, examples_by_category: dict[str, list[str]] | None = None, hourly_distribution: dict[int, int] | None = None, resolution_by_category: dict[str, float] | None = None, escalation_phrases: list[tuple[str, list[str]]] | None = None):
    """Write dual output: contexto_{ts}.json + contexto_{ts}.md with YAML front-matter.

    stratification: optional dict mapping phone -> tier name ("low" | "mid" | "high").
        Required for the JSON payload's "stratification" field.
    total_dataset_size: optional int with the full dataset size (denominator for the
        30% sampling ratio). When None, defaults to len(sample) which is non-ideal but
        keeps backward compat.
    master_sections: optional 4-key dict with keys ``contexto_general``, ``tematicas``,
        ``dudas``, ``propuesta_taxonomia``. When provided, the MD is written via
        ``escribir_reporte_ejecutivo`` (4-section executive report). When None,
        falls back to the legacy YAML-front-matter-only format for backward compat.
    master_context: optional dict with keys ``summary``, ``generated_at``,
        ``labels_distribution``. For backward compat only; ``master_sections`` is
        preferred and takes precedence for the JSON ``master_context.sections`` field.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    # Build contacts list — same data in both formats
    contacts_out = []
    for idx, item in enumerate(sample):
        # Support both 3-tuple (phone, name, summary_text) and 4-tuple (..., conversation_snippet)
        if len(item) >= 4:
            phone, name, summary_text, conv_snippet = item[0], item[1], item[2], item[3]
        else:
            phone, name, summary_text = item[0], item[1], item[2]
            conv_snippet = None
        m = metrics.get(phone, {
            "total_messages": 0,
            "multimedia_pct": 0.0,
            "from_me_pct": 0.0,
            "first_message": None,
            "last_message": None,
            "media_types": [],
        })
        contact_label = name if name else f"Contacto {phone[-4:]}"
        contacts_out.append({
            "phone": phone,
            "name": name or "",
            "contact_label": contact_label,
            "metrics": m,
            "profile_summary": summary_text or "",
            "conversation_snippet": conv_snippet if conv_snippet else "",
        })

    # Build stratification dict from sample using provided stratification map
    stratification_out = {}
    for phone, *_ in sample:
        stratification_out[phone] = stratification.get(phone, "unknown") if stratification else "unknown"

    # Build master_context for JSON — include sections dict when available
    mc_for_json = dict(master_context) if master_context else {}
    if master_sections:
        mc_for_json["sections"] = master_sections

    # JSON
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", ts),
        "db_name": db_name,
        "total_contacts": total_dataset_size if total_dataset_size is not None else len(sample),
        "sampled_contacts": len(sample),
        "stratification": stratification_out,
        "master_context": mc_for_json if mc_for_json else None,
        "contacts": [
            {
                "phone": c["phone"],
                "name": c["name"],
                "metrics": c["metrics"],
                "profile_summary": c["profile_summary"],
                "conversation_snippet": c.get("conversation_snippet", ""),
            }
            for c in contacts_out
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # MD: use executive report when master_sections available, else legacy YAML-only
    if master_sections:
        labels_dist = (master_context or {}).get("labels_distribution", {})
        escribir_reporte_ejecutivo(
            master_sections=master_sections,
            db_name=db_name,
            sample_size=len(sample),
            ts=ts,
            labels_distribution=labels_dist,
            output_dir=output_dir,
            examples_by_category=examples_by_category,
            hourly_distribution=hourly_distribution,
            resolution_by_category=resolution_by_category,
            escalation_phrases=escalation_phrases,
        )
    else:
        # Legacy YAML-only format (backward compat for callers still using master_context)
        date_str = time.strftime("%Y-%m-%d", ts)
        yaml_header = [
            "---",
            f"date: {date_str}",
            f"title: Reporte de Analisis de Contexto",
            f"db_name: {db_name}",
            f"sample_size: {len(sample)}",
            "tier_method: quantile (P33/P66 inclusive)",
        ]
        if master_context:
            mc = master_context
            labels_dist = mc.get("labels_distribution", {})
            yaml_header.append("master_context:")
            yaml_header.append(f"  generated_at: {mc.get('generated_at', '')}")
            yaml_header.append(f"  database: {db_name}")
            yaml_header.append(f"  sample_size: {len(sample)}")
            yaml_header.append("  labels_distribution:")
            if labels_dist:
                for k, v in labels_dist.items():
                    yaml_header.append(f"    {k}: {v}")
            else:
                yaml_header.append("    {}")
            summary_text = mc.get("summary", "") or ""
            yaml_header.append("  summary: |")
            for line in summary_text.splitlines():
                yaml_header.append(f"    {line}")
        yaml_header.append("---")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(yaml_header))

    return json_path, md_path


def mostrar_progreso(actual, total, prefijo='', sufijo='', longitud=30):
    porcentaje = f"{100 * (actual / float(total)):.1f}"
    llenado = int(longitud * actual // total)
    barra = '█' * llenado + '-' * (longitud - llenado)
    print(f"\r{prefijo}: [{barra}] {porcentaje}% {sufijo}", end='', flush=True)

def remove_think_tags(text):
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def parse_label(summary: str) -> str:
    """Extract the Vínculo Comercial label from a per-contact summary.

    Returns the matched label, or 'Otro' if no label is found.
    Format expected: '*   **Vínculo Comercial:** Cliente' or equivalent.
    """
    match = re.search(r"V[ií]nculo Comercial[:*\s]+([A-Za-zÁÉÍÓÚáéíóú]+)", summary or "")
    if match:
        candidate = match.group(1).strip()
        if candidate in LABELS:
            return candidate
    return "Otro"


def extract_temas(summary: str) -> str | None:
    """Extract the 'Temas Clave:' line content from a per-contact summary.

    Returns the comma-separated keyword list (already trimmed) or None if
    the line is missing or empty. The expected line format is:

        *   **Temas Clave:** pedido, entrega, factura, pago, devolucion

    Behavioural contract:
      - Walks the summary line-by-line.
      - Matches any line that contains "Temas Clave:" (case-insensitive).
      - Returns the substring after the first colon, stripping any leading
        `**` or whitespace, then `.strip()`-ed.
      - Returns None if no matching line is found OR if the matched value is
        empty/whitespace (e.g. "Temas Clave:   ").
    """
    for line in (summary or "").splitlines():
        if re.search(r"temas\s+clave", line, re.IGNORECASE):
            # Find the colon, strip any leading ** and whitespace from what follows.
            _, _, after = line.partition(":")
            value = after.lstrip(" *").strip()
            return value if value else None
    return None


def aggregate_for_master(
    summaries: dict,
    cursor: sqlite3.Cursor,
    phone_to_name: dict,
) -> tuple[dict, str]:
    """Build rich master-call input: per-label profile + raw chat snippet.

    Returns (labels_distribution, master_input_string).
      - labels_distribution: {"Cliente": 20, "Proveedor": 15, ...}
      - master_input_string: ≤ ~600 lines, 6 contacts sampled per label,
        each contact gets its stored `Temas Clave` plus the last ~12
        chat lines extracted from the open cursor.
    """
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for phone, summary in summaries.items():
        if not summary:
            continue
        label = parse_label(summary)
        grouped[label].append((phone, summary))

    distribution = {label: len(items) for label, items in grouped.items()}

    blocks = []
    for label, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        sample = random.sample(items, min(6, len(items)))
        contact_lines = []
        for phone, summary in sample:
            temas = extract_temas(summary) or "(sin temas)"
            # Re-extract from the live cursor; same helper used by the
            # per-contact loop, so the snippet format is consistent.
            muestra = extraer_muestra_contacto(cursor, phone, phone_to_name.get(phone, ""))
            snippet_lines = (muestra or "").splitlines()[-12:]   # last 12 chat lines
            snippet = " | ".join(snippet_lines)[:600]           # hard cap
            contact_lines.append(
                f"  - {phone}\n    Temas: {temas}\n    Snippet: {snippet}"
            )
        header = f"=== {label} ({len(items)} contactos, muestreo {len(sample)}) ==="
        blocks.append(header + "\n" + "\n".join(contact_lines))

    return distribution, "\n\n".join(blocks)


MASTER_SYNTHESIS_PROMPT = (
    "Eres un analista senior de inteligencia comercial B2B. Recibirás una "
    "muestra estratificada de conversaciones reales de WhatsApp, agrupadas "
    "por Vínculo Comercial. Cada contacto incluye Temas Clave (resumidos por "
    "IA) y un fragmento crudo de su conversación.\n\n"
    "Produce un Reporte Ejecutivo estructurado en EXACTAMENTE cinco secciones, "
    "cada una iniciando con su encabezado Markdown en una línea propia. "
    "Respeta los encabezados al pie de la letra (sin renombrar):\n\n"
    "## 1. Contexto General del Entorno\n"
    "[2-3 párrafos: qué hace el negocio, cómo opera, canales principales, "
    "volumen relativo por tipo de vínculo. Tono ejecutivo, sin relleno.]\n\n"
    "## 2. Temáticas o Categorías Más Comunes\n"
    "[Lista priorizada de 5-8 patrones transversales de conversación con "
    "frecuencia relativa estimada. Cada ítem: '- <tema> (<N> contactos)' "
    "seguido de una línea de evidencia del snippet.]\n\n"
    "## 3. Dudas o Consultas Frecuentes\n"
    "[Lista de 5-10 preguntas reales o implícitas que los usuarios hacen. "
    "Esta sección es insumo directo para chatbots. Formato: '- ¿<pregunta>?' "
    "seguido de una línea de contexto breve.]\n\n"
    "## 4. Propuesta de Taxonomía\n"
    "[Árbol jerárquico Markdown con guiones. Máximo 3 niveles de "
    "profundidad. Cada categoría hoja debe tener 2-3 ejemplos reales "
    "derivados de los snippets. Formato:\n"
    "  - <Categoría nivel 1>\n"
    "    - <Subcategoría nivel 2>\n"
    "      - <Tema nivel 3>: ejemplo1, ejemplo2]\n\n"
    "## 5. Distribución de Sentimiento por Vínculo\n"
    "[Para cada Vínculo Comercial de la muestra (Cliente, Empleado, Proveedor, "
    "Otro, etc.), una línea con: '- **<Vínculo>:** dominante=<positivo|neutral|"
    "negativo|frustrado>, secundario=<otro>, evidencia=<una cita textual del "
    "snippet que justifique el dominante>. Si no hay datos suficientes para "
    "alguna categoría, omitir.]\n\n"
    "Restricciones:\n"
    "- Idioma: español.\n"
    "- Tono: ejecutivo, denso, sin disclaimers ni frases de cortesía.\n"
    "- Longitud total: 500-800 palabras. Si te quedas corto, profundiza; "
    "si te excedes, recorta las evidencias a una línea cada una.\n"
    "- NO inventes datos. Cita solo lo respaldado por los snippets.\n"
    "- NO incluyas secciones adicionales fuera de las cinco.\n\n"
    "Muestra de contactos:\n{master_input}"
)


class MasterCallEmptyResponse(ValueError):
    """Raised when the API returns HTTP 200 with an empty/whitespace body.
    Surfaces a non-recoverable-as-success case to the retry layer below."""
    pass


def _parse_master_sections(text: str) -> dict[str, str] | None:
    """Parse the 5-section master response into a dict.

    Splits on ``## 1.``, ``## 2.``, ``## 3.``, ``## 4.``, ``## 5.`` markers,
    normalizes keys to ``contexto_general``, ``tematicas``, ``dudas``,
    ``propuesta_taxonomia``, ``sentimiento``, and returns the dict.

    Returns None if any of the five markers is missing (degrades gracefully
    so the caller can fall back to a fresh master call).
    """
    if not text:
        return None

    # Map section index to canonical key name
    key_map = {
        "1": "contexto_general",
        "2": "tematicas",
        "3": "dudas",
        "4": "propuesta_taxonomia",
        "5": "sentimiento",
    }

    sections: dict[str, str] = {}
    for idx, key in key_map.items():
        marker = f"## {idx}."
        if marker not in text:
            return None  # malformed — degrade gracefully
        _, _, after = text.partition(marker)
        # Next marker (or end of string) terminates this section
        next_markers = [f"## {n}." for n in key_map if n != idx]
        earliest_next = float("inf")
        for nm in next_markers:
            pos = after.find(nm)
            if pos != -1 and pos < earliest_next:
                earliest_next = pos
        content = after[:earliest_next] if earliest_next != float("inf") else after
        sections[key] = content.strip()

    return sections


def master_call_with_retry(master_input: str) -> tuple[dict[str, str] | None, int, int, int]:
    """Returns (master_sections_dict, prompt_tokens, candidate_tokens, total_tokens)
    or (None, 0, 0, 0) after exhausted retries.

    ``master_sections_dict`` has keys: ``contexto_general``, ``tematicas``,
    ``dudas``, ``propuesta_taxonomia``.  Returns ``None`` when the API
    returns an empty/whitespace body or the 4-section parse fails.
    """
    prompt = MASTER_SYNTHESIS_PROMPT.format(master_input=master_input)
    prompt_tokens = candidate_tokens = total_tokens = 0

    for attempt in (1, 2):
        try:
            text, prompt_tokens, candidate_tokens, total_tokens, _ = llamar_api(prompt, raw_prompt=True, fail_fast=False)
            if not text or not text.strip():
                raise MasterCallEmptyResponse("Empty response from master call")
            cleaned = remove_think_tags(text)
            sections = _parse_master_sections(cleaned)
            if sections is None:
                # Malformed response — treat as failure and retry
                raise ValueError("Missing section marker in master response")
            return sections, prompt_tokens, candidate_tokens, total_tokens
        except Exception:
            if attempt == 2:
                print("[WARN] Master synthesis call failed after retry. "
                      "Individual results remain available.")
                return None, 0, 0, 0
            # else: fall through to the next iteration (the retry).
    return None, 0, 0, 0  # unreachable


def is_recent(updated_at: str, hours: int = 24) -> bool:
    """True if the SQLite CURRENT_TIMESTAMP string is within `hours` of now (UTC).

    CRITICAL-3 fix: the previous draft compared `dt.datetime.now()` (local
    time) against a SQLite `CURRENT_TIMESTAMP` value (UTC). On a UTC-3
    deployment, that 3-hour offset caused a 1-hour-old row to appear 4 hours
    old and the resume window to silently shrink. We now force both sides to
    UTC.
    """
    if not updated_at:
        return False
    try:
        import datetime as dt
        # SQLite CURRENT_TIMESTAMP format is 'YYYY-MM-DD HH:MM:SS' in UTC.
        # Attach tzinfo=utc explicitly so the arithmetic below cannot drift
        # to local time.
        stored = dt.datetime.strptime(updated_at[:19], "%Y-%m-%d %H:%M:%S")
        stored = stored.replace(tzinfo=dt.timezone.utc)
        now = dt.datetime.now(dt.timezone.utc)
        age = now - stored
        return age < dt.timedelta(hours=hours)
    except ValueError:
        return False


def seleccionar_base_datos(db_name=None):
    rutas_validas = []
    # Escanear dinámicamente el escritorio (directorio padre de wpp_analytics)
    for folder in base_dir.parent.iterdir():
        try:
            if folder.is_dir() and folder.name != 'wpp_analytics':
                db_file = folder / 'database' / 'whatsapp.sqlite'
                if db_file.exists():
                    rutas_validas.append((folder.name, db_file))
        except PermissionError:
            continue   # skip inaccessible folder, keep scanning siblings

    if not rutas_validas:
        print("[ERROR] No se encontró ninguna base de datos de WhatsApp en el Escritorio.")
        print("Asegúrate de que tus carpetas de WhatsApp tengan el archivo 'database/whatsapp.sqlite' sincronizado.")
        return None

    # If --db was provided, try to match directly without prompting
    if db_name:
        for nombre, db_file in rutas_validas:
            if nombre == db_name:
                print(f"[INFO] Base de datos seleccionada por --db: {nombre}")
                return db_file
        print(f"[ERROR] No se encontró la base de datos '{db_name}' en el Escritorio.")
        print(f"Bases disponibles: {', '.join(n for n, _ in rutas_validas)}")
        return None

    if len(rutas_validas) == 1:
        print(f"[INFO] Detectada base de datos: {rutas_validas[0][0]}")
        return rutas_validas[0][1]

    print("\nSe detectaron múltiples bases de datos disponibles:")
    for idx, (nombre, _) in enumerate(rutas_validas):
        print(f" {idx + 1}. {nombre}")

    while True:
        try:
            opcion = input("\nSelecciona el número de la base de datos a analizar: ").strip()
            idx = int(opcion) - 1
            if 0 <= idx < len(rutas_validas):
                print(f"[INFO] Seleccionada base de datos: {rutas_validas[idx][0]}")
                return rutas_validas[idx][1]
            else:
                print("[ERROR] Opción fuera de rango. Intenta de nuevo.")
        except ValueError:
            print("[ERROR] Entrada inválida. Ingresa un número.")

def obtener_todos_los_contactos(db_path):
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phone, name FROM contacts")
            return cursor.fetchall()
    except Exception as e:
        print(f"[ERROR] Error al leer los contactos de la base de datos: {str(e)}")
        return []

def extraer_muestra_contacto(cursor, phone, name):
    """Extract a per-contact chat sample using the caller's existing cursor.

    Refactored from a self-contained connection-per-contact to a shared cursor
    pattern: procesar_chats_con_ia already opens one connection per run, and
    opening 90+ extra connections for a 90-contact sample is wasteful and risks
    transient locks when writes happen concurrently elsewhere.
    """
    try:
        contact_label = name if name else f"Contacto {phone[-4:]}"
        seen_messages = set()
        
        cursor.execute("""
            SELECT from_me, body, media_name, mime_type 
            FROM messages 
            WHERE contact_phone = ? 
            ORDER BY timestamp ASC
        """, (phone,))
        messages = cursor.fetchall()

        if not messages:
            return None
            
        chat_lines = []
        last_sender = None
        last_msg_parts = []
        
        for from_me, body, media_name, mime_type in messages:
            msg_body = (body or "").strip()
            msg_body = msg_body.replace("\n", " ")
            
            if not msg_body and mime_type:
                media_type = mime_type.split('/')[0].capitalize()
                if mime_type == 'application/pdf':
                    media_type = "PDF"
                msg_body = f"[{media_type} adjunto: {media_name or 'Archivo'}]"
            
            if not msg_body:
                continue
                
            msg_lower = msg_body.lower()
            if "mensaje eliminado" in msg_lower or "archivo omitido" in msg_lower:
                continue
                
            if msg_lower in seen_messages:
                continue
            seen_messages.add(msg_lower)
            
            sender = "Nosotros" if from_me == 1 else "Cliente"
            
            if sender == last_sender:
                last_msg_parts.append(msg_body)
            else:
                if last_sender is not None:
                    chat_lines.append(f"{last_sender}: {'. '.join(last_msg_parts)}")
                last_sender = sender
                last_msg_parts = [msg_body]
                
        if last_sender is not None and last_msg_parts:
            chat_lines.append(f"{last_sender}: {'. '.join(last_msg_parts)}")
            
        if chat_lines:
            lines = [f"--- CONVERSACIÓN CON: {contact_label} (Teléfono: {phone}) ---"]
            # Extraer hasta 40 mensajes consolidados
            lines.extend(chat_lines[-40:])
            return "\n".join(lines)
            
        return None
    except Exception as e:
        print(f"[ERROR] Error al extraer mensajes del contacto {phone}: {str(e)}")
        return None

def registrar_logs_v2(lote_num, db_name, analizados, de_cache, prompt_tokens, candidate_tokens, total_tokens, tiempo_segundos):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_line = (
        f"[{timestamp}] [LOTE {lote_num}] DB={db_name} | Analizados={analizados} | Caché={de_cache} | "
        f"Tokens Entrada={prompt_tokens} | Tokens Salida={candidate_tokens} | Total Tokens={total_tokens} | "
        f"Tiempo Lote={tiempo_segundos:.2f}s\n"
    )
    
    try:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(log_line)
    except Exception as e:
        print(f"[ERROR] No se pudo escribir en logs.txt: {str(e)}")


def registrar_logs_v3(db_name: str, prompt_tokens: int, candidate_tokens: int, total_tokens: int, tiempo_segundos: float):
    """Log the master-call token accounting to logs.txt."""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_line = (
        f"[{timestamp}] [MASTER] DB={db_name} | "
        f"Tokens Entrada={prompt_tokens} | Tokens Salida={candidate_tokens} | "
        f"Total Tokens={total_tokens} | Tiempo={tiempo_segundos:.2f}s\n"
    )
    try:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(log_line)
    except Exception as e:
        print(f"[ERROR] No se pudo escribir en logs.txt: {str(e)}")


def llamar_api(prompt, is_individual=False, fail_fast: bool = False, raw_prompt: bool = False):
    if not api_key:
        print("\n[ERROR] No se ha configurado ninguna clave de API.")
        print("Crea un archivo '.env' en esta carpeta con la clave de API correspondiente.")
        return None, 0, 0, 0, 0

    # Determinar si es una clave compatible con OpenAI/Minimax (empieza con sk-)
    is_openai_compatible = api_key.startswith("sk-")
    active_model = model_name

    # Si es compatible con OpenAI pero el modelo por defecto sigue siendo Gemini, usar MiniMax-M3 por defecto
    if is_openai_compatible:
        if not active_model or "gemini" in active_model.lower():
            active_model = "MiniMax-M3"
    else:
        if not active_model or "gemini" not in active_model.lower():
            active_model = "gemini-2.5-flash"

    # Construir instrucciones
    # raw_prompt=True: el prompt ya viene formateado externamente (e.g. MASTER_SYNTHESIS_PROMPT)
    # is_individual=True: prompt es una conversación individual de WhatsApp
    if raw_prompt:
        instrucciones = prompt
    elif is_individual:
        instrucciones = (
            "Analiza la siguiente conversación de WhatsApp entre 'Nosotros' (Usuario Principal) y un 'Cliente/Contacto' e identifica:\n"
            "1. Vínculo Comercial: Clasifica al contacto en uno de estos 6 valores: "
            f"[{', '.join(LABELS)}].\n"
            "2. Temas Clave: Hasta 5 palabras clave precisas que representen la interacción.\n\n"
            "Devuelve la respuesta en este formato Markdown:\n"
            "*   **Vínculo Comercial:** [uno de los 6 valores]\n"
            "*   **Temas Clave:** [palabra1, palabra2, palabra3, palabra4, palabra5]\n\n"
            f"Conversación:\n{prompt}"
        )
    else:
        raise ValueError("llamar_api: must specify is_individual=True or raw_prompt=True")

    start_time = time.time()
    try:
        if is_openai_compatible:
            # Usar la URL de Minimax por defecto, o la configurada en api_base_url
            url = api_base_url if api_base_url else "https://api.minimax.io/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": active_model,
                "messages": [
                    {"role": "user", "content": instrucciones}
                ],
                "temperature": 0.1,
                "max_tokens": 2048 if is_individual else 4096
            }
            
            req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req) as response:
                elapsed_time = time.time() - start_time
                res_data = json.loads(response.read().decode('utf-8'))
                
                text_output = res_data['choices'][0]['message']['content']
                usage = res_data.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                candidate_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                return text_output, prompt_tokens, candidate_tokens, total_tokens, elapsed_time
        else:
            # Configurar para Google Gemini
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            body = {
                "contents": [
                    {
                        "parts": [
                            {"text": instrucciones}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048 if is_individual else 4096
                }
            }
            
            req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req) as response:
                elapsed_time = time.time() - start_time
                res_data = json.loads(response.read().decode('utf-8'))
                
                text_output = res_data['candidates'][0]['content']['parts'][0]['text']
                metadata = res_data.get('usageMetadata', {})
                prompt_tokens = metadata.get('promptTokenCount', 0)
                candidate_tokens = metadata.get('candidatesTokenCount', 0)
                total_tokens = metadata.get('totalTokenCount', 0)
                
                return text_output, prompt_tokens, candidate_tokens, total_tokens, elapsed_time
            
    except urllib.error.HTTPError as e:
        if fail_fast and e.code in (401, 403):
            sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")
        print(f"\n[ERROR] Error HTTP de la API: {e.code} - {e.reason}")
        try:
            print("Detalles del error:", e.read().decode('utf-8'))
        except Exception:
            pass
        return None, 0, 0, 0, 0
    except Exception as e:
        print(f"\n[ERROR] Error de conexión o procesamiento: {str(e)}")
        return None, 0, 0, 0, 0

def _extract_db_override(argv):
    """Pre-scan argv for `--db NAME` so both interactive and CLI paths honor it
    without parsing the full argparse surface. Returns NAME or None."""
    i = 1
    while i < len(argv):
        if argv[i] == '--db' and i + 1 < len(argv):
            return argv[i + 1]
        # also handle `--db=NAME` style
        if argv[i].startswith('--db='):
            return argv[i].split('=', 1)[1] or None
        i += 1
    return None


def ensure_schema(cursor):
    """Create conversation_summaries table if it doesn't exist.

    Called from both the --with-metrics branch and the interactive branch,
    immediately after opening the connection, so that INSERTs into
    conversation_summaries never fail with `no such table` on a fresh DB.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_phone TEXT NOT NULL,
            period TEXT NOT NULL,
            summary TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(contact_phone) REFERENCES contacts(phone),
            UNIQUE(contact_phone, period)
        )
    """)


def main():
    print("=========================================================")
    print("   Analizador de Contexto Interactivo - wpp_analytics    ")
    print("=========================================================")

    # Honor --db even in the interactive-menu path (avoids forcing CLI mode
    # just to skip the DB prompt).
    db_override = _extract_db_override(sys.argv)
    db_path = seleccionar_base_datos(db_override)
    if not db_path:
        return
        
    db_name = db_path.parent.parent.name

    # -----------------------------------------------------------------------
    # Phase 1: CLI branch — stratified sampling + metrics + dual output
    # Activated ONLY by --with-metrics. Other flags (e.g. --db) are honored
    # transparently in the interactive-menu path via _extract_db_override.
    # -----------------------------------------------------------------------
    if '--with-metrics' in sys.argv:
        args = parse_args()
        if not args.with_metrics:
            # Defensive: should not happen because the guard above already gated
            # the branch, but keeps the contract explicit.
            print("[INFO] --with-metrics es requerido para activar esta ruta.")
            return

        # 1. Fetch all contacts
        todos_contactos = obtener_todos_los_contactos(db_path)
        if not todos_contactos:
            print("[ERROR] No se encontraron contactos en la base de datos.")
            return
        print(f"[INFO] Total de contactos disponibles: {len(todos_contactos)}")

        # 2. Build counts dict via Q1 aggregation
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute("""
            SELECT contact_phone, COUNT(*) AS total_messages
            FROM messages
            GROUP BY contact_phone;
        """)
        counts = {row[0]: row[1] for row in cursor.fetchall()}

        # 3. Compute tier thresholds and bucket contacts
        p33, p66 = compute_tier_thresholds(counts)
        print(f"[INFO] Umbrales de cuantiles — P33: {p33:.1f}, P66: {p66:.1f}")

        tiers = {"low": [], "mid": [], "high": []}
        phone_to_name = {phone: name for phone, name in todos_contactos}
        for phone, count in counts.items():
            tier = assign_tier(count, p33, p66)
            tiers[tier].append(phone)

        for tier_name in ("low", "mid", "high"):
            print(f"[INFO] {tier_name.upper()} tier: {len(tiers[tier_name])} contactos")

        # 4. Stratified sample
        sample_phones = stratified_sample(tiers, budget_ratio=args.sample_size)
        print(f"[INFO] Muestra estratificada: {len(sample_phones)} contactos "
              f"({len(sample_phones)/len(todos_contactos)*100:.1f}% del total)")
        print(f"[INFO] Iniciando análisis LLM de {len(sample_phones)} contactos. "
              f"Esto puede tardar varios minutos si hay chats válidos.")

        # 5. Metrics pass (Q1+Q2)
        metrics = compute_metrics(cursor, sample_phones)

        # 6. LLM loop over sampled contacts via shared function
        sample_with_names = [(p, phone_to_name.get(p, ""), None) for p in sample_phones]
        summaries, _token_totals, _cache_stats = procesar_chats_con_ia(
            sample_with_names,
            db_path,
            options={
                "cursor": cursor,
                "connection": conn,
                "metrics_enabled": True,
                "fail_fast": True,
                "interactive": False,
                "registrar_logs": registrar_logs_v2,
            },
        )

        print()

        # 7. Master Business Context — synthesis call (phase-5)
        master_sections: dict[str, str] | None = None
        master_meta: dict = {}
        master_start_time = time.time()
        if summaries:
            # 7a. Resume check — attempt JSON deserialization first (phase-5 format),
            # then fall back to fresh call for legacy phase-4b rows
            cursor.execute(
                "SELECT summary, updated_at FROM conversation_summaries "
                "WHERE contact_phone = '__MAESTRO__' AND period = 'master'"
            )
            cached = cursor.fetchone()
            needs_fresh_call = True
            if cached and cached[1] and is_recent(cached[1], hours=24):
                saved_summary = cached[0] or ""
                try:
                    master_sections = json.loads(saved_summary)
                    # Schema check: if missing new sections, force fresh call
                    # (avoids stale cache after prompt format changes)
                    _required_keys = {
                        "contexto_general", "tematicas", "dudas",
                        "propuesta_taxonomia", "sentimiento",
                    }
                    if not _required_keys.issubset(master_sections.keys()):
                        print(f"[INFO] Master context cacheado en {cached[1]} pero "
                              f"sin secciones nuevas. Regenerando.")
                        needs_fresh_call = True
                    else:
                        print(f"[INFO] Master context reutilizado de {cached[1]} (<24h).")
                        needs_fresh_call = False
                except json.JSONDecodeError:
                    # Legacy phase-4b row — force fresh call (master_sections stays None,
                    # will be replaced below)
                    print(f"[INFO] Master context en formato legacy (<24h pero no JSON). "
                          "Generando nuevo contexto maestro.")
    distribution, master_input = aggregate_for_master(summaries, cursor, phone_to_name)
    if needs_fresh_call and master_input:
        # 7b. Synthesize (master_input pre-aggregated above)
        master_sections, pt, ct, tt = master_call_with_retry(master_input)
        master_elapsed = time.time() - master_start_time
        if master_sections:
            # Persist as JSON string (not raw text)
            try:
                json_summary = json.dumps(master_sections, ensure_ascii=False)
                cursor.execute("""
                    INSERT OR REPLACE INTO conversation_summaries
                        (contact_phone, period, summary, updated_at)
                    VALUES ('__MAESTRO__', 'master', ?, CURRENT_TIMESTAMP)
                """, (json_summary,))
                conn.commit()
            except Exception as e:
                print(f"[WARN] No se pudo persistir el contexto maestro en SQLite. "
                      "La síntesis se mantiene en memoria para esta corrida.")
            # Log master-call token accounting
            registrar_logs_v3(db_name, pt, ct, tt, master_elapsed)
        else:
            # Master call failed — log failure
            registrar_logs_v3(db_name, 0, 0, 0, master_elapsed)
    if master_sections:
        master_meta = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "labels_distribution": distribution,
        }

        # Build sample_for_output: (phone, name, summary_text, conversation_snippet)
        # conversation_snippet is last ~200 chars of extracted conversation.
        # Must happen BEFORE conn.close() since it uses the live cursor.
        sample_for_output = []
        for p in sample_phones:
            name = phone_to_name.get(p, "")
            summary_text = summaries.get(p)
            muestra = extraer_muestra_contacto(cursor, p, name)
            snippet = ""
            if muestra:
                snippet_lines = muestra.splitlines()[-8:]
                snippet_text = "\n".join(snippet_lines)
                if len(snippet_text) > 500:
                    snippet_text = snippet_text[:500]
                snippet = snippet_text
            sample_for_output.append((p, name, summary_text, snippet))

        # P0.3: time metrics — both queries need the live cursor
        hourly_distribution = compute_hourly_distribution(cursor, sample_phones)
        conn.close()

        # 8. Dual output
        ts = time.localtime()

        # Build flat stratification map (phone -> tier name) for the JSON payload
        stratification_map = {}
        for tier_name, phones in tiers.items():
            for phone in phones:
                stratification_map[phone] = tier_name

        # Build examples_by_category: 2-3 conversation snippets per contact category.
        # Category extracted from the LLM-generated profile_summary (format: **Vínculo X: ...**).
        examples_by_category: dict[str, list[str]] = {}
        category_pattern = re.compile(r'\*\*\s*V[ií]nculo[^:*]+:\*\*\s+(.+?)(?:\n|$)', re.IGNORECASE)
        phone_to_category: dict[str, str] = {}
        for phone, name, summary_text, snippet in sample_for_output:
            if summary_text:
                match = category_pattern.search(summary_text)
                phone_to_category[phone] = (
                    match.group(1).strip() if match else "Sin clasificar"
                )
            if not summary_text or not snippet:
                continue
            match = category_pattern.search(summary_text)
            category = match.group(1).strip() if match else "Sin clasificar"
            bucket = examples_by_category.setdefault(category, [])
            if len(bucket) < 3:
                bucket.append(snippet)
            if all(len(v) >= 3 for v in examples_by_category.values()):
                break

        resolution_by_category = compute_resolution_by_category(
            metrics, phone_to_category
        )

        snippets_by_phone = {
            phone: snippet
            for phone, _name, _summary, snippet in sample_for_output
            if snippet
        }
        escalation_phrases = extract_escalation_phrases(snippets_by_phone)

        # 8a. MD writer (replaces compilar_reporte_local)
        escribir_reporte_ejecutivo(
            master_sections=master_sections or {},
            db_name=db_name,
            sample_size=len(sample_phones),
            ts=ts,
            labels_distribution=master_meta.get("labels_distribution", {}),
            output_dir=args.output_dir,
            examples_by_category=examples_by_category,
            hourly_distribution=hourly_distribution,
            resolution_by_category=resolution_by_category,
            escalation_phrases=escalation_phrases,
        )

        # 8b. JSON writer (unchanged signature, extended payload)
        json_path, _md_path = dual_output_writer(
            sample_for_output, metrics, summaries, db_name, ts, args.output_dir,
            stratification=stratification_map,
            total_dataset_size=len(todos_contactos),
            master_sections=master_sections,
            master_context={
                "summary": (master_sections or {}).get("contexto_general", ""),
                "generated_at": master_meta.get("generated_at", ""),
                "labels_distribution": master_meta.get("labels_distribution", {}),
            },
            examples_by_category=examples_by_category,
            hourly_distribution=hourly_distribution,
            resolution_by_category=resolution_by_category,
            escalation_phrases=escalation_phrases,
        )
        print(f"[INFO] Salida JSON: {json_path.name}")
        print(f"[INFO] Reporte ejecutivo: contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}.md")
        print("[INFO] Proceso completado.")
        return
    # -----------------------------------------------------------------------
    # Default: interactive menu (preserves existing behavior)
    # -----------------------------------------------------------------------
    
    # 1. Obtener todos los contactos
    todos_contactos = obtener_todos_los_contactos(db_path)
    if not todos_contactos:
        print("[ERROR] No se encontraron contactos en la base de datos.")
        return
        
    print(f"[INFO] Total de contactos disponibles para analizar: {len(todos_contactos)}")
    
    # Menú de selección de modo
    print("\nSelecciona el modo de ejecución:")
    print(" 1. Procesar en lotes de 50 (con confirmación manual para continuar)")
    print(" 2. Procesar TODOS los contactos de forma automática (sin detenerse)")
    
    modo_auto = False
    while True:
        opcion = input("\nSelecciona una opción (1 o 2): ").strip()
        if opcion == '1':
            modo_auto = False
            break
        elif opcion == '2':
            modo_auto = True
            break
        else:
            print("[ERROR] Opción inválida. Elige 1 o 2.")
    
    # Ensure conversation_summaries table exists (idempotent, used by both branches)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        ensure_schema(cursor)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WARN] No se pudo asegurar la tabla de resúmenes: {str(e)}")

    # Mezclar aleatoriamente en memoria para una muestra diversa
    random.shuffle(todos_contactos)
    
    total_contactos = len(todos_contactos)
    lote_num = 1
    offset = 0
    lote_size = 50
    
    # Contadores globales de tokens para el resumen final
    global_prompt_tokens = 0
    global_candidate_tokens = 0
    global_total_tokens = 0
    global_start_time = time.time()
    total_nuevos_analizados = 0
    total_usados_cache = 0
    
    while offset < total_contactos:
        limite_lote = min(offset + lote_size, total_contactos)
        contacts_batch = todos_contactos[offset : limite_lote]
        chats_procesados = len(contacts_batch)
        
        print(f"\n--- Procesando Lote #{lote_num} ({chats_procesados} chats, del {offset+1} al {limite_lote}) ---")

        lote_start_time = time.time()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        _summaries_batch, _token_totals, _cache_stats = procesar_chats_con_ia(
            contacts_batch,
            db_path,
            options={
                "cursor": cursor,
                "connection": conn,
                "metrics_enabled": False,
                "fail_fast": False,
                "interactive": True,
                "registrar_logs": None,
            },
        )

        # CRITICAL-1 fix: project per-batch cache stats into run-level globals
        total_usados_cache     += _cache_stats["omitidos_por_cache"]
        total_nuevos_analizados += _cache_stats["nuevos_analizados"]
        global_prompt_tokens += _token_totals["prompt_tokens"]
        global_candidate_tokens += _token_totals["candidate_tokens"]
        global_total_tokens += _token_totals["total_tokens"]
        nuevos_analizados       = _cache_stats["nuevos_analizados"]
        omitidos_por_cache      = _cache_stats["omitidos_por_cache"]
        lote_prompt_tokens      = _token_totals["prompt_tokens"]
        lote_candidate_tokens   = _token_totals["candidate_tokens"]
        lote_total_tokens       = _token_totals["total_tokens"]

        conn.close()
        
        lote_elapsed = time.time() - lote_start_time
        
        # Limpiar barra antes de imprimir estadísticas
        print() # Asegurar nueva línea
        print(f"--- Estadísticas del Lote #{lote_num} ---")
        print(f" Analizados ahora: {nuevos_analizados} | Usados de caché: {omitidos_por_cache}")
        print(f" Tiempo de este lote: {lote_elapsed:.2f} segundos")
        if nuevos_analizados > 0:
            print(f" Tokens de Entrada usados: {lote_prompt_tokens}")
            print(f" Tokens de Salida usados: {lote_candidate_tokens}")
            print(f" Tokens Totales del lote: {lote_total_tokens}")
            
            # Registrar en logs.txt
            registrar_logs_v2(lote_num, db_name, nuevos_analizados, omitidos_por_cache, lote_prompt_tokens, lote_candidate_tokens, lote_total_tokens, lote_elapsed)
        print("------------------------------------------")
        
        offset += lote_size
        if offset >= total_contactos:
            print("\n[INFO] Se han procesado todos los contactos disponibles.")
            break
            
        # Si NO está en modo automático, preguntar al usuario
        if not modo_auto:
            respuesta = input(f"\n¿Deseas continuar con el siguiente lote de 50 chats para expandir el contexto? (s/n): ").strip().lower()
            if respuesta != 's':
                print("[INFO] Análisis finalizado por el usuario.")
                break
        
        lote_num += 1
        
    # Mostrar resumen final al terminar todo
    global_elapsed = time.time() - global_start_time
    print("\n=========================================================")
    print("   ANÁLISIS COMPLETADO CON ÉXITO")
    print("=========================================================")
    print(f" Total de contactos procesados: {total_contactos}")
    print(f" Perfiles nuevos creados en esta corrida: {total_nuevos_analizados}")
    print(f" Perfiles recuperados de caché local: {total_usados_cache}")
    print(f" Tiempo total transcurrido: {global_elapsed:.2f} segundos")
    if total_nuevos_analizados > 0:
        print(f" Tokens de Entrada totales: {global_prompt_tokens}")
        print(f" Tokens de Salida totales: {global_candidate_tokens}")
        print(f" Tokens Totales consumidos: {global_total_tokens}")
    print("=========================================================\n")

if __name__ == "__main__":
    main()
