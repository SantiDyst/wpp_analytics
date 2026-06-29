#### Módulo de Analítica y Cerebro de Datos: wpp_analytics

Este repositorio independiente se encarga de analizar los datos históricos guardados en la base de datos local SQLite del proyecto principal `auto_wpp` e integrar servicios de Inteligencia Artificial para el descubrimiento de contexto y análisis de sentimientos.

---

#### Requisitos Previos

1.  **Python 3** instalado en el sistema.
2.  Una base de datos activa con chats guardados en `C:\Users\Atencion online 2\Desktop\auto_wpp\database\whatsapp.sqlite`.
3.  Una clave de API de **Google Gemini** (Gemini API Key).

---

#### Instrucciones de Configuración y Uso

1.  **Configurar Clave de API:**
    *   Crea un archivo llamado **`.env`** en la raíz de esta carpeta (`wpp_analytics`).
    *   Agrega la siguiente línea con tu clave de API de Google Gemini:
        ```text
        GEMINI_API_KEY=tu_clave_aqui
        ```

2.  **Ejecutar el Análisis:**
    *   Abre una terminal en esta carpeta y ejecuta:
        ```powershell
        python analizar_contexto.py
        ```

3.  **Resultado:**
    *   El script extraerá automáticamente una muestra representativa de **100 chats individuales** al azar.
    *   Filtrará redundancias (respuestas automáticas o spam repetido) y codificará los archivos multimedia como marcadores ligeros para ahorrar tokens.
    *   Enviará esta muestra limpia a la API de Gemini (usando librerías estándar nativas sin requerir paquetes externos de pip).
    *   Generará el reporte final de diagnóstico temático en el archivo **`reporte_contexto.md`**.

---

#### Estructura de Archivos del Módulo

*   **`analizar_contexto.py`**: Script principal de procesamiento, extracción y comunicación con la API de Gemini.
*   **`.env`**: Archivo de configuración local (no se debe compartir en repositorios públicos).
*   **`reporte_contexto.md`**: Reporte generado por la IA detallando el contexto general y las categorías de clasificación descubiertas.
