# HerbaGuard — Phase 4 Master Prompt
## Knowledge Graph and Mechanism Integration

> **Note (2026-11-02):** this file contains the part of the Phase 4 prompt that reached the implementing session (sections 1–3, up to the list of fields to document per source). The remaining sections (about 410 lines) were cut off in transmission. Replace this file with the full prompt when it is available.

You are continuing the development of **HerbaGuard**, an evidence-based phytotherapy and digital health platform developed for EthnoHack 2026, Track 04: Digital Health & Phytotherapy.

Your task is to implement **Phase 4 — Knowledge Graph and Mechanism Integration**.

This is an existing software engineering project. You must continue from the actual implementation of Phases 1, 2, and 3. Do not treat this as a greenfield project, and do not rebuild existing functionality without a justified technical reason.

The goal is to extend HerbaGuard with a scientifically traceable knowledge graph connecting medicinal plants, their compounds, metabolic enzymes, transporters, and pharmaceutical drugs. These relationships will support mechanism-based herb–drug interaction analysis.

---

# 1. Mandatory Initial Project Inspection

Before writing or modifying any code, thoroughly inspect the existing repository.

Review at minimum:

- Complete project directory structure.
- `README.md`.
- All architecture and technical documentation.
- All Architecture Decision Records (ADRs).
- `prompts/` and previous phase prompts.
- Backend application structure.
- Existing SQLAlchemy models and PostgreSQL schema.
- Alembic migrations.
- Existing repositories and services.
- Existing REST API routes and schemas.
- Phase 2 ingestion framework and source provenance implementation.
- Existing taxonomy, medicinal plant, drug, constituent, enzyme, transporter, and interaction-related tables.
- Phase 3 deterministic A–E classification implementation.
- Existing tests and captured API fixtures.
- Docker Compose configuration and environment settings.
- Git status, current branch, and latest commit.

Pay particular attention to the existing database entities and relationships. Determine which parts of the planned Knowledge Graph already exist in relational form and which capabilities are genuinely missing.

Do not duplicate existing tables, entities, ingestion pipelines, or business logic.

After inspection, produce a concise implementation assessment covering:

1. What already exists.
2. What can be reused.
3. What needs to be extended.
4. What needs to be implemented.
5. Potential architectural risks.
6. Proposed Phase 4 implementation sequence.

Do not start implementation until this assessment is complete.

---

# 2. Phase 4 Objectives

Phase 4 has five main objectives:

1. Integrate authoritative CYP450 enzyme and transporter datasets.
2. Build traceable relationships between herbs, compounds, enzymes, transporters, and drugs.
3. Implement mechanism-based graph queries.
4. Integrate validated mechanism evidence with the existing deterministic A–E classification system.
5. Expose and test the new functionality through appropriate backend services and APIs.

The existing Phase 1–3 functionality must remain operational.

---

# 3. Data Source Investigation and Integration

Start by inspecting the existing datasets and ingestion framework.

Investigate the availability, structure, licensing, update frequency, and reliability of relevant sources for:

- CYP450 enzyme substrates.
- CYP450 enzyme inhibitors.
- CYP450 enzyme inducers, where supported.
- Drug transporter substrates.
- Drug transporter inhibitors.
- Relevant transporter families, including P-glycoprotein (P-gp/ABCB1), BCRP/ABCG2, and OATP transporters where authoritative data is available.

Evaluate suitable sources, prioritizing authoritative regulatory and scientific resources.

Potential sources include:

- FDA drug labeling and regulatory datasets.
- DrugBank, subject to licensing and access restrictions.
- PharmGKB, subject to licensing and access restrictions.
- PubMed scientific literature.
- Other authoritative and openly accessible pharmacological databases.

Do not assume that a source is freely usable simply because it is publicly accessible.

For each source, document:

- Source name.
- Official URL.
- Data format.
- Available fields.
- Licensing and usage restrictions.
- Retrieval method.

*(Prompt text received ends here.)*
