# Phase 5 — AI, Hybrid RAG and Multi-Provider LLM Integration

> Saved 2026-11-03 before implementation, on branch `feat/phase-5-ai-rag` (HEAD `0788b62`). The text below is the complete prompt as received in chat.

## 1. Role and Objective

Act as a senior AI Engineer, Data Engineer, Backend Architect, and Software Engineer working on HerbaGuard, a scientific evidence platform for medicinal plants and herb–drug interactions.

Your task is to implement Phase 5: AI, Hybrid Retrieval-Augmented Generation (RAG), and Multi-Provider LLM Integration.

This phase must build on the existing HerbaGuard implementation from Phases 0–4. It must not recreate, replace, or weaken functionality that already exists.

The objective is to introduce an evidence-grounded AI layer that allows users to ask natural-language questions about medicinal plants, herbal substances, drugs, pharmacological mechanisms, scientific literature, and herb–drug interactions.

The system must retrieve relevant evidence from the existing HerbaGuard database, use the existing Knowledge Graph and API capabilities, and generate answers with traceable references to the underlying sources.

The implementation must prioritize:

* Scientific accuracy and evidence traceability.
* Explicit uncertainty and transparent limitations.
* Deterministic interaction classification.
* Provider-independent LLM architecture.
* Reproducible retrieval and evaluation.
* Data privacy and security.
* Local development without mandatory paid API access.
* Maintainability and production-oriented engineering.

Do not start Phase 6 or implement frontend functionality beyond what is strictly necessary for backend integration testing.

## 2. Mandatory Preliminary Repository Audit

Before writing or modifying code, inspect the complete repository and understand the existing architecture.

Read the relevant documentation, including:

* `README.md`
* `docs/architecture.md`
* `docs/data-model.md`
* `docs/api/`
* `docs/decisions/`
* `docs/mechanism-paths.md`
* `docs/interaction-classification.md`
* `docs/mechanism-sources.md`
* Existing ingestion, provenance, data quality, and search documentation.
* Existing Phase 5 planning documentation, if present.
* Relevant database migrations and existing models.

Inspect:

* Existing PostgreSQL schema and migrations.
* Existing `search_chunks` implementation and current search capabilities.
* Existing source provenance and evidence models.
* Existing plant, drug, constituent, enzyme, transporter, and interaction relationships.
* Existing mechanism graph queries and services.
* Existing API routes, schemas, repositories, and service conventions.
* Existing configuration and environment variable management.
* Existing logging, error handling, testing, and Docker configuration.
* Existing dependencies and Python version constraints.

Use the actual repository implementation as the source of truth.

Do not assume that a table, endpoint, model, field, or integration exists simply because it was planned in an earlier phase.

Identify reusable functionality before introducing new abstractions.

### Audit Deliverable

Before implementation, provide:

* Current architecture relevant to AI/RAG.
* Existing retrieval and search capabilities.
* Existing evidence and provenance structures.
* Available source content and its limitations.
* Database changes that may be necessary.
* Recommended implementation design.
* Potential compatibility and migration risks.
* Exact implementation plan for Phase 5.

Do not proceed with a redesign of existing architecture unless a concrete technical problem requires it.

## 3. Architecture Principles

The AI layer must operate as an additional service layer on top of the existing HerbaGuard backend.

The intended architecture is:

User Question
→ Question Processing
→ Query Understanding
→ Retrieval Orchestration
→ Hybrid Retrieval
→ Evidence Filtering and Ranking
→ Knowledge Graph Context Retrieval
→ Evidence Assembly
→ LLM Provider Interface
→ Grounded Answer Generation
→ Citation and Evidence Validation
→ Structured API Response

The architecture must reuse existing HerbaGuard services wherever possible.

### Important architectural decisions

* PostgreSQL remains the primary database.
* The existing relational Knowledge Graph remains authoritative.
* Do not introduce Neo4j.
* Do not duplicate the existing interaction classification engine.
* Do not create a separate evidence database.
* Do not introduce unnecessary microservices.
* Keep the AI layer modular and testable.
* Keep retrieval, evidence assembly, model invocation, and response validation as separate responsibilities.

Document significant architectural decisions through ADRs when necessary.

## 4. Multi-Provider LLM Architecture

This is a core requirement of Phase 5.

HerbaGuard must not be permanently coupled to a single LLM provider.

Implement a provider-independent LLM abstraction that supports switching between different providers through configuration without changing the RAG pipeline, API contracts, or business logic.

### 4.1 Initial provider support

Implement the following providers where technically appropriate:

**Ollama — Local Provider**

* Initial default provider.
* Initial model: `qwen3:4b`.
* Local inference through Ollama.
* No mandatory API key.
* Configurable Ollama base URL.
* Configurable model name.
* Proper timeout and connection error handling.

**Anthropic Provider**

* Support Anthropic API integration.
* Model identifier must be configurable.
* API key must be supplied through environment variables.
* Never hardcode a specific model identifier into business logic.
* Do not require an API key for local development or automated tests.

**OpenAI Provider**

* Support OpenAI API integration.
* Model identifier must be configurable.
* API key must be supplied through environment variables.
* Do not hardcode a specific model identifier into business logic.
* Do not require an API key for local development or automated tests.

**Extensibility**

* Design the abstraction so that additional providers can be integrated without modifying the core RAG orchestration.
* Consider a generic OpenAI-compatible provider only if it provides meaningful additional flexibility.
* Avoid implementing unnecessary integrations merely to increase the provider count.

### 4.2 Provider interface

Create a common provider interface with a consistent contract.

The interface should support:

* Text generation.
* System instructions.
* User messages and contextual evidence.
* Configurable generation parameters.
* Token usage metadata where available.
* Model and provider identification.
* Structured output where supported.
* Timeout handling.
* Provider-specific error normalization.

Use typed request and response schemas.

The RAG service must communicate with the provider interface rather than directly importing or invoking provider SDKs.

Provider-specific implementations must remain isolated.

### 4.3 Provider selection

Support environment-based configuration similar to:

```
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:4b

OLLAMA_BASE_URL=http://localhost:11434

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=

OPENAI_API_KEY=
OPENAI_MODEL=
```

The exact configuration names may be adapted to existing project conventions.

Requirements:

* Validate configuration at startup or when the AI service is initialized.
* Do not fail the entire application if optional providers are not configured.
* Fail clearly when an explicitly selected provider is unavailable or incorrectly configured.
* Never silently switch to a different provider.
* Do not expose API keys through API responses, logs, or exception messages.
* Allow switching providers by changing configuration.
* Support dependency injection for provider implementations.
* Keep provider selection independent of retrieval and evidence processing.

### 4.4 Fallback behavior

Implement fallback only when explicitly configured.

For example:

* Primary provider: Anthropic.
* Fallback provider: Ollama.

A fallback must:

* Be explicitly enabled.
* Record which provider actually generated the response.
* Preserve the same evidence context.
* Handle provider-specific failures safely.
* Never silently downgrade the model.
* Never return a partially generated response as a successful answer.

Do not make fallback behavior mandatory for the initial implementation.

### 4.5 Provider testing

Automated tests must not depend on real paid API calls.

Implement:

* Mock providers.
* Provider contract tests.
* Provider selection tests.
* Missing API key tests.
* Invalid configuration tests.
* Timeout and connection failure tests.
* Fallback tests, if fallback is implemented.
* Structured output tests.

If real API credentials are unavailable, verify provider integrations through mocked HTTP/API responses and document what has not been verified against live services.

## 5. Embedding Architecture

Implement an embedding abstraction independently of the LLM provider abstraction.

The embedding model must not be assumed to be the same as the generation model.

Evaluate suitable embedding models for HerbaGuard, considering:

* Scientific terminology.
* Botanical names and synonyms.
* Drug names and generic names.
* Pharmacological terminology.
* Multilingual potential where relevant.
* Local execution.
* Resource consumption.
* Licensing and model availability.

Candidate models may include:

* `BAAI/bge-m3`
* `sentence-transformers/all-MiniLM-L6-v2`
* Other technically suitable models identified during the audit.

Do not select a model purely based on popularity.

Benchmark at least two viable candidates if the environment allows it.

The evaluation must consider retrieval relevance, latency, resource consumption, and compatibility with the existing data model.

### Requirements

* Configurable embedding model.
* Consistent embedding dimensions.
* Documented embedding normalization strategy.
* Reproducible embedding generation.
* Batch processing where appropriate.
* Proper handling of missing or invalid text.
* Model version tracking.
* Ability to regenerate embeddings when the embedding model changes.

If the existing `search_chunks` table is suitable, extend it instead of creating redundant storage.

If a schema change is necessary, implement it through an Alembic migration.

Do not silently mix vectors produced by different embedding models or dimensions.

## 6. Hybrid Retrieval System

Implement Hybrid Retrieval combining semantic and lexical search.

### 6.1 Semantic retrieval

Use vector similarity search to retrieve evidence relevant to the user's question.

Prefer PostgreSQL with pgvector if compatible with the existing database setup.

Requirements:

* Vector similarity search.
* Configurable top-k.
* Similarity thresholds.
* Metadata filtering.
* Efficient indexing where justified.
* Deterministic behavior for identical inputs and database state.

### 6.2 Keyword retrieval

Use PostgreSQL Full-Text Search or an appropriate existing lexical search implementation.

It must support exact and partial matching of:

* Scientific plant names.
* Common plant names.
* Synonyms.
* Drug names.
* Generic drug names.
* Active constituents.
* CYP enzymes.
* Transporters.
* Interaction terminology.
* Scientific phrases.

Pay particular attention to botanical synonyms and drug aliases already supported by HerbaGuard.

### 6.3 Hybrid ranking

Combine semantic and keyword retrieval using a documented ranking approach.

Evaluate Reciprocal Rank Fusion (RRF) or another justified fusion strategy.

The implementation must:

* Avoid duplicate evidence chunks.
* Preserve source identifiers.
* Preserve provenance.
* Preserve evidence metadata.
* Support filtering by source, evidence type, plant, drug, and other relevant fields.
* Avoid ranking irrelevant keyword matches above highly relevant evidence without justification.

Do not treat vector similarity as scientific evidence quality.

### 6.4 Retrieval metadata

Every retrieved evidence item should preserve, where available:

* Evidence identifier.
* Source name.
* Source URL.
* Source licence.
* Retrieval timestamp.
* Publication date.
* Evidence type.
* Plant or drug association.
* Scientific location, section, or page.
* Original excerpt.
* Extraction method.
* Provenance information.

The retrieval system must never lose the connection between a chunk and its original source.

## 7. Knowledge Graph Integration

Integrate the existing PostgreSQL Knowledge Graph into the retrieval pipeline.

Do not recreate the graph.

Use existing services and queries to retrieve structured context related to:

* Plants.
* Botanical synonyms.
* Herbal substances.
* Active constituents.
* Enzymes.
* Transporters.
* Drugs.
* Mechanism relationships.
* Evidence supporting those relationships.

The system should be able to enrich retrieved documents with relevant graph context.

Examples:

* A question about St John's wort and warfarin should retrieve relevant EMA evidence, FDA label information, and existing interaction classification.
* A question about Ginkgo and P-glycoprotein should retrieve relevant mechanism relationships and preserve uncertainty in the source wording.
* A question about CYP3A4 should retrieve related enzyme and drug mechanism information without assuming that shared enzyme membership proves a clinical interaction.

Graph context must remain distinguishable from direct source evidence.

A graph relationship must not be presented as stronger evidence than its underlying source supports.

## 8. Question Understanding and Query Processing

Implement a question-processing layer that can identify relevant entities and query intent.

Supported intents should include:

* Plant information.
* Plant safety information.
* Drug information.
* Herb–drug interaction questions.
* Pharmacological mechanisms.
* Active constituents.
* Scientific evidence lookup.
* Evidence comparison.
* Source and provenance questions.
* General questions about HerbaGuard data coverage.

The system should recognize:

* Botanical scientific names.
* Common names and synonyms.
* Drug brand names and generic names.
* Enzyme identifiers.
* Transporter identifiers.
* Relevant scientific terminology.

Reuse existing entity resolution and ambiguity handling wherever possible.

Do not make the LLM the sole authority for entity resolution.

When the question contains an ambiguous entity:

* Use existing deterministic entity resolution.
* Return candidates when necessary.
* Ask for clarification when ambiguity materially affects the answer.
* Do not guess the intended plant or drug.

Do not overcomplicate the initial implementation with an autonomous agent architecture.

A controlled query-processing pipeline is preferred.

## 9. Evidence Assembly and Context Management

Create a dedicated evidence assembly service.

Its responsibility is to prepare a structured and traceable context for answer generation.

The context should:

* Contain the most relevant retrieved evidence.
* Include relevant graph relationships.
* Preserve source attribution.
* Preserve original excerpts.
* Distinguish direct evidence from contextual information.
* Include relevant interaction classifications.
* Include uncertainty and conflicting evidence.
* Avoid duplicate passages.
* Respect model context limits.

Implement configurable limits for:

* Maximum retrieved chunks.
* Maximum context length.
* Maximum evidence items.
* Maximum tokens sent to the model.

Do not truncate evidence in a way that removes important qualifiers, negations, conditions, or uncertainty.

For example, the difference between:

* "Inhibits P-glycoprotein."
* "May inhibit P-glycoprotein."

must be preserved.

The same applies to statements such as:

* "No interaction reported."
* "No evidence found."
* "Interaction has not been assessed."

These statements must never be treated as interchangeable.

## 10. Grounded Answer Generation

Implement a dedicated answer generation service.

The LLM must receive:

* System instructions.
* The user's question.
* Retrieved evidence.
* Relevant graph context.
* Existing deterministic interaction classification.
* Explicit instructions about evidence quality and uncertainty.

### Core generation rules

The LLM must:

* Answer only within the scope of available evidence.
* Distinguish documented facts from interpretation.
* Preserve scientific uncertainty.
* Avoid inventing mechanisms, interactions, publications, or source references.
* Avoid presenting experimental findings as established clinical outcomes.
* Avoid presenting traditional use as proof of clinical efficacy.
* Avoid interpreting the absence of evidence as evidence of safety.
* Clearly identify conflicting sources.
* Explain when available evidence is insufficient.
* Cite the evidence used in its answer.

The LLM must not:

* Independently classify herb–drug interactions.
* Override the deterministic A–E classification.
* Invent an interaction severity.
* Invent clinical recommendations.
* Recommend starting, stopping, or changing medication.
* Provide personalized diagnoses.
* Prescribe treatment or dosage.
* Claim that a plant or combination is safe merely because no interaction was found.

### Answer structure

Use a structured response model containing fields similar to:

```
{
  "answer": "Evidence-grounded natural-language response.",
  "intent": "herb_drug_interaction",
  "provider": "ollama",
  "model": "qwen3:4b",
  "classification": {
    "class": "A",
    "description": "Existing deterministic classification.",
    "source": "Existing interaction classification service"
  },
  "evidence": [
    {
      "evidence_id": "existing-evidence-id",
      "source": "EMA",
      "source_url": "original-source-url",
      "excerpt": "Verbatim source excerpt",
      "evidence_type": "regulatory_monograph",
      "location": "Section 4.5"
    }
  ],
  "limitations": [],
  "insufficient_evidence": false,
  "disclaimer": "Educational information, not medical advice."
}
```

This is an illustrative contract, not permission to invent identifiers or classifications.

Adapt it to the existing API conventions and actual database schema.

The classification field must be obtained from the existing deterministic service, not generated by the LLM.

## 11. Citation and Evidence Validation

Citation integrity is a critical requirement.

Implement validation to ensure that:

* Every cited evidence identifier exists in the retrieved context.
* Every citation refers to an actual database evidence record.
* Source URLs come from stored provenance.
* Excerpts match the underlying evidence.
* The model cannot introduce fabricated source identifiers.
* Unsupported claims are detected or flagged where technically feasible.

Prefer structured citation references over free-form citations generated by the model.

If the LLM produces an invalid citation:

* Do not silently accept it.
* Flag it for validation.
* Remove unsupported citation references or reject the response according to the established validation policy.

Do not claim that automated citation validation proves every generated scientific statement is factually correct.

Document this limitation.

## 12. Deterministic Classification Protection

This requirement is non-negotiable.

The existing A–E classification engine from Phases 3 and 4 remains authoritative.

The AI layer must:

* Call the existing classification service when an interaction question requires it.
* Return the actual classification and explanation produced by that service.
* Preserve mechanism assessment outcomes.
* Preserve source-specific caveats.
* Preserve the distinction between clinical, experimental, uncertain, and conflicting evidence.
* Never derive a new A–E classification from an LLM response.
* Never allow model output to modify database classifications.

The following established examples must remain consistent:

* St John's wort + warfarin: A.
* St John's wort + atorvastatin: B.
* St John's wort + isotretinoin: C.
* Hawthorn + warfarin: D.
* Echinacea + nimodipine: C.

Use existing regression tests and fixtures where available.

Do not hardcode these examples into production classification logic.

## 13. API Integration

Expose the AI functionality through versioned API endpoints consistent with existing conventions.

Consider endpoints such as:

**POST `/api/v1/ai/ask`**

* Accepts a natural-language question.
* Supports optional conversation context only if justified.
* Runs question understanding, retrieval, evidence assembly, and generation.
* Returns a structured, evidence-grounded answer.

**POST `/api/v1/ai/retrieve`**

* Performs retrieval without LLM generation.
* Useful for debugging and retrieval evaluation.
* Returns ranked evidence and provenance.

**GET `/api/v1/ai/providers`**

* Returns available provider identifiers and configuration status.
* Must never expose API keys or secret configuration values.
* Must distinguish configured providers from currently reachable providers if both are reported.

**GET `/api/v1/ai/health`**

* Reports AI subsystem health without unnecessarily invoking paid model APIs.
* Separates database, embedding, retrieval, and generation provider status.

These are proposed endpoints. Adapt naming and structure to the existing API architecture.

Requirements:

* Pydantic request and response schemas.
* Input validation.
* Consistent error envelopes.
* Appropriate HTTP status codes.
* Request IDs.
* Pagination or result limits where appropriate.
* Safe logging.
* No API secrets in responses.
* No raw prompt or sensitive user data in logs.

Do not expose internal provider SDK exceptions directly to clients.

## 14. Prompt Engineering

Create versioned, documented system prompts for:

* General scientific question answering.
* Herb–drug interaction explanations.
* Evidence comparison.
* Insufficient-evidence responses.

Prompts must explicitly define:

* HerbaGuard's scientific scope.
* Evidence hierarchy and limitations.
* Citation requirements.
* Uncertainty handling.
* The prohibition against medical advice.
* The prohibition against inventing evidence.
* The authority of the deterministic A–E classification engine.

Keep prompts separate from business logic.

Do not rely on prompt instructions alone for security, citation validation, or classification integrity. Enforce critical requirements in application code.

## 15. Evaluation Framework

Build a reproducible evaluation framework for the retrieval and generation pipeline.

Do not evaluate the system only by demonstrating that it produces fluent answers.

### 15.1 Retrieval evaluation

Create a curated evaluation dataset containing representative questions about:

* Plants and botanical synonyms.
* Drugs and generic/brand names.
* Herb–drug interactions.
* CYP enzymes.
* Transporters.
* Active constituents.
* EMA monographs.
* NCCIH information.
* FDA labels.
* PubMed literature.
* Conflicting evidence.
* Missing evidence.

Evaluate:

* Recall@K.
* Precision@K where ground truth is available.
* Mean Reciprocal Rank (MRR).
* Retrieval latency.
* Duplicate retrieval rate.
* Source coverage.

Compare semantic, keyword, and hybrid retrieval.

Document the methodology and limitations of the evaluation dataset.

### 15.2 Generation evaluation

Evaluate:

* Faithfulness to retrieved evidence.
* Citation validity.
* Citation completeness.
* Unsupported claim rate.
* Appropriate uncertainty.
* Correct use of deterministic classifications.
* Correct handling of conflicting evidence.
* Refusal of unsupported medical advice.
* Response consistency.

Use deterministic checks wherever possible.

Use a documented manual review procedure for scientific quality that cannot be reliably assessed through automated tests.

Do not use an LLM judge as the sole measure of scientific correctness.

### 15.3 Provider comparison

If multiple providers are available, create a benchmark procedure to compare:

* Answer quality.
* Citation validity.
* Evidence faithfulness.
* Latency.
* Token usage and cost where available.
* Failure rate.

The benchmark must work with local Ollama and optional cloud providers.

Do not require paid API calls to run the automated test suite.

Do not claim that one provider is scientifically superior without supporting evaluation results.

## 16. Security, Privacy and Reliability

Implement appropriate protections:

* API keys exclusively through environment variables.
* No secrets in source code or fixtures.
* No sensitive prompt content in logs.
* Request timeouts.
* Provider error normalization.
* Input size limits.
* Context size limits.
* Rate limiting if consistent with existing backend infrastructure.
* Protection against prompt injection contained in retrieved documents.
* Strict separation between retrieved content and system instructions.
* No tool execution or database writes initiated by LLM-generated instructions.
* No unrestricted SQL execution.
* No model-generated modifications to the Knowledge Graph.
* No autonomous medical decisions.

Retrieved documents must be treated as untrusted data.

The model must not follow instructions found inside source documents that attempt to override HerbaGuard's system instructions.

## 17. Database and Migrations

Inspect the existing database before designing schema changes.

Potential additions may include:

* Embedding model metadata.
* Embedding version information.
* Retrieval evaluation records.
* AI request metadata.
* Optional generation evaluation records.

Do not store complete user prompts or generated answers unnecessarily.

If storing AI requests is justified, document:

* What is stored.
* Why it is stored.
* Retention considerations.
* Privacy implications.

All schema changes must use Alembic migrations.

Do not modify historical migration files that have already been applied.

Avoid storing redundant copies of existing evidence.

## 18. Observability

Add appropriate structured observability for the AI subsystem.

Track, where available:

* Provider.
* Model.
* Request duration.
* Retrieval duration.
* Number of retrieved chunks.
* Number of evidence sources.
* Token usage.
* Provider errors.
* Citation validation failures.
* Evaluation results.

Never log API keys or full sensitive prompt contents.

Reuse existing request ID and logging conventions.

## 19. Docker and Development Experience

Update Docker configuration only where necessary.

Ensure the existing application continues to work when:

* Ollama is unavailable.
* No cloud provider API key is configured.
* The embedding model has not yet been downloaded.
* Optional AI dependencies are unavailable.

The non-AI HerbaGuard API must remain operational independently of optional LLM providers.

Document:

* How to install and run Ollama.
* How to pull `qwen3:4b`.
* How to configure Anthropic.
* How to configure OpenAI.
* How to switch providers.
* How to configure embeddings.
* How to run retrieval without generation.
* How to run evaluation tests.

Update `.env.example` without adding actual credentials.

## 20. Documentation Requirements

Create or update relevant documentation, following the existing documentation structure.

Expected documentation may include:

* `docs/ai/architecture.md`
* `docs/ai/llm-providers.md`
* `docs/ai/embedding-models.md`
* `docs/ai/hybrid-retrieval.md`
* `docs/ai/prompt-design.md`
* `docs/ai/evaluation.md`
* `docs/ai/security.md`
* `docs/api/` documentation for new endpoints.
* Relevant ADRs.

Document:

* Architecture decisions.
* Provider switching.
* Model configuration.
* Embedding selection.
* Retrieval ranking.
* Citation validation.
* Evaluation methodology.
* Known limitations.
* Cost and infrastructure considerations.

All documentation must be written in English.

Use English technical terminology consistently.

## 21. Testing Requirements

Add comprehensive tests covering:

**Provider Layer**

* Ollama provider contract.
* Anthropic provider contract.
* OpenAI provider contract.
* Provider selection.
* Missing credentials.
* Invalid configuration.
* Timeouts.
* Connection errors.
* Mocked generation.
* Optional fallback behavior.

**Embedding Layer**

* Embedding generation.
* Invalid input.
* Dimension validation.
* Model metadata.
* Version compatibility.

**Retrieval**

* Semantic search.
* Keyword search.
* Hybrid ranking.
* Duplicate elimination.
* Metadata filtering.
* Botanical synonyms.
* Drug aliases.
* Missing evidence.
* Provenance preservation.

**Knowledge Graph Integration**

* Graph context retrieval.
* Mechanism relationship retrieval.
* Evidence provenance.
* Conflicting mechanism evidence.
* Separation of direct evidence and graph context.

**Generation**

* Grounded answer generation.
* Citation validation.
* Unsupported citation rejection.
* Insufficient evidence.
* Conflicting evidence.
* Uncertainty preservation.
* Prompt injection resistance.
* Medical advice restrictions.

**Classification Integrity**

* Existing A–E classifications remain unchanged.
* The LLM cannot override classification results.
* No classification is inferred from shared enzyme membership alone.

**API**

* Valid requests.
* Invalid requests.
* Provider unavailable.
* Missing configuration.
* Retrieval-only operation.
* Error handling.
* Health reporting.
* No secret exposure.

Run the complete existing test suite, not just newly introduced tests.

Do not remove, weaken, skip, or rewrite existing tests merely to make the new implementation pass.

## 22. Performance and Resource Considerations

The initial environment may not have sufficient resources for larger models.

Optimize for a practical local development environment.

Prioritize:

* Qwen3-4B local inference.
* Efficient embedding generation.
* Batched processing.
* Retrieval indexing.
* Bounded context.
* Configurable result limits.
* Reasonable timeouts.
* Avoiding unnecessary model invocations.

Do not assume GPU availability.

Do not introduce a paid service as a mandatory dependency.

If performance limitations are identified, document them with actual measurements where possible.

## 23. Scope Boundaries

Phase 5 includes:

* LLM provider abstraction.
* Initial Ollama/Qwen3-4B integration.
* Optional Anthropic and OpenAI integrations.
* Embedding abstraction and model evaluation.
* Hybrid retrieval.
* Existing Knowledge Graph context integration.
* Evidence assembly.
* Grounded answer generation.
* Citation validation.
* AI API endpoints.
* Evaluation framework.
* Security and observability.
* Tests and documentation.

Phase 5 does NOT include:

* Frontend AI chat interface.
* Frontend redesign.
* Autonomous AI agents.
* LLM-controlled database writes.
* LLM-generated interaction classifications.
* Medical diagnosis or treatment recommendations.
* Fine-tuning or LoRA training.
* Replacing PostgreSQL with Neo4j.
* Reimplementing Phases 1–4.
* Starting Phase 6.

If a task is outside Phase 5, document it as a future improvement rather than implementing it.

## 24. Implementation Workflow

Follow this workflow strictly.

**Step 1 — Audit**

* Inspect the repository and relevant documentation.
* Understand the existing data and API architecture.
* Identify reusable components.
* Identify actual gaps.

**Step 2 — Design**

* Propose the AI/RAG architecture.
* Define provider and embedding interfaces.
* Define retrieval and evidence assembly contracts.
* Identify necessary migrations.
* Document important decisions.

**Step 3 — Save the Phase Prompt**

Before implementation, save the complete standalone Phase 5 prompt in `prompts/phase-5-ai-rag.md`. If the file already exists, inspect it and update it without deleting relevant project history or useful decisions.

**Step 4 — Implement in Logical Subphases**

Use the following implementation order:

* 5.1 — AI architecture, configuration, and provider abstractions.
* 5.2 — Ollama/Qwen3-4B integration and optional Anthropic/OpenAI adapters.
* 5.3 — Embedding abstraction and embedding model evaluation.
* 5.4 — Hybrid retrieval implementation.
* 5.5 — Knowledge Graph context integration and evidence assembly.
* 5.6 — Grounded answer generation and citation validation.
* 5.7 — AI API endpoints, security, and observability.
* 5.8 — Retrieval and generation evaluation framework.
* 5.9 — Full regression testing, documentation, and final validation.

These are implementation subphases within Phase 5, not permission to start Phase 6.

After completing each logical subphase, verify the implementation before proceeding.

If a major architectural decision or unexpected problem arises, stop and report it before making a potentially disruptive change.

**Step 5 — Validate**

* Run formatting and linting.
* Run type checking.
* Run all relevant unit tests.
* Run integration tests.
* Run database migration checks.
* Run existing regression tests.
* Verify Docker compatibility.
* Test local Ollama integration where the environment allows.
* Test provider switching with mocked cloud providers.
* Verify the existing non-AI API still works independently.

**Step 6 — Final Report**

At the end of Phase 5, provide a detailed report containing:

* Implementation overview.
* Architecture and design decisions.
* Files created and modified.
* Database migrations.
* LLM providers implemented.
* Embedding model selected and benchmark results.
* Retrieval implementation and evaluation results.
* Knowledge Graph integration.
* API endpoints.
* Citation and evidence validation.
* Security measures.
* Test results.
* Performance measurements.
* Known limitations.
* Features that could not be verified.
* Git status.
* Remaining tasks.
* Suggested next phase.

Do not claim that a live provider integration works if it was only tested using mocks.

Do not claim that scientific accuracy has been established merely because automated tests pass.

## 25. Git and Change Management Rules

These rules are mandatory.

* Do not run `git commit`.
* Do not run `git push`.
* Do not amend commits.
* Do not rebase, squash, reset, or rewrite Git history.
* Do not create tags.
* Do not automatically merge branches.
* Do not stage changes unless explicitly requested.
* Do not modify Git history indirectly.

The user is responsible for reviewing, committing, and pushing all changes.

At the end, provide:

* Current branch.
* Current HEAD.
* Git status.
* Modified files.
* Untracked files.
* Whether anything is staged.
* Suggested commit message.
* Detailed commit description.

## 26. Definition of Done

Phase 5 is complete only when:

* HerbaGuard has a working provider-independent LLM architecture.
* Qwen3-4B can be used locally through Ollama.
* Anthropic and OpenAI adapters are implemented and tested without mandatory paid credentials.
* Provider switching works through configuration.
* Embedding generation is configurable and documented.
* Hybrid semantic and keyword retrieval works.
* Retrieved evidence retains source provenance.
* Existing Knowledge Graph context is integrated.
* Grounded answers include validated evidence references.
* Insufficient and conflicting evidence are handled explicitly.
* The LLM cannot modify or override A–E classifications.
* AI API endpoints work.
* Security and error handling are implemented.
* Retrieval and generation evaluation can be reproduced.
* Existing tests continue to pass.
* Documentation is complete.
* No Phase 6 implementation has started.

The final objective is not simply to integrate an LLM. It is to build a reliable, traceable, provider-independent scientific RAG system that uses HerbaGuard's existing evidence and Knowledge Graph to generate useful explanations without inventing scientific conclusions or weakening the deterministic safety classification system.

Start with the repository audit. Do not begin implementation until the audit and proposed architecture have been presented. Stop after completing Phase 5 and wait for explicit approval before starting another phase.

---

# Addendum (2026-11-03) — Additional Implementation Constraints: Future Dataset Expansion Compatibility

Given in chat after the Phase 5 audit; mandatory throughout Phase 5. Summary of the binding requirements (full wording in the chat of 2026-11-03):

1. **Current corpus is an initial dataset** (≈2,875 chunks). Future sources may include IMPPAT, Dr Duke, LOTUS, KNApSAcK, COCONUT, PubChem, ChEMBL, ChEBI. No hardcoded counts, source lists or source-specific logic that blocks new sources; retrieval, filtering, ranking, citation and context assembly must work with growing data; provenance to the original dataset preserved.
2. **Model-independent embeddings:** `EmbeddingProvider` abstraction; store model id, model version, dimension, timestamp and source-text hash; never mix models in one similarity search; configurable, validated dimensions; manageable model/dimension changes; incremental embedding; stale detection by hash and model version; no full re-embedding when only a subset changed. Do not commit to a model before the benchmark justifies it.
3. **Configurable, source-aware chunking**, independent of source implementations; keep sentences, qualifiers, conditions and negations together; strategy and version stored; re-chunking and re-indexing supported.
4. **Retrieval for an expanding knowledge base:** FTS + pgvector + RRF with adjustable weights, top-k, source preferences and filters (plants, drugs, compounds, enzymes, transporters, source, evidence type); no fixed dataset list; source-specific adapters separate from the common interface; graceful handling of missing embeddings and partially indexed data; new evidence searchable without architectural change.
5. **Re-indexing and incremental processing:** index new evidence; update embeddings when text changes; invalidate stale entries when evidence is superseded (without deleting provenance or superseded statements); re-chunk when rules change; re-embed selected documents or sources; track status and failures; safe retries; no duplicate chunks or embeddings; content hashes and stable identifiers.
6. **Baseline vs final evaluation:** label the current evaluation as a baseline; no corpus-count assumptions in questions or metrics; extensible question set; keyword vs semantic vs hybrid; Recall@k, Precision@k, MRR, latency, source coverage, citation validity; rerun after dataset expansion.
7. **Scientific integrity** distinctions (traditional use vs efficacy; in-vitro vs clinical; mechanistic plausibility vs established interaction; absence of reports vs safety; experimental activity vs therapeutic benefit; source statements vs validated conclusions). A–E classification stays authoritative; the LLM never overrides it, invents mechanisms or conclusions, upgrades experimental findings, gives dosing or treatment advice, or treats missing evidence as safety.
8. **Model downloads:** inspect the existing Ollama installation; use the installed Qwen3-4B GGUF if possible; avoid duplicate downloads; measure real inference performance; download embedding models only for a meaningful benchmark; no paid credits assumed; cloud providers optional; **no source material sent to cloud providers unless licensing and configuration explicitly permit it**.
9. **Reporting:** state which components are expansion-compatible, which assumptions come from the current corpus, what must be reassessed after expansion, whether embedding models/dimensions can change without redesign, how incremental re-indexing works, baseline retrieval results and their limits, and remaining technical/licensing risks. No dataset expansion or later phases; no Git operations.
