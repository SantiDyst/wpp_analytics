#### Diagnóstico y Propuesta de Optimización de Base de Datos (`sql_features`)

Este documento analiza el esquema actual de SQLite de la solución de WhatsApp y propone una arquitectura optimizada a largo plazo para asegurar que las consultas y búsquedas semánticas realizadas por agentes de IA sean eficientes, rápidas y no consuman memoria de disco innecesaria.

---

#### 1. Estado y Estructura Actual

El esquema actual (definido en `src/config/database.js`) está estructurado de la siguiente forma:

*   **Tabla `contacts`:** Almacena los números y nombres de agenda.
*   **Tabla `messages`:** Almacena el cuerpo de los mensajes y los metadatos de los adjuntos, incluyendo el binario completo del archivo en la columna `media_data` (tipo `BLOB`).
*   **Optimizaciones activas:** Modo de registro Write-Ahead Logging (`WAL`), tiempo de espera de bloqueo de base de datos (`busy_timeout=5000`), e índices en `(contact_phone, timestamp)` y `timestamp`.

#### Puntos Fuertes del Diseño Actual:
*   Los índices garantizan velocidad en ordenamiento cronológico y filtros por cliente.
*   El modo `WAL` evita que las escrituras del bot bloqueen las lecturas de los reportes.

---

#### 2. Cuello de Botella Detectado: Archivos Binarios en la Tabla Principal

El almacenamiento de archivos multimedia (`media_data` de tipo `BLOB` que contiene fotos, audios y documentos PDFs) dentro de la misma tabla `messages` provoca que cada fila tenga un tamaño en bytes sumamente heterogéneo y potencialmente enorme (hasta 15 MB por mensaje).

#### Impacto en el Rendimiento:
1.  **Búsquedas de Texto Lentas:** Al hacer búsquedas de palabras clave (ej. buscar "presupuesto" con `LIKE '%presupuesto%'`), SQLite realiza un *Full Table Scan* (escaneo completo de la tabla). Al tener binarios pesados incrustados en las filas, SQLite debe cargar megabytes de datos innecesarios a la memoria RAM desde el disco para procesar la búsqueda.
2.  **Crecimiento Descontrolado del Archivo:** El archivo `.sqlite` crece rápidamente en tamaño (superando los 300MB en pocos días), dificultando copias de seguridad, sincronizaciones o transferencias.

---

#### 3. Propuesta de Arquitectura Optimizada (Versión 2.0)

Para garantizar un rendimiento óptimo a largo plazo, se proponen dos alternativas de optimización:

#### Propuesta A: Almacenamiento de Multimedia en Disco (Altamente Recomendada)
Extraer los binarios del archivo SQLite y guardarlos de forma local en una carpeta física (`public/media/` o `database/media/`), almacenando únicamente la ruta del archivo en la base de datos.

*   **Nuevo esquema para `messages`:**
    ```sql
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        whatsapp_message_id TEXT UNIQUE NOT NULL,
        contact_phone TEXT NOT NULL,
        from_me INTEGER NOT NULL,
        body TEXT,
        media_path TEXT DEFAULT NULL, -- Ruta local del archivo en disco (ej. "media/12345.jpg")
        media_name TEXT DEFAULT NULL,
        mime_type TEXT DEFAULT NULL,
        timestamp DATETIME NOT NULL,
        FOREIGN KEY(contact_phone) REFERENCES contacts(phone)
    );
    ```
*   **Resultado:** El archivo `.sqlite` se reducirá en un 95% de tamaño, conteniendo únicamente texto. Las búsquedas serán instantáneas y el disco almacenará las imágenes/audios en su sistema de archivos nativo, que es mucho más eficiente para archivos pesados.

#### Propuesta B: Normalización por Tabla de Adjuntos Separada
Si es estrictamente necesario mantener todo dentro del mismo archivo de base de datos, se debe normalizar el esquema moviendo la columna `media_data` a una tabla secundaria.

*   **Esquema Normalizado:**
    ```sql
    -- Tabla principal ligera para chats y búsquedas de texto rápidas
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        whatsapp_message_id TEXT UNIQUE NOT NULL,
        contact_phone TEXT NOT NULL,
        from_me INTEGER NOT NULL,
        body TEXT,
        mime_type TEXT DEFAULT NULL,
        timestamp DATETIME NOT NULL,
        FOREIGN KEY(contact_phone) REFERENCES contacts(phone)
    );

    -- Tabla secundaria pesada (solo se consulta al requerir ver/abrir el multimedia)
    CREATE TABLE IF NOT EXISTS message_attachments (
        message_id INTEGER PRIMARY KEY,
        media_data BLOB NOT NULL,
        media_name TEXT DEFAULT NULL,
        FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
    );
    ```

---

#### 4. Búsqueda de Texto Avanzada: SQLite FTS5

Para que las búsquedas por palabras clave de la IA sean instantáneas (incluso con millones de mensajes), se puede habilitar la extensión nativa **FTS5** (Full-Text Search) de SQLite.

FTS5 crea una tabla virtual indexada para texto que funciona de manera similar a un motor de búsqueda como Google o Elasticsearch:

```sql
-- Crear tabla virtual FTS5
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    message_id UNINDEXED,
    body
);

-- Consulta ultra rápida en milisegundos para buscar palabras clave
SELECT message_id FROM messages_fts WHERE messages_fts MATCH 'presupuesto';
```
*(Esta configuración permite buscar prefijos, raíces de palabras y consultas complejas de texto de manera extremadamente eficiente sin sobrecargar la CPU).*
