# Data Model — Schema v1

**Status:** Implemented in `backend/src/herbaguard/models/` and migration `backend/alembic/versions/0001_initial_schema_v1.py`. Tables are empty until Phase 2 ingestion.

The schema follows four rules from the Phase 0 research (`docs/research/scientific-and-ethical-considerations.md`):

1. **Source identifiers are preserved** next to internal UUIDs (WFO, IPNI, RxCUI, PMID, EMA document numbers…).
2. **Nothing derived exists without provenance**: every row created by ingestion is linked to the raw record it came from.
3. **Conflicting statements are never merged**: each source's statement is its own row; the interaction class shown to users is computed at query time.
4. **Integrity is enforced by the database** (CHECK, UNIQUE, FK constraints), not only by application code. The database tests prove the key rules.

## 1. Entity overview

```
                         ┌──────────────┐
                         │    source    │ licence, licence_status, redistributable, is_official
                         └──────┬───────┘
          ┌─────────────────────┼──────────────────────────┐
          ▼                     ▼                          ▼
   ┌─────────────┐      ┌───────────────┐          ┌──────────────────┐
   │ingestion_run│◄─────│ source_record │◄─────────│   provenance     │──► any entity row
   └─────────────┘      └───────────────┘          └──────────────────┘   (entity_table, entity_id)
          ▲                     ▲
          └──── data_quality_issue

 taxon ──< taxon_name                    drug ──< drug_class_membership >── drug_class (ATC)
   │                                      │
   └──< herbal_substance ──< indication   └──< drug_target_role >── target ──< target_modulation
          │       │                                                   ▲            │
          │       └──< herbal_substance_constituent >── constituent ──┘ (subject is substance
          │                                                                 OR constituent)
          └──< interaction_assertion >── drug | drug_class
                    │
                    └──< interaction_assertion_evidence >── evidence_item ──< chunk (FTS + vector)
```

## 2. Tables

### 2.1 Provenance layer

| Table | Purpose | Key constraints |
|---|---|---|
| `source` | One row per data source (from the Phase 0 registry). Holds licence text, URL, `licence_status` (`verified` / `catalogue` / `to_verify`), `redistributable`, `is_official` (false for ETHCSTWIN wrappers). | PK `code`; CHECK on `licence_status` |
| `ingestion_run` | One execution of a connector (PROV *Activity*): parameters, statistics, code version, status. | CHECK `status ∈ {running, succeeded, partial, failed}` |
| `source_record` | One retrieved artefact exactly as received (PROV *Entity*): URL, request parameters, HTTP status, content type, SHA-256, path of raw file, optional small JSON payload, source version, retrieval time. | UNIQUE (`source_code`, `native_id`, `content_sha256`) makes re-ingestion idempotent and detects upstream changes; CHECK on HTTP status range |
| `provenance` | Links any derived row (`entity_table`, `entity_id`) to a `source_record` and `ingestion_run`, with extraction method/version, location within the record and an optional verbatim excerpt (only if the licence permits). | UNIQUE (entity, record, method). Polymorphic by design (no FK on `entity_id`); validated by data tests from Phase 2 |
| `data_quality_issue` | Validation failures are stored, never silently dropped. | CHECK `severity ∈ {info, warning, error}` |

### 2.2 Taxonomy

| Table | Purpose | Key constraints |
|---|---|---|
| `taxon` | Accepted plant taxon. `wfo_id` is the primary external identifier; IPNI, WCVP `plant_name_id`, GBIF key, NCBI tax_id, POWO ID and Wikidata ID are cross-references. | UNIQUE `wfo_id`; CHECK `wfo_id ~ '^wfo-[0-9]{10}$'` (the ETHCSTWIN wrapper returns the bare number 728093, which must be converted) |
| `taxon_name` | Every name string that maps to a taxon: accepted, synonym, common, pharmaceutical (e.g. *Hyperici herba*). `taxon_id` may be NULL for unresolved names — they are never guessed. | CHECK on `name_type`; UNIQUE (`normalized_name`, `name_type`, `language`, `taxon_id`, `source_code`) **NULLS NOT DISTINCT** |
| `herbal_substance` | Taxon + plant part, the unit regulators assess (EMA monographs are about *Hyperici herba*, not *Hypericum perforatum* in general). Holds pharmaceutical name, EMA URL/outcome, curated-scope flag. | UNIQUE (`taxon_id`, `plant_part`); FK to taxon is RESTRICT |

### 2.3 Pharmacology (the knowledge graph)

| Table | Purpose | Key constraints |
|---|---|---|
| `drug` | Drug at RxNorm ingredient level (e.g. warfarin, RxCUI 11289). | UNIQUE `rxcui` |
| `drug_class` | Drug class, normally ATC (e.g. `B01AA`). Needed because EMA statements often name classes ("coumarin-type anticoagulants"). | CHECK `level BETWEEN 1 AND 5` |
| `drug_class_membership` | Drug ↔ class, with the source of the mapping (RxClass). | Composite PK |
| `constituent` | Chemical constituent keyed by InChIKey; ChEBI ID and PubChem CID as cross-references. | UNIQUE `inchikey`; CHECK InChIKey format |
| `herbal_substance_constituent` | Substance contains constituent; `is_marker` for monograph marker substances (e.g. hyperforin). | Composite PK |
| `target` | Enzyme / transporter / receptor (e.g. CYP3A4 = UniProt P08684). | UNIQUE `symbol`, UNIQUE `uniprot_accession`; CHECK `target_type` |
| `target_modulation` | Herbal substance **or** constituent induces / inhibits / activates a target, with evidence type and conditions. First premise of class B. | CHECK exactly one subject; CHECK `effect`, `evidence_type`; UNIQUE … NULLS NOT DISTINCT |
| `drug_target_role` | Drug is a substrate / sensitive substrate / inhibitor / inducer of a target. Second premise of class B. | CHECK `role`; UNIQUE (drug, target, role, source) |

### 2.4 Evidence and retrieval

| Table | Purpose | Key constraints |
|---|---|---|
| `evidence_item` | A citable unit: monograph section, label section, article, fact sheet. Evidence type from the Phase 0 vocabulary (`REG`, `GOV`, `SR`, `RCT`, `CLIN`, `CASE`, `ANIMAL`, `INVITRO`, `TRAD`, `SPONT`, `COMP`). Includes `is_superseded` so superseded EMA documents can be kept for lineage but never used as evidence. | UNIQUE (`source_code`, `external_id`); CHECK on `evidence_type` and year range |
| `indication` | Therapeutic indication of a substance with its **EMA use category** (`well_established_use` / `traditional_use`), never merged. Optional MeSH ID. | CHECK on `use_category` |
| `interaction_assertion` | One statement from one source that a substance interacts with a drug **or** a drug class. Keeps the source's own wording (`object_label_verbatim`, `severity_wording`), section, use category, mechanism and conditions (e.g. hyperforin dose threshold). `status` = active / superseded / rejected. | CHECK exactly one of `drug_id` / `drug_class_code`; CHECK on `evidence_type`, `use_category`, `status` |
| `interaction_assertion_evidence` | Assertion ↔ evidence items. | Composite PK |
| `chunk` | Retrieval unit for the assistant: text, metadata, `embedding vector(384)` (HNSW cosine index) and a generated `tsvector` column (GIN index) for hybrid search. | UNIQUE (`evidence_item_id`, `ordinal`) |

## 3. What is computed, not stored

| Value | Why it is not a column |
|---|---|
| Interaction class A–E for a herb–drug pair | Derived from all active assertions plus mechanism edges at query time, so new evidence immediately changes the result and the reasoning stays inspectable. |
| Severity | HerbaGuard never computes severity; it relays `severity_wording` from the source. |

## 4. Conventions

- Primary keys: UUID v4 (`id`), except natural keys for `source.code` and `drug_class.code`.
- Timestamps: `timestamptz`, `created_at` / `updated_at` set by the database.
- Vocabularies: `text` columns + CHECK constraints (simpler to evolve than native ENUM types). The allowed values live in `herbaguard/domain/enums.py`.
- Constraint names follow a deterministic convention (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`) that stays within PostgreSQL's 63-character limit; a test enforces this.
- Embedding dimension 384 matches the embedding model planned for Phase 5 (`bge-small-en-v1.5`). Choosing a model with another dimension requires a migration.
- `alembic check` in CI verifies that models and migrations agree.

## 5. Known limitations of schema v1

- `provenance.entity_id` has no foreign key (polymorphic). Orphan detection is a Phase 2 data-validation test.
- Product-level data (brands, extract ratios, hyperforin content) is not modelled; conditions are kept as text.
- Multi-species substances (e.g. *Crataegus* spp.) need one `herbal_substance` per taxon or a later many-to-many; to be decided during Phase 2 ingestion of hawthorn.
