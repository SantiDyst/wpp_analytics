# Delta for stratified-sampling

## Purpose

Adds volume-tier stratified sampling to the contact selection process. Contacts are bucketed into three tiers (Low / Medium / High) based on per-contact message counts computed at runtime from the current dataset. Sample allocation is proportional across tiers with a minimum of 1 contact per non-empty tier; total sample respects the strict 30% budget (no floor-induced overflow).

**What existing behavior this modifies**: Nothing — this is purely additive. Existing interactive-menu runs (no CLI flags) are unaffected.

---

## ADDED Requirements

### Requirement: Quantile Threshold Computation

The system SHALL compute stratum boundaries at runtime from the current dataset by calculating the 33rd and 66th percentile of messages-per-contact across all contacts.

#### Scenario: Quantiles computed from dataset

- GIVEN a database with contacts having message counts [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 100, 200, 500]
- WHEN the stratified sampling run begins
- THEN the system computes P33 ≈ 17 and P66 ≈ 47 as tier cutoffs
- AND Low tier = contacts with < 17 messages
- AND Mid tier = contacts with 17–47 messages
- AND High tier = contacts with > 47 messages

#### Scenario: Quantiles recalculated per run

- GIVEN a database processed in a first run producing thresholds P33=20, P66=80
- WHEN a second run is executed on the same database after new messages are added
- THEN the system SHALL recalculate thresholds from the updated dataset
- AND SHALL NOT reuse the first run's thresholds

---

### Requirement: Tier Assignment

The system SHALL assign each contact to exactly one tier (Low, Mid, or High) based on its total message count relative to the computed quantile boundaries.

#### Scenario: Contact assigned to Low tier

- GIVEN a contact with 12 messages and computed thresholds P33=17, P66=47
- WHEN tier assignment occurs
- THEN the contact is assigned to Low tier

#### Scenario: Contact on exact boundary assigned to Mid tier

- GIVEN a contact with exactly 17 messages and thresholds P33=17, P66=47
- WHEN tier assignment occurs
- THEN the contact is assigned to Mid tier (lower-bound inclusive)

---

### Requirement: Proportional Allocation Across Tiers

The system SHALL allocate the 30% sample proportionally across all three tiers, where each tier's share of the sample equals its share of the total contact population.

#### Scenario: Proportional split reflects population

- GIVEN a database with 300 total contacts distributed: Low=150, Mid=90, High=60
- WHEN a 30% sample (90 contacts) is allocated
- THEN Low tier receives 45 contacts (150/300 × 90)
- AND Mid tier receives 27 contacts (90/300 × 90)
- AND High tier receives 18 contacts (60/300 × 90)

#### Scenario: Proportional allocation rounds down

- GIVEN a database with 301 total contacts and Low tier = 151 contacts
- WHEN a 30% sample (~90 contacts) is allocated
- THEN Low tier allocation = floor(151/301 × 90) = floor(45.09) = 45
- AND the remainder (0.09 contact) is discarded without redistribution

---

### Requirement: Minimum Coverage Per Non-Empty Tier

The system SHALL allocate a minimum of 1 contact per non-empty tier when the total budget allows, distributing the remaining budget proportionally across all non-empty tiers.

#### Scenario: Small tier receives minimum coverage

- GIVEN a database with 100 contacts: Low=90, Mid=8, High=2
- WHEN a 30% sample (30 contacts) is allocated
- AND budget = max(int(0.30 × 100), 3) = 30
- AND desired = {Low, Mid, High} (1 each for minimum coverage)
- AND remaining budget = 30 − 3 = 27 distributed proportionally
- THEN Low receives ~26–27 contacts, Mid receives ~2–3 contacts, High receives 1 contact
- AND total sample equals 30 exactly (no overflow)

#### Scenario: Tier with zero contacts

- GIVEN a database where all contacts have message counts below the P33 threshold
- WHEN High tier has 0 contacts
- THEN High tier is skipped from BOTH the 1-per-tier minimum coverage AND the proportional distribution
- AND 30% sample is distributed proportionally across Low and Mid only

---

### Requirement: Sample Size Is 30% of Total Contacts

The system SHALL select exactly 30% of total contacts per run, with no minimum floor.

#### Scenario: 30% sample with no floor

- GIVEN a database with 10 total contacts
- WHEN stratified sampling runs
- THEN the sample size SHALL be 3 contacts (floor(10 × 0.30))
- AND there is no minimum floor applied to the total sample

#### Scenario: Small database with strict-budget allocation

- GIVEN a database with 10 contacts: Low=3, Mid=3, High=4
- WHEN a 30% sample (3 contacts) is allocated with strict-budget rules
- AND budget = max(int(0.30 × 10), 3) = 3
- AND all three tiers are non-empty (N_tiers = 3)
- THEN each non-empty tier receives 1 contact (minimum coverage)
- AND total sample = 3 exactly (no overflow)

---
