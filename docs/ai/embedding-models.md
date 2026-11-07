# Embedding Models (Phase 5)

**Default: `nomic-embed-text`** (Ollama, 768 dimensions), selected by the measured comparison below. Change with `HERBAGUARD_EMBEDDING_MODEL` (and run `herbaguard ai index` so the new model's vectors exist); vectors of different models are stored side by side and never compared ([hybrid-retrieval.md](hybrid-retrieval.md) §2).

## 1. Candidates

| Model (Ollama tag) | Params | Dim | Context | Licence (model card) | Notes |
|---|---|---|---|---|---|
| `all-minilm` (all-MiniLM-L6-v2) | 23 M | 384 | 256 tokens | Apache-2.0 | Truncates long label sections |
| `nomic-embed-text` (v1.5) | 137 M | 768 | 8,192 tokens | Apache-2.0 | Needs task prefixes `search_query:` / `search_document:` (set automatically) |
| `bge-m3` | 568 M | 1,024 | 8,192 tokens | MIT | Multilingual |

All run locally on CPU through Ollama; vectors are L2-normalised by HerbaGuard; the model version stored with each vector is the Ollama digest.

## 2. Method

The same 5,106 segments (identical text, `title | section` + segment) were embedded once per model; the same 35-question baseline (`data/evaluation/rag_baseline_v1.yaml`, 31 questions scored), the same retrieval settings and the same database state were used for every run (`herbaguard ai evaluate-retrieval --embedding-model …`, report `docs/ai/results/retrieval_baseline_v1_2026-11-06.json`). Query latency was measured with all non-HerbaGuard containers stopped (machine otherwise idle).

## 3. Results (baseline v1, 2026-11-06)

| Mode | Model | Hit@5 | Recall@5 | Recall@10 | Prec@5 | Prec@10 | MRR | Median / p95 latency |
|---|---|---|---|---|---|---|---|---|
| keyword | – | 0.871 | 0.492 | 0.546 | 0.361 | 0.268 | 0.677 | 30 / 72 ms |
| semantic | all-minilm | 0.806 | 0.367 | 0.496 | 0.348 | 0.271 | 0.535 | 311 / 356 ms |
| hybrid | all-minilm | 0.871 | 0.425 | 0.562 | 0.374 | 0.293 | 0.739 | 323 / 736 ms |
| semantic | nomic-embed-text | 0.871 | 0.457 | 0.551 | 0.342 | 0.277 | 0.709 | 340 / 393 ms |
| **hybrid** | **nomic-embed-text** | **0.871** | **0.466** | **0.635** | **0.368** | **0.300** | **0.759** | 356 / 1,124 ms |
| semantic | bge-m3 | 0.806 | 0.388 | 0.516 | 0.336 | 0.268 | 0.710 | 392 / 450 ms |
| hybrid | bge-m3 | 0.806 | 0.421 | 0.544 | 0.361 | 0.271 | 0.700 | 436 / 1,410 ms |

Resource use (development machine: Ryzen 7 5700U, 14 GB RAM, CPU only):

| Model | Download | Loaded in RAM | Query embedding (median, warm) | Full index (5,106 segments) | Vectors / HNSW index |
|---|---|---|---|---|---|
| all-minilm | 46 MB | 49 MB | 334 ms | 340 s | 7.7 MB / 10 MB |
| nomic-embed-text | 274 MB | 389 MB | 357 ms | 1,808 s | 15 MB / 20 MB |
| bge-m3 | 1.2 GB | 1,244 MB | 399 ms | ≈ 100 min (estimated from a timed 64-segment sample; the full run's wall clock spans a machine suspension) | 20 MB / 40 MB |

Query-time cost is dominated by embedding the question (≈ 0.35 s via Ollama); the database part of hybrid retrieval takes tens of milliseconds. **Indexing is a one-time cost per model**; afterwards only new or changed segments are embedded (incremental indexing re-runs in < 1 s when nothing changed).

## 4. Decision

`nomic-embed-text` gives the best hybrid Recall@10 (0.635), MRR (0.759) and Precision@10 (0.300) at a third of bge-m3's memory and indexing time. bge-m3's multilingual strength is not exercised by the English-only baseline; it should be re-evaluated if non-English questions or sources are added. all-minilm is the low-resource option.

## 5. Limitations

* Baseline only: 31 scored questions written by the implementer; differences of a few hundredths correspond to one or two questions. Re-run after the dataset expansion (`data/evaluation/rag_expanded_v2.yaml`).
* The brand-name question (`brand-coumadin`) scored 0 for all modes because RxNav was unreachable during the run (no network); it measures entity resolution, not embeddings.
* Keyword retrieval is strong here because retrieval is scoped to recognised entities and text relevance rules favour lexical matches ([evaluation.md](evaluation.md) §1).
