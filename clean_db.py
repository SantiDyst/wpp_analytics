import sqlite3
import re
import time
from pathlib import Path

base_dir = Path(__file__).parent
report_path = base_dir / 'reporte_contexto_v2.md'

def remove_think_tags(text):
    if not text:
        return text
    # Eliminar etiquetas <think>...</think> y todo su contenido
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # También por seguridad si quedó alguna etiqueta abierta
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()

def seleccionar_base_datos():
    # Buscar base de datos en el escritorio
    for folder in base_dir.parent.iterdir():
        if folder.is_dir() and folder.name != 'wpp_analytics':
            db_file = folder / 'database' / 'whatsapp.sqlite'
            if db_file.exists():
                return db_file
    return None

def main():
    print("[INFO] Iniciando limpieza de bloques de razonamiento en la base de datos...")
    db_path = seleccionar_base_datos()
    if not db_path:
        print("[ERROR] No se encontró la base de datos.")
        return
        
    print(f"[INFO] Conectando a la base de datos: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Leer perfiles actuales
    cursor.execute("SELECT id, contact_phone, summary FROM conversation_summaries WHERE period = 'profile'")
    rows = cursor.fetchall()
    
    print(f"[INFO] Encontrados {len(rows)} perfiles para limpiar.")
    
    # 2. Limpiar y actualizar en la BD
    actualizados = 0
    for row_id, phone, summary in rows:
        cleaned_summary = remove_think_tags(summary)
        if cleaned_summary != summary:
            cursor.execute("UPDATE conversation_summaries SET summary = ? WHERE id = ?", (cleaned_summary, row_id))
            actualizados += 1
            
    conn.commit()
    print(f"[INFO] Se limpiaron y actualizaron {actualizados} perfiles en SQLite.")
    
    # 3. Compilar el nuevo reporte reporte_contexto_v2.md
    print("[INFO] Compilando reporte_contexto_v2.md limpio en español...")
    cursor.execute("""
        SELECT cs.contact_phone, COALESCE(c.name, 'Desconocido') as name, cs.summary 
        FROM conversation_summaries cs
        LEFT JOIN contacts c ON cs.contact_phone = c.phone
        WHERE cs.period = 'profile'
        ORDER BY cs.updated_at DESC
    """)
    profiles = cursor.fetchall()
    conn.close()
    
    report_lines = [
        "---",
        "date: " + time.strftime('%Y-%m-%d'),
        "title: Reporte de Análisis Relacional y Perfiles de WhatsApp (V2)",
        "---",
        "",
        "#### REPORTE CONSOLIDADO DE CONTACTOS",
        f"Total de contactos perfilados en este reporte: {len(profiles)}",
        "",
        "Este reporte recopila la información de tus contactos analizados en la base de datos de forma individual mediante IA, detallando su categoría ocupacional, allegados, tópicos y dinámica relacional.",
        "",
        "---",
        ""
    ]
    
    for idx, (phone, name, summary) in enumerate(profiles):
        contact_label = f"{name} ({phone})" if name != 'Desconocido' else f"Contacto {phone}"
        report_lines.append(f"### #{idx+1} - {contact_label}")
        report_lines.append(summary.strip())
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
        
    print("[OK] Limpieza y compilación finalizada con éxito.")

if __name__ == "__main__":
    main()
