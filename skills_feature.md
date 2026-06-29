#### Plan de Implementación: Skill de Asistente de WhatsApp (`whatsapp_assistant`)

Este documento detalla el diseño, la arquitectura y los pasos para empaquetar las herramientas de consulta, búsqueda y análisis de bases de datos de WhatsApp en una Skill nativa compatible con agentes de IA (como Hermes o Antigravity).

---

#### 1. Estructura de Carpetas de la Skill

Para registrar la Skill de forma nativa en el sistema del agente, se creará un directorio de Skill dentro de las rutas de personalización del agente (`.agents/skills/whatsapp_assistant/` o en la ruta de configuración global de Gemini):

```text
skills/
└── whatsapp_assistant/
    ├── SKILL.md                 # Instrucciones, metadatos y "recetas" para la IA
    └── scripts/
        ├── analizar_contexto.py # Análisis general y taxonomía (existente)
        └── buscar_datos.py      # Buscador dinámico y multipropósito por argumentos (nuevo)
```

---

#### 2. Definición del Buscador Dinámico (`buscar_datos.py`)

Este script actuará como un motor de búsqueda parametrizado para la IA. Utilizará `argparse` en Python para aceptar argumentos en consola:

*   **Parámetros aceptados:**
    *   `--db`: Nombre de la base de datos a analizar (ej. `auto_wpp` o `auto_wpp_2`).
    *   `--mode`: Modo de búsqueda, que puede ser `keyword` (búsqueda exacta por SQL) o `semantic` (extracción inteligente con IA).
    *   `--query`: El texto o dato a buscar (ej. "presupuesto", "DNI de Juan Pérez", "reunión pendiente").

*   **Lógica de Operación:**
    *   **Modo Keyword (`--mode keyword`):** Realiza un filtro SQL ultra rápido utilizando `LIKE` sobre el cuerpo de los mensajes. Es ideal para buscar términos específicos como "presupuesto", "CBU", "descuento", etc.
    *   **Modo Semántico (`--mode semantic`):** Realiza un filtro SQL preliminar de mensajes sospechosos o chats relevantes y luego los procesa con la API de Gemini (Temperatura 0.1) aplicando un prompt dinámico basado en tu consulta (ej. *"De los siguientes mensajes, extrae el DNI del cliente mencionado"* o *"Identifica los detalles de la reunión acordada"*).

---

#### 3. Estructura del Archivo de Configuración (`SKILL.md`)

Este archivo enseña a la IA a invocar el script dinámico pasando los argumentos correctos según lo que tú le pidas en el chat:

```yaml
---
name: whatsapp_assistant
description: Permite al agente interactuar con las bases de datos de WhatsApp del Escritorio para generar reportes generales o realizar búsquedas específicas (DNI, presupuestos, citas, clientes).
---
```

#### Instrucciones del Asistente (Recetas de Comandos):
*   **Si el usuario pide buscar un término exacto (ej. "presupuesto"):**
    La IA ejecutará: `python scripts/buscar_datos.py --db "<nombre_db>" --mode "keyword" --query "presupuesto"`
*   **Si el usuario pide extraer un dato semántico (ej. "el DNI de Carlos" o "citas de la otra semana"):**
    La IA ejecutará: `python scripts/buscar_datos.py --db "<nombre_db>" --mode "semantic" --query "DNI de Carlos"`

---

#### 4. Pasos para la Puesta en Marcha

#### Paso 1: Mover y crear los scripts
Mover `analizar_contexto.py` y crear el buscador dinámico `buscar_datos.py` con soporte para argumentos en `skills/whatsapp_assistant/scripts/`.

#### Paso 2: Crear el archivo de configuración `SKILL.md`
Crear `SKILL.md` en la raíz de la Skill documentando las reglas de invocación para la IA y detallando los parámetros `--db`, `--mode` y `--query`.

#### Paso 3: Registrar la Skill en el Agente
Colocar la carpeta `whatsapp_assistant` dentro del directorio `.agents/skills/` del espacio de trabajo de tu agente.

#### Paso 4: Validar en el chat con consultas dinámicas
Una vez cargada la Skill, podrás chatear con la IA pidiéndole búsquedas libres:
*   *Usuario:* "Hermes, busca si alguien pasó un CBU en auto_wpp_2"
*   *IA (ejecuta en segundo plano):* `python buscar_datos.py --db "auto_wpp_2" --mode "keyword" --query "CBU"`
*   *IA:* "Sí, en el chat con el contacto +5493772... se envió el CBU: 01700..."
