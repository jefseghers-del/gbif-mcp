"""Tests voor gbif_mcp/server.py: toolregistratie en één integratieachtige test van soort_status.

Geen netwerk: `gbif_mcp.gbif.get_json` en `gbif_mcp.inbo.get_json` worden gemonkeypatcht.
"""
from __future__ import annotations

import asyncio

import pytest

from gbif_mcp import gbif, inbo
from gbif_mcp import gebiedsanalyse as ga
from gbif_mcp.server import mcp

VERWACHTE_TOOLS = {
    "zoek_soort",
    "soort_status",
    "waarnemingen",
    "soorten_in_gebied",
    "telling_in_gebied",
    "gebieden_rond",
    "kaart_gebieden",
    "datarapport_natuur",
    "exporteer_bevraging",
    "lijst",
    "geocodeer_adres",
    "dataset_info",
    "bronnen",
}


def test_server_registreert_precies_de_dertien_tools():
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == VERWACHTE_TOOLS


def test_elke_tool_heeft_een_beschrijving():
    for tool in asyncio.run(mcp.list_tools()):
        assert tool.description, f"tool {tool.name} heeft geen beschrijving"


def test_bronnen_bevat_verwachte_codes_en_groep():
    resultaat = asyncio.run(mcp.call_tool("bronnen", {}))
    assert resultaat.is_error is False
    codes = {b["code"] for b in resultaat.structured_content["result"]}
    for verwacht in ("soortenbesluit", "hrl_iv_vl", "rodelijst_vl", "unielijst", "beschermd", "kern", "rodelijst_broedvogels_2016"):
        assert verwacht in codes


# ---------------------------------------------------------------------------------------
# soort_status: gemockte INBO species-list respons (dr542, kenmerkwaardecode cat3) en
# lege GBIF-checklists (related/distributions).
# ---------------------------------------------------------------------------------------

FIXTURE_TAXON_KEY = 2426612


async def _fake_inbo_get_json(url, params=None, *, ttl=3600):
    if url.endswith("/bie-index/search"):
        return {
            "searchResults": {
                "results": [
                    {
                        "guid": str(FIXTURE_TAXON_KEY),
                        "scientificName": "Alytes obstetricans",
                        "commonNameSingle": "vroedmeesterpad",
                        "rank": "species",
                        "taxonomicStatus": "accepted",
                        "kingdom": "Animalia",
                    }
                ]
            }
        }
    if url.endswith(f"/species-list/ws/species/{FIXTURE_TAXON_KEY}"):
        return [
            {
                "dataResourceUid": "dr542",
                "lsid": str(FIXTURE_TAXON_KEY),
                "scientificName": "Alytes obstetricans",
                "kvpValues": [{"key": "kenmerkwaardecode", "value": "cat3"}],
            }
        ]
    raise AssertionError(f"onverwachte inbo-URL in deze test: {url}")


async def _fake_gbif_get_json(url, params=None, *, ttl=3600):
    if url.endswith("/related"):
        return {"results": []}
    raise AssertionError(f"onverwachte gbif-URL in deze test: {url}")


async def _fake_exoot_keys():
    return set(), []


async def _fake_hrl_eu_keys():
    return {}, []


def test_soort_status_met_gemockte_bronnen(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inbo, "get_json", _fake_inbo_get_json)
    monkeypatch.setattr(gbif, "get_json", _fake_gbif_get_json)
    # deze doen anders netwerkcalls (Unielijst/INBO-exotenlijst/GRIIS, EU-checklists)
    monkeypatch.setattr(ga, "_exoot_keys", _fake_exoot_keys)
    monkeypatch.setattr(ga, "hrl_eu_keys", _fake_hrl_eu_keys)

    resultaat = asyncio.run(mcp.call_tool("soort_status", {"soort": "Alytes obstetricans"}))
    assert resultaat.is_error is False
    r = resultaat.structured_content
    assert r["soort"]["taxon_key"] == FIXTURE_TAXON_KEY
    assert r["samenvatting"]["soortenbesluit"] == "cat. 3"
    assert any(v["lijst_code"] == "soortenbesluit" and v["categorie"] == "cat. 3" for v in r["vermeldingen"])
    assert r["exoot"] is False


def test_disclaimer_zit_in_de_serverinstructies():
    """De disclaimer geldt voor de hele server, niet alleen voor het rapport."""
    from gbif_mcp import DISCLAIMER
    from gbif_mcp.server import mcp as server_mcp

    instr = server_mcp.instructions
    assert DISCLAIMER in instr
    for kern in ("Betaversie", "geen product", "geen garantie", "geen aansprakelijkheid", "zelf volledig verantwoordelijk"):
        assert kern in instr


def test_disclaimer_in_manifest():
    import json
    from pathlib import Path

    from gbif_mcp import DISCLAIMER

    m = json.loads((Path(__file__).parent.parent / "mcpb-src" / "manifest.json").read_text())
    assert m["description"].startswith("Betaversie, geen product")
    assert m["long_description"].startswith(DISCLAIMER)
    assert "gmail" not in json.dumps(m)
