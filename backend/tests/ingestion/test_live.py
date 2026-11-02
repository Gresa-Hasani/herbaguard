"""LIVE checks against the real services (opt-in: ``pytest -m live``).

They verify reachability and the response structures the pipelines rely on. They are excluded
from CI because external services can be slow or down; results must be reported separately.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from herbaguard.core.config import Settings
from herbaguard.ingestion.http import HttpClient
from herbaguard.ingestion.parsers.ema_crosscheck import crosscheck
from herbaguard.ingestion.parsers.ema_inventory import find_monograph_links, parse_inventory
from herbaguard.ingestion.parsers.ema_monograph import parse_monograph
from herbaguard.ingestion.parsers.nccih_html import SAFETY_SECTION, parse_fact_sheet
from herbaguard.ingestion.pipelines.ema import INVENTORY_URL

pytestmark = pytest.mark.live
E = "ethcstwin.di.uoa.gr:65000"


@pytest.fixture(scope="module")
def http() -> Iterator[HttpClient]:
    client = HttpClient(Settings())
    yield client
    client.close()


@pytest.mark.parametrize(
    ("url", "params", "check"),
    [
        (
            f"https://wfo.{E}/names/",
            {"full_name_no_authors": "Hypericum perforatum"},
            lambda d: d["results"][0]["id"] == 728093,
        ),
        (
            f"https://wcvp.{E}/plants/",
            {"taxon_name": "Hypericum perforatum"},
            lambda d: d["results"][0]["plant_name_id"] == 516286,
        ),
        (
            f"https://taxtree.{E}/names/search/",
            {"name_txt": "Hypericum perforatum"},
            lambda d: d["results"][0]["tax_id"] == 65561,
        ),
        (
            "https://list.worldfloraonline.org/matching_rest.php",
            {"input_string": "Hypericum perforatum"},
            lambda d: d["match"]["wfo_id"] == "wfo-0000728093",
        ),
        (
            "https://api.gbif.org/v1/species/match",
            {"name": "Hypericum perforatum", "strict": "true"},
            lambda d: d["usageKey"] == 3189486,
        ),
        (
            "https://rxnav.nlm.nih.gov/REST/rxcui.json",
            {"name": "warfarin", "search": 2},
            lambda d: d["idGroup"]["rxnormId"] == ["11289"],
        ),
        (
            "https://api.fda.gov/drug/label.json",
            {"search": 'drug_interactions:"St. John\'s Wort"', "limit": 1},
            lambda d: d["meta"]["results"]["total"] > 100,
        ),
        (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            {
                "db": "pubmed",
                "term": '"Hypericum"[MeSH Terms] AND "Herb-Drug Interactions"[MeSH Terms]',
                "retmode": "json",
            },
            lambda d: int(d["esearchresult"]["count"]) > 100,
        ),
        (
            "https://query.wikidata.org/sparql",
            {"format": "json", "query": 'SELECT ?i WHERE { ?i wdt:P7715 "wfo-0000728093" }'},
            lambda d: d["results"]["bindings"][0]["i"]["value"].endswith("Q158289"),
        ),
    ],
)
def test_json_endpoint(
    http: HttpClient, url: str, params: dict[str, object], check: object
) -> None:
    result = http.get(url, params=params)
    assert result.status_code == 200
    assert check(result.json())  # type: ignore[operator]


def test_ema_inventory_and_st_johns_wort_monograph(http: HttpClient) -> None:
    inventory = parse_inventory(http.get(INVENTORY_URL).content)
    row = next(r for r in inventory if r.latin_name == "Hyperici herba" and not r.combination)
    finals, _ = find_monograph_links(http.get(row.url).content.decode())
    assert len(finals) == 1
    pdf = http.get(f"https://www.ema.europa.eu{finals[0]}").content
    monograph = parse_monograph(pdf)
    assert monograph.document_number == "EMA/HMPC/7695/2021"
    assert set(monograph.completeness().values()) == {"complete"}
    assert all(c.status in {"verified", "both_empty"} for c in crosscheck(pdf, monograph))


def test_nccih_fact_sheet(http: HttpClient) -> None:
    sheet = parse_fact_sheet(
        http.get("https://www.nccih.nih.gov/health/st-johns-wort").content.decode()
    )
    assert sheet.section(SAFETY_SECTION) is not None
