#### 1. Contexto General del Entorno

El entorno de estas conversaciones corresponde a una entidad o departamento de **Reconocimientos Médicos** que gestiona **licencias por motivos de salud** para **empleados públicos o agentes** (frecuentemente docentes, como se menciona en varias conversaciones). El servicio se ofrece tanto de forma online (principalmente vía WhatsApp y una plataforma "Recibo Digital") como presencial, con diferencias en los procedimientos según la localidad (ej. Capital Federal vs. Interior). La gestión incluye la solicitud de turnos para evaluación médica, la recepción y revisión de documentación (certificados médicos, formularios de licencia), la emisión de actas de licencia (enviadas por correo electrónico), y la resolución de diversas incidencias relacionadas con estos trámites.

#### 2. Las 5 Temáticas o Categorías de Conversación Más Comunes

1.  **Reenvío de Actas de Licencia / Problemas de Recepción:** Numerosas consultas de clientes que no recibieron el acta de su licencia médica en su correo electrónico o solicitan que se la reenvíen.
2.  **Solicitud y Seguimiento de Turnos Online:** Clientes que solicitan un turno para gestionar su licencia, preguntan por el estado de un turno ya solicitado o por qué el médico fiscal no se ha comunicado.
3.  **Requisitos y Procedimientos para la Gestión de Licencias:** Consultas sobre la documentación necesaria (certificado médico, formulario de licencia), cómo aplicar (online vs. presencial, especialmente la distinción para agentes de Capital) y trámites para tipos específicos de licencia (maternidad, acompañamiento familiar, artículos específicos).
4.  **Corrección o Aclaración de Actas de Licencia:** Solicitudes para corregir datos en un acta ya emitida, como fechas de inicio/fin, cantidad de días otorgados, artículo de licencia, o la localidad asignada.
5.  **Actualización de Datos Personales (principalmente correo electrónico):** Clientes que necesitan actualizar su dirección de correo electrónico en el sistema (generalmente asociado al "Recibo Digital") para poder recibir sus actas de licencia.

#### 3. Dudas o Consultas Más Frecuentes de los Usuarios

1.  **"No recibí mi acta de licencia, ¿pueden reenviármela?"** (y variantes como "aún no me llega").
2.  **"¿Qué documentos necesito para solicitar mi licencia?"** (frecuentemente se refieren al certificado médico y al formulario de licencia de su lugar de trabajo).
3.  **"¿Cuándo se comunicará el médico fiscal después de solicitar mi turno?"** o **"¿Por qué el médico aún no me contactó?"**.
4.  **"Necesito corregir mi acta de licencia porque tiene errores"** (en fechas, días, el artículo de la licencia, o la localidad).
5.  **"¿Cómo puedo actualizar mi correo electrónico para recibir las actas?"**
6.  **"¿Debo realizar mi trámite de licencia de forma presencial o puedo hacerlo online?"** (especialmente relevante para agentes de Corrientes Capital).

#### 4. Propuesta de Taxonomía o Categorías Específicas para Clasificación Automática

Para clasificar de forma automática estas conversaciones, se propone la siguiente taxonomía jerárquica:

*   **LICENCIAS_MEDICAS**
    *   **SOLICITUD_TURNO**
        *   `SOL_TURNO_NUEVO` (Cliente solicita un turno inicial para licencia)
        *   `SOL_TURNO_REPROGRAMAR` (Cliente solicita reasignar un turno perdido o modificar uno existente)
        *   `SOL_TURNO_INFO_REQUISITOS` (Cliente pregunta qué necesita para solicitar un turno)
    *   **SEGUIMIENTO_Y_ESTADO**
        *   `SEG_TURNO_MEDICO_NO_CONTACTA` (Cliente pregunta por qué el médico fiscal no se ha comunicado aún)
        *   `SEG_ACTA_NO_GENERADA` (Cliente pregunta por qué no se ha generado/recibido el acta después de la evaluación)
        *   `SEG_DEMORA_GENERAL` (Cliente consulta por demoras en cualquier etapa del proceso de licencia)
    *   **RECEPCION_ACTA**
        *   `REC_ACTA_NO_RECIBIDA` (Cliente informa que no recibió el acta en su correo)
        *   `REC_ACTA_SOLICITAR_REENVIO` (Cliente solicita específicamente el reenvío de un acta)
        *   `REC_ACTA_PROBLEMAS_ACCESO` (Cliente tiene problemas para abrir o visualizar el acta recibida)
    *   **CORRECCION_ACTA**
        *   `CORR_ACTA_FECHAS_DIAS` (Cliente solicita corregir fechas o número de días en el acta)
        *   `CORR_ACTA_DATOS_PERSONALES` (Cliente solicita corregir DNI, localidad, o nombre en el acta)
        *   `CORR_ACTA_ARTICULO_TIPO_LICENCIA` (Cliente solicita corregir el artículo de la licencia o si incluye alta/sin alta)
        *   `CORR_ACTA_CRITERIO_MEDICO` (Cliente expresa desacuerdo o consulta sobre el criterio médico en la concesión de días)
    *   **REQUISITOS_Y_PROCEDIMIENTOS_LICENCIA**
        *   `REQ_PROC_DOCUMENTACION_GENERAL` (Consulta sobre certificado médico, formulario de licencia, etc.)
        *   `REQ_PROC_MODALIDAD_PRESENCIAL_ONLINE` (Consulta si debe ir presencial o puede hacer el trámite online)
        *   `REQ_PROC_LICENCIA_ESPECIFICA` (Consultas sobre licencias de maternidad, acompañamiento familiar, accidente, salud mental, Art. 12/27, etc.)
        *   `REQ_PROC_ALTA_LABORAL` (Consulta sobre el procedimiento para obtener el alta laboral o volver al trabajo)
    *   **PROBLEMAS_EN_GESTION**
        *   `PROB_GEST_LICENCIA_DENEGADA` (Cliente informa que su licencia fue denegada o no procesada)
        *   `PROB_GEST_SITUACION_IRREGULAR` (Agente con situación administrativa irregular previa que afecta la nueva licencia)
        *   `PROB_GEST_ERROR_PLATAFORMA` (Cliente experimenta un error al usar "Recibo Digital" o el sistema online)

*   **INFORMACION_AGENTE**
    *   `INFO_AGENTE_ALTA_NUEVO_REGISTRO` (Consulta o trámite para dar de alta a un agente nuevo en el sistema)
    *   `INFO_AGENTE_ACTUALIZACION_DATOS` (Actualización de correo electrónico, domicilio, situación de revista, etc.)

*   **CONSULTAS_VARIAS**
    *   `CONS_VARIAS_GENERAL` (Preguntas de carácter informativo no directamente relacionadas con una licencia específica)
    *   `CONS_VARIAS_QUEJA_RECLAMO` (Expresiones de insatisfacción con el servicio o el proceso en general)
    *   `CONS_VARIAS_FUERA_DE_AMBITO` (Consultas que no corresponden al área de reconocimientos médicos, ej. junta médica por pensión).