"""Loading and validating the committed curation files in ``data/curated/``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

CURATED_DIR = Path(__file__).resolve().parents[4] / "data" / "curated"


class HerbEntry(BaseModel):
    key: str
    common_name: str
    ema_latin_name: str
    plant_part: str
    taxa: list[str] = Field(min_length=1)
    ema_botanical_names: list[str] = Field(min_length=1)
    nccih_slug: str | None
    pubmed_mesh: str
    openfda_terms: list[str] = Field(min_length=1)
    openfda_exclude: list[str] = Field(default_factory=list)


class HerbList(BaseModel):
    version: int
    herbs: list[HerbEntry]

    @field_validator("herbs")
    @classmethod
    def _unique_keys(cls, herbs: list[HerbEntry]) -> list[HerbEntry]:
        keys = [h.key for h in herbs]
        if len(keys) != len(set(keys)):
            msg = "Duplicate herb keys in herbs.yaml"
            raise ValueError(msg)
        return herbs

    def get(self, key: str) -> HerbEntry:
        return next(h for h in self.herbs if h.key == key)


class LexiconDrug(BaseModel):
    name: str
    patterns: list[str] = Field(min_length=1)
    seen_in: list[str] = Field(default_factory=list)


class LexiconClass(BaseModel):
    label: str
    atc: list[str] = Field(min_length=1)
    patterns: list[str] = Field(min_length=1)
    seen_in: list[str] = Field(default_factory=list)


class LexiconUnmapped(BaseModel):
    phrase: str
    reason: str
    seen_in: list[str] = Field(default_factory=list)


class Lexicon(BaseModel):
    version: int
    drugs: list[LexiconDrug]
    classes: list[LexiconClass]
    unmapped: list[LexiconUnmapped] = Field(default_factory=list)

    @field_validator("classes")
    @classmethod
    def _atc_format(cls, classes: list[LexiconClass]) -> list[LexiconClass]:
        import re

        for entry in classes:
            for code in entry.atc:
                if not re.fullmatch(r"[A-Z](\d{2}([A-Z]([A-Z](\d{2})?)?)?)?", code):
                    msg = f"Invalid ATC code {code!r} for {entry.label!r}"
                    raise ValueError(msg)
        return classes


@lru_cache
def load_herbs(path: Path | None = None) -> HerbList:
    data = yaml.safe_load((path or CURATED_DIR / "herbs.yaml").read_text(encoding="utf-8"))
    return HerbList.model_validate(data)


@lru_cache
def load_lexicon(path: Path | None = None) -> Lexicon:
    data = yaml.safe_load(
        (path or CURATED_DIR / "interaction_lexicon.yaml").read_text(encoding="utf-8")
    )
    return Lexicon.model_validate(data)


# --------------------------------------------------------------------------- Phase 4


class TargetEntry(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z0-9-]{2,32}$")
    name: str
    type: str = Field(pattern=r"^(enzyme|transporter)$")
    gene: str | None
    uniprot: str | None = Field(default=None, pattern=r"^[A-Z0-9]{6,10}$")
    aliases: list[str] = Field(default_factory=list)


class TargetList(BaseModel):
    version: int
    targets: list[TargetEntry]

    @field_validator("targets")
    @classmethod
    def _unique(cls, targets: list[TargetEntry]) -> list[TargetEntry]:
        symbols = [t.symbol for t in targets]
        accessions = [t.uniprot for t in targets if t.uniprot]
        if len(symbols) != len(set(symbols)) or len(accessions) != len(set(accessions)):
            msg = "Duplicate target symbol or UniProt accession in targets.yaml"
            raise ValueError(msg)
        return targets


class ConstituentEntry(BaseModel):
    name: str
    inchikey: str = Field(pattern=r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
    pubchem_cid: int | None = None
    chebi_id: str | None = None
    molecular_formula: str | None = None


class FdaNonDrugRow(BaseModel):
    name: str
    kind: str = Field(pattern=r"^(herb|constituent|out_of_scope)$")
    herb_key: str | None = None
    constituent: ConstituentEntry | None = None
    found_in: list[str] = Field(default_factory=list)
    note: str | None = None


class SkipPattern(BaseModel):
    pattern: str
    reason: str


class FdaDrugAlias(BaseModel):
    fda_name: str
    also_for: list[str] = Field(min_length=1)
    note: str


class MechanismSources(BaseModel):
    version: int
    fda_non_drug_rows: list[FdaNonDrugRow]
    fda_skip_patterns: list[SkipPattern] = Field(default_factory=list)
    fda_drug_aliases: list[FdaDrugAlias] = Field(default_factory=list)
    ema_subject_terms: dict[str, list[str]] = Field(default_factory=dict)

    def drug_alias(self, name: str) -> FdaDrugAlias | None:
        key = name.strip().lower()
        return next((a for a in self.fda_drug_aliases if a.fda_name.lower() == key), None)

    def non_drug_row(self, name: str) -> FdaNonDrugRow | None:
        key = name.strip().lower()
        return next((r for r in self.fda_non_drug_rows if r.name.lower() == key), None)


@lru_cache
def load_targets(path: Path | None = None) -> TargetList:
    data = yaml.safe_load((path or CURATED_DIR / "targets.yaml").read_text(encoding="utf-8"))
    return TargetList.model_validate(data)


@lru_cache
def load_mechanism_sources(path: Path | None = None) -> MechanismSources:
    data = yaml.safe_load(
        (path or CURATED_DIR / "mechanism_sources.yaml").read_text(encoding="utf-8")
    )
    return MechanismSources.model_validate(data)
