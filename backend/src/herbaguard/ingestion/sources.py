"""Registry of the data sources selected in the Phase 0 audit.

Licence fields mirror ``docs/research/dataset-audit.md``; ``licence_status`` records how far
each statement has been verified. Ingestion for these sources is implemented in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from herbaguard.domain.enums import LicenceStatus


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    code: str
    name: str
    provider: str
    priority: str  # P0 | P1 | P2
    access_method: str
    homepage_url: str
    is_official: bool
    licence: str | None
    licence_status: LicenceStatus
    redistributable: bool


SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        code="wfo_ethcstwin",
        name="World Flora Online (ETHCSTWIN wrapper)",
        provider="ETHCSTWIN / University of Athens (data: World Flora Online)",
        priority="P0",
        access_method="api",
        homepage_url="https://wfo.ethcstwin.di.uoa.gr:65000/docs",
        is_official=False,
        licence="CC0 (WFO backbone)",
        licence_status=LicenceStatus.CATALOGUE,
        redistributable=True,
    ),
    SourceDefinition(
        code="wfo",
        name="World Flora Online Plant List - matching API",
        provider="World Flora Online Consortium",
        priority="P0",
        access_method="api",
        homepage_url="https://list.worldfloraonline.org/matching.php",
        is_official=True,
        licence="CC0",
        licence_status=LicenceStatus.CATALOGUE,
        redistributable=True,
    ),
    SourceDefinition(
        code="ema_hmpc",
        name="EMA HMPC herbal inventory and EU herbal monographs",
        provider="European Medicines Agency",
        priority="P0",
        access_method="pdf",
        homepage_url="https://www.ema.europa.eu/en/human-regulatory-overview/herbal-medicinal-products",
        is_official=True,
        licence="Reproduction authorised with source acknowledgement (to verify)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=False,
    ),
    SourceDefinition(
        code="openfda_label",
        name="openFDA drug labels (SPL)",
        provider="U.S. Food and Drug Administration",
        priority="P0",
        access_method="api",
        homepage_url="https://open.fda.gov/apis/drug/label/",
        is_official=True,
        licence="openFDA licence (CC0, to verify)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=True,
    ),
    SourceDefinition(
        code="rxnav",
        name="RxNorm / RxClass (RxNav APIs)",
        provider="U.S. National Library of Medicine",
        priority="P0",
        access_method="api",
        homepage_url="https://lhncbc.nlm.nih.gov/RxNav/APIs/",
        is_official=True,
        licence="Free from NLM; ATC codes owned by WHO CC (store codes only)",
        licence_status=LicenceStatus.CATALOGUE,
        redistributable=False,
    ),
    SourceDefinition(
        code="pubmed",
        name="PubMed via NCBI E-utilities",
        provider="U.S. National Library of Medicine",
        priority="P0",
        access_method="api",
        homepage_url="https://www.ncbi.nlm.nih.gov/books/NBK25501/",
        is_official=True,
        licence="Metadata free; abstracts publisher-copyrighted (local store only)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=False,
    ),
    SourceDefinition(
        code="nccih",
        name="NCCIH Herbs at a Glance",
        provider="U.S. National Center for Complementary and Integrative Health",
        priority="P0",
        access_method="web_page",
        homepage_url="https://www.nccih.nih.gov/health/herbsataglance",
        is_official=True,
        licence="U.S. government work (public domain, to verify page notices)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=True,
    ),
    # --- Phase 4: mechanism layer (P1 in the audit) ---
    SourceDefinition(
        code="fda_cyp_table",
        name=(
            "FDA: Examples of Drugs that Interact with CYP Enzymes and Transporter Systems "
            "(For Healthcare Professionals)"
        ),
        provider="U.S. Food and Drug Administration",
        priority="P1",
        access_method="web_page",
        homepage_url=(
            "https://www.fda.gov/drugs/drug-interactions-labeling/"
            "healthcare-professionals-fdas-examples-drugs-interact-cyp-enzymes-and-transporter-systems"
        ),
        is_official=True,
        licence="U.S. government work (public domain, to verify page notices)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=True,
    ),
    # --- Cross-reference sources used during taxonomic normalisation (P1 in the audit) ---
    SourceDefinition(
        code="wcvp_ethcstwin",
        name="World Checklist of Vascular Plants (ETHCSTWIN wrapper)",
        provider="ETHCSTWIN / University of Athens (data: Royal Botanic Gardens, Kew)",
        priority="P1",
        access_method="api",
        homepage_url="https://wcvp.ethcstwin.di.uoa.gr:65000/docs",
        is_official=False,
        licence="WCVP download licence (to verify)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=False,
    ),
    SourceDefinition(
        code="taxtree_ethcstwin",
        name="NCBI Taxonomy (ETHCSTWIN TaxTree wrapper)",
        provider="ETHCSTWIN / University of Athens (data: NCBI)",
        priority="P1",
        access_method="api",
        homepage_url="https://taxtree.ethcstwin.di.uoa.gr:65000/docs",
        is_official=False,
        licence="NCBI Taxonomy (public, per NCBI policies)",
        licence_status=LicenceStatus.CATALOGUE,
        redistributable=True,
    ),
    SourceDefinition(
        code="gbif",
        name="GBIF Species API",
        provider="Global Biodiversity Information Facility",
        priority="P1",
        access_method="api",
        homepage_url="https://www.gbif.org/developer/species",
        is_official=True,
        licence="GBIF Backbone Taxonomy CC BY 4.0 (to verify)",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=True,
    ),
    SourceDefinition(
        code="wikidata",
        name="Wikidata Query Service",
        provider="Wikimedia Foundation",
        priority="P1",
        access_method="api",
        homepage_url="https://query.wikidata.org/",
        is_official=True,
        licence="CC0",
        licence_status=LicenceStatus.CATALOGUE,
        redistributable=True,
    ),
    SourceDefinition(
        code="herbaguard_curated",
        name="HerbaGuard curation files (data/curated/)",
        provider="HerbaGuard team",
        priority="P0",
        access_method="repository",
        homepage_url="data/curated/",
        is_official=False,
        licence="MIT (project licence)",
        licence_status=LicenceStatus.VERIFIED,
        redistributable=True,
    ),
    SourceDefinition(
        code="ddid",
        name="DDID — Drug–Diet (herb and food) Interaction Database",
        provider="Hangzhou Normal University (bddg.hznu.edu.cn)",
        priority="P1",
        access_method="download",
        homepage_url="https://bddg.hznu.edu.cn/ddid/download/",
        is_official=True,
        licence="Not stated in the downloaded files; terms of use not yet verified",
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=False,
    ),
    SourceDefinition(
        code="supp_ai",
        name="SUPP.AI — supplement–drug interaction mentions extracted from the literature",
        provider="Allen Institute for AI (supp.ai)",
        priority="P2",
        access_method="download",
        homepage_url="https://supp.ai/",
        is_official=False,
        licence=(
            "Not in download. supp.ai: dataset 'public and available for download', © AI2 All Rights "
            "Reserved; AI2 Terms forbid redistribution without written permission. No dataset licence "
            "found; local research use only (checked 2026-11-07)"
        ),
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=False,
    ),
    SourceDefinition(
        code="livertox",
        name="LiverTox — clinical and research information on drug-induced liver injury",
        provider="NIDDK / National Library of Medicine (NCBI Bookshelf NBK547852)",
        priority="P1",
        access_method="download",
        homepage_url="https://www.ncbi.nlm.nih.gov/books/NBK547852/",
        is_official=True,
        licence=(
            "Copyright free (NIDDK); acknowledgement requested. The download's terms of use treat "
            "documents without a licence statement as public domain; none of the chapters has one."
        ),
        licence_status=LicenceStatus.VERIFIED,
        redistributable=True,
    ),
    SourceDefinition(
        code="nih_dsld",
        name="NIH Dietary Supplement Label Database (DSLD)",
        provider="NIH Office of Dietary Supplements (dsld.od.nih.gov)",
        priority="P2",
        access_method="download",
        homepage_url="https://dsld.od.nih.gov/",
        is_official=True,
        licence=(
            "Not in download. NIH ODS database of manufacturers' label text (their trademarks and "
            "wording). dsld/ods sites refused automated access (HTTP 403, 2026-11-07); terms not "
            "confirmed; verify before any redistribution"
        ),
        licence_status=LicenceStatus.TO_VERIFY,
        redistributable=False,
    ),
    SourceDefinition(
        code="herbaguard_ai_index",
        name="HerbaGuard retrieval index (segments and embeddings derived from stored text)",
        provider="HerbaGuard team",
        priority="P0",
        access_method="internal",
        homepage_url="docs/ai/hybrid-retrieval.md",
        is_official=False,
        licence="Derived index; each segment keeps the licence of its source document",
        licence_status=LicenceStatus.VERIFIED,
        redistributable=False,
    ),
)


def get_source(code: str) -> SourceDefinition:
    for source in SOURCES:
        if source.code == code:
            return source
    msg = f"Unknown source code: {code}"
    raise KeyError(msg)
