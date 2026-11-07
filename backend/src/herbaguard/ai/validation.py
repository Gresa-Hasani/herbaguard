"""Validation of model answers (pure, deterministic). Prompts ask for these rules; this module
enforces them in code. Passing validation does NOT prove that every statement is scientifically
correct; it checks citations and a defined set of failure patterns (docs/ai/security.md §4).

Policy (``validate``):

* **Citations** — ids not present in the context are removed (``invalid_citation``). A paragraph
  left without any valid citation is removed (``uncited_paragraph``).
* **Unsupported specifics** — a paragraph that names an enzyme/transporter symbol or a dose-like
  number (``\\d+ mg``…) that does not occur in any item it cites is removed
  (``unsupported_target`` / ``unsupported_number``).
* **Lost hedging** — a paragraph that states an effect without the hedge its cited graph item has
  ("inhibits" where the item says "may inhibit") is flagged (``hedge_dropped``) and removed.
* **Critical** (the whole answer is rejected): a class letter different from the deterministic one
  (or any class when none was computed) — ``classification_conflict``; an assertion that something
  is safe/harmless/risk-free — ``safety_claim``; a direct instruction to start, stop or change
  medicines or a dose — ``medical_directive``; no paragraph left — ``no_supported_content``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from herbaguard.ai.context import ContextItem, EvidenceContext

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "paragraphs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "citations"],
            },
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
        "insufficient_evidence": {"type": "boolean"},
    },
    "required": ["paragraphs", "limitations", "insufficient_evidence"],
}

Severity = Literal["removed", "critical", "warning"]


@dataclass(frozen=True, slots=True)
class Issue:
    rule: str
    severity: Severity
    message: str
    paragraph: int | None = None
    text: str | None = None  # the offending paragraph/limitation (audit only; never shown to users)


@dataclass(frozen=True, slots=True)
class Paragraph:
    text: str
    citations: tuple[str, ...]


@dataclass(slots=True)
class ValidationResult:
    paragraphs: list[Paragraph]
    limitations: list[str]
    insufficient_evidence: bool
    issues: list[Issue] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return any(i.severity == "critical" for i in self.issues)


class AnswerFormatError(ValueError):
    """The model output is not valid JSON of the expected shape."""


def parse(text: str) -> tuple[list[Paragraph], list[str], bool]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = "The model did not return valid JSON."
        raise AnswerFormatError(msg) from exc
    if not isinstance(data, dict) or not isinstance(data.get("paragraphs"), list):
        msg = "The model output has no 'paragraphs' list."
        raise AnswerFormatError(msg)
    paragraphs = []
    for p in data["paragraphs"]:
        if not isinstance(p, dict) or not isinstance(p.get("text"), str):
            msg = "A paragraph has no text."
            raise AnswerFormatError(msg)
        cites = p.get("citations") or []
        if not isinstance(cites, list):
            cites = []
        paragraphs.append(Paragraph(p["text"].strip(), tuple(str(c).strip() for c in cites)))
    limitations = [str(x) for x in data.get("limitations") or [] if str(x).strip()]
    return paragraphs, limitations, bool(data.get("insufficient_evidence", False))


_CLASS = re.compile(r"\bclass(?:es)?\s*[:(]?\s*['\"]?([A-E])\b(?![-–])", re.I)
_SAFE = re.compile(
    r"\b(is|are|be|considered|generally|completely|totally|perfectly|likely|possibly|probably|usually)"
    r"\s+(safe|harmless)\b|"
    r"\bsafe to (take|use|combine|consume)\b|\b(no|without) (any )?(risk|danger)\b|\brisk-free\b|"
    r"\bthere (is|are) no interactions?\b|"
    r"\bno (safety )?concerns?\b|"
    r"\b(can|could|may) (be )?safely\b|\bsafely (take|use|combine|consume|be (taken|used|combined))\b",
    re.I,
)
_NEGATION = re.compile(
    r"\b(not|no|never|cannot|can't|isn't|aren't|doesn't|does not|do not|nor|neither|unclear whether|"
    r"whether)\b[^.]{0,60}$",
    re.I,
)
_DIRECTIVE = re.compile(
    r"\b(you|patients?|users?) (should|must|need to|ought to) (stop|start|discontinue|increase|decrease|"
    r"reduce|change|switch|avoid|take|use|combine)\b|\b(i|we) (recommend|advise|suggest)\b|"
    r"^\s*(stop|start|discontinue|avoid|do not take|don't take) (taking|using|your)\b",
    re.I,
)
# References the model may invent. Each must occur in the context (item text, URL, external id or
# title); otherwise the paragraph is removed. Ported from the earlier Evidence Assistant on main.
_REFERENCES = (
    ("PMID", re.compile(r"\bPMID:?\s*(\d{5,9})\b", re.I)),
    ("DOI", re.compile(r"\b(10\.\d{4,9}/[^\s\]\)]+)", re.I)),
    ("URL", re.compile(r"(https?://[^\s\]\)]+)", re.I)),
)
_DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(mg|g|mcg|µg|ug|ml|iu|units?)\b", re.I)
_TARGET = re.compile(
    r"\b(CYP\s?\d[A-Z]\d{0,2}|P-?gp|P-glycoprotein|BCRP|OATP1B[13]?|OAT[13]|OCT2|MATE\d?(?:-K)?)\b",
    re.I,
)
_CLINICAL_CLAIM = re.compile(
    r"\b(in (?:humans?|patients?|people|clinical practice)|clinically|clinical(?:ly)? (?:significant|relevant|"
    r"evidence|interaction)|established (?:clinical )?interaction|confirmed interaction)\b",
    re.I,
)
_EXPERIMENT_HEDGE = re.compile(
    r"\b(animals?|rats?|mice|dogs?|rabbits?|pigs?|species (?:is |was )?not stated|not (?:human|clinical)|"
    r"laboratory|experimental|in vitro)\b",
    re.I,
)
_HEDGED_GRAPH = re.compile(
    r"\b(may|might|could|can|possibly|probably|potentially) (inhibit|induce)\b", re.I
)


# --- limitation statements (corrected 2026-11-07) -------------------------------------------------
# A limitation may *deny or limit* a safety conclusion ("The absence of reported interactions does not
# mean the combination is safe.") but must never assert one. The safety wording is checked within its
# own sentence and clause; it is accepted only when one of these denial constructions governs it
# directly. Anything else stays a critical safety claim.
_CLAUSE_BOUNDARY = re.compile(
    r"[,;:()\u2013\u2014]|\s-\s|\b(?:and|but|so|therefore|thus|hence|however|although|though|yet|while|"
    r"whereas|because|since)\b",
    re.I,
)
# subject between the denial and the safety wording ("the combination", "that ginkgo"): no verbs or
# connectives that would start a new assertion ("No interaction means it is safe")
_NP = (r"(?:(?!(?:means?|shows?|proves?|indicates?|suggests?|impl(?:y|ies)|confirms?|establish(?:es)?|"
       r"is|are|was|were|be|been|so|thus|therefore|hence)\b)[\w'-]+\s+){0,5}"
       r"(?:(?:is|are|was|were|be|would be|will be)\s+)?")  # fmt: skip
_NEG = r"(?:\b(?:not|never|cannot)|n't)"
_DENIAL = re.compile(
    # "is not / cannot be / has not been shown to be / should not be assumed to be" + safety wording
    rf"{_NEG}\s+(?:necessarily\s+|always\s+|automatically\s+|yet\s+)?(?:(?:be|been)\s+)?"
    r"(?:(?:shown|proven|established|demonstrated|confirmed|known|assumed|presumed|considered|regarded|"
    r"thought)\s+)?(?:to\s+)?$"
    # "does not mean / imply / establish (that) the combination is" + safety wording
    rf"|{_NEG}\s+(?:necessarily\s+|automatically\s+|by itself\s+|on its own\s+)?"
    rf"(?:mean|imply|implies|indicate|establish|show|prove|confirm|guarantee|suggest)\w*\s+(?:that\s+)?{_NP}$"
    # "no / insufficient evidence (to show) that the combination is" + safety wording
    r"|\b(?:no|insufficient|limited|inadequate|not enough|lack of|absence of)\s+(?:[\w'-]+\s+){0,2}?"
    r"(?:evidence|data|proof|studies|research)\s+(?:(?:to\s+)?(?:show|establish|confirm|prove|suggest|"
    rf"support|indicate|demonstrate)\w*\s+(?:that\s+)?|that\s+){_NP}$"
    # "unclear whether / unknown if the combination is" + safety wording
    rf"|\bwhether\s+{_NP}$|\b(?:unclear|uncertain|unknown|not known|not clear)\s+if\s+{_NP}$",
    re.I,
)


def limitation_safety_claims(text: str) -> list[str]:
    """Safety wording in a limitation that is not denied by its own sentence and clause."""
    claims = []
    for sentence in _sentences(text.replace("\u2019", "'")):
        for match in _SAFE.finditer(sentence):
            clause = _CLAUSE_BOUNDARY.split(sentence[: match.start()])[-1]
            if not _DENIAL.search(clause):
                claims.append(match.group(0))
    return claims


# --- effect direction ---------------------------------------------------------------------------
# A claimed change in exposure/effect must have the same direction in the cited source text and must
# not contradict a cited mechanism: induction lowers a substrate's exposure, inhibition raises it.
_UP = r"(?:increas\w*|rais\w*|elevat\w*|enhanc\w*|potentiat\w*|higher|boost\w*|prolong\w*)"
_DOWN = r"(?:decreas\w*|reduc\w*|lower\w*|diminish\w*|weaken\w*|shorten\w*)"
_QUANTITY = (r"(?:exposure|levels?|concentrations?|plasma|auc|cmax|bioavailability|effects?|efficacy|"
             r"effectiveness|activity|action|clearance)")  # fmt: skip
_GAP = r"\W+(?:[\w'-]+\W+){0,6}?"
_CLAIM_UP = re.compile(rf"\b{_UP}{_GAP}{_QUANTITY}\b|\b{_QUANTITY}{_GAP}{_UP}\b", re.I)
_CLAIM_DOWN = re.compile(rf"\b{_DOWN}{_GAP}{_QUANTITY}\b|\b{_QUANTITY}{_GAP}{_DOWN}\b", re.I)
_INHIBITION = re.compile(r"\binhibit\w*", re.I)  # an inhibitor raises a substrate's exposure
_INDUCTION = re.compile(r"\binduc\w*", re.I)  # an inducer lowers it
_BLEEDING = re.compile(r"\b(?:bleed\w*|ha?emorrhag\w*)\b", re.I)
# "clearance" moves opposite to exposure: "increased clearance" is a decrease in exposure.
_CLEARANCE_UP = re.compile(rf"\b{_UP}{_GAP}clearance\b|\bclearance{_GAP}{_UP}\b", re.I)
_CLEARANCE_DOWN = re.compile(rf"\b{_DOWN}{_GAP}clearance\b|\bclearance{_GAP}{_DOWN}\b", re.I)

# --- clinical risk (corrected 2026-11-07) -----------------------------------------------------------
# A claim about adverse-event risk ("may increase the risk of bleeding", "lowers the risk of clots") is
# a clinical claim. It needs a cited statement that states the same risk change directly. It is never
# derived from a mechanism or an exposure change: lower exposure does not imply lower risk, and a
# bleeding warning about the drug alone does not support a herb-caused bleeding risk.
_RISK_NOUN = re.compile(
    r"\b(?:risks?|bleed\w*|ha?emorrhag\w*|toxicit\w*|adverse (?:events?|effects?|reactions?)|"
    r"side[- ]effects?|thrombo\w*|clot\w*|strokes?|embol\w*|rejection)\b",
    re.I,
)
_RISK_FAMILIES = {
    "bleeding": re.compile(r"\b(?:bleed\w*|ha?emorrhag\w*)", re.I),
    "thrombosis": re.compile(r"\b(?:thrombo\w*|clot\w*|strokes?|embol\w*)", re.I),
    "toxicity": re.compile(r"\btoxic\w*", re.I),
    "adverse effects": re.compile(r"\b(?:adverse|side[- ]effects?)", re.I),
    "rejection": re.compile(r"\brejection\b", re.I),
}
_DIRECTION_WORD = re.compile(rf"\b(?:(?P<up>{_UP})|(?P<down>{_DOWN}))\b", re.I)
_RISK_PHRASE = (
    re.compile(  # masked before exposure/effect detection ("adverse effects" is not an effect)
        rf"\b(?:{_UP}|{_DOWN}){_GAP}{_RISK_NOUN.pattern}(?:\s+of\s+[\w'-]+(?:\s+[\w'-]+)?)?|"
        rf"{_RISK_NOUN.pattern}{_GAP}(?:{_UP}|{_DOWN})|{_RISK_NOUN.pattern}",
        re.I,
    )
)
_CLAUSES = re.compile(r"(?<=[.;!?])\s+|,|\b(?:and|but|while|whereas)\b")
# drug-centric sources: only their sentences that name the herb are statements about the herb
_DRUG_CENTRIC_SOURCES = {"openfda_label", "fda_cyp_table"}
_GENERIC_HERB_WORDS = {
    "herb", "herba", "herbal", "plant", "root", "radix", "leaf", "leaves", "folium", "flower", "flos",
    "fruit", "fructus", "seed", "semen", "bark", "cortex", "rhizome", "rhizoma", "extract", "extracts",
    "juice", "oil", "aetheroleum", "tea", "common", "dried", "powder",
}  # fmt: skip


# sentence split that keeps abbreviations together ("St. John's wort", "e.g.", "i.e.", "vs.", "Dr.")
_SOURCE_SENTENCE_END = re.compile(
    r"(?<!\bSt\.)(?<!\bDr\.)(?<!\bvs\.)(?<!e\.g\.)(?<!i\.e\.)(?<!\bapprox\.)(?<=[.!?])\s+"
)


def _source_sentences(text: str) -> list[str]:
    return [x.strip() for x in _SOURCE_SENTENCE_END.split(text) if x.strip()]


def _risk_claims(text: str) -> set[tuple[str, frozenset[str]]]:
    """(direction, outcome families) of non-negated risk statements; the direction word nearest to
    the risk noun decides ("lower exposure raises the risk of stroke" is a higher risk)."""
    found: set[tuple[str, frozenset[str]]] = set()
    for clause in _CLAUSES.split(text):
        families = frozenset(f for f, pattern in _RISK_FAMILIES.items() if pattern.search(clause))
        for noun in _RISK_NOUN.finditer(clause):
            before = clause[: noun.start()]
            window = " ".join(before.split()[-7:])
            matches = list(_DIRECTION_WORD.finditer(window))
            word: re.Match[str] | None
            if matches:
                word = matches[-1]
                negated = bool(_STRENGTH_NEGATION.search(window[: word.start()]))
            else:
                after = " ".join(clause[noun.end() :].split()[:5])
                word = _DIRECTION_WORD.search(after)
                negated = word is not None and bool(
                    re.search(r"\b(?:not|no|never)\b", after[: word.start()], re.I)
                )
            if word is None or negated:
                continue
            found.add(("up" if word.group("up") else "down", families))
    return found


def risk_issue(paragraph: str, evidence: str) -> str | None:
    """Why a paragraph's adverse-event risk claim lacks direct support in ``evidence``, or None."""
    supported = _risk_claims(evidence)
    for direction, families in sorted(_risk_claims(paragraph), key=lambda c: (c[0], sorted(c[1]))):
        if any(d == direction and (not families or families & f) for d, f in supported):
            continue
        outcome = ", ".join(sorted(families)) or "adverse events"
        level = "higher" if direction == "up" else "lower"
        return f"Claims a {level} risk of {outcome} that no cited statement directly supports."
    return None


def _terms(name: str) -> set[str]:
    words = re.findall(r"[a-z][a-z']{3,}", _fold(name).replace("liquorice", "licorice"))
    return {w for w in words if w not in _GENERIC_HERB_WORDS}


def _mentions(text: str, terms: set[str]) -> bool:
    folded = _fold(text).replace("liquorice", "licorice")
    return any(re.search(rf"\b{re.escape(t)}\b", folded) for t in terms)


def herb_evidence(items: list[ContextItem], herb_terms: set[str]) -> str:
    """Cited text that is about the herb: herb-specific items whole (monographs, fact sheets, mechanism
    and experimental records); from drug labels and the FDA table only the sentences naming the herb."""
    parts = []
    for item in items:
        if item.kind == "classification":
            continue
        if (
            item.kind in ("mechanism", "observation")
            or item.source_code not in _DRUG_CENTRIC_SOURCES
        ):
            parts.append(item.text)
        else:
            parts.extend(x for x in _source_sentences(item.text) if _mentions(x, herb_terms))
    return " ".join(parts)


# --- strength of evidence --------------------------------------------------------------------------
_STRENGTH = re.compile(
    r"\b(clinically (?:significant|relevant|important|meaningful)|clinical significance|"
    r"well[- ]documented|well[- ]established|(?:firmly |clearly )?(?:established|confirmed|proven)|"
    r"definitive(?:ly)?)\b",
    re.I,
)
_STRENGTH_NEGATION = re.compile(
    r"\b(?:not|no|never|neither|nor|without|cannot|can't|isn't|aren't|wasn't|hasn't|haven't|unclear|"
    r"lack(?:s|ing)?|insufficient|whether|yet to be)\b[^.;]{0,50}$",
    re.I,
)


def _direction(text: str) -> set[str]:
    """Directions of exposure/effect changes claimed in ``text`` (clearance inverted)."""
    found: set[str] = set()
    # per clause: "clearance increased by 43% and AUC decreased" holds two separate statements
    for sentence in re.split(r"(?<=[.;!?])\s+|,|\b(?:and|but|while|whereas)\b", text):
        if _CLAIM_UP.search(sentence) and not _CLEARANCE_UP.search(sentence):
            found.add("up")
        if _CLAIM_DOWN.search(sentence) and not _CLEARANCE_DOWN.search(sentence):
            found.add("down")
        if _CLEARANCE_UP.search(sentence):
            found.add("down")
        if _CLEARANCE_DOWN.search(sentence):
            found.add("up")
    return found


def _affirmative(pattern: re.Pattern[str], text: str) -> list[str]:
    """Matches of ``pattern`` that are not negated within their sentence."""
    out = []
    for match in pattern.finditer(text):
        if not _STRENGTH_NEGATION.search(text[: match.start()].rsplit(".", maxsplit=1)[-1]):
            out.append(match.group(0).lower())
    return out


def direction_issue(paragraph: str, evidence: str) -> str | None:
    """Why a paragraph's effect-direction or risk claim is not supported by ``evidence`` (the cited
    source texts that may support it, without classification items), or None."""
    reason = risk_issue(paragraph, evidence)
    if reason:
        return reason
    if _BLEEDING.search(paragraph) and not _BLEEDING.search(evidence):
        return "Claims a bleeding risk that the cited items do not mention."
    claims = _direction(_RISK_PHRASE.sub(" ", paragraph))  # exposure and effect claims only
    if not claims:
        return None
    # Evidence direction from exposure/effect statements (clearance inverted) and from mechanism verbs
    # (inhibition raises a substrate's exposure, induction lowers it) — not from bare "increased".
    evidence = _RISK_PHRASE.sub(" ", evidence)
    evidence_dirs = _direction(evidence)
    up = "up" in evidence_dirs or bool(_INHIBITION.search(evidence))
    down = "down" in evidence_dirs or bool(_INDUCTION.search(evidence))
    if "up" in claims and down and not up:
        return "Claims an increase, but the cited items describe a decrease or induction."
    if "down" in claims and up and not down:
        return "Claims a decrease, but the cited items describe an increase or inhibition."
    if not up and not down:
        return "Claims a change in exposure or effect that the cited items do not describe."
    return None


def strength_issue(paragraph: str, evidence: str) -> str | None:
    """Affirmative strength claims ('clinically significant', 'well-documented', 'confirmed', …)
    must appear affirmatively in a cited source text."""
    supported = set(_affirmative(_STRENGTH, evidence))
    for claim in _affirmative(_STRENGTH, paragraph):
        key = claim.replace("firmly ", "").replace("clearly ", "").replace("-", " ")
        if not any(key in s.replace("-", " ") for s in supported):
            return f"States '{claim}', which no cited source states."
    return None


# --- attributed safety statements (approved 2026-11-07) ------------------------------------------
# Default: any safety wording rejects the answer (critical). The only exception is *reporting* what a
# cited source says about a herb's general safety, word for word in its material qualifiers. It is
# never an independent HerbaGuard assessment, never about a particular person, never about a
# combination with a medicine, and never an absence-of-risk claim.
_ALWAYS_CRITICAL = re.compile(
    r"\b(?:no|without) (?:any )?(?:risk|danger)\b|\brisk-free\b|\bno (?:safety )?concerns?\b|"
    r"\bthere (?:is|are) no interactions?\b|"
    r"\bsafe to (?:take|use|combine|consume)\b",
    re.I,
)
_ATTRIBUTION_SOURCE = re.compile(
    r"\b(?:NCCIH|EMA|HMPC|(?:EU |European Union )?(?:herbal )?monograph|FDA|(?:drug |product )?label|"
    r"fact sheet|government summary|the source|the review|the study)\b",
    re.I,
)
_ATTRIBUTION_VERB = re.compile(
    r"\b(?:states?|stated|says|said|notes?|noted|reports?|reported|describes?|described|concludes?|"
    r"concluded|indicates?|indicated|according to|considers?)\b",
    re.I,
)
_PERSONAL_OR_ADVICE = re.compile(
    r"\b(?:you|your|yourself|this patient|for (?:him|her|them)|in your case|recommend\w*|should|"
    r"can (?:be )?(?:taken|used|safely)|safely|therefore|so it|so you)\b",
    re.I,
)
_COMBINATION = re.compile(
    r"\b(?:with|together|combin\w*|concomitant\w*|co-?administ\w*|interact\w*|alongside|plus|while taking)\b",
    re.I,
)
_UPGRADE = re.compile(
    r"\b(?:completely|totally|perfectly|always|definitely|certainly|proven|guaranteed)\b", re.I
)
_QUALIFIERS = [  # material qualifiers that must be carried over from the source sentence
    r"\b(?:likely|possibly|probably|generally|usually|considered|thought to be)\b",  # hedging
    r"\b(?:research suggests|suggests?|may|might|uncertain|unclear|not known|limited evidence)\b",  # uncertainty
    r"\b(?:most|healthy|adults?|children|women|men|elderly|older adults|pregnan\w*)\b",  # population
    r"\b(?:short[- ]term|long[- ]term|up to \d+ (?:days?|weeks?|months?|years?)|for \d+ (?:days?|weeks?|months?))\b",
    r"\b(?:by mouth|orally|oral|topical\w*|as a food(?: ingredient)?|in foods?|as a tea|when used|when taken|"
    r"as directed)\b",  # route / use
    r"\b(?:recommended amounts?|typical amounts?|moderate amounts?|small amounts?|amounts? (?:commonly )?"
    r"(?:found|used) in foods?|doses?|\d+(?:[.,]\d+)? ?(?:mg|g|ml|cups?))\b",  # quantity
]
_SAFE_CORE = re.compile(
    r"\b((?:likely|possibly|probably|generally|usually|considered|thought to be)\s+)?(?:considered\s+)?safe\b",
    re.I,
)


_SUBJECT_STOPWORDS = {
    "that",
    "this",
    "these",
    "those",
    "their",
    "there",
    "which",
    "with",
    "also",
    "products",
    "preparations",
    "extracts",
    "generally",
    "likely",
    "possibly",
    "probably",
    "usually",
    "considered",
    "thought",
}


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]


def _fold(text: str) -> str:
    return " ".join(text.lower().replace("\u2019", "'").replace("-", " ").split())


def attributed_safety_issue(sentence: str, sources: list[str], drugs: set[str]) -> str | None:
    """None if ``sentence`` is a permitted, source-attributed safety statement; otherwise the reason
    it stays a critical ``safety_claim``. Anything not positively established is rejected."""
    if _ALWAYS_CRITICAL.search(sentence):
        return "absence-of-risk or 'safe to take/use/combine' wording is never allowed"
    if _PERSONAL_OR_ADVICE.search(sentence):
        return "safety wording addressed to a person or phrased as advice"
    folded = _fold(sentence)
    if _COMBINATION.search(sentence) or any(d and d in folded for d in drugs):
        return "safety wording in the context of a combination or interaction"
    if not (_ATTRIBUTION_SOURCE.search(sentence) and _ATTRIBUTION_VERB.search(sentence)):
        return "safety wording not attributed to a named source"
    if _UPGRADE.search(sentence):
        return "certainty stronger than any source states"
    core = _SAFE_CORE.search(sentence)
    if core is None:
        return "no recognised safety expression"
    answer_hedge = _fold(core.group(1) or "")
    for source in sources:
        for candidate in _sentences(source):
            m = _SAFE_CORE.search(candidate)
            if m is None or _NEGATION.search(candidate[: m.start()]):
                continue
            if _fold(m.group(1) or "") != answer_hedge:
                continue  # different certainty ("likely safe" reported as "safe", or the reverse)
            needed = {
                _fold(q.group(0))
                for pattern in _QUALIFIERS
                for q in re.finditer(pattern, candidate, re.I)
            }
            missing = sorted(q for q in needed if q not in folded)
            if missing:
                return f"source qualifiers missing: {', '.join(missing)}"
            # last: the subject (e.g. "licorice root") must be what the cited source is about
            head = _ATTRIBUTION_SOURCE.sub(
                " ", _ATTRIBUTION_VERB.sub(" ", sentence[: core.start()])
            )
            subject = [
                w for w in re.findall(r"[a-z]{4,}", _fold(head)) if w not in _SUBJECT_STOPWORDS
            ]
            if any(w not in _fold(source) for w in subject):
                return "the cited source is not about this subject (incorrect attribution)"
            return None
    return "no cited source states this safety wording with the same certainty"


def _norm_target(t: str) -> str:
    t = t.upper().replace(" ", "")
    return {"P-GLYCOPROTEIN": "PGP", "P-GP": "PGP"}.get(t, t)


def validate(
    paragraphs: list[Paragraph],
    limitations: list[str],
    insufficient: bool,
    context: EvidenceContext,
    *,
    expected_classes: set[str],
) -> ValidationResult:
    items = context.by_label()
    result = ValidationResult([], limitations, insufficient)
    drugs = {  # drugs of the herb–drug pairs asked about (from the deterministic classification items)
        _fold(m.group(1))
        for i in context.items if i.kind == "classification"
        for m in [re.search(r"Pair: .+? \+ (.+)", i.text)] if m
    }  # fmt: skip
    pairs = [m for i in context.items if i.kind == "classification"
             for m in [re.search(r"Pair: (.+?) \+ (.+)", i.text)] if m]  # fmt: skip
    herb_terms = set().union(*(_terms(m.group(1)) for m in pairs))
    drug_terms = set().union(*(_terms(m.group(2)) for m in pairs))
    reference_text = " ".join(
        part
        for i in context.items
        for part in (i.text, i.url or "", i.external_id or "", i.title or "")
    ).lower()
    for index, para in enumerate(paragraphs):
        valid = tuple(dict.fromkeys(c for c in para.citations if c in items))
        for bad in sorted(set(para.citations) - set(valid)):
            result.issues.append(
                Issue(
                    "invalid_citation",
                    "removed",
                    f"Citation '{bad[:20]}' is not in the context.",
                    index,
                )
            )
        if not valid:
            result.issues.append(
                Issue("uncited_paragraph", "removed", "Paragraph without a valid citation.", index)
            )
            continue
        cited_text = " ".join(items[c].text + " " + " ".join(items[c].qualifiers) for c in valid)

        for match in _CLASS.finditer(para.text):
            letter = match.group(1).upper()
            if letter not in expected_classes:
                result.issues.append(Issue("classification_conflict", "critical",
                    f"The answer states class {letter}; HerbaGuard computed {', '.join(sorted(expected_classes)) or 'no class'}.", index))  # fmt: skip
        sources = [items[c].text for c in valid
                   if items[c].kind in ("statement", "excerpt") and items[c].role == "direct_evidence"]  # fmt: skip
        for match in _SAFE.finditer(para.text):
            if _NEGATION.search(para.text[: match.start()].split(".")[-1]):
                continue
            sentence = next((x for x in _sentences(para.text) if match.group(0) in x), para.text)
            why = attributed_safety_issue(sentence, sources, drugs)
            if why is None:
                result.issues.append(Issue("attributed_safety_statement", "warning",
                    "Source-attributed safety wording with all source qualifiers; allowed.", index))  # fmt: skip
            else:
                result.issues.append(
                    Issue(
                        "safety_claim",
                        "critical",
                        f"Claims safety: '{match.group(0)}' ({why}).",
                        index,
                    )
                )
        if _DIRECTIVE.search(para.text):
            result.issues.append(
                Issue("medical_directive", "critical", "Gives a direct medical instruction.", index)
            )

        cited_targets = {_norm_target(t) for t in _TARGET.findall(cited_text)}
        unsupported_targets = {
            t
            for t in (_norm_target(x) for x in _TARGET.findall(para.text))
            if t not in cited_targets
        }
        if unsupported_targets:
            result.issues.append(Issue("unsupported_target", "removed",
                f"Names {', '.join(sorted(unsupported_targets))}, which the cited items do not mention.", index))  # fmt: skip
            continue
        cited_numbers = {m.group(0).lower().replace(" ", "") for m in _DOSE.finditer(cited_text)}
        unsupported_numbers = [m.group(0) for m in _DOSE.finditer(para.text)
                               if m.group(0).lower().replace(" ", "") not in cited_numbers]  # fmt: skip
        if unsupported_numbers:
            result.issues.append(Issue("unsupported_number", "removed",
                f"States {', '.join(unsupported_numbers)}, which the cited items do not contain.", index))  # fmt: skip
            continue
        invented = [f"{kind} {value.rstrip('.,;')}" for kind, pattern in _REFERENCES
                    for value in pattern.findall(para.text)
                    if value.lower().rstrip(".,;") not in reference_text]  # fmt: skip
        if invented:
            result.issues.append(Issue("unsupported_reference", "removed",
                f"Cites {', '.join(invented)}, which no item in the context contains.", index))  # fmt: skip
            continue
        hedged = [
            items[c]
            for c in valid
            if items[c].role == "graph_context" and _HEDGED_GRAPH.search(items[c].text)
        ]
        if (
            hedged
            and re.search(r"\b(inhibits|induces)\b", para.text, re.I)
            and not _HEDGED_GRAPH.search(para.text)
        ):
            result.issues.append(Issue("hedge_dropped", "removed",
                "States an effect without the hedging used by the source ('may').", index))  # fmt: skip
            continue
        # most specific diagnosis first: animal/unstated-species records presented as clinical
        experimental = [items[c] for c in valid if items[c].kind == "observation"]
        non_human = [i for i in experimental if not any("human study" in q for q in i.qualifiers)]
        if (non_human and len(non_human) == len(valid) and _CLINICAL_CLAIM.search(para.text)
                and not _EXPERIMENT_HEDGE.search(para.text)):  # fmt: skip
            result.issues.append(Issue("experimental_as_clinical", "removed",
                "Presents animal or unspecified-species records as clinical evidence.", index))  # fmt: skip
            continue
        source_text = " ".join(items[c].text for c in valid if items[c].kind != "classification")
        # A sentence about the herb is checked only against cited statements about the herb, so that an
        # unrelated passage (e.g. a label's own bleeding warning) cannot support it. Sentences about the
        # drug alone, and answers without a herb-drug pair, use all cited text as before.
        about_herb = (
            herb_evidence([items[c] for c in valid], herb_terms) if herb_terms else source_text
        )
        reason = None
        for sentence in _source_sentences(para.text):
            names_drug_only = not _mentions(sentence, herb_terms) and _mentions(
                sentence, drug_terms
            )
            reason = direction_issue(sentence, source_text if names_drug_only else about_herb)
            if reason:
                break
        if reason:
            result.issues.append(Issue("effect_direction_unsupported", "removed", reason, index))
            continue
        reason = strength_issue(para.text, source_text)
        if reason:
            result.issues.append(Issue("unsupported_strength_claim", "removed", reason, index))
            continue
        result.paragraphs.append(Paragraph(para.text, valid))

    for text_ in limitations:
        claims = limitation_safety_claims(text_)
        if claims:
            result.issues.append(Issue("safety_claim", "critical",
                                       f"A limitation claims safety: '{claims[0]}'.", text=text_))  # fmt: skip
    if not result.paragraphs:
        result.issues.append(
            Issue("no_supported_content", "critical", "No paragraph passed validation.")
        )
    # audit trail: every paragraph-level issue carries the paragraph it refers to
    result.issues = [
        Issue(i.rule, i.severity, i.message, i.paragraph,
              i.text if i.text is not None or i.paragraph is None else paragraphs[i.paragraph].text)
        for i in result.issues
    ]  # fmt: skip
    return result
