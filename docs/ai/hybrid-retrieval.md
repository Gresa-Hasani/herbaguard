# Hybrid Retrieval and the Retrieval Index (Phase 5)

Implementation: `ai/indexing/` (segments, embeddings), `ai/retrieval.py` (search), `ai/fusion.py` (RRF). Schema: migration 0005 (`retrieval_segment`, `segment_embedding`).

## 1. Retrieval units: segments

Stored `chunk` rows (Phase 2) remain the canonical text for citations. Retrieval searches **segments** cut from chunks:

* A segment is a character range `[char_start, char_end)` of `chunk.text`; the text is not copied. Every segment maps back to its chunk, evidence item, source and provenance.
* Strategy `sentence_window` (default): whole sentences packed up to `segment_max_chars` (1,200), consecutive segments sharing `segment_overlap_sentences` (1) sentence. **A sentence is never split** — qualifiers, conditions and negations stay with their statement; semicolons are not boundaries (*"is not recommended; plasma concentrations … may be decreased"* stays together). A sentence longer than the limit becomes its own segment.
* Strategy `whole_chunk`: one segment per chunk (for short, self-contained records).
* Per-source overrides without code changes: `HERBAGUARD_SEGMENT_STRATEGY_BY_SOURCE='{"pubmed":"whole_chunk"}'`, `HERBAGUARD_SEGMENT_MAX_CHARS_BY_SOURCE='{"openfda_label":1500}'`. A new strategy is one function registered in `segmenter.STRATEGIES`.
* Stored with each segment: `strategy`, `strategy_version` (includes the parameters, e.g. `v1-max1200-ov1`), `chunk_text_sha256`, `text_sha256` (of the embedded text), and a full-text vector: evidence title (weight A) + segment text (weight B).

Initial index (2026-11-03): 2,875 chunks → 5,106 segments (labels 3,487, PubMed 1,310, EMA 215, NCCIH 87, FDA table 7). Build time 18.6 s; an unchanged re-run takes 0.6 s.

## 2. Embeddings

`segment_embedding` holds one vector per (segment, model) with `model`, `model_version` (provider digest), `provider`, `dimension`, `text_sha256`, `embedded_at`. The vector column has **no fixed dimension**; a CHECK keeps `dimension = vector_dims(embedding)`. Several models can coexist (used for the benchmark). Each model gets a partial HNSW index on `embedding::vector(<dim>)` filtered by model. The embedded text is `title | section` + segment text; vectors are L2-normalised. Details and the model choice: [embedding-models.md](embedding-models.md).

## 3. Retrieval

| Retriever | How | Notes |
|---|---|---|
| Keyword | PostgreSQL full-text search over segment vectors: any word of the question (OR) plus each entity name as a phrase (synonyms, accepted and pharmaceutical names, common names, drug names, target symbols); `ts_rank_cd` with length normalisation | Exact names, CYP symbols, drug names |
| Semantic | Cosine distance on the configured model's vectors, **only** rows whose model, model version and dimension match and whose text hash equals the current segment's (stale vectors ignored); optional `retrieval_min_similarity` | Paraphrases ("coumarin-type anticoagulants" ≈ warfarin) |
| Hybrid | Reciprocal Rank Fusion of both lists | Default |

**Fusion.** `score = Σ w_r / (k + rank_r)`, `k = 60`, weights `retrieval_keyword_weight` / `retrieval_vector_weight` (1.0 / 1.0), optional per-source multipliers `retrieval_source_weights` (empty = neutral). RRF uses ranks only, so ts_rank and cosine values never need to be put on one scale. Ties are broken by segment id (deterministic).

**De-duplication and diversity.** At most `retrieval_max_per_evidence_item` (2) segments per evidence item; overlapping segments of the same chunk are never both returned.

**Filters.** Source codes, evidence types, and entity scopes resolved through the generic link tables: herb → `herbal_substance_evidence`; drug → evidence of `interaction_assertion`s naming it and `drug_target_role` rows; enzyme/transporter → `target_modulation` and `drug_target_role`. `/ai/ask` scopes to *any* recognised entity; `/ai/retrieve` combines given filters with AND. Superseded evidence is never returned.

**Scores are not evidence quality.** `fused_score`, `similarity` and `keyword_score` rank text relevance only; responses say so.

Questions without any recognised herb, drug, enzyme, transporter or constituent use only passages with semantic similarity ≥ `ai_unscoped_min_similarity` (0.6), so unrelated text is not presented as an answer.

## 4. Incremental indexing and re-indexing

```bash
herbaguard ai index                       # new/changed chunks → segments; missing/stale vectors → embeddings
herbaguard ai index --source pubmed       # one source only
herbaguard ai index --model nomic-embed-text   # embed with another model (coexists with the current one)
herbaguard ai index --segments-only
herbaguard ai status                      # coverage for the configured model
```

| Event | What happens |
|---|---|
| New evidence ingested | its chunks get segments; only those segments are embedded |
| Chunk text changed | hash differs → its segments are rebuilt → their vectors are stale (hash) → re-embedded |
| Segmentation parameters changed | strategy version differs → segments rebuilt for all chunks of the affected sources |
| Embedding model updated (new digest) | model version differs → re-embedded |
| Embedding model changed | new model's vectors are created next to the old ones; switch `HERBAGUARD_EMBEDDING_MODEL`; old vectors can be deleted later |
| Evidence superseded | its segments are removed from the index; the evidence item, chunks, provenance and statements are kept |
| Embedding failure | batch retried per segment; remaining failures recorded as `embedding_failed` data-quality issues; the next run retries them |

Every run is an `ingestion_run` of source `herbaguard_ai_index` with statistics and issues. Segment ids are deterministic (`uuid5` of chunk, strategy, version, ordinal), embeddings are keyed by (segment, model): re-running never duplicates.

## 5. Latency

Keyword retrieval: tens of milliseconds. Semantic retrieval is dominated by embedding the question on the CPU (see [evaluation.md](evaluation.md)).

## 6. Dataset expansion

* No source list, evidence type list, corpus size or model is hard-coded in retrieval, fusion, assembly or indexing. A new source is indexed and filterable as soon as its evidence is stored as `evidence_item`/`chunk` and linked through the existing link tables.
* **Assumptions from the current corpus** (to be re-assessed after expansion): segment size 1,200 characters (fits label sections and abstracts), RRF k = 60 and equal weights, top-k 40/40/10, `ai_unscoped_min_similarity` 0.6, the context budget (≈ 2,600 tokens, tuned to CPU inference), and the embedding model choice. All are configuration.
* Compound databases (IMPPAT, LOTUS, KNApSAcK, COCONUT, ChEBI/PubChem) are largely structured records, not prose: they will mainly enter through the knowledge graph (constituents, targets) and need a segmentation strategy that renders records as short text (a new strategy, not a redesign).
