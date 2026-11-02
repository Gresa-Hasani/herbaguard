"""Parser for PubMed ``efetch`` XML (``db=pubmed&retmode=xml``)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass(slots=True)
class PubmedArticle:
    pmid: str
    title: str
    abstract: str
    journal: str | None
    year: int | None
    doi: str | None
    publication_types: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    language: str | None = None


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _year(article: ET.Element) -> int | None:
    for path in (
        ".//Article/Journal/JournalIssue/PubDate/Year",
        ".//Article/ArticleDate/Year",
        ".//PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year",
    ):
        node = article.find(path)
        if node is not None and node.text and node.text.isdigit():
            return int(node.text)
    medline = article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate")
    if medline is not None and medline.text and (m := re.match(r"(\d{4})", medline.text)):
        return int(m.group(1))
    return None


def parse_efetch(xml_bytes: bytes) -> list[PubmedArticle]:
    root = ET.fromstring(xml_bytes)  # noqa: S314 - NCBI XML, no external entities
    articles: list[PubmedArticle] = []
    for node in root.findall("PubmedArticle"):
        pmid = _text(node.find("MedlineCitation/PMID"))
        parts = []
        for abstract_text in node.findall(".//Article/Abstract/AbstractText"):
            label = abstract_text.get("Label")
            body = _text(abstract_text)
            parts.append(f"{label}: {body}" if label else body)
        doi = next(
            (
                _text(aid)
                for aid in node.findall("PubmedData/ArticleIdList/ArticleId")
                if aid.get("IdType") == "doi"
            ),
            None,
        )
        articles.append(
            PubmedArticle(
                pmid=pmid,
                title=_text(node.find(".//Article/ArticleTitle")),
                abstract="\n\n".join(p for p in parts if p),
                journal=_text(node.find(".//Article/Journal/Title")) or None,
                year=_year(node),
                doi=doi,
                publication_types=[
                    _text(pt) for pt in node.findall(".//PublicationTypeList/PublicationType")
                ],
                mesh_terms=[
                    _text(m) for m in node.findall(".//MeshHeadingList/MeshHeading/DescriptorName")
                ],
                language=_text(node.find(".//Article/Language")) or None,
            )
        )
    return articles
