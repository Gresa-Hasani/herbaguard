# HerbaGuard — Phase 0 Prompt: Research and Dataset Audit

**Project:** HerbaGuard — EthnoHack 2026, Track 04: Digital Health & Phytotherapy
**Phase:** 0 of 8
**Type:** Research and planning only — no application code

---

## Role

You are acting as Senior Software Architect, Senior Data Engineer, AI Engineer, Bioinformatics Engineer and Full-Stack Developer for **HerbaGuard**, a scientifically grounded, AI-assisted digital health and phytotherapy platform. HerbaGuard links traditional herbal knowledge and regulatory herbal monographs with modern scientific evidence. Its focus is evidence-based herb–drug interaction intelligence with full provenance, explainability and visible uncertainty.

## Objective

Build the scientific, technical and hackathon foundation for HerbaGuard. Read the official hackathon material in full, audit all relevant datasets and APIs with real requests, evaluate licensing and feasibility, prioritise sources, define the MVP, and recommend the architecture for Phase 1.

## Inputs

1. `EthnoHack 2026 Opening Ceremony.pptx.pdf` — all 26 slides.
2. `datasets_all_tracks.docx` — the complete dataset catalogue (16 pages), including its reference list and embedded hyperlinks.
3. The official Devpost page `https://ethnohack2026.devpost.com/` (requirements, submission checklist, judging criteria).

If the files are not in the repository, search the user's machine (e.g., the Downloads folder). Do not copy organizer files into the repository.

## Tasks

1. Inspect the repository and environment (git status, installed tooling).
2. Read the full presentation and the full dataset catalogue. Do not stop at titles or selected pages.
3. Extract and document: event objectives, Track 04 requirements and directions, suggested datasets/APIs, evaluation criteria, submission requirements, deadlines, constraints and responsible-use guidance. Tag every item as an explicit organizer statement, an inference, or our own recommendation. Do not invent requirements.
4. Systematically evaluate every catalogue resource relevant to Track 04 across: clinical/regulatory evidence; safety and herb–drug interactions; medicinal plant and ethnobotanical knowledge; chemistry and natural products; plant taxonomy; clinical terminologies and ontologies. Briefly note why non-Track-04 resources are out of scope.
5. Investigate the seven ETHCSTWIN-hosted APIs (`wfo`, `ipni`, `wcvp`, `coconut`, `brenda`, `chebi`, `taxtree` at `<name>.ethcstwin.di.uoa.gr:65000`): reachability, OpenAPI documentation, authentication, parameters, response schemas, operations, rate limits, real example responses, data coverage, integration complexity, and whether each is an organizer wrapper or an official API.
6. Execute representative requests against accessible public APIs using one reference entity with well-documented interactions (St John's wort, *Hypericum perforatum*). Record HTTP status, latency and response content. Never assume an API works because its documentation exists.
7. Use only read-only endpoints. Never call import, export or administrative endpoints that change server state. Never bypass CAPTCHAs, bot protection or authentication.
8. Evaluate licensing and access for each resource. Mark every claim as tested, confirmed on the provider page, taken from the catalogue, or still to verify.
9. Classify resources P0 (essential), P1 (high value), P2 (optional), P3 (deferred/excluded), with reasoning.
10. Identify scientific limitations and data-quality risks observed in real data (name ambiguity, synonyms, duplicate records, document versions, licensing).
11. Define a herb–drug interaction classification that is evidence-driven and reproducible (documented / potential / suspected / no evidence found / insufficient information) and an evidence-type vocabulary.
12. Define the MVP scope realistically against the submission deadline, including a curated herb list, MoSCoW feature list, cut order and verifiable demo scenarios.
13. Evaluate the proposed technology stack (FastAPI, PostgreSQL, Neo4j, RAG components, React, Docker, GitHub Actions). Justify each decision; document alternatives; list the decisions the user must make.
14. Save this prompt as `prompts/phase-0-research-and-dataset-audit.md`.

## Constraints

- No application functionality is implemented in Phase 0.
- All documentation is written in English.
- Scientific integrity: traditional use ≠ efficacy; in-vitro ≠ clinical; absence of evidence ≠ safety; spontaneous reports ≠ causality; never fabricate references or results.
- Respect licensing, the Nagoya Protocol and Local Contexts principles; never expose restricted community knowledge.
- **Git:** never run `git commit`, `git push`, amend, rebase, tag or any history-changing command. Read-only git inspection is allowed. Leave every change uncommitted.
- Temporary downloads and scripts go in a scratch directory outside the repository.

## Expected deliverables

| File | Content |
|---|---|
| `docs/research/ethnohack-requirements.md` | Event facts, Track 04 requirements, deliverables, judging criteria, organizer guidance, open questions |
| `docs/research/dataset-audit.md` | Per-resource evaluation table, priorities, rationale, data-quality risks |
| `docs/research/api-audit.md` | ETHCSTWIN and public API tests with real results, complexity ranking, fallback plan |
| `docs/research/scientific-and-ethical-considerations.md` | Principles, interaction classes, evidence types, identifier integrity, conflict rules, AI safeguards, ethics and licensing |
| `docs/research/mvp-scope.md` | Problem, timeline, users, curated coverage, MoSCoW, cut order, demo scenarios, success criteria |
| `docs/research/technology-evaluation.md` | Stack evaluation, Neo4j decision, canonical entity sketch, repository structure, user decisions |
| `prompts/phase-0-research-and-dataset-audit.md` | This prompt |

## Validation criteria

- Both organizer documents were read in full (26 slides; full catalogue including references).
- Every ETHCSTWIN endpoint was contacted, and at least one real read request per endpoint was executed and inspected.
- Every "works" statement about an API is backed by a recorded request and response.
- Every licence statement carries a verification marker.
- No organizer requirement is invented; inferences and recommendations are labelled.
- All deliverable files exist, are in English, and are internally consistent.
- `git status` shows only new or modified files; no commits were created.

## Stopping condition

When all deliverables are written and validated, produce the mandatory Phase 0 completion report (overview, implemented work, files, decisions, data sources, testing and validation, known issues, git status, next-phase preview, suggested commit message and description). State clearly that no commit or push was performed. **Stop and wait for the user's explicit approval before starting Phase 1.**
