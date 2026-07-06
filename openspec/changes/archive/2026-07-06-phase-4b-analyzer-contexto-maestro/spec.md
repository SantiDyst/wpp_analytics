# Delta for analyzer-contexto-maestro

## Purpose

Phase 4b addresses two feedback items from the first production run: prompt field reduction (removing two high-cost/low-value fields from the per-contact extraction) and the new Master Business Context synthesis call. The prompt change (issue 6) is foundational — its 2-field output format is consumed by the master call aggregation (issue 7).

**What existing behavior this modifies**: The prompt strings inside `llamar_api()` are replaced with a reduced 2-field extraction. A new master synthesis call is added after the per-contact batch loop. The output format for per-contact summaries changes from 4 fields to 2 fields.

---

## ADDED Requirements

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

---

## MODIFIED Requirements

None.

## REMOVED Requirements

None.

---

## Coverage

| Requirement | Happy Path | Edge Case |
|-------------|------------|-----------|
| REQ-005-001 Prompt fields | 2-field extraction correct | TODO comment present |
| REQ-005-002 Aggregation | Groups by label, samples ≤10 | All labels ≤10 uses all |
| REQ-005-003 Synthesis | YAML front-matter + SQLite | Stores with `__MAESTRO__` key |
| REQ-005-004 Retry/fail | Retry once, then warn | Individual results preserved |
| REQ-005-005 Resume | Recent row reused | Stale row triggers fresh call |

## Cross-Reference

REQ-005-002 (aggregation) depends on REQ-005-001 (prompt format): the master call aggregates `Vínculo Comercial` labels and `Temas Clave` keywords produced by the reduced 2-field prompt.
