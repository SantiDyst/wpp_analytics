import os
import sqlite3
import json
import urllib.request
import urllib.error
import time
import random
from pathlib import Path

# Configurar rutas locales
base_dir = Path(__file__).parent
env_path = base_dir / '.env'
report_path = base_dir / 'reporte_contexto.md'
log_file_path = base_dir / 'logs.txt'

# Cargar API Key y Modelo desde archivo .env si existe
api_key = ""
model_name = "gemini-2.5-flash"
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('GEMINI_API_KEY='):
                api_key = line.split('=', 1)[1].strip()
            elif line.startswith('GEMINI_MODEL='):
                model_name = line.split('=', 1)[1].strip()

# Si no hay API Key en .env, buscar en variables de entorno del sistema
if not api_key:
    api_key = os.environ.get('GEMINI_API_KEY', '')
if not model_name:
    model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')

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

def extraer_muestra_mensajes(db_path, contacts_batch):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        sample_text = []
        seen_messages = set()
        
        for idx, (phone, name) in enumerate(contacts_batch):
            contact_label = name if name else f"Contacto {phone[-4:]}"
            
            cursor.execute("""
                SELECT from_me, body, media_name, mime_type 
                FROM messages 
                WHERE contact_phone = ? 
                ORDER BY timestamp ASC
            """, (phone,))
            messages = cursor.fetchall()
            
            if not messages:
                continue
                
            chat_lines = []
            for from_me, body, media_name, mime_type in messages:
                msg_body = (body or "").strip().replace("\n", " ")
                
                if not msg_body and mime_type:
                    media_type = mime_type.split('/')[0].capitalize()
                    if mime_type == 'application/pdf':
                        media_type = "PDF"
                    msg_body = f"[{media_type} adjunto: {media_name or 'Archivo'}]"
                
                if not msg_body:
                    continue
                
                normalized_msg = msg_body.lower()
                if normalized_msg in seen_messages:
                    continue
                seen_messages.add(normalized_msg)
                
                sender = "Vendedor" if from_me == 1 else "Cliente"
                chat_lines.append(f"{sender}: {msg_body}")
            
            if chat_lines:
                sample_text.append(f"--- CHAT #{idx+1} ({contact_label}) ---")
                # Muestra de hasta 30 mensajes para mayor contexto
                sample_text.extend(chat_lines[-30:])
                sample_text.append("")
                
        conn.close()
        return "\n".join(sample_text)
    except Exception as e:
        print(f"[ERROR] Error al extraer mensajes: {str(e)}")
        return None

def registrar_logs(lote_num, db_name, chats_procesados, prompt_tokens, candidate_tokens, total_tokens, tiempo_segundos, palabras_generadas):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_line = (
        f"[{timestamp}] [LOTE {lote_num}] DB={db_name} | Chats Procesados={chats_procesados} | "
        f"Tokens Entrada={prompt_tokens} | Tokens Salida={candidate_tokens} | Total Tokens={total_tokens} | "
        f"Tiempo API={tiempo_segundos:.2f}s | Palabras Generadas={palabras_generadas}\n"
    )
    
    # Escribir en consola
    print("\n--- Estadísticas del Lote ---")
    print(f" Tiempo de respuesta API: {tiempo_segundos:.2f} segundos")
    print(f" Tokens de Entrada (Prompt): {prompt_tokens}")
    print(f" Tokens de Salida (Respuesta): {candidate_tokens}")
    print(f" Tokens Totales Usados: {total_tokens}")
    print(f" Palabras generadas en el reporte: {palabras_generadas}")
    print("-----------------------------\n")
    
    # Escribir en logs.txt
    try:
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(log_line)
    except Exception as e:
        print(f"[ERROR] No se pudo escribir en logs.txt: {str(e)}")

def llamar_gemini_api(prompt, current_report=None):
    if not api_key:
        print("\n[ERROR] No se ha configurado la clave de API de Gemini.")
        print("Crea un archivo '.env' en esta carpeta con la siguiente línea:")
        print("GEMINI_API_KEY=tu_clave_aqui")
        return None, 0, 0, 0, 0
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    # Construir el prompt de consolidación si ya hay un reporte previo
    if current_report:
        instrucciones = (
            "Actualiza y consolida el reporte anterior de análisis incorporando los nuevos chats. "
            "Fusiona las temáticas comunes, ajusta la taxonomía propuesta si aparecen nuevos tipos de trámites y "
            "elimina duplicaciones. Mantén la estructura y el formato minimalista con títulos ####.\n\n"
            "### REPORTE ANTERIOR:\n"
            f"{current_report}\n\n"
            "### NUEVOS CHATS A INCORPORAR:\n"
            f"{prompt}"
        )
    else:
        instrucciones = (
            "Analiza el siguiente conjunto de conversaciones de WhatsApp de reconocimientos médicos e identifica:\n"
            "1. El contexto general de este entorno (¿de qué tipo de negocio, servicio, entidad o trámite se trata?).\n"
            "2. Las 5 temáticas o categorías de conversación más comunes que se repiten naturalmente.\n"
            "3. Cuáles son las dudas o consultas más frecuentes de los usuarios.\n"
            "4. Una propuesta de taxonomía o categorías específicas que deberíamos utilizar en el futuro para clasificar automáticamente estas conversaciones.\n\n"
            f"Muestra de conversaciones:\n{prompt}"
        )
        
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": instrucciones
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,  # Temperatura analítica estricta
            "maxOutputTokens": 4096
        }
    }
    
    start_time = time.time()
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            elapsed_time = time.time() - start_time
            res_data = json.loads(response.read().decode('utf-8'))
            
            # Extraer el texto generado
            text_output = res_data['candidates'][0]['content']['parts'][0]['text']
            
            # Extraer métricas de tokens si están disponibles
            metadata = res_data.get('usageMetadata', {})
            prompt_tokens = metadata.get('promptTokenCount', 0)
            candidate_tokens = metadata.get('candidatesTokenCount', 0)
            total_tokens = metadata.get('totalTokenCount', 0)
            
            return text_output, prompt_tokens, candidate_tokens, total_tokens, elapsed_time
            
    except urllib.error.HTTPError as e:
        print(f"\n[ERROR] Error HTTP de la API de Gemini: {e.code} - {e.reason}")
        try:
            print("Detalles del error:", e.read().decode('utf-8'))
        except:
            pass
        return None, 0, 0, 0, 0
    except Exception as e:
        print(f"\n[ERROR] Error de conexión o procesamiento: {str(e)}")
        return None, 0, 0, 0, 0

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
    
    # Mezclar aleatoriamente en memoria
    random.shuffle(todos_contactos)
    
    lote_num = 1
    offset = 0
    lote_size = 100
    reporte_actual = None
    
    while offset < len(todos_contactos):
        contacts_batch = todos_contactos[offset : offset + lote_size]
        chats_procesados = len(contacts_batch)
        
        print(f"\n--- Procesando Lote #{lote_num} ({chats_procesados} chats, del {offset+1} al {offset+chats_procesados}) ---")
        
        # Extraer mensajes para este lote (30 mensajes por chat)
        muestra = extraer_muestra_mensajes(db_path, contacts_batch)
        
        if not muestra:
            print("[WARN] No se pudo extraer información para este lote. Saltando...")
            offset += lote_size
            continue
            
        # Llamar a Gemini con temperatura 0.1
        resultado, p_tok, c_tok, t_tok, t_api = llamar_gemini_api(muestra, reporte_actual)
        
        if resultado:
            reporte_actual = resultado
            
            # Guardar en archivo
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(reporte_actual)
                
            palabras_generadas = len(reporte_actual.split())
            
            # Registrar estadísticas
            registrar_logs(lote_num, db_name, chats_procesados, p_tok, c_tok, t_tok, t_api, palabras_generadas)
            print(f"[OK] Reporte actualizado y guardado en: {report_path}")
        else:
            print("[ERROR] Ocurrió un error al procesar con Gemini.")
            break
            
        offset += lote_size
        if offset >= len(todos_contactos):
            print("\n[INFO] Se han procesado todos los contactos disponibles.")
            break
            
        # Preguntar de forma interactiva si desea continuar
        respuesta = input(f"\n¿Deseas continuar con el siguiente lote de 100 chats para expandir el contexto? (s/n): ").strip().lower()
        if respuesta != 's':
            print("[INFO] Análisis finalizado por el usuario.")
            break
            
        lote_num += 1

if __name__ == "__main__":
    main()
