---
date: 2026-06-29
title: Plan de Analytics Versión 2
---

#### Plan de Implementación: Analytics Versión 2

Este documento detalla el plan acordado para transformar el módulo de analítica [[analizar_contexto.py]] en un motor de perfilado relacional y ocupacional de tus contactos utilizando la API de MiniMax.

---

#### 1. Modificaciones en el Código Principal

Se realizarán los siguientes cambios en [[analizar_contexto.py]]:
*   **Ajuste del Tamaño de Lote:** Configurar `lote_size = 100` para procesar los chats en grupos de 100 contactos.
*   **Prompt de Perfilado Relacional:** Sustituir el análisis de "reconocimientos médicos" por instrucciones específicas para identificar:
    *   **Categoría Ocupacional:** Clasificación del contacto (Empresario/Emprendedor, Estudiante, Desempleado u Otro).
    *   **Allegados:** Vínculos familiares o laborales mencionados.
    *   **Temas Principales:** Tópicos recurrentes de conversación.
    *   **Dinámica Relacional:** Tipo de relación y tono dominante.
*   **Limpieza Estructural Eficiente:**
    *   Unificación de mensajes consecutivos del mismo emisor en un solo párrafo para ahorrar tokens de metadatos.
    *   Eliminación automática de avisos de sistema ("Este mensaje fue eliminado").
*   **Visual de Carga (Barra de Progreso):** Implementar un indicador visual nativo en texto que informe del progreso en tiempo real de la corrida general de análisis.

---

#### 2. Ciclo Interactivo en Consola y Menú de Inicio

*   **Menú de Selección de Modo:** Al iniciar, el programa permite seleccionar entre:
    *   `Opción 1`: Procesar en lotes de 100 con confirmación manual para continuar.
    *   `Opción 2`: Procesar todos los contactos de forma automática y secuencial sin detener el script.
*   El script procesará los contactos individualmente y los guardará directamente en la base de datos local SQLite.
*   **Compilador Local:** El archivo [[reporte_contexto_vxx.md]] se creará de forma local mediante Python, leyendo todos los perfiles guardados de SQLite. Esto elimina el cuello de botella del límite de tokens de salida de la API de raíz.

---

#### 3. Relación de Archivos

*   Script principal: [[analizar_contexto.py]]
*   Configuración local: [[.env]]
*   Reporte consolidado: [[reporte_contexto_v2.md]]
