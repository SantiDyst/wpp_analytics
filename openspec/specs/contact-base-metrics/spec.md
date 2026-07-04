# Delta for contact-base-metrics

## Purpose

Adds a per-contact base-metrics pass computed before the LLM analysis loop. Metrics include total message count, multimedia percentage (with NULL/missing-mime handling), from-me percentage, distinct media types, and date range. Results are available for both JSON serialization and Markdown compilation.

**What existing behavior this modifies**: Nothing — the metrics pass is opt-in via `--with-metrics` and does not affect the existing LLM profiling loop or `conversation_summaries` cache writes.

---

## ADDED Requirements

### Requirement: Total Message Count

The system SHALL compute the total message count per contact as `COUNT(*)` from the `messages` table filtered by `contact_phone`.

#### Scenario: Contact with messages

- GIVEN a contact with phone "+5491112345678" and 312 messages in the database
- WHEN the metrics pass executes
- THEN `total_messages` for that contact SHALL be 312

#### Scenario: Contact with no messages

- GIVEN a contact with phone "+5491112345678" and 0 messages in the database
- WHEN the metrics pass executes
- THEN `total_messages` for that contact SHALL be 0

---

### Requirement: Multimedia Percentage with NULL Handling

The system SHALL compute `multimedia_pct` as `COUNT(mime_type IS NOT NULL) / total * 100`. Rows where `mime_type` is NULL or empty string SHALL be treated as non-multimedia.

#### Scenario: Multimedia percentage calculated correctly

- GIVEN a contact with 100 total messages, of which 23 have a non-NULL `mime_type`
- WHEN `multimedia_pct` is computed
- THEN the result SHALL be 23.0

#### Scenario: NULL mime_type rows excluded from numerator

- GIVEN a contact with 100 total messages, 30 having `mime_type = NULL` and 20 having `mime_type = 'image/jpeg'`
- WHEN `multimedia_pct` is computed
- THEN the numerator SHALL be 20 (not 50)
- AND the result SHALL be 20.0

#### Scenario: Empty string mime_type treated as non-multimedia

- GIVEN a contact with 50 messages where some rows have `mime_type = ''` (empty string)
- WHEN `multimedia_pct` is computed
- THEN rows with empty string `mime_type` SHALL be counted as non-multimedia
- AND SHALL NOT contribute to the numerator

---

### Requirement: From-Me Percentage

The system SHALL compute `from_me_pct` as `SUM(from_me) / total * 100`, where `from_me = 1` indicates messages sent by the user and `from_me = 0` indicates messages received.

#### Scenario: From-me percentage calculated

- GIVEN a contact with 200 messages, 80 marked `from_me = 1`
- WHEN `from_me_pct` is computed
- THEN the result SHALL be 40.0

---

### Requirement: Distinct Media Types

The system SHALL compute `media_types` as the set of distinct non-NULL `mime_type` values for the contact.

#### Scenario: Distinct mime types collected

- GIVEN a contact with mime_types: `['image/jpeg', 'image/jpeg', 'audio/ogg', NULL, 'image/jpeg', 'application/pdf']`
- WHEN `media_types` is computed
- THEN the result SHALL be `['image/jpeg', 'audio/ogg', 'application/pdf']`

---

### Requirement: Date Range

The system SHALL compute `first_message` as `MIN(timestamp)` and `last_message` as `MAX(timestamp)` for each contact, formatted as `YYYY-MM-DD`.

#### Scenario: Date range extracted from timestamps

- GIVEN a contact whose messages have timestamps ranging from "2024-01-15T10:30:00" to "2026-06-20T18:45:00"
- WHEN date range is computed
- THEN `first_message` SHALL be "2024-01-15"
- AND `last_message` SHALL be "2026-06-20"

#### Scenario: Single message date range

- GIVEN a contact with only one message at timestamp "2025-03-01T12:00:00"
- WHEN date range is computed
- THEN `first_message` SHALL equal `last_message` SHALL be "2025-03-01"

---
