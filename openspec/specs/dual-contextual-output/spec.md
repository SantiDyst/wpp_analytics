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
