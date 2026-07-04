# Delta for industry-taxonomy-seeds

## Purpose

Phase 3 delivers five hand-authored YAML seed taxonomies for the verticals `salud`, `educacion`, `retail`, `general`, and `personal` under `taxonomias_seed/`. These files serve as canonical starting points for new clients, eliminating the one-vertical-at-a-time manual bootstrap that Phase 2 required. All five files conform to the schema locked in Phase 2 (`medical_licenses.yaml`) and are activated by running `bootstrap_taxonomy.py --seed taxonomias_seed/<vertical>.yaml --client <client>` per vertical.

## What existing behavior this modifies

Nothing. Phase 3 is purely additive — no existing code, taxonomy files, or loader behavior are modified.

---

## ADDED Requirements

### Requirement: REQ-001 — Schema Conformance

**Applies to:** All five YAML seed files (`salud.yaml`, `educacion.yaml`, `retail.yaml`, `general.yaml`, `personal.yaml`)

The system SHALL ensure that each seed file parses with `yaml.safe_load` without error and that its key shape is byte-identical to `taxonomias_seed/medical_licenses.yaml`. Each file MUST contain exactly the top-level keys `domain` (UPPER_SNAKE_CASE string), `description` (Spanish text ≤ 100 characters), and `categories` (a dict). Under `categories`, every key MUST be UPPER_SNAKE_CASE and its value MUST be a dict of subcategory keys. Every subcategory key MUST be UPPER_SNAKE_CASE and its value MUST be a non-empty list of UPPER_SNAKE_CASE tag strings.

#### Scenario: All 5 files parse and match schema

- GIVEN the five files `salud.yaml`, `educacion.yaml`, `retail.yaml`, `general.yaml`, and `personal.yaml` exist in `taxonomias_seed/`
- WHEN each file is loaded with `yaml.safe_load`
- THEN no exception is raised AND the resulting object contains exactly the keys `domain`, `description`, and `categories` with the same nesting depth as `medical_licenses.yaml`

#### Scenario: File with wrong top-level key is rejected

- GIVEN a file that contains a top-level key `categoria` instead of `categories`
- WHEN the file is validated against the schema
- THEN it is marked REJECTED because the required `categories` key is absent

#### Scenario: File with non-UPPER_SNAKE_CASE domain is rejected

- GIVEN a file whose `domain` value is `salud-general` (lowercase with hyphen)
- WHEN the file is validated against the schema
- THEN it is marked REJECTED because `domain` is not UPPER_SNAKE_CASE

---

### Requirement: REQ-002 — Tag Density

**Applies to:** All five YAML seed files

Each subcategory list SHALL contain between 2 and 6 tags inclusive. The median tag count across all subcategories within a single file SHALL be between 2 and 4 inclusive.

#### Scenario: Fictional subcategory with 3 tags is ACCEPTED

- GIVEN a subcategory containing exactly 3 tags
- WHEN the tag density rule is evaluated
- THEN the subcategory is ACCEPTED (within the 2–6 range)

#### Scenario: Fictional subcategory with 0 tags is REJECTED

- GIVEN a subcategory that contains an empty list `[]`
- WHEN the tag density rule is evaluated
- THEN the subcategory is REJECTED because it contains fewer than 2 tags

#### Scenario: Fictional subcategory with 8 tags is REJECTED

- GIVEN a subcategory that contains 8 tags
- WHEN the tag density rule is evaluated
- THEN the subcategory is REJECTED because it exceeds the maximum of 6 tags

---

### Requirement: REQ-003 — salud.yaml exists with healthcare-relevant verticals

The file `taxonomias_seed/salud.yaml` SHALL exist and SHALL contain healthcare-relevant categories and subcategories including but not limited to: appointment scheduling (`TURNOS`), prescription management (`RECETAS`), lab and imaging results (`RESULTADOS`), insurance coverage (`COBERTURA`), billing (`FACTURACION`), and patient intake (`ATENCION_PACIENTE`). The file SHALL contain at least 3 top-level categories.

#### Scenario: salud.yaml contains TURNOS subcategory with valid tags

- GIVEN `salud.yaml` exists in `taxonomias_seed/`
- WHEN the file is inspected
- THEN it contains a category with a subcategory `TURNOS` (or equivalent healthcare scheduling key) whose tag list has 2–6 tags

#### Scenario: salud.yaml missing healthcare verticals

- GIVEN `salud.yaml` exists but contains no subcategory related to appointments, prescriptions, or patient care
- WHEN the file is validated against the health vertical requirement
- THEN it is REJECTED because it lacks healthcare-relevant content

---

### Requirement: REQ-004 — educacion.yaml exists with education-relevant verticals

The file `taxonomias_seed/educacion.yaml` SHALL exist and SHALL contain education-relevant categories and subcategories including but not limited to: enrollment (`INSCRIPCIONES`), teacher records and leave (`DOCENTES`, `LICENCIAS_ARTICULO`), student records (`ESTUDIANTES`), parent communication (`PADRES`), institution info (`INSTITUCION`), and tuition payments (`PAGOS`). The file SHALL contain at least 3 top-level categories.

#### Scenario: educacion.yaml contains DOCENTES and LICENCIAS_ARTICULO subcategories

- GIVEN `educacion.yaml` exists in `taxonomias_seed/`
- WHEN the file is inspected
- THEN it contains subcategories related to `DOCENTES` (teachers) and `LICENCIAS_ARTICULO` (leave by article type) with 2–6 tags each

#### Scenario: educacion.yaml missing teacher-related content

- GIVEN `educacion.yaml` exists but contains no subcategories related to docentes, estudiantes, or inscripciones
- WHEN the file is validated against the education vertical requirement
- THEN it is REJECTED because it lacks education-relevant content

---

### Requirement: REQ-005 — retail.yaml exists with retail-relevant verticals

The file `taxonomias_seed/retail.yaml` SHALL exist and SHALL contain retail-relevant categories and subcategories including but not limited to: product catalog (`PRODUCTOS`), point-of-sale transactions (`VENTAS`), quotes and estimates (`PRESUPUESTOS`), inventory management (`STOCK`), customer records (`CLIENTES`), and returns (`DEVOLUCIONES`). The file SHALL contain at least 3 top-level categories.

#### Scenario: retail.yaml contains PRODUCTOS and VENTAS subcategories

- GIVEN `retail.yaml` exists in `taxonomias_seed/`
- WHEN the file is inspected
- THEN it contains subcategories related to `PRODUCTOS` (products) and `VENTAS` (sales) with 2–6 tags each

#### Scenario: retail.yaml missing commerce content

- GIVEN `retail.yaml` exists but contains no subcategories related to products, sales, or inventory
- WHEN the file is validated against the retail vertical requirement
- THEN it is REJECTED because it lacks retail-relevant content

---

### Requirement: REQ-006 — general.yaml breadth (4–5 cross-cutting categories)

The file `taxonomias_seed/general.yaml` SHALL exist and SHALL contain between 4 and 5 top-level categories inclusive. Categories SHALL be cross-cutting and cover: general inquiries (`CONSULTAS`), location and access (`UBICACION_ACCESO`), complaints (`QUEJAS_RECLAMOS`), out-of-scope routing (`FUERA_DE_AMBITO`), and pricing/hours (`PRECIOS_HORARIOS`). These five are the approved categories; a sixth category makes the file over-broad.

#### Scenario: general.yaml has exactly 4 top-level categories — ACCEPTED

- GIVEN `general.yaml` contains exactly 4 top-level categories
- WHEN the breadth rule is evaluated
- THEN the file is ACCEPTED

#### Scenario: general.yaml has exactly 5 top-level categories — ACCEPTED

- GIVEN `general.yaml` contains exactly 5 top-level categories
- WHEN the breadth rule is evaluated
- THEN the file is ACCEPTED

#### Scenario: general.yaml has exactly 6 top-level categories — REJECTED

- GIVEN `general.yaml` contains exactly 6 top-level categories
- WHEN the breadth rule is evaluated
- THEN the file is REJECTED because it exceeds the maximum of 5 categories

---

### Requirement: REQ-007 — personal.yaml chat-action-oriented shape

The file `taxonomias_seed/personal.yaml` SHALL exist and its subcategory keys SHALL be named after chat actions or conversational intents — examples: `COORDINAR_PLAN`, `RECORDATORIO`, `PEDIR_OPINION`, `COMPARTIR_ARCHIVO`. Subcategory names that represent life themes rather than actions (e.g., `SALUD_PERSONAL`, `FAMILIA`, `TRABAJO`) do not match the required shape.

#### Scenario: personal.yaml subcategory named with action verb — PASS

- GIVEN `personal.yaml` contains a subcategory `PEDIR_OPINION`
- WHEN the shape rule is evaluated
- THEN the subcategory name is ACCEPTED because it reflects a chat action

#### Scenario: personal.yaml subcategory named after a life theme — REJECTED

- GIVEN `personal.yaml` contains a subcategory `SALUD_PERSONAL`
- WHEN the shape rule is evaluated
- THEN the subcategory name is REJECTED because it is theme-oriented rather than action-oriented

---

### Requirement: REQ-008 — taxonomias_seed/README.md lists exactly the 5 new file names

The file `taxonomias_seed/README.md` SHALL list exactly the five new seed file names (`salud.yaml`, `educacion.yaml`, `retail.yaml`, `general.yaml`, `personal.yaml`). The previous list that included `servicios_profesionales.yaml` SHALL be replaced by the current list. No file name outside these five SHALL appear in the list.

#### Scenario: README lists exactly the 5 new file names

- GIVEN `taxonomias_seed/README.md` is updated
- WHEN the file is inspected
- THEN it contains entries for `salud.yaml`, `educacion.yaml`, `retail.yaml`, `general.yaml`, and `personal.yaml` and does NOT contain `servicios_profesionales.yaml`

#### Scenario: README still contains old file name

- GIVEN `taxonomias_seed/README.md` still contains `servicios_profesionales.yaml`
- WHEN the README is validated
- THEN it is REJECTED because the outdated file name is present

---

## Coverage

| Requirement | Happy Path | Edge Case |
|-------------|------------|-----------|
| REQ-001 Schema | All 5 parse with `yaml.safe_load` and match key shape | Wrong key; non-UPPER_SNAKE_CASE domain |
| REQ-002 Tag Density | 3-tag subcategory accepted | 0 tags rejected; 8 tags rejected |
| REQ-003 salud.yaml | TURNOS subcategory present | Missing healthcare verticals |
| REQ-004 educacion.yaml | DOCENTES + LICENCIAS_ARTICULO present | Missing education verticals |
| REQ-005 retail.yaml | PRODUCTOS + VENTAS present | Missing retail verticals |
| REQ-006 general.yaml breadth | 4 categories PASS; 5 categories PASS | 6 categories REJECTED |
| REQ-007 personal.yaml shape | Action-verb name PASS | Theme-name REJECTED |
| REQ-008 README.md | 5 correct names listed | Old name `servicios_profesionales` still present |
