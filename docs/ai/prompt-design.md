# Prompt Design (Phase 5)

Prompts are versioned files in `backend/src/herbaguard/ai/prompts/` with front matter (`id`, `version`, `purpose`). The response of every answer lists the prompts used (`generation.prompts`, e.g. `["system_v1", "interaction_v1"]`). A changed prompt gets a new version file; old versions stay for reproducibility.

| File | Used when |
|---|---|
| `system_v1.md` | Always (prepended). Scope, evidence kinds, data-not-instructions rule, hedging, "no interaction reported ≠ no evidence ≠ not assessed ≠ safe", authority of the A–E class, no medical advice, citation format |
| `interaction_v1.md` | Intent `herb_drug_interaction` with statement evidence |
| `comparison_v1.md` | Intent `evidence_comparison` (several herbs, or "compare/differ/conflict") |
| `general_v1.md` | Plant, drug, mechanism, constituent, evidence and coverage questions |
| `insufficient_v1.md` | Class D or E for a pair, or a herb–drug question without any decisive statement |

The user message contains the question, a note when personal advice was asked for, and the evidence items rendered as tagged blocks:

```
<classification id="C1" role="deterministic_classification"> … </classification>
<evidence id="S1" role="direct_evidence" source="ema_hmpc" evidence_type="REG (Regulatory document)" document="EMA/HMPC/7695/2021#4.5#WEU" location="section 4.5">
verbatim sentence
[statement type: …] [use category: …] [conditions: …]
</evidence>
<evidence id="M1" role="graph_context" …> Ginkgo folium may inhibit ABCB1 … [source wording is hedged: 'may'] </evidence>
```

Angle brackets and double quotes inside source text are replaced (`‹ › '`) so a document cannot close its block or open a new one.

Structured output: `{"paragraphs": [{"text", "citations": ["S1", …]}], "limitations": [...], "insufficient_evidence": bool}` (JSON schema passed to the provider).

**Prompts are not the safety mechanism.** Every critical rule is enforced again in code (`ai/validation.py`, [architecture.md](architecture.md) §3); prompts only make compliant answers more likely.

Qwen3 thinking mode is switched off (`think: false`): answers are short, structured and grounded in given items, and CPU time is limited.
