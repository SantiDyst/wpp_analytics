import os
import sys
import sqlite3
import json
import argparse
import urllib.request
import urllib.error
import re
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

base_dir = Path(__file__).parent.parent
env_path = base_dir / '.env'

TAXONOMIA = """
LICENCIAS_MEDICAS
  SOLICITUD_TURNO: SOL_TURNO_NUEVO | SOL_TURNO_REPROGRAMAR | SOL_TURNO_INFO_REQUISITOS
  SEGUIMIENTO_Y_ESTADO: SEG_TURNO_MEDICO_NO_CONTACTA | SEG_ACTA_NO_GENERADA | SEG_DEMORA_GENERAL
  RECEPCION_ACTA: REC_ACTA_NO_RECIBIDA | REC_ACTA_SOLICITAR_REENVIO | REC_ACTA_PROBLEMAS_ACCESO
  CORRECCION_ACTA: CORR_ACTA_FECHAS_DIAS | CORR_ACTA_DATOS_PERSONALES | CORR_ACTA_ARTICULO_TIPO_LICENCIA | CORR_ACTA_CRITERIO_MEDICO
  REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA: REQ_PROC_DOCUMENTACION_GENERAL | REQ_PROC_MODALIDAD_PRESENCIAL_ONLINE | REQ_PROC_LICENCIA_ESPECIFICA | REQ_PROC_ALTA_LABORAL
  PROBLEMAS_EN_GESTION: PROB_GEST_LICENCIA_DENEGADA | PROB_GEST_SITUACION_IRREGULAR | PROB_GEST_ERROR_PLATAFORMA
INFORMACION_AGENTE: INFO_AGENTE_ALTA_NUEVO_REGISTRO | INFO_AGENTE_ACTUALIZACION_DATOS
CONSULTAS_VARIAS: CONS_VARIAS_GENERAL | CONS_VARIAS_QUEJA_RECLAMO | CONS_VARIAS_FUERA_DE_AMBITO
"""

PALABRAS_DOMINIO = [
    "acta", "actas", "turno", "turnos", "medico", "médico", "fiscal", "fiscales",
    "licencia", "licencias", "recibo digital", "reenvio", "reenvío", "correo",
    "certificado", "maternidad", "art. 12", "art. 27", "art 12", "art 27",
    "alta", "salud mental", "reprogramar", "docente", "agente", "capital",
    "interior", "reconocimiento", "reconocimientos", "junta medica", "junta médica",
    "cbu", "dni", "presupuesto"
]

api_key = ""
model_name = "gemini-2.5-flash"
api_base_url = ""

if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip()
            if key in ('GEMINI_API_KEY', 'MINIMAX_API_KEY', 'API_KEY'):
                api_key = val
            elif key in ('GEMINI_MODEL', 'MINIMAX_MODEL', 'MODEL_NAME'):
                model_name = val
            elif key in ('API_BASE_URL', 'BASE_URL'):
                api_base_url = val

if not api_key:
    api_key = os.environ.get('GEMINI_API_KEY', os.environ.get('MINIMAX_API_KEY', os.environ.get('API_KEY', '')))
if not api_base_url:
    api_base_url = os.environ.get('API_BASE_URL', os.environ.get('BASE_URL', ''))


def remove_think_tags(text):
    if not text:
        return text
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def seleccionar_db(nombre_db=None):
    candidatos = []
    for folder in base_dir.parent.iterdir():
        if folder.is_dir() and folder.name != 'wpp_analytics':
            db_file = folder / 'database' / 'whatsapp.sqlite'
            if db_file.exists():
                candidatos.append((folder.name, db_file))

    if not candidatos:
        print("[ERROR] No se encontraron bases de datos en el Escritorio.")
        return None, None

    if nombre_db:
        for nombre, ruta in candidatos:
            if nombre == nombre_db:
                return nombre, ruta
        print(f"[ERROR] No se encontró la base '{nombre_db}'. Disponibles: {[n for n,_ in candidatos]}")
        return None, None

    if len(candidatos) == 1:
        return candidatos[0]

    print("Bases de datos disponibles:")
    for idx, (nombre, _) in enumerate(candidatos):
        print(f"  {idx + 1}. {nombre}")
    while True:
        try:
            opcion = int(input("Selecciona el número de la base: ").strip()) - 1
            if 0 <= opcion < len(candidatos):
                return candidatos[opcion]
        except ValueError:
            pass
        print("[ERROR] Opción inválida.")


def buscar_keyword(db_path, query, limit):
    patron = f"%{query}%"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.timestamp, c.name, m.contact_phone, m.from_me, m.body
        FROM messages m
        LEFT JOIN contacts c ON m.contact_phone = c.phone
        WHERE m.body LIKE ?
        ORDER BY m.timestamp DESC
        LIMIT ?
    """, (patron, limit))
    rows = cursor.fetchall()
    conn.close()
    return rows


def pre_filtrar_semantic(db_path, query, limit):
    palabras = re.findall(r'\w+', query.lower())
    palabras = [p for p in palabras if len(p) >= 3]
    extras = [p for p in PALABRAS_DOMINIO if p in query.lower()]
    candidatos = list(dict.fromkeys(palabras + extras))
    if not candidatos:
        candidatos = [query]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    placeholders = ' OR '.join(['m.body LIKE ?'] * len(candidatos))
    params = [f"%{p}%" for p in candidatos]

    cursor.execute(f"""
        SELECT DISTINCT m.contact_phone, c.name
        FROM messages m
        LEFT JOIN contacts c ON m.contact_phone = c.phone
        WHERE {placeholders}
        ORDER BY m.timestamp DESC
        LIMIT ?
    """, (*params, limit))
    contactos = cursor.fetchall()
    conn.close()
    return contactos


def extraer_chat(db_path, phone, ultimos=30):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT from_me, body, timestamp
        FROM messages
        WHERE contact_phone = ? AND body IS NOT NULL AND body != ''
        ORDER BY timestamp ASC
    """, (phone,))
    rows = cursor.fetchall()
    conn.close()

    seen = set()
    lines = []
    for from_me, body, ts in rows:
        body_clean = (body or "").replace("\n", " ").strip()
        if not body_clean or body_clean.lower() in seen:
            continue
        if "mensaje eliminado" in body_clean.lower() or "archivo omitido" in body_clean.lower():
            continue
        seen.add(body_clean.lower())
        sender = "Nosotros" if from_me == 1 else "Cliente"
        lines.append(f"[{ts}] {sender}: {body_clean}")

    return "\n".join(lines[-ultimos:])


def llamar_api(prompt):
    if not api_key:
        print("[ERROR] No hay API key configurada en .env")
        return None

    is_openai_compatible = api_key.startswith("sk-")
    active_model = model_name
    if is_openai_compatible:
        if not active_model or "gemini" in active_model.lower():
            active_model = "MiniMax-M3"
    else:
        if not active_model or "gemini" not in active_model.lower():
            active_model = "gemini-2.5-flash"

    try:
        if is_openai_compatible:
            url = api_base_url if api_base_url else "https://api.minimax.io/v1/chat/completions"
            body = {
                "model": active_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 4096,
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={api_key}"
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
            }
            headers = {"Content-Type": "application/json"}

        req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode('utf-8'))
            if is_openai_compatible:
                return data['choices'][0]['message']['content']
            return data['candidates'][0]['content']['parts'][0]['text']
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code}: {e.reason}")
        try:
            print(e.read().decode('utf-8'))
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def modo_keyword(db_path, query, limit):
    print(f"\n[INFO] Búsqueda KEYWORD: '{query}' (límite: {limit})")
    rows = buscar_keyword(db_path, query, limit)
    if not rows:
        print("[INFO] No se encontraron coincidencias.")
        return

    print(f"\n[OK] {len(rows)} resultado(s):\n")
    for ts, name, phone, from_me, body in rows:
        remitente = "NOSOTROS" if from_me == 1 else "CLIENTE"
        nombre = name or f"Contacto {phone[-4:]}"
        body_short = (body[:160] + "...") if len(body) > 160 else body
        print(f"• {ts} | {nombre} ({phone}) [{remitente}]")
        print(f"  └─ {body_short}\n")


def modo_semantic(db_path, query, limit, classify):
    print(f"\n[INFO] Búsqueda SEMANTIC: '{query}' (límite contactos: {limit})")
    contactos = pre_filtrar_semantic(db_path, query, limit)
    if not contactos:
        print("[INFO] No se encontraron contactos candidatos.")
        return

    print(f"[INFO] {len(contactos)} contacto(s) candidato(s). Consultando IA...\n")

    instrucciones_extra = ""
    if classify:
        instrucciones_extra = (
            "Además, clasifica cada coincidencia encontrada según la siguiente taxonomía del dominio "
            "(Reconocimientos Médicos - licencias para empleados públicos):\n\n"
            f"{TAXONOMIA}\n"
            "Indica la ruta taxonómica exacta (ej. LICENCIAS_MEDICAS > RECEPCION_ACTA > REC_ACTA_NO_RECIBIDA).\n"
        )

    prompt_base = (
        f"Consulta del usuario: \"{query}\"\n\n"
        "A continuación hay extractos de conversaciones de WhatsApp con distintos contactos. "
        "Para cada contacto indica si la conversación contiene información relevante a la consulta del usuario. "
        "Si la hay, extrae el dato específico pedido (DNI, nombre, fecha, monto, CBU, etc.) citando el fragmento textual entre comillas.\n"
        f"{instrucciones_extra}\n"
        "Formato de salida por contacto (usá '---' como separador):\n"
        "### Contacto: <nombre> (<teléfono>)\n"
        "- Coincidencia: SÍ/NO\n"
        "- Dato extraído: <el dato pedido o 'N/A'>\n"
        "- Fragmento textual: \"<cita literal>\"\n"
        + ("- Clasificación: <ruta_taxonómica o 'N/A'>\n" if classify else "")
    )

    resultados_texto = []
    for phone, name in contactos:
        chat = extraer_chat(db_path, phone)
        if not chat:
            continue
        nombre = name or f"Contacto {phone[-4:]}"
        resultados_texto.append(f"--- CONVERSACIÓN CON: {nombre} (Tel: {phone}) ---\n{chat}")

    if not resultados_texto:
        print("[INFO] Ningún contacto tenía texto útil para analizar.")
        return

    prompt = prompt_base + "\n" + "\n\n".join(resultados_texto)

    respuesta = llamar_api(prompt)
    if not respuesta:
        return

    print(f"[OK] Respuesta de la IA (modelo: {model_name}):\n")
    print(remove_think_tags(respuesta))
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Buscador dinámico de chats en la base de datos de WhatsApp (auto_wpp)."
    )
    parser.add_argument("--db", help="Nombre de la carpeta de la base de datos (ej. auto_wpp). Si se omite, se detecta o se pregunta.")
    parser.add_argument("--mode", required=True, choices=["keyword", "semantic"], help="Modo de búsqueda.")
    parser.add_argument("--query", required=True, help="Texto o dato a buscar.")
    parser.add_argument("--limit", type=int, default=50, help="Límite de resultados (default 50).")
    parser.add_argument("--classify", action="store_true", help="(semantic) Clasificar con la taxonomía del reporte_contexto.md.")
    args = parser.parse_args()

    nombre_db, db_path = seleccionar_db(args.db)
    if not db_path:
        return

    print(f"[INFO] Base de datos seleccionada: {nombre_db}")

    if args.mode == "keyword":
        modo_keyword(db_path, args.query, args.limit)
    else:
        classify = args.classify or True
        modo_semantic(db_path, args.query, args.limit, classify)


if __name__ == "__main__":
    main()