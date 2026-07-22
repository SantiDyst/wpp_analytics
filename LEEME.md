#### Módulo de Analítica y Cerebro de Datos: wpp_analytics

Este repositorio independiente se encarga de analizar los datos históricos guardados en la base de datos local SQLite del proyecto principal `auto_wpp` e integrar servicios de Inteligencia Artificial para el descubrimiento de contexto y análisis de sentimientos.

---

#### Requisitos Previos

1.  **Python 3** instalado en el sistema.
2.  Una base de datos activa con chats guardados en `C:\Users\Atencion online 2\Desktop\auto_wpp\database\whatsapp.sqlite`.
3.  Una clave de API de **Google Gemini** o compatible (MiniMax, OpenAI).
4.  Dependencia adicional para taxonomía: `pip install pyyaml`. Si no está instalada, `buscar_datos.py --classify` sigue funcionando pero usa la taxonomía hardcodeada de respaldo y emite un aviso por stderr.

---

#### Instrucciones de Configuración y Uso

1.  **Configurar Clave de API:**
    *   El archivo **`.env`** ya existe en la raíz con tu clave.
    *   Si necesitás regenerarlo, agregá: `MINIMAX_API_KEY=tu_clave_aqui` (recomendado, el script detecta por prefijo `sk-*` y enruta a `api.minimax.io` con modelo `MiniMax-M3`).
    *   Alternativa legacy: `GEMINI_API_KEY=tu_clave_aqui` (sigue funcionando, enrutado a Gemini).

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
│   ├── analizar_contexto.py      ← pipeline Etapa 1 (perfilado + reporte ejecutivo con master context)
│   ├── buscar_datos.py           ← buscador dinámico (Etapa 3 inicial, taxonomía YAML)
│   ├── bootstrap_taxonomy.py     ← materializa taxonomía_<cliente>_v1.yaml desde seed
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
│   └── contexto_YYYYMMDD_HHMMSS.{md,json}   ← reporte ejecutivo + JSON pareado
│
├── taxonomias_seed/              ← taxonomías por industria
│   ├── general.yaml
│   ├── salud.yaml
│   ├── educacion.yaml
│   ├── retail.yaml
│   ├── personal.yaml
│   └── medical_licenses.yaml
│
├── skills/                       ← empaquetado para agentes de IA (Fase 5 — pendiente)
│   └── whatsapp_assistant/
│
├── tests/                        ← tests automatizados (pendiente)
│
└── 99_archivo/                   ← histórico/deprecado
    └── mejoras_with_metrics.md   ← gap analysis P0/P1 (2026-07-21)
```

---

#### Salidas del Análisis (`contexto_*.md`)

El reporte ejecutivo generado por `analizar_contexto.py` incluye 8 secciones:

1. Contexto General del Entorno (master context en front-matter YAML)
2. Temáticas o Categorías Más Comunes
3. Dudas o Consultas Frecuentes
4. Propuesta de Taxonomía
5. Ejemplos de Diálogo
6. Patrones de Tiempo (distribución horaria + mediana de resolución)
7. Triggers de Escalación
8. Sentimiento por Vínculo

---

#### Estado Actual (2026-07-22)

**Fases completadas (archivadas en `openspec/changes/archive/`):**
- Phase 1 — context-analyzer
- Phase 2 — taxonomy-yaml (loader en `buscar_datos.py`)
- Phase 3 — industry-taxonomy-seeds (6 YAMLs en `taxonomias_seed/`)
- Phase 4a — analyzer-bugfixes (cache check, DRY extraction, fail-fast, permissions, token logging)
- Phase 4b — analyzer-contexto-maestro (prompt trim + master context synthesis)

**Fases con planning abandonado (features ya implementadas):**
- Phase 4c — analyzer-feedback-fixes
- Phase 5 — executive-report

**Pendiente para futuro:**
- P1.3 — exportar `intents.json` con frases y acciones por categoría (formato NLU estándar)
- Skills (`skills/whatsapp_assistant/`) y tests automatizados (`tests/`)

Ver [`PLAN_PRODUCTO.md`](./PLAN_PRODUCTO.md) para el detalle del roadmap completo.