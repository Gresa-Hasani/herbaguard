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
