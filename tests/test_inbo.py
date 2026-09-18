"""Tests voor gbif_mcp/inbo.py op een vast fixture-item (Rode Lijst-vermelding vroedmeesterpad)."""
from __future__ import annotations

import asyncio

import pytest

from gbif_mcp import inbo
from gbif_mcp.inbo import dekking, lijst_items, lijsten_van_taxon, soort_uit_item, vermelding_uit_item
from gbif_mcp.lijsten import PER_CODE

FIXTURE_ITEM = {
    "id": 1,
    "name": "Alytes obstetricans (Laurenti, 1768)",
    "commonName": "vroedmeesterpad",
    "scientificName": "Alytes obstetricans",
    "lsid": "2426612",
    "dataResourceUid": "dr606",
    "kvpValues": [
        {"key": "RLC", "value": "EN"},
        {"key": "RLC_gepubliceerd", "value": "Bedreigd"},
        {"key": "JaarPublicatie", "value": "2024"},
        {"key": "source", "value": "Speybroeck_etal_2024"},
        {"key": "kingdom", "value": "Animalia"},
        {"key": "class", "value": "Amphibia"},
    ],
}


def test_vermelding_uit_item():
    lijst = PER_CODE["rodelijst_vl"]
    v = vermelding_uit_item(lijst, FIXTURE_ITEM)
    assert v.lijst_code == "rodelijst_vl"
    assert v.categorie == "EN"
    assert v.toelichting == "Bedreigd"
    assert v.jaar == "2024"
    assert v.bronvermelding == "Speybroeck_etal_2024"
    assert "dr606" in v.url


def test_soort_uit_item():
    s = soort_uit_item(FIXTURE_ITEM)
    assert s.taxon_key == 2426612
    assert s.wetenschappelijke_naam == "Alytes obstetricans"
    assert s.nederlandse_naam == "vroedmeesterpad"
    assert s.rijk == "Animalia"
    assert s.klasse == "Amphibia"
    assert s.match_type == "INBO_LIJST"
    assert s.url == "https://www.gbif.org/species/2426612"
    assert "2426612" in s.url_inbo


# --- lijst_items: kvp_filter (dr552, source=Devos_etal_2016) ---------------------------

BROEDVOGEL_ITEMS = [
    {
        "id": 1,
        "name": "Vanellus vanellus",
        "scientificName": "Vanellus vanellus",
        "lsid": "5229493",
        "dataResourceUid": "dr552",
        "kvpValues": [{"key": "source", "value": "Devos_etal_2016"}, {"key": "threatStatus", "value": "VU"}],
    },
    {
        "id": 2,
        "name": "Andere soort",
        "scientificName": "Andere soort",
        "lsid": "9999991",
        "dataResourceUid": "dr552",
        "kvpValues": [{"key": "source", "value": "Ander_werk_2010"}, {"key": "threatStatus", "value": "LC"}],
    },
    {
        "id": 3,
        "name": "Nog een soort",
        "scientificName": "Nog een soort",
        "lsid": "9999992",
        "dataResourceUid": "dr552",
        "kvpValues": [{"key": "source", "value": "Devos_etal_2016"}, {"key": "threatStatus", "value": "EN"}],
    },
]


async def _fake_get_json_broedvogels(url, params=None, **kwargs):
    return BROEDVOGEL_ITEMS


def test_lijst_items_past_kvp_filter_toe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inbo, "get_json", _fake_get_json_broedvogels)
    lijst = PER_CODE["rodelijst_broedvogels_2016"]
    items = asyncio.run(lijst_items(lijst))
    assert len(items) == 2
    assert all(inbo._kvp(it).get("source") == "Devos_etal_2016" for it in items)


# --- lijsten_van_taxon: item zonder Devos_etal_2016 wordt niet als broedvogel-Rode-Lijst geteld ---


async def _fake_get_json_species(url, params=None, **kwargs):
    return [
        {
            "dataResourceUid": "dr552",
            "lsid": "9999991",
            "scientificName": "Andere soort",
            "kvpValues": [{"key": "source", "value": "Ander_werk_2010"}, {"key": "threatStatus", "value": "LC"}],
        }
    ]


def test_lijsten_van_taxon_negeert_niet_matchende_kvp_filter(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inbo, "get_json", _fake_get_json_species)
    vermeldingen = asyncio.run(lijsten_van_taxon(9999991))
    assert not any(v.lijst_code == "rodelijst_broedvogels_2016" for v in vermeldingen)


# --- dekking ------------------------------------------------------------------------------


def test_dekking_groepeert_op_taxongroep_en_jaar():
    items = [
        {"kvpValues": [{"key": "taxonomische_groep", "value": "Amfibieen"}, {"key": "JaarPublicatie", "value": "2024"}]},
        {"kvpValues": [{"key": "taxonomische_groep", "value": "Libellen"}, {"key": "JaarPublicatie", "value": "2021"}]},
        {"kvpValues": [{"key": "taxonomische_groep", "value": "Amfibieen"}, {"key": "JaarPublicatie", "value": "2024"}]},
    ]
    resultaat = dekking(items)
    assert "Amfibieen 2024" in resultaat
    assert "Libellen 2021" in resultaat
