import os
import sys
import sqlite3
import json
import argparse
import statistics
import urllib.request
import urllib.error
import time
import random
from pathlib import Path

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
report_path = output_dir / 'reporte_contexto_v2.md'
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
            if interactive:
                mostrar_progreso(
                    idx + 1, len(sample_list),
                    prefijo="Progreso General",
                    sufijo=f"({idx+1}/{len(sample_list)}) Analizando: {contact_label[:15]}",
                    longitud=30,
                )
            continue

        muestra = extraer_muestra_contacto(db_path, phone, name)
        if not muestra:
            summaries[phone] = None
            if interactive:
                print(f"\n[WARN] No se pudo analizar el contacto {contact_label}.")
            continue

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

            if interactive:
                mostrar_progreso(
                    idx + 1, len(sample_list),
                    prefijo="Progreso General",
                    sufijo=f"({idx+1}/{len(sample_list)}) Analizando: {contact_label[:15]}",
                    longitud=30,
                )
                time.sleep(0.5)
        else:
            summaries[phone] = None
            if interactive:
                print(f"\n[WARN] No se pudo analizar el contacto {contact_label}.")

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


def dual_output_writer(sample, metrics, summaries, db_name, ts, output_dir, stratification=None, total_dataset_size=None):
    """Write dual output: contexto_{ts}.json + contexto_{ts}.md with YAML front-matter.

    stratification: optional dict mapping phone -> tier name ("low" | "mid" | "high").
        Required for the JSON payload's "stratification" field.
    total_dataset_size: optional int with the full dataset size (denominator for the
        30% sampling ratio). When None, defaults to len(sample) which is non-ideal but
        keeps backward compat.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"contexto_{time.strftime('%Y%m%d_%H%M%S', ts)}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    # Build contacts list — same data in both formats
    contacts_out = []
    for idx, (phone, name, summary_text) in enumerate(sample):
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
        })

    # Build stratification dict from sample using provided stratification map
    stratification_out = {}
    if stratification:
        for phone, _, _ in sample:
            stratification_out[phone] = stratification.get(phone, "unknown")
    else:
        for phone, _, _ in sample:
            stratification_out[phone] = "unknown"

    # JSON
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", ts),
        "db_name": db_name,
        "total_contacts": total_dataset_size if total_dataset_size is not None else len(sample),
        "sampled_contacts": len(sample),
        "stratification": stratification_out,
        "contacts": [
            {
                "phone": c["phone"],
                "name": c["name"],
                "metrics": c["metrics"],
                "profile_summary": c["profile_summary"],
            }
            for c in contacts_out
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Markdown with YAML front-matter
    date_str = time.strftime("%Y-%m-%d", ts)
    md_lines = [
        "---",
        f"date: {date_str}",
        f"title: Reporte de Analisis de Contexto",
        f"db_name: {db_name}",
        f"sample_size: {len(sample)}",
        "tier_method: quantile (P33/P66 inclusive)",
        "---",
        "",
        f"## Muestra Estratificada — {len(sample)} contactos",
        "",
        "Este reporte fue generado automaticamente con muestreo estratificado por volumen de mensajes.",
        "",
    ]
    for idx, (phone, name, summary_text) in enumerate(sample):
        m = metrics.get(phone, {
            "total_messages": 0,
            "multimedia_pct": 0.0,
            "from_me_pct": 0.0,
            "first_message": None,
            "last_message": None,
            "media_types": [],
        })
        contact_label = name if name else f"Contacto {phone[-4:]}"
        md_lines.append(f"### #{idx+1} - {contact_label} ({phone})")
        md_lines.append("")
        md_lines.append("| Métrica | Valor |")
        md_lines.append("|---------|------|")
        md_lines.append(f"| Mensajes totales | {m['total_messages']} |")
        md_lines.append(f"| Mensajes multimedia (%%) | {m['multimedia_pct']} |")
        md_lines.append(f"| Mensajes enviados por mí (%%) | {m['from_me_pct']} |")
        md_lines.append(f"| Primer mensaje | {m['first_message'] or 'N/A'} |")
        md_lines.append(f"| Último mensaje | {m['last_message'] or 'N/A'} |")
        md_lines.append(f"| Tipos de medio | {', '.join(m['media_types']) or 'Ninguno'} |")
        md_lines.append("")
        if summary_text:
            md_lines.append("**Perfil:**")
            md_lines.append(summary_text.strip())
        else:
            md_lines.append("*Sin resumen disponible.*")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return json_path, md_path


def mostrar_progreso(actual, total, prefijo='', sufijo='', longitud=30):
    porcentaje = f"{100 * (actual / float(total)):.1f}"
    llenado = int(longitud * actual // total)
    barra = '█' * llenado + '-' * (longitud - llenado)
    print(f"\r{prefijo}: [{barra}] {porcentaje}% {sufijo}", end='', flush=True)

def remove_think_tags(text):
    import re
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


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
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT phone, name FROM contacts")
        contacts = cursor.fetchall()
        conn.close()
        return contacts
    except Exception as e:
        print(f"[ERROR] Error al leer los contactos de la base de datos: {str(e)}")
        return []

def extraer_muestra_contacto(db_path, phone, name):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        contact_label = name if name else f"Contacto {phone[-4:]}"
        seen_messages = set()
        
        cursor.execute("""
            SELECT from_me, body, media_name, mime_type 
            FROM messages 
            WHERE contact_phone = ? 
            ORDER BY timestamp ASC
        """, (phone,))
        messages = cursor.fetchall()
        
        conn.close()
        
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

def llamar_api(prompt, current_report=None, is_individual=False, fail_fast: bool = False):
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
    if is_individual:
        instrucciones = (
            "Analiza la siguiente conversación de WhatsApp entre 'Nosotros' (Usuario Principal) y un 'Cliente/Contacto' e identifica:\n"
            "1. Categoría Ocupacional: Clasifica al contacto en [Empresario/Emprendedor], [Estudiante], [Desempleado], [Personal] u [Otro/Indet.] con su respectiva justificación textual basada en evidencias del chat.\n"
            "2. Allegados y Círculo Social: Identifica nombres de terceros mencionados en el chat y su parentesco o vínculo con el contacto (ej. esposa, hijo, socio, amigo).\n"
            "3. Temas Principales: Los 3 asuntos o tópicos de conversación más recurrentes entre ambos.\n"
            "4. Dinámica Relacional: Define el tipo de relación (comercial, familiar, amistosa) y el tono dominante de la interacción (formal, casual, tenso, cordial).\n\n"
            "Devuelve la respuesta utilizando exactamente el siguiente formato Markdown para que quede limpio y rico en detalles:\n"
            "*   **Categoría Ocupacional:** [Categoría] (Justificación descriptiva)\n"
            "*   **Allegados:** [Vínculos y nombres de terceros, o 'Ninguno detectado']\n"
            "*   **Temas Principales:** [Temas]\n"
            "*   **Dinámica Relacional:** [Relación y tono]\n\n"
            f"Conversación:\n{prompt}"
        )
    elif current_report:
        instrucciones = (
            "Actualiza y consolida el reporte anterior de análisis relacional incorporando los nuevos chats. "
            "Fusiona las temáticas comunes, refina las clasificaciones de los contactos y agrega los nuevos "
            "contactos identificados con su respectivo perfil sin duplicar información. "
            "Mantén la estructura y el formato minimalista con títulos ####.\n\n"
            "### REPORTE ANTERIOR:\n"
            f"{current_report}\n\n"
            "### NUEVOS CHATS A INCORPORAR:\n"
            f"{prompt}"
        )
    else:
        instrucciones = (
            "Analiza el siguiente conjunto de conversaciones de WhatsApp de diversos contactos e identifica para cada uno:\n"
            "1. Categoría Ocupacional: Clasifica al contacto en [Empresario/Emprendedor], [Estudiante], [Desempleado], [Personal] o [Otro] con su respectiva justificación textual basada en evidencias del chat.\n"
            "2. Allegados y Círculo Social: Identifica nombres de terceros mencionados y su parentesco o vínculo con el contacto (ej. esposa, hijo, socio, amigo).\n"
            "3. Temas Principales: Los 3 asuntos o tópicos de conversación más recurrentes.\n"
            "4. Dinámica Relacional: Define el tipo de relación (comercial, familiar, amistosa) y el tono dominante de la interacción (formal, casual, tenso, cordial).\n\n"
            "Devuelve la información estructurada por contacto de forma clara y minimalista usando títulos #### para cada sección.\n\n"
            f"Muestra de conversaciones:\n{prompt}"
        )

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

def compilar_reporte_local(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Leer todos los perfiles guardados de la BD ordenados por actualización o nombre
        cursor.execute("""
            SELECT cs.contact_phone, COALESCE(c.name, 'Desconocido') as name, cs.summary 
            FROM conversation_summaries cs
            LEFT JOIN contacts c ON cs.contact_phone = c.phone
            WHERE cs.period = 'profile'
            ORDER BY cs.updated_at DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        report_lines = [
            "---",
            "date: " + time.strftime('%Y-%m-%d'),
            "title: Reporte de Análisis Relacional y Perfiles de WhatsApp (V2)",
            "---",
            "",
            "#### REPORTE CONSOLIDADO DE CONTACTOS",
            f"Total de contactos perfilados en este reporte: {len(rows)}",
            "",
            "Este reporte recopila la información de tus contactos analizados en la base de datos de forma individual mediante IA, detallando su categoría ocupacional, allegados, tópicos y dinámica relacional.",
            "",
            "---",
            ""
        ]

        for idx, (phone, name, summary) in enumerate(rows):
            contact_label = f"{name} ({phone})" if name != 'Desconocido' else f"Contacto {phone}"
            report_lines.append(f"### #{idx+1} - {contact_label}")
            report_lines.append(summary.strip())
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
            
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
            
    except Exception as e:
        print(f"[ERROR] No se pudo compilar el reporte local: {str(e)}")

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
              f"({len(sample_phones)/len(todos_contactos)*100:.1f}%% del total)")

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

        # 7. Dual output (phase-4a: master context synthesis added in phase-4b)
        conn.close()
        ts = time.localtime()

        # Build flat stratification map (phone -> tier name) for the JSON payload
        stratification_map = {}
        for tier_name, phones in tiers.items():
            for phone in phones:
                stratification_map[phone] = tier_name

        json_path, md_path = dual_output_writer(
            sample_with_names, metrics, summaries, db_name, ts, args.output_dir,
            stratification=stratification_map,
            total_dataset_size=len(todos_contactos),
        )
        print(f"[INFO] Salida JSON: {json_path.name}")
        print(f"[INFO] Salida MD:   {md_path.name}")
        print(f"[INFO] Reporte legacy (reporte_contexto_v2.md) también actualizado.")
        compilar_reporte_local(db_path)
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
    
    # Asegurar que exista la tabla de resúmenes (por si acaso no se creó)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
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
        
        # Compilar el reporte completo leyendo TODOS los perfiles de la BD local
        compilar_reporte_local(db_path)
        
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
    print(f" Reporte unificado disponible en: {report_path.name}")
    print("=========================================================\n")

if __name__ == "__main__":
    main()
