import os
import sqlite3
import json
import urllib.request
import urllib.error
import time
import random
from pathlib import Path

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

def seleccionar_base_datos():
    rutas_validas = []
    try:
        # Escanear dinámicamente el escritorio (directorio padre de wpp_analytics)
        for folder in base_dir.parent.iterdir():
            if folder.is_dir() and folder.name != 'wpp_analytics':
                db_file = folder / 'database' / 'whatsapp.sqlite'
                if db_file.exists():
                    rutas_validas.append((folder.name, db_file))
    except Exception as e:
        print(f"[ERROR] No se pudo escanear el Escritorio en busca de bases de datos: {str(e)}")
        return None
    
    if not rutas_validas:
        print("[ERROR] No se encontró ninguna base de datos de WhatsApp en el Escritorio.")
        print("Asegúrate de que tus carpetas de WhatsApp tengan el archivo 'database/whatsapp.sqlite' sincronizado.")
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

def llamar_api(prompt, current_report=None, is_individual=False):
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
            "1. Categoría Ocupacional: Clasifica al contacto en [Empresario/Emprendedor], [Estudiante], [Desempleado] u [Otro/Indet.] con su respectiva justificación textual basada en evidencias del chat.\n"
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
            "1. Categoría Ocupacional: Clasifica al contacto en [Empresario/Emprendedor], [Estudiante], [Desempleado] o [Otro] con su respectiva justificación textual basada en evidencias del chat.\n"
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
        print(f"\n[ERROR] Error HTTP de la API: {e.code} - {e.reason}")
        try:
            print("Detalles del error:", e.read().decode('utf-8'))
        except:
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

def main():
    print("=========================================================")
    print("   Analizador de Contexto Interactivo - wpp_analytics    ")
    print("=========================================================")
    
    db_path = seleccionar_base_datos()
    if not db_path:
        return
        
    db_name = db_path.parent.parent.name
    
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
        
        lote_prompt_tokens = 0
        lote_candidate_tokens = 0
        lote_total_tokens = 0
        lote_start_time = time.time()
        nuevos_analizados = 0
        omitidos_por_cache = 0
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for idx, (phone, name) in enumerate(contacts_batch):
            contact_label = name if name else f"Contacto {phone[-4:]}"
            global_idx = offset + idx + 1
            
            # Mostrar la barra de carga visual
            sufijo_barra = f"({global_idx}/{total_contactos}) Analizando: {contact_label[:15]}"
            mostrar_progreso(global_idx, total_contactos, prefijo='Progreso General', sufijo=sufijo_barra, longitud=30)
            
            # Verificar si ya existe en la base de datos
            cursor.execute("SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'", (phone,))
            row = cursor.fetchone()
            
            if row:
                omitidos_por_cache += 1
                total_usados_cache += 1
                continue
                
            # Si no existe, extraer sus mensajes y llamar a la API
            muestra = extraer_muestra_contacto(db_path, phone, name)
            if not muestra:
                continue
                
            resultado, p_tok, c_tok, t_tok, t_api = llamar_api(muestra, is_individual=True)
            
            if resultado:
                lote_prompt_tokens += p_tok
                lote_candidate_tokens += c_tok
                lote_total_tokens += t_tok
                
                global_prompt_tokens += p_tok
                global_candidate_tokens += c_tok
                global_total_tokens += t_tok
                
                nuevos_analizados += 1
                total_nuevos_analizados += 1
                
                # Guardar el perfil limpio en SQLite
                perfil_limpio = remove_think_tags(resultado)
                cursor.execute("""
                    INSERT OR REPLACE INTO conversation_summaries (contact_phone, period, summary, updated_at)
                    VALUES (?, 'profile', ?, CURRENT_TIMESTAMP)
                """, (phone, perfil_limpio))
                conn.commit()
                
                # Pequeño retardo entre llamadas a la API para evitar rate limit
                time.sleep(0.5)
            else:
                # Si falla o da error, imprimir nueva línea para no romper la barra
                print(f"\n[WARN] No se pudo analizar el contacto {contact_label}.")
        
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
