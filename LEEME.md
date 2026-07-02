#### Módulo de Analítica y Cerebro de Datos: wpp_analytics

Este repositorio independiente se encarga de analizar los datos históricos guardados en la base de datos local SQLite del proyecto principal `auto_wpp` e integrar servicios de Inteligencia Artificial para el descubrimiento de contexto y análisis de sentimientos.

---

#### Requisitos Previos

1.  **Python 3** instalado en el sistema.
2.  Una base de datos activa con chats guardados en `C:\Users\Atencion online 2\Desktop\auto_wpp\database\whatsapp.sqlite`.
3.  Una clave de API de **Google Gemini** o compatible (MiniMax, OpenAI).

---

#### Instrucciones de Configuración y Uso

1.  **Configurar Clave de API:**
    *   El archivo **`.env`** ya existe en la raíz con tu clave de Gemini.
    *   Si necesitás regenerarlo, agregá: `GEMINI_API_KEY=tu_clave_aqui`

2.  **Ejecutar el Análisis General:**
    *   Doble clic en `ejecutar_analisis.bat`, o:
    ```powershell
    python scripts\analizar_contexto.py
    ```
    *   Perfila los contactos uno por uno con IA y guarda resultados en `outputs/`.

3.  **Búsqueda Dinámica en Chats:**
    *   Modo keyword (SQL puro, sin gastar API):
    ```powershell
    python scripts\buscar_datos.py --db auto_wpp --mode keyword --query "acta"
    ```
    *   Modo semántico (con IA + taxonomía):
    ```powershell
    python scripts\buscar_datos.py --db auto_wpp --mode semantic --query "clientes que pidieron reenvío de acta" --classify --limit 10
    ```

4.  **Resultado:**
    *   Los reportes se generan en `outputs/`.
    *   Los perfiles de contactos quedan guardados en la base SQLite del cliente.

---

#### Estructura del Proyecto

```
wpp_analytics/
├── .env                          ← API key (no subir a git)
├── .gitignore
├── LEEME.md                      ← este archivo
├── PLAN_PRODUCTO.md              ← plan maestro del producto (pipeline 3 etapas)
├── ejecutar_analisis.bat         ← lanzador del análisis principal
│
├── scripts/                      ← scripts ejecutables
│   ├── analizar_contexto.py      ← pipeline Etapa 1 (perfilado general)
│   ├── buscar_datos.py           ← buscador dinámico (Etapa 3 inicial)
│   └── clean_db.py               ← limpieza de bloques <think> en perfiles guardados
│
├── docs/                         ← documentación de referencia
│   ├── propuesta_comercial.md    ← 3 planes comerciales
│   ├── reporte_contexto.md       ← análisis histórico (Reconocimientos Médicos)
│   ├── analytics_version_2.md    ← plan original V2 (referencia)
│   ├── skills_feature.md         ← diseño histórico de la Skill
│   └── sql_features.md           ← propuestas de optimización SQL
│
├── outputs/                      ← archivos generados (ignorado por git)
│   ├── logs.txt
│   └── reporte_contexto_v2.md
│
├── taxonomias_seed/              ← taxonomías por industria (Fase 3)
│
├── skills/                       ← empaquetado para agentes de IA (Fase 5)
│   └── whatsapp_assistant/
│
├── tests/                        ← tests automatizados (futuro)
│
└── 99_archivo/                   ← histórico/deprecado (no tocar)
```

---

#### Roadmap

Ver [`PLAN_PRODUCTO.md`](./PLAN_PRODUCTO.md) para el plan completo de evolución del producto en 10 fases.

Estado actual: **Fase 0 completada** (estructura ordenada + `buscar_datos.py` operativo).