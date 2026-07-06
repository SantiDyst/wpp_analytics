# Delta for dual-contextual-output

## Purpose

Adds dual output generation: a machine-readable JSON file and a human-readable Markdown file with YAML front-matter. Both files share the same timestamp stem and are written to the `outputs/` directory. The JSON and Markdown contain equivalent contact data; they differ only in format.

**What existing behavior this modifies**: Nothing — dual output is opt-in via CLI flags and does not replace the existing `reporte_contexto_v2.md` single-file behavior for interactive runs.

---

## ADDED Requirements

### Requirement: JSON Output File

The system SHALL write a JSON file to `outputs/contexto_{YYYYMMDD}_{HHMMSS}.json` containing structured per-contact data including metrics and profile summaries.

#### Scenario: JSON file created with correct name

- GIVEN a run at 2026-07-04 11:45:00
- WHEN dual output is enabled
- THEN the JSON file SHALL be named `outputs/contexto_20260704_114500.json`
- AND the file SHALL contain valid JSON

#### Scenario: JSON structure contains contacts array

- GIVEN a sample of 3 contacts with metrics
- WHEN the JSON file is written
- THEN the top-level JSON object SHALL contain a `contacts` array
- AND each element in `contacts` SHALL include `phone`, `name`, `metrics`, and `profile_summary`

---

### Requirement: Markdown Output File with YAML Front-Matter

The system SHALL write a Markdown file to `outputs/contexto_{YYYYMMDD}_{HHMMSS}.md` beginning with YAML front-matter and containing human-readable contact profiles.

#### Scenario: Markdown file created with YAML front-matter

- GIVEN a run at 2026-07-04 11:45:00
- WHEN dual output is enabled
- THEN the Markdown file SHALL be named `outputs/contexto_20260704_114500.md`
- AND the file SHALL begin with `---`
- AND the YAML block SHALL contain `date:` and `title:` fields
- AND the YAML block SHALL end with `---`

#### Scenario: Markdown body contains contact profiles

- GIVEN a sample of contacts with profile summaries
- WHEN the Markdown file is written
- THEN each contact profile SHALL appear as a Markdown section
- AND SHALL include the contact name and a human-readable summary

---

### Requirement: Same Data in Both Formats

The system SHALL produce JSON and Markdown containing identical per-contact data (metrics and profile summaries). The only differences between the two files are format and structure.

#### Scenario: Metrics match across JSON and Markdown

- GIVEN a contact with `total_messages = 312`, `multimedia_pct = 23.4`
- WHEN dual output is generated
- THEN the JSON `contacts[].metrics.total_messages` SHALL be 312
- AND the Markdown contact section SHALL display the same `total_messages` value

---

### Requirement: REQ-004-001 — Cache Check Before API Call in `--with-metrics`

The system SHALL query `conversation_summaries` for an existing `period='profile'` row before calling `llamar_api()` in the `--with-metrics` processing path. If a cached row exists, the system SHALL skip the API call and increment the cache-skip counter.

#### Scenario: Cache hit skips API call

- GIVEN a contact `+5491112345678` exists in `conversation_summaries` with `period='profile'`
- WHEN the `--with-metrics` processing loop reaches that contact
- THEN the system executes `SELECT summary FROM conversation_summaries WHERE contact_phone = ? AND period = 'profile'`
- AND finds a non-null row
- AND skips the call to `llamar_api()`
- AND increments `omitidos_por_cache` and `total_usados_cache`

#### Scenario: Cache miss proceeds to API call

- GIVEN a contact `+5491112345678` has no row in `conversation_summaries` with `period='profile'`
- WHEN the `--with-metrics` processing loop reaches that contact
- THEN the `SELECT` returns `None`
- AND the system calls `llamar_api()` normally
- AND the result is written to `conversation_summaries`

---

### Requirement: REQ-004-002 — DRY Consolidation of Processing Loops

The system SHALL provide a single shared function `procesar_chats_con_ia(sample_list, db_path, options)` that consolidates the two previously separate processing loops. The `options` dict MUST carry `cursor`, `connection`, `metrics_enabled`, `fail_fast`, `interactive`, and `registrar_logs` keys. The function MUST return a 3-tuple `(summaries_dict, token_totals_dict, cache_stats_dict)` where `cache_stats_dict` carries `nuevos_analizados` and `omitidos_por_cache` counts.

#### Scenario: `--with-metrics` path calls shared function with token accumulation

- GIVEN `--with-metrics` is active and a sample of 10 contacts is selected
- WHEN the processing loop calls `procesar_chats_con_ia(sample_list, db_path, options)` with `options['cursor']`, `options['connection']`, `options['metrics_enabled']=True`, `options['fail_fast']=True`, `options['registrar_logs']=registrar_logs_v2`
- THEN the function iterates over all contacts in `sample_list`
- AND accumulates `prompt_tokens`, `candidate_tokens`, and `total_tokens` from each `llamar_api()` call
- AND calls `registrar_logs_v2()` once at batch completion with accumulated token totals

#### Scenario: Interactive path calls shared function without token accumulation

- GIVEN the interactive path is active (no `--with-metrics` flag)
- WHEN the existing confirmation loop calls `procesar_chats_con_ia(sample_list, db_path, options)` with `options['cursor']`, `options['connection']`, `options['metrics_enabled']=False`, `options['fail_fast']=False`, `options['interactive']=True`, `options['registrar_logs']=None`
- THEN the function iterates over contacts with user confirmation prompts
- AND does NOT call `registrar_logs_v2()`
- AND returns `(summaries_dict, token_totals_dict)` with zeroed token counts

---

### Requirement: REQ-004-003 — Fail-Fast on HTTP 401/403

The function `llamar_api()` SHALL accept a `fail_fast: bool = False` parameter. When `fail_fast=True` and the HTTP response status is 401 or 403, the function SHALL call `sys.exit(f"[FATAL] Credenciales rechazadas (HTTP {e.code}). Abortando.")` instead of returning `(None, 0, 0, 0, 0)`.

#### Scenario: HTTP 401 triggers fail-fast abort

- GIVEN `llamar_api()` is called with `fail_fast=True` and the API returns HTTP 401
- WHEN the function detects the 401 status code
- THEN it writes `sys.exit("[FATAL] Credenciales rechazadas (HTTP 401). Abortando.")`
- AND the Python process terminates immediately

#### Scenario: HTTP 403 triggers fail-fast abort

- GIVEN `llamar_api()` is called with `fail_fast=True` and the API returns HTTP 403
- WHEN the function detects the 403 status code
- THEN it writes `sys.exit("[FATAL] Credenciales rechazadas (HTTP 403). Abortando.")`
- AND the Python process terminates immediately

#### Scenario: HTTP 401 does not abort when fail_fast=False (default)

- GIVEN `llamar_api()` is called with `fail_fast=False` (default) and the API returns HTTP 401
- WHEN the function detects the 401 status code
- THEN it prints an error message
- AND returns `(None, 0, 0, 0, 0)` without calling `sys.exit()`

---

### Requirement: REQ-004-004 — Per-Folder Permission Error Handling

The function `seleccionar_base_datos()` SHALL catch `PermissionError` inside the per-folder iteration loop and continue scanning remaining folders without aborting the entire scan. A single inaccessible folder MUST NOT prevent processing of subsequent valid folders.

#### Scenario: Inaccessible folder is skipped without aborting scan

- GIVEN `seleccionar_base_datos()` is scanning `Desktop/wpp_analytics/` siblings
- AND one subfolder `Desktop/inaccessible/` raises `PermissionError` on `folder.is_dir()` or `db_file.exists()`
- WHEN the exception is raised inside the loop
- THEN the exception is caught with `except PermissionError: continue`
- AND the scan proceeds to the next folder
- AND the function returns valid `(folder_name, db_path)` tuples for all accessible folders

#### Scenario: All folders inaccessible triggers graceful empty return

- GIVEN all subfolders in `Desktop/` raise `PermissionError`
- WHEN the scan loop exhausts all entries
- THEN the function returns an empty list `rutas_validas = []`
- AND the calling code handles the empty list appropriately (prompts user or exits)

---

### Requirement: REQ-004-005 — Token Logging for `--with-metrics`

After `procesar_chats_con_ia()` completes a batch with `metrics_enabled=True`, the system SHALL call `registrar_logs_v2()` with the accumulated `prompt_tokens`, `candidate_tokens`, and `total_tokens` values from the batch.

#### Scenario: Token totals logged after successful batch

- GIVEN a `--with-metrics` run processes 10 contacts
- AND each contact's `llamar_api()` call returns non-zero token counts
- WHEN the batch completes
- THEN `registrar_logs_v2()` is called once with the accumulated totals
- AND the `outputs/logs.txt` file contains an entry with the correct accumulated token values

#### Scenario: Zero tokens logged when all calls fail

- GIVEN a `--with-metrics` run where all `llamar_api()` calls return `(None, 0, 0, 0, 0)` due to API errors
- WHEN the batch completes
- THEN `registrar_logs_v2()` is called with `prompt_tokens=0`, `candidate_tokens=0`, `total_tokens=0`
- AND the `outputs/logs.txt` file reflects zero consumption for that run

---
### Requirement: REQ-005-001 — Reduced Prompt Field Extraction

The system SHALL extract exactly 2 fields per contact in `llamar_api()`: (1) `Vínculo Comercial` — one of 6 hardcoded labels (Cliente, Proveedor, Empleado, Familiar, Spam, Otro); (2) `Temas Clave` — up to 5 keyword tokens. The system SHALL NOT request `Categoría Ocupacional detallada` or `Allegados y Círculo Social`.

A `# TODO: Read from taxonomy YAML when Phase 3 lands` comment SHALL be present in the code adjacent to the hardcoded label list.

#### Scenario: Prompt extracts only 2 fields

- GIVEN a contact with name "Juan Perez" and a message history
- WHEN `llamar_api()` is called for that contact
- THEN the prompt instructs the model to extract exactly: (a) `Vínculo Comercial: Clasifica al contacto en [Cliente], [Proveedor], [Empleado], [Familiar], [Spam], [Otro]`; (b) `Temas Clave: Palabras clave precisas (máximo 5)`
- AND the prompt does NOT contain the phrases `Categoría Ocupacional detallada` or `Allegados`

#### Scenario: TODO comment present for Phase 3 integration

- GIVEN the `llamar_api()` function is inspected
- WHEN the section containing the 6-label list is found
- THEN a line `# TODO: Read from taxonomy YAML when Phase 3 lands` appears nearby
- AND the 6 labels (Cliente, Proveedor, Empleado, Familiar, Spam, Otro) are present as a list or string literal

---

### Requirement: REQ-005-002 — Master Call Input Aggregation

After processing all contacts, the system SHALL aggregate per-contact summaries by `Vínculo Comercial` label. For each label, the system SHALL sample at most 10 contacts (or all if fewer) and build a compact input string for the master synthesis call by concatenating each sampled contact's `Temas Clave` keywords.

#### Scenario: Aggregation groups contacts by Vínculo label

- GIVEN 50 contacts have been processed with `Vínculo Comercial` values: 20 Cliente, 15 Proveedor, 10 Empleado, 5 Familiar
- WHEN the aggregation step runs
- THEN the system produces a dict mapping each label to its contacts: `{"Cliente": [...20...], "Proveedor": [...15...], ...}`
- AND for each label, at most 10 contacts are selected (Cliente: 10 of 20; Proveedor: 10 of 15; Empleado: 10 of 10; Familiar: 5 of 5)

#### Scenario: Master input string concatenates Temas Clave

- GIVEN 3 sampled contacts with labels `Cliente` have `Temas Clave` values: ["pedido", "entrega"], ["factura", "pago"], ["devolucion"]
- WHEN the compact input string is built
- THEN the resulting string contains the concatenated keywords: `Cliente: pedido, entrega, factura, pago, devolucion`
- AND the master call input reflects this aggregation for all labels

---

### Requirement: REQ-005-003 — Master Call Synthesis and Persistence

The system SHALL make one API call with a synthesis prompt asking for an executive business summary. The result SHALL be written as YAML front-matter at the top of the Markdown output file. The system SHALL also store the result in `conversation_summaries` with `period='master'` and `contact_phone='__MAESTRO__'`.

#### Scenario: Master call result written as YAML front-matter

- GIVEN a successful master synthesis API call returns `"## Resumen Ejecutivo\n\nLa cartera de clientes se compone principalmente de..."`
- WHEN the output Markdown file is written
- THEN the first lines of the file are: `---`, `title: "Contexto Maestro del Negocio"`, `date: {current date}`, `---`
- AND immediately after the front-matter comes the synthesis text

#### Scenario: Master context persisted to SQLite for resume

- GIVEN a successful master synthesis call
- WHEN the result is available
- THEN the system executes: `INSERT OR REPLACE INTO conversation_summaries (contact_phone, period, summary, timestamp) VALUES ('__MAESTRO__', 'master', '{synthesis_text}', datetime('now'))`
- AND a subsequent run with resume enabled can read this row

---

### Requirement: REQ-005-004 — Master Call Failure Handling

The system SHALL retry the master synthesis API call exactly once on failure. If the retry also fails, the system SHALL log a warning and continue — individual per-contact results SHALL remain usable in the output regardless of master call outcome.

#### Scenario: Master call succeeds on first try

- GIVEN the master synthesis call is the next step after per-contact processing
- WHEN the API call returns HTTP 200 with valid content
- THEN the result is written to output and SQLite without any retry logic

#### Scenario: Master call retry on first failure

- GIVEN the master synthesis call is attempted and the API returns HTTP 500
- WHEN the failure is detected
- THEN the system retries the same call exactly one additional time
- AND if the retry succeeds (HTTP 200), the result is written normally
- AND if the retry fails, a warning is logged to `outputs/logs.txt`: `"[WARN] Master synthesis call failed after retry. Individual results remain available."`

#### Scenario: Individual results usable after master failure

- GIVEN the master synthesis call fails after retry
- WHEN the output Markdown file is written
- THEN the file contains all per-contact summaries
- AND the file does NOT contain a master context section
- AND individual contacts' `Vínculo Comercial` and `Temas Clave` are present

---

### Requirement: REQ-005-005 — Master Context Resume Capability

On subsequent runs, the system SHALL read any existing `period='master'` row from `conversation_summaries` before calling the master API. If a row exists with a `timestamp` within 24 hours of the current run, the system SHALL skip the master API call and reuse the stored synthesis.

#### Scenario: Recent master row found — API call skipped

- GIVEN `conversation_summaries` contains a row with `contact_phone='__MAESTRO__'`, `period='master'`, and `timestamp` of 3 hours ago
- WHEN a new `--with-metrics` run starts
- THEN the system reads the existing row before calling the master API
- AND skips the API call
- AND uses the stored synthesis text for the YAML front-matter

#### Scenario: No master row — API call proceeds

- GIVEN `conversation_summaries` has no row with `contact_phone='__MAESTRO__'` and `period='master'`
- WHEN a new `--with-metrics` run reaches the master synthesis step
- THEN the system makes the API call
- AND stores the result per REQ-005-003

#### Scenario: Stale master row (>24h) — API call proceeds

- GIVEN `conversation_summaries` contains a row with `contact_phone='__MAESTRO__'`, `period='master'`, and `timestamp` of 30 hours ago
- WHEN a new `--with-metrics` run reaches the master synthesis step
- THEN the system treats the row as stale
- AND makes a fresh API call
- AND overwrites the stale row with the new synthesis per REQ-005-003
