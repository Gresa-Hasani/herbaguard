"""Drug normalisation through RxNav: names / product RxCUIs → RxNorm ingredients, ATC classes.

Every RxNav response is snapshotted as a ``source_record`` of source ``rxnav``. Nothing is
guessed: a name that does not resolve to exactly one ingredient is reported and skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from herbaguard.domain.enums import IssueSeverity
from herbaguard.ingestion.context import IngestionContext
from herbaguard.ingestion.loaders import add_class_membership, upsert_drug, upsert_drug_class

RXNAV = "https://rxnav.nlm.nih.gov/REST"
SOURCE = "rxnav"
METHOD = "rxnav_normalisation_v1"


@dataclass(frozen=True, slots=True)
class Ingredient:
    drug_id: uuid.UUID
    rxcui: str
    name: str


@dataclass(frozen=True, slots=True)
class ProductIngredients:
    ingredients: tuple[Ingredient, ...]
    multi_ingredient: bool


class DrugResolver:
    def __init__(self, ctx: IngestionContext) -> None:
        self.ctx = ctx
        self._by_name: dict[str, Ingredient | None] = {}
        self._by_product: dict[str, ProductIngredients | None] = {}
        self._atc_done: set[str] = set()
        self._classes: dict[str, str | None] = {}

    def reset(self) -> None:
        """Forget cached lookups (after a rollback the cached rows may no longer exist)."""
        self._by_name.clear()
        self._by_product.clear()
        self._atc_done.clear()
        self._classes.clear()

    # ------------------------------------------------------------------ ingredients

    def _ingredient(self, rxcui: str, name: str) -> Ingredient:
        drug_id = upsert_drug(self.ctx.session, rxcui=rxcui, name=name, tty="IN")
        self._load_atc(drug_id, rxcui)
        return Ingredient(drug_id, rxcui, name)

    def by_name(self, name: str) -> Ingredient | None:
        key = name.lower().strip()
        if key in self._by_name:
            return self._by_name[key]
        fetched = self.ctx.fetch(
            f"{RXNAV}/rxcui.json",
            params={"name": name, "search": 2},
            native_id=f"name:{key}",
            source_code=SOURCE,
        )
        ids = (fetched.json().get("idGroup") or {}).get("rxnormId") or [] if fetched.ok else []
        result: Ingredient | None = None
        if len(ids) != 1:
            self.ctx.issue(
                "drug_name_unresolved",
                f"RxNorm returned {len(ids)} concepts for '{name}'.",
                record=fetched.record,
                name=name,
                rxcuis=ids,
            )
        else:
            product = self.by_product_rxcui(ids[0], label=name)
            if product is None or product.multi_ingredient or len(product.ingredients) != 1:
                self.ctx.issue(
                    "drug_name_not_single_ingredient",
                    f"'{name}' does not map to exactly one RxNorm ingredient.",
                    record=fetched.record,
                    name=name,
                )
            else:
                result = product.ingredients[0]
                self.ctx.provenance(
                    "drug", result.drug_id, fetched.record, METHOD, location=f"name={name}"
                )
        self._by_name[key] = result
        return result

    def by_product_rxcui(
        self, rxcui: str, *, label: str | None = None
    ) -> ProductIngredients | None:
        """Ingredients of any RxNorm concept (IN itself, or a product via related IN/MIN)."""
        if rxcui in self._by_product:
            return self._by_product[rxcui]
        props = self.ctx.fetch(
            f"{RXNAV}/rxcui/{rxcui}/properties.json",
            native_id=f"properties:{rxcui}",
            source_code=SOURCE,
        )
        properties = (props.json().get("properties") or {}) if props.ok else {}
        result: ProductIngredients | None
        if properties.get("tty") == "IN":
            ingredient = self._ingredient(rxcui, properties["name"])
            self.ctx.provenance(
                "drug", ingredient.drug_id, props.record, METHOD, location=f"rxcui={rxcui}"
            )
            result = ProductIngredients((ingredient,), False)
        elif not properties:
            self.ctx.issue(
                "rxcui_unknown",
                f"RxNav has no properties for RxCUI {rxcui}.",
                record=props.record,
                label=label,
            )
            result = None
        else:
            # The "+" must stay literal: RxNav answers HTTP 400 to the encoded form "IN%2BMIN".
            related = self.ctx.fetch(
                f"{RXNAV}/rxcui/{rxcui}/related.json?tty=IN+MIN",
                native_id=f"related:{rxcui}",
                source_code=SOURCE,
            )
            if not related.ok:
                self.ctx.issue(
                    "rxnav_error",
                    f"RxNav HTTP {related.result.status_code} for related ingredients of {rxcui}.",
                    severity=IssueSeverity.ERROR,
                    record=related.record,
                    label=label,
                )
                self._by_product[rxcui] = None
                return None
            groups = (related.json().get("relatedGroup") or {}).get("conceptGroup") or []
            ins = [
                c for g in groups if g.get("tty") == "IN" for c in g.get("conceptProperties") or []
            ]
            mins = [
                c for g in groups if g.get("tty") == "MIN" for c in g.get("conceptProperties") or []
            ]
            ingredients = []
            for concept in ins:
                ingredient = self._ingredient(concept["rxcui"], concept["name"])
                self.ctx.provenance(
                    "drug",
                    ingredient.drug_id,
                    related.record,
                    METHOD,
                    location=f"related_to={rxcui}",
                )
                ingredients.append(ingredient)
            result = ProductIngredients(tuple(ingredients), bool(mins) or len(ingredients) > 1)
        self._by_product[rxcui] = result
        return result

    # ------------------------------------------------------------------ ATC

    def _load_atc(self, drug_id: uuid.UUID, rxcui: str) -> None:
        if rxcui in self._atc_done:
            return
        self._atc_done.add(rxcui)
        fetched = self.ctx.fetch(
            f"{RXNAV}/rxclass/class/byRxcui.json",
            params={"rxcui": rxcui, "relaSource": "ATC"},
            native_id=f"atc:{rxcui}",
            source_code=SOURCE,
        )
        infos = (
            ((fetched.json().get("rxclassDrugInfoList") or {}).get("rxclassDrugInfo") or [])
            if fetched.ok
            else []
        )
        for info in infos:
            item = info.get("rxclassMinConceptItem") or {}
            code, name = item.get("classId"), item.get("className")
            if not code or not name:
                continue
            upsert_drug_class(self.ctx.session, code=code, name=name)
            self.ctx.provenance(
                "drug_class", code, fetched.record, METHOD, location=f"via rxcui={rxcui}"
            )
            add_class_membership(self.ctx.session, drug_id=drug_id, code=code, source_code=SOURCE)
            self.ctx.provenance(
                "drug_class_membership", f"{drug_id}:{code}", fetched.record, METHOD
            )

    def drug_class(self, code: str) -> str | None:
        """Ensure an ATC class exists (name from RxClass). Returns the code, or None if unknown."""
        if code in self._classes:
            return self._classes[code]
        fetched = self.ctx.fetch(
            f"{RXNAV}/rxclass/class/byId.json",
            params={"classId": code},
            native_id=f"class:{code}",
            source_code=SOURCE,
        )
        concepts = (
            ((fetched.json().get("rxclassMinConceptList") or {}).get("rxclassMinConcept") or [])
            if fetched.ok
            else []
        )
        atc = [c for c in concepts if c.get("classType") == "ATC1-4" and c.get("classId") == code]
        result: str | None = None
        if atc:
            upsert_drug_class(self.ctx.session, code=code, name=atc[0]["className"])
            self.ctx.provenance("drug_class", code, fetched.record, METHOD)
            result = code
        else:
            self.ctx.issue(
                "atc_code_unknown",
                f"RxClass does not know ATC code {code}.",
                severity=IssueSeverity.ERROR,
                record=fetched.record,
                code=code,
            )
        self._classes[code] = result
        return result
