# Mejoras del Analizador de Contexto — Roadmap `with-metrics`

**Proyecto:** wpp_analytics
**Fecha:** 2026-07-21
**Origen:** Evaluación del reporte `contexto_20260721_111207.md`
**Alcance:** Mejoras al script `scripts/analizar_contexto.py` (rama `--with-metrics`) y a los outputs `.md` / `.json`.

---

## 1. Contexto y gap analysis

El reporte ejecutivo del 2026-07-21 (231 contactos muestreados de 774, base `auto_wpp`) detecta correctamente el dominio (Reconocimientos Médicos, Corrientes, SisPer, Médico Fiscal) y entrega una taxonomía y dudas accionables. Sin embargo, le faltan piezas para ser suficiente como input de un chatbot de soporte en producción.

### Gaps identificados

| # | Gap | Impacto |
|---|-----|---------|
| 1 | El campo `stratification` del JSON se persiste vacío | Bug — los tiers calculados no llegan al output |
| 2 | El `.md` no incluye ejemplos de diálogo por categoría | Bot no ve cómo hablan realmente los usuarios |
| 3 | No hay métricas de tiempo (picos horarios, resolución) | Bot no puede priorizar ni escalar por urgencia |
| 4 | No hay análisis de sentimiento / frustración por categoría | Bot responde con tono incorrecto |
| 5 | No se extraen frases de escalación (derivar, consultar, asesoría) | Bot no sabe cuándo pasar a humano |
| 6 | No existe un `intents.json` con frases por categoría | Re-trabajo si se quiere entrenar NLU después |

---

## 2. Roadmap priorizado

### P0 — Mínimo viable (1 a 2 horas)

#### P0.1 — Fix bug `stratification` vacío

- **Qué:** Persistir el dict `stratification` (phone → tier) en el JSON.
- **Por qué:** Es la metadata base del muestreo estratificado. Sin esto, no se puede auditar qué tier representa cada contacto en el output.
- **Cómo:** Revisar `dual_output_writer` en `scripts/analizar_contexto.py` (~línea 475). El dict `stratification` ya se pasa como argumento; falta escribirlo en el payload JSON bajo la clave `stratification`.
- **Criterio de éxito:** Re-correr el script y verificar que `contexto_*.json` tenga `stratification` con 231 entradas del tipo `{"5493XXXXXXXX": "low" | "mid" | "high"}`.
- **Esfuerzo:** ~5 minutos.

#### P0.2 — Sección "Ejemplos de Diálogo" en el `.md`

- **Qué:** Agregar al reporte ejecutivo 2 a 3 `conversation_snippet` representativos por categoría de la taxonomía.
- **Por qué:** Es lo primero que consume quien diseña las respuestas del bot. Sin ejemplos, las respuestas suenan a manual.
- **Cómo:** En `escribir_reporte_ejecutivo` (línea ~395), después de cada sub-categoría, inyectar 2-3 snippets del sample. Fuente: `sample_for_output` ya contiene los snippets.
- **Criterio de éxito:** Cada hoja de la taxonomía tiene al menos 2 ejemplos de cómo el usuario formuló esa consulta en la vida real.
- **Esfuerzo:** ~30 minutos.

#### P0.3 — Métricas de tiempo en el `.md`

- **Qué:** Incorporar dos agregados: (a) histograma de mensajes por hora del día, (b) mediana de `last_message - first_message` por categoría.
- **Por qué:** Define la ventana de atención efectiva y el SLA implícito que el bot debe respetar.
- **Cómo:**
  - Hora del día: parsear `timestamp` de la tabla `messages` para todos los contactos muestreados, agrupar por hora, escribir mini-tabla markdown.
  - Duración del caso: `last_message - first_message` por contacto, agrupar por categoría, calcular mediana.
- **Criterio de éxito:** El `.md` muestra un bloque "Patrones de Tiempo" con: (i) tabla hora → % mensajes, (ii) tabla categoría → mediana de días de resolución.
- **Esfuerzo:** ~1 hora.

---

### P1 — Enriquecimiento (1 a 2 días)

#### P1.1 — Análisis de sentimiento por categoría

- **Qué:** Etiquetar cada contacto del sample con `positivo | neutral | negativo | frustrado` usando el LLM en el master pass.
- **Por qué:** Cambia el tono y la prioridad de respuesta del bot. Un usuario frustrado necesita escalación temprana, uno neutral puede seguir en el flujo FAQ.
- **Cómo:** Agregar campo `sentiment` al `master_sections` y propagarlo al JSON. En el `.md`, tabla de distribución por categoría.
- **Criterio de éxito:** Distribución de sentimiento visible por categoría. Bot puede ajustar tono según `sentiment` del último mensaje del usuario.
- **Esfuerzo:** ~4 horas (incluye prompt engineering).

#### P1.2 — Extracción de frases de escalación

- **Qué:** Buscar en los snippets patrones léxicos que indiquen derivación a humano: `derivar`, `consulte con`, `asesoría legal`, `le bloqueo`, etc.
- **Por qué:** El bot necesita saber **cuándo** rendirse y pasar a un humano. Las frases de escalación ya existen en los chats reales.
- **Cómo:** Regex simple sobre `conversation_snippet` del sample. Listar las 10 frases más frecuentes y mapearlas a la categoría destino.
- **Criterio de éxito:** Sección "Triggers de Escalación" en el `.md` con frases canónicas y categoría sugerida.
- **Esfuerzo:** ~3 horas.

#### P1.3 — Generar `intents.json`

- **Qué:** Exportar un archivo paralelo `intents_YYYYMMDD_HHMMSS.json` con la estructura: por cada categoría, sus frases de ejemplo, sus sinónimos detectados y su acción sugerida.
- **Por qué:** Es el formato estándar de NLU (Dialogflow, Rasa, Botpress, custom). Permite entrenar el bot sin re-procesar los snippets.
- **Cómo:** Reutilizar la taxonomía y los snippets del sample. Esquema:
  ```json
  {
    "intents": [
      {
        "name": "renviar_acta",
        "category": "Licencias Médicas > Emisión y entrega de actas",
        "examples": ["...", "...", "..."],
        "synonyms": ["acta", "licencia", "email", "recibir"],
        "suggested_action": "verificar_email_y_reenviar"
      }
    ]
  }
  ```
- **Criterio de éxito:** Archivo `outputs/intents_*.json` válido, parseable, con al menos 1 intent por hoja de la taxonomía.
- **Esfuerzo:** ~6 horas.

---

### P2 — Operativo (1 semana)

#### P2.1 — Re-correr con `sample_size=0.50`

- **Qué:** Subir el muestreo del 30% al 50% para tener más cobertura.
- **Por qué:** Reduce el riesgo de que una categoría minoritaria quede sub-representada. La actual distribución (Cliente 201/231 ≈ 87%) puede esconder casos raros pero críticos.
- **Cómo:** Re-correr con `python scripts/analizar_contexto.py --with-metrics --db auto_wpp --sample-size 0.50`.
- **Criterio de éxito:** El sample es ≥ 380 contactos. Categorías como `Proveedor` y `Otro` (hoy con 1 contacto cada una) pasan a tener ≥ 3.
- **Esfuerzo:** ~5 minutos de comando, ~25 min de procesamiento (doble de tokens).
- **Costo:** ~80k tokens extra contra MiniMax-M3.

#### P2.2 — Tracking histórico de corridas

- **Qué:** Versionar los outputs `contexto_*.md` / `contexto_*.json` con timestamp (ya lo están) y agregar un `contexto_history.csv` con métricas agregadas por corrida.
- **Por qué:** Permite detectar drift: ¿la categoría más frecuente cambió en el último mes? ¿Aparecieron temas nuevos? ¿El sentimiento empeoró?
- **Cómo:** Al final de cada corrida, agregar una fila al CSV con: `fecha, total_contacts, sampled, top_category, sentiment_dist, escalations_count, tokens_used`.
- **Criterio de éxito:** Después de 3 corridas (una por semana), se puede graficar la evolución de la categoría dominante.
- **Esfuerzo:** ~4 horas (incluye un mini-dashboard en markdown o un plot simple con `matplotlib`).

#### P2.3 — Prompt versioning

- **Qué:** Mover los prompts del LLM a archivos `.txt` o `.yaml` separados, no hardcodeados en `.py`.
- **Por qué:** Hoy un cambio de prompt requiere tocar el script. Si se versiona el prompt, se puede comparar runs con prompts distintos y medir el impacto.
- **Cómo:** Crear `prompts/master_pass_v1.txt`, `prompts/contact_summary_v1.txt`, etc. Cargarlos en el script con `Path(...) / 'prompts' / ...`.
- **Criterio de éxito:** Cero strings de prompt hardcodeados en `analizar_contexto.py`. Cada cambio de prompt es un diff de un `.txt`.
- **Esfuerzo:** ~3 horas.

---

## 3. Resumen de esfuerzo

| Prioridad | Items | Esfuerzo total | Beneficio principal |
|-----------|-------|----------------|---------------------|
| P0 | 3 | ~1.5 horas | Reporte completo y útil |
| P1 | 3 | ~1.5 días | Bot con tono, escalación, intents |
| P2 | 3 | ~1 semana | Operación robusta y versionable |

## 4. Dependencias y riesgos

- **MiniMax-M3 rate limits**: P1.1 (sentimiento) y P2.1 (sample 0.50) duplican el consumo de tokens. Validar cuota antes de correr.
- **Calidad del LLM en sentimiento**: P1.1 depende de que M3 devuelva etiquetas consistentes. Hacer un eval set manual de 20 contactos antes de confiar.
- **Drift en `auto_wpp`**: hasta que el sync vuelva a funcionar (bug de WA Web version jump en `auto_wpp`), el dataset no se actualiza. Esto limita P2.2.

## 5. Recomendación de orden de ejecución

1. **P0.1** (5 min, sin riesgo, fix de bug) → habilita todo lo demás
2. **P0.2** (30 min, alto valor) → primer entregable visible
3. **P0.3** (1 h, valor medio) → completa el `.md`
4. **P1.2** (3 h, alto valor) → habilita el bot
5. **P1.1** (4 h) y **P1.3** (6 h) en paralelo
6. **P2** cuando esté el bot en producción

---

## 6. Definition of Done del roadmap completo

- [ ] `contexto_*.json` con `stratification` no vacío
- [ ] `contexto_*.md` con sección "Ejemplos de Diálogo" (≥ 2 por categoría)
- [ ] `contexto_*.md` con sección "Patrones de Tiempo"
- [ ] `contexto_*.md` con distribución de sentimiento por categoría
- [ ] `contexto_*.md` con "Triggers de Escalación"
- [ ] `intents_*.json` parseable y completo
- [ ] `contexto_history.csv` con ≥ 3 corridas registradas
- [ ] Prompts externalizados en `prompts/*.txt`
