#### Plan Maestro del Producto: wpp_analytics Pipeline

Este documento describe el plan completo para evolucionar `wpp_analytics` desde un módulo de análisis puntual a un **pipeline de 3 etapas** orientado a producto comercializable. El plan está diseñado para que cualquier IA pueda retomar el trabajo donde otro lo dejó.

**Contexto del problema:**
*   El proyecto nace analizando chats de WhatsApp de un cliente específico (Reconocimientos Médicos).
*   Hoy `analizar_contexto.py` y `buscar_datos.py` resuelven casos puntuales, pero la taxonomía está hardcodeada y no hay flujo continuo entre etapas.
*   La meta es convertir esto en un **paquete vendible** que sirva para *cualquier* cliente: descubrimiento → taxonomía → IA operativa.

---

#### Arquitectura del Pipeline

```
[WhatsApp DB local (.sqlite)]
            │
            ▼
   ┌─────────────────────┐
   │ ETAPA 1: Discovery  │ →  reporte_contexto.md + perfil_cliente_<db>.json
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ ETAPA 2: Taxonomía  │ →  taxonomia_<cliente>_v<n>.yaml
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ ETAPA 3: IA Operativa│ →  buscador + skill + reportes + chatbot
   └─────────────────────┘
```

---

#### ETAPA 1: Paneo General (Context Discovery)

**Estado actual (`analizar_contexto.py`):**
*   Toma muestra aleatoria de 100 chats.
*   Envía a la IA para descubrir temáticas generales.
*   Genera solo `reporte_contexto.md`.

**Mejoras requeridas:**

1. **Muestreo estratificado** (no aleatorio puro):
    *   Dividir contactos en estratos: `top_activos`, `nuevos`, `dormidos`, `grupales`.
    *   Tomar muestra proporcional de cada estrato.
    *   Configurable vía parámetro o constante al inicio del script.

2. **Discovery iterativo en 2 pasadas:**
    *   **Pasada 1 (amplia):** identificar temáticas, vertical del cliente, idioma, geografía, tipo de interacciones.
    *   **Pasada 2 (focalizada):** validar/refinar lo descubierto en la primera.

3. **Métricas base automáticas** (calcular con SQL antes de enviar a la IA):
    *   Total de chats y mensajes.
    *   Rango de fechas cubierto.
    *   Densidad de mensajes por día.
    *   Ratio entrante/saliente.
    *   Porcentaje de mensajes multimedia.
    *   Distribución horaria de actividad.

4. **Auto-detección de industria/vertical:**
    *   Prompt inicial dedicado a clasificar al cliente en una de estas categorías: `educación`, `salud`, `retail`, `servicios profesionales`, `comercio`, `otro`.
    *   Esta detección guía la elección de la taxonomía por defecto de la Etapa 2.

5. **Salida dual (JSON + Markdown):**
    *   `reporte_contexto_<db>_<fecha>.md`: para lectura humana.
    *   `perfil_cliente_<db>_<fecha>.json`: estructura consumible por la Etapa 2.

**Salidas esperadas:**
*   `reporte_contexto_<db>_<fecha>.md`
*   `perfil_cliente_<db>_<fecha>.json` con esta estructura mínima:
    ```json
    {
      "cliente": "auto_wpp",
      "fecha": "2026-07-02",
      "industria": "salud",
      "total_chats": 1234,
      "total_mensajes": 56789,
      "rango_fechas": ["2024-01-01", "2026-07-02"],
      "tematicas_principales": ["...", "..."],
      "taxonomia_sugerida": ["...", "..."]
    }
    ```

---

#### ETAPA 2: Taxonomía Especializada

**Estado actual:**
*   La taxonomía de Reconocimientos Médicos está hardcodeada como string en `buscar_datos.py:10-22`.
*   Sirve solo para ese cliente específico.

**Mejoras requeridas:**

1. **Taxonomía dinámica:**
    *   Leer el `perfil_cliente_*.json` de Etapa 1.
    *   Generar una taxonomía inicial basada en la industria detectada + temáticas descubiertas.
    *   Persistir como `taxonomia_<cliente>_v<n>.yaml`.

2. **Versionado:**
    *   Cada ejecución genera una nueva versión (`v1`, `v2`, ...).
    *   Permitir rollback a versiones anteriores.

3. **Jerarquía N-niveles:**
    *   No fija de 3 niveles como ahora. Configurable según el dominio.
    *   Categoría → Subcategoría → Tag (opcional).

4. **Multi-taxonomía:**
    *   Si el cliente tiene varios negocios/líneas, soportar varias taxonomías en paralelo.
    *   Cada mensaje/chat puede tener clasificación en múltiples taxonomías.

5. **Taxonomías semilla por industria:**
    *   `taxonomia_seed_salud.yaml`, `taxonomia_seed_educacion.yaml`, etc.
    *   Sirven como punto de partida que la Etapa 1 refina.

6. **Feedback loop:**
    *   Tabla SQLite `taxonomy_corrections` para guardar reasignaciones manuales del cliente.
    *   La próxima corrida las incorpora para mejorar la consistencia.

**Salidas esperadas:**
*   `taxonomia_<cliente>_v<n>.yaml`
*   Tablas SQLite: `taxonomies`, `taxonomy_versions`, `taxonomy_corrections`.

---

#### ETAPA 3: IA Operativa (Entrenada para el cliente)

**Estado actual:**
*   `buscar_datos.py` con modos `keyword` y `semantic` (recién implementado, funcional).
*   Soporta `--classify` con la taxonomía hardcodeada de Reconocimientos Médicos.

**Mejoras requeridas:**

1. **Extender `buscar_datos.py` con nuevos modos:**
    *   `--mode taxonomy`: clasificar chats en bulk según la taxonomía vigente (lee del YAML).
    *   `--mode trend`: cómo evoluciona un tema en el tiempo (requiere timestamps).
    *   `--mode sentiment`: tono por chat o por tema.
    *   `--mode alerts`: detectar picos anómalos (quejas, demoras, etc.).
    *   `--mode query`: responder preguntas libres del cliente sobre sus chats.

2. **Carga dinámica de taxonomía:**
    *   Reemplazar la constante `TAXONOMIA` en `buscar_datos.py:10-22` por lectura desde `taxonomia_<cliente>_v<n>.yaml`.
    *   Mantener la taxonomía hardcodeada solo como fallback si no hay YAML.

3. **Skill empaquetable:**
    *   Crear `skills/whatsapp_assistant/` con `SKILL.md` + scripts.
    *   Permitir instalación en cualquier agente compatible.

4. **Generador de reportes periódicos:**
    *   Reporte semanal/mensual automático.
    *   Comparativa contra corrida anterior (qué cambió).

5. **Agente conversacional local:**
    *   Mini-chatbot que el cliente puede consultar en lenguaje natural.
    *   Combina keyword + semantic + taxonomía para responder.

6. **Exportadores:**
    *   CSV, Excel, PDF para presentar resultados a clientes finales.

7. **API local opcional (Flask):**
    *   Endpoints REST para integrar con dashboards o herramientas externas.
    *   `/api/buscar`, `/api/clasificar`, `/api/reporte`.

**Salidas esperadas:**
*   `buscar_datos.py` extendido.
*   `skills/whatsapp_assistant/SKILL.md`.
*   `skills/whatsapp_assistant/scripts/` con los scripts.
*   Reportes periódicos automáticos.

---

#### Producto Final Comercial (3 capas)

| Capa | Entregable | Modelo de cobro |
|---|---|---|
| **Backup** | Respaldo SQLite + visualizador offline. | Pago único, bajo. |
| **Auditoría** | Etapas 1 + 2 → reporte + taxonomía especializada. | Por análisis, medio. |
| **IA Continua** | Etapa 3 → buscador + skill + chatbot + reportes periódicos. | Mensual, alto. |

Esto encaja con los 3 planes definidos en `propuesta_comercial.md`.

---

#### Mejoras Transversales al Proyecto

1. **UI amigable con `rich`:**
    *   Reemplazar la barra de progreso ASCII por barra con `rich.progress`.
    *   Tablas coloreadas para estadísticas.
    *   Menús interactivos lindos.

2. **Multi-tenant:**
    *   Soporte para múltiples clientes en una sola instalación.
    *   Configuración por cliente en `clientes/<nombre>/config.yaml`.

3. **Persistencia de metadata:**
    *   Tablas SQLite adicionales:
        *   `clients` (id, nombre, industria, fecha_alta).
        *   `analysis_runs` (id, client_id, fecha, tipo, parámetros).
        *   `taxonomies` (id, client_id, version, contenido_yaml).
        *   `taxonomy_corrections` (id, mensaje_id, categoria_original, categoria_correcta).

4. **Comparación temporal:**
    *   Diff entre corridas para mostrar evolución.
    *   Gráficos de tendencia por temática.

5. **Anonimización automática:**
    *   Reemplazar DNI, nombres, teléfonos por hashes en reportes de demo.
    *   Útil para vender datos agregados sin exponer PII.

6. **Local-first como feature de venta:**
    *   Toda la pipeline corre en la máquina del cliente.
    *   Nada se sube a la nube. Diferenciador clave vs. SaaS tradicionales.

---

#### Roadmap Concreto

| Fase | Tarea | Archivos a tocar | Prioridad |
|---|---|---|---|
| **1** | Refactor `analizar_contexto.py`: muestreo estratificado + salida JSON + métricas base. | `analizar_contexto.py` | Alta |
| **2** | Refactor `buscar_datos.py`: leer taxonomía desde YAML en lugar de hardcoded. | `buscar_datos.py` | Alta |
| **3** | Crear `taxonomias_seed/` con YAMLs por industria. | `taxonomias_seed/salud.yaml`, `educacion.yaml`, etc. | Alta |
| **4** | Agregar modos nuevos a `buscar_datos.py` (`taxonomy`, `trend`, `sentiment`, `alerts`). | `buscar_datos.py` | Media |
| **5** | Empaquetar Skill: `skills/whatsapp_assistant/` con `SKILL.md`. | `skills/whatsapp_assistant/SKILL.md`, `scripts/` | Media |
| **6** | Integrar `rich` para UI amigable. | todos los scripts | Media |
| **7** | Tablas SQLite de metadata (`clients`, `analysis_runs`, `taxonomies`). | nuevo `init_db.py` | Media |
| **8** | Comparación temporal entre corridas. | nuevo `comparar_corridas.py` | Baja |
| **9** | Dashboard web local (Flask + Chart.js). | nuevo `dashboard/app.py` | Baja |
| **10** | Agente conversacional local (chatbot). | nuevo `chatbot.py` | Baja |

---

#### Archivos Actuales del Proyecto

| Carpeta / Archivo | Rol | Estado |
|---|---|---|
| `LEEME.md` | README principal con instrucciones de uso. | Actualizado. |
| `PLAN_PRODUCTO.md` | Este documento (plan maestro). | Actualizado. |
| `ejecutar_analisis.bat` | Lanzador del análisis principal. | Actualizado. |
| `scripts/analizar_contexto.py` | Pipeline de perfilado general (Etapa 1). | Funcional, requiere mejoras. |
| `scripts/buscar_datos.py` | Buscador dinámico keyword + semantic (Etapa 3 inicial). | Funcional, requiere mejoras. |
| `scripts/clean_db.py` | Limpia bloques `<think>` de perfiles guardados. | Funcional. |
| `docs/propuesta_comercial.md` | 3 planes comerciales (Express / Activo / VIP). | Solo referencia. |
| `docs/reporte_contexto.md` | Reporte de Reconocimientos Médicos (análisis previo). | Solo referencia. |
| `docs/analytics_version_2.md` | Plan original de la V2 (perfilado por contacto). | Solo referencia. |
| `docs/skills_feature.md` | Diseño de la Skill `whatsapp_assistant`. | Solo referencia (ahora integrado en este PLAN). |
| `docs/sql_features.md` | Diagnóstico y propuestas de optimización SQL (FTS5, normalización). | Solo referencia (Fase futura). |
| `outputs/` | Archivos generados (`logs.txt`, `reporte_contexto_v2.md`). | Ignorado por git. |
| `taxonomias_seed/` | Taxonomías semilla por industria (Fase 3). | Vacío, pendiente. |
| `skills/whatsapp_assistant/` | Empaquetado de Skill para agentes IA (Fase 5). | Vacío, pendiente. |
| `tests/` | Tests automatizados. | Vacío, pendiente. |
| `99_archivo/` | Histórico/deprecado. | No tocar. |
| `.env` | Configuración de API key (Gemini o compatible). | Activo. |

---

#### Estado Actual del Proyecto (al 2026-07-02)

**Hecho:**
*   `scripts/analizar_contexto.py` funcional con perfilado individual por contacto, lotes, caché local, compilación de reporte V2 en `outputs/`.
*   `scripts/buscar_datos.py` creado con modos `keyword` y `semantic`, soporte para taxonomía (hardcoded por ahora).
*   Pruebas realizadas en `auto_wpp` con keyword ("acta") y semantic ("docentes que pidieron turno y no fueron contactados") → resultados coherentes con la taxonomía esperada.
*   **Estructura del proyecto ordenada** (Fase 0): `scripts/`, `docs/`, `outputs/`, `taxonomias_seed/`, `skills/`, `tests/`.
*   `.gitignore` actualizado para ignorar `outputs/`.
*   `LEEME.md` y `PLAN_PRODUCTO.md` reflejan la nueva estructura.

**Pendiente (según roadmap):**
*   Fases 1-10 listadas arriba.

---

#### Convenciones del Proyecto

*   **Lenguaje:** Python 3, sin dependencias externas obligatorias (solo stdlib: `sqlite3`, `urllib`, `json`, `argparse`, `re`).
*   **Dependencias opcionales:** `rich` (UI), `pyyaml` (configs), `flask` (dashboard).
*   **Encoding:** forzar UTF-8 en stdout/stderr al inicio de cada script (`sys.stdout.reconfigure(encoding='utf-8')`).
*   **Compatibilidad API:**
    *   Claves `sk-*` → OpenAI/MiniMax compatible (`https://api.minimax.io/v1/chat/completions`, modelo `MiniMax-M3`).
    *   Otras claves → Google Gemini (`gemini-2.5-flash` por default).
*   **Taxonomía:** hardcoded como string en `buscar_datos.py` actualmente. Migrar a YAML externo en Fase 2.
*   **Limpieza:** función `remove_think_tags()` para eliminar bloques `<think>...</think>` de respuestas IA.
*   **Reportes:** siempre con front-matter YAML (`---`, `date:`, `title:`).

---

#### Notas para Retomar el Trabajo

Si otra IA continúa este plan:

1.   **Primero:** leer este archivo completo y `buscar_datos.py` (estado actual de Etapa 3 inicial).
2.   **Validar:** que `buscar_datos.py` funcione en modo `keyword` y `semantic` con una DB real antes de modificar.
3.   **Priorizar:** Fases 1 y 2 del roadmap (refactor + taxonomía YAML). Sin ellas, el resto depende de Etapa 1.
4.   **Mantener:** compatibilidad con el código existente, no romper `analizar_contexto.py` ni `clean_db.py`.
5.   **Documentar:** cada cambio significativo en este mismo `PLAN_PRODUCTO.md` o en un changelog nuevo.