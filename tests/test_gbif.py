"""Tests voor gbif_mcp/gbif.py: puur functionele stukjes, geen netwerk."""
from __future__ import annotations

import asyncio

import pytest

from gbif_mcp import gbif
from gbif_mcp.gbif import _waarneming, broedindicatie, gbif_zoek_url, records_in_gebied


def test_waarneming_met_eventdate_met_t_geeft_datum_zonder_tijd():
    o = {
        "key": 123,
        "species": "Alytes obstetricans",
        "eventDate": "2024-05-03T00:00:00",
        "year": 2024,
        "decimalLatitude": 51.05,
        "decimalLongitude": 3.72,
    }
    w = _waarneming(o)
    assert w.datum == "2024-05-03"
    assert w.gbif_id == 123
    assert w.url == "https://www.gbif.org/occurrence/123"


def test_waarneming_zonder_eventdate_met_year_month_day():
    o = {"key": 456, "species": "Alytes obstetricans", "year": 2020, "month": 6, "day": 9}
    w = _waarneming(o)
    assert w.datum == "2020-06-09"


def test_waarneming_zonder_eventdate_en_zonder_dag():
    o = {"key": 789, "species": "Alytes obstetricans", "year": 2020, "month": 6}
    w = _waarneming(o)
    assert w.datum == "2020-06"


def test_gbif_zoek_url_laat_limit_en_facet_weg():
    params = {"country": "BE", "taxonKey": 5, "limit": 50, "facet": ["datasetKey", "year"], "facetLimit": 25}
    url = gbif_zoek_url(params)
    assert "limit=" not in url
    assert "facet=" not in url
    assert "facetLimit=" not in url
    assert "taxonKey=5" in url
    assert "country=BE" in url


# --- broedindicatie ----------------------------------------------------------------------


def test_broedindicatie_true_bij_lifestage_juvenile():
    assert broedindicatie({"lifeStage": "juvenile"}) is True


def test_broedindicatie_true_bij_occurrence_remarks():
    assert broedindicatie({"occurrenceRemarks": "nest met jongen"}) is True


def test_broedindicatie_false_bij_lege_velden():
    assert broedindicatie({"lifeStage": None, "reproductiveCondition": "", "behavior": None, "occurrenceRemarks": ""}) is False
    assert broedindicatie({}) is False


# --- records_in_gebied: twee pagina's -----------------------------------------------------


def test_records_in_gebied_haalt_alle_paginas_op(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get_json(url, params=None, *, ttl=3600, pogingen=3, schijf_ttl=None, verwijder_velden=()):
        if params.get("offset", 0) == 0:
            return {"results": [{"key": 1}, {"key": 2}], "endOfRecords": False}
        return {"results": [{"key": 3}], "endOfRecords": True}

    monkeypatch.setattr(gbif, "get_json", _fake_get_json)
    records, volledig, zonder = asyncio.run(
        records_in_gebied([100, 200], geometry=None, gadm_gid=None, jaar_van=None, jaar_tot=None, budget_s=5.0)
    )
    assert volledig is True
    assert zonder == []
    assert [r["key"] for r in records] == [1, 2, 3]


def test_persoonsgegevens_worden_bij_ontvangst_verwijderd(monkeypatch):
    """Geen verwerking van waarnemersnamen: ze mogen niet in de cache, noch in een antwoord."""
    import asyncio

    import httpx

    from gbif_mcp import gbif, http

    antwoord = {"count": 1, "endOfRecords": True, "results": [{
        "key": 1, "speciesKey": 2, "year": 2024, "decimalLatitude": 51.0, "decimalLongitude": 3.7,
        "datasetKey": "d", "recordedBy": "Jan Janssens", "identifiedBy": "Piet Peeters", "recordedByID": "orcid:x",
        "rightsHolder": "Jan Janssens", "basisOfRecord": "HUMAN_OBSERVATION",
    }]}

    def handler(request):
        return httpx.Response(200, json=antwoord)

    http.leeg_cache()
    monkeypatch.setattr(http, "_clients", {})
    orig = httpx.AsyncClient

    def nep_client(*a, **k):
        return orig(*a, transport=httpx.MockTransport(handler), **k)

    monkeypatch.setattr(httpx, "AsyncClient", nep_client)
    totaal, waarnemingen, *_ = asyncio.run(gbif.zoek_waarnemingen(taxon_key=2, geometry=None, gadm_gid=None, jaar_van=None, jaar_tot=None, limit=5))
    assert totaal == 1
    w = waarnemingen[0].model_dump()
    assert "waarnemer" not in w
    assert "Janssens" not in str(w) and "Peeters" not in str(w)
    # ook de cache bevat de namen niet
    assert "Janssens" not in str(http._cache) and "Peeters" not in str(http._cache)
    assert all(v not in str(http._cache) for v in gbif.PERSOONSVELDEN)
