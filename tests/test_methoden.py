"""Spoor A: geen methodefilter, methode per record, dekkingswaarschuwing waarnemingen.be. Geen netwerk.

Records zijn geanonimiseerd (geen waarnemers, geen dossierlocaties); de protocolwaarden zijn letterlijke
GBIF-waarden uit het facet samplingProtocol voor België (7 oktober 2026).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from gbif_mcp import dekking, gbif, server
from gbif_mcp.methoden import methode
from gbif_mcp.schema import Soort
from tests.conftest import DATASET_FIXTURE


def _rec(key: int, **velden) -> dict:
    o = {"key": key, "species": "Pipistrellus pipistrellus", "eventDate": "2025-06-01", "year": 2025,
         "decimalLatitude": 51.0, "decimalLongitude": 3.7, "datasetKey": dekking.WNM_INBO_DATASET,
         "basisOfRecord": "HUMAN_OBSERVATION"}
    o.update(velden)
    return o


# A1 — geen filter op methode ---------------------------------------------------------------------


def test_geen_filter_op_basis_protocol_gedrag_of_levensstadium():
    p = gbif._occurrence_params(taxon_key=734, geometry="POLYGON((0 0,1 0,1 1,0 0))", gadm_gid=None, jaar_van=2020, jaar_tot=None)
    assert p["occurrenceStatus"] == "PRESENT"
    for veld in ("basisOfRecord", "samplingProtocol", "behavior", "lifeStage"):
        assert veld not in p


# A2 — methode -------------------------------------------------------------------------------------


@pytest.mark.parametrize("velden,verwacht", [
    ({"basisOfRecord": "MACHINE_OBSERVATION", "samplingProtocol": "pam deployment of a wildlife acoustics song meter mini bat bat detector"}, "batdetector"),
    ({"basisOfRecord": "HUMAN_OBSERVATION", "samplingProtocol": "bat detector"}, "batdetector"),
    ({"samplingProtocol": "feces"}, "uitwerpselen"),
    ({"samplingProtocol": "seen"}, "zicht"),
    ({"samplingProtocol": "bat winter roosts counts (per individual)"}, "telling winterverblijfplaats"),
    ({"basisOfRecord": "PRESERVED_SPECIMEN"}, "collectie-exemplaar"),
    ({"basisOfRecord": "HUMAN_OBSERVATION", "samplingProtocol": "unknown"}, "onbekend"),
    ({"basisOfRecord": "HUMAN_OBSERVATION"}, "onbekend"),
    ({"basisOfRecord": "OCCURRENCE"}, "onbekend"),
    ({"samplingProtocol": "indoors"}, "niet vertaald: 'indoors'"),
    ({"samplingProtocol": "seen", "behavior": "dead"}, "dood gevonden (zicht)"),
])
def test_methode_uit_letterlijke_velden(velden, verwacht):
    assert methode(velden)[0] == verwacht


def test_machine_observation_zonder_protocol_wordt_niet_gegokt():
    m, bron = methode({"basisOfRecord": "MACHINE_OBSERVATION"})
    assert m.startswith("machinale registratie") and "niet gespecificeerd" in m
    assert bron == "basisOfRecord"


def test_opmerkingen_worden_niet_geinterpreteerd():
    assert methode({"occurrenceRemarks": "met batdetector gehoord"})[0] == "onbekend"


# Test 1 + A2 + A3 via de tool `waarnemingen` -------------------------------------------------------


@pytest.fixture
def nep_gbif(monkeypatch):
    records = [
        _rec(1, basisOfRecord="MACHINE_OBSERVATION", samplingProtocol="pam deployment of a eco obs gsm batcorder bat detector",
             datasetKey="ander-dataset"),
        _rec(2, samplingProtocol="bat detector", dynamicProperties='{"rbac":false}'),
        _rec(3, samplingProtocol="feces", lifeStage="Unknown"),
        _rec(4, basisOfRecord="MATERIAL_SAMPLE"),
    ]
    gezien: list[dict] = []

    async def nep_get_json(url, params=None, **kw):
        gezien.append(dict(params or {}))
        return {"count": 4, "results": records, "endOfRecords": True, "facets": [
            {"field": "BASIS_OF_RECORD", "counts": [{"name": "HUMAN_OBSERVATION", "count": 2}, {"name": "MACHINE_OBSERVATION", "count": 1},
                                                    {"name": "MATERIAL_SAMPLE", "count": 1}]}]}

    async def nep_resolve(naam):
        return Soort(taxon_key=5218465, wetenschappelijke_naam="Pipistrellus pipistrellus", url="u", nederlandse_naam="gewone dwergvleermuis")

    monkeypatch.setattr(gbif, "get_json", nep_get_json)
    monkeypatch.setattr(server, "_resolve", nep_resolve)
    return gezien


def test_waarnemingen_neemt_alle_methoden_mee(nep_gbif):
    r = asyncio.run(server.waarnemingen("gewone dwergvleermuis", lat=51.0, lon=3.7, straal_m=500))
    assert "basisOfRecord" not in nep_gbif[-1]
    per_id = {w.gbif_id: w for w in r.waarnemingen}
    assert per_id[1].basis == "MACHINE_OBSERVATION" and per_id[1].methode == "batdetector"
    assert per_id[2].methode == "batdetector" and per_id[2].protocol == "bat detector"
    assert per_id[2].dynamische_eigenschappen == '{"rbac":false}'
    assert per_id[3].methode == "uitwerpselen" and per_id[3].levensstadium == "Unknown"
    assert per_id[4].methode == "materiaalstaal"
    assert r.per_methode == {"batdetector": 2, "uitwerpselen": 1, "materiaalstaal": 1}
    assert {b["basis"] for b in r.per_basis} == {"HUMAN_OBSERVATION", "MACHINE_OBSERVATION", "MATERIAL_SAMPLE"}


# A3 — dekkingswaarschuwing uit de datasetbeschrijving ------------------------------------------------


def test_kanttekening_citeert_datasetbeschrijving_met_versie(nep_gbif):
    r = asyncio.run(server.waarnemingen("gewone dwergvleermuis", lat=51.0, lon=3.7, straal_m=500))
    k = r.kanttekening
    assert DATASET_FIXTURE["title"] in k
    assert f"versie {DATASET_FIXTURE['version']}" in k and DATASET_FIXTURE["doi"] in k
    assert "INBO-led fieldwork" in k  # letterlijk citaat uit de beschrijving
    assert "niet aan INBO gekoppeld" in k and "vleermuizen" in k
    assert r.dekking_bron["versie"] == DATASET_FIXTURE["version"]


def test_kanttekening_zonder_beschrijving_zegt_dat(monkeypatch):
    async def faalt(url, params=None, **kw):
        raise RuntimeError("weg")

    monkeypatch.setattr(dekking, "get_json", faalt)
    tekst, meta = asyncio.run(dekking.kanttekening())
    assert "niet nagegaan" in tekst and "INBO-led" not in tekst
    assert meta["fout"] == "RuntimeError"


# A4 — dekkingsindicator per soortgroep ----------------------------------------------------------------


def _facet(monkeypatch, counts):
    async def nep(url, params=None, **kw):
        if "/dataset/" in url:
            return DATASET_FIXTURE
        return {"count": sum(c for _, c in counts), "facets": [{"field": "DATASET_KEY", "counts": [{"name": n, "count": c} for n, c in counts]}]}

    monkeypatch.setattr(dekking, "get_json", nep)


def test_groep_waarschuwt_boven_drempel(monkeypatch):
    _facet(monkeypatch, [(dekking.WNM_INBO_DATASET, 17), ("ander", 3)])
    (g,) = asyncio.run(dekking.per_groep(geometry="POLYGON((0 0,1 0,1 1,0 0))", gadm_gid=None, jaar_van=None, jaar_tot=None))
    assert g["groep"] == "vleermuizen" and g["totaal"] == 20
    assert g["per_dataset"][0]["aandeel"] == 0.85
    assert "85%" in g["waarschuwing"]


def test_groep_zonder_records_waarschuwt_nul_is_niet_afwezig(monkeypatch):
    _facet(monkeypatch, [])
    (g,) = asyncio.run(dekking.per_groep(geometry=None, gadm_gid="BEL.1.1_1", jaar_van=None, jaar_tot=None))
    assert "niet dat de groep afwezig is" in g["waarschuwing"]


def test_groep_gemengd_geen_waarschuwing(monkeypatch):
    _facet(monkeypatch, [(dekking.WNM_INBO_DATASET, 5), ("ander", 5)])
    (g,) = asyncio.run(dekking.per_groep(geometry=None, gadm_gid="x", jaar_van=None, jaar_tot=None))
    assert g["waarschuwing"] is None


def test_groepenlijst_is_configureerbaar(monkeypatch, tmp_path):
    eigen = tmp_path / "dekking.json"
    eigen.write_text(json.dumps({"drempel": 0.5, "inbo_datasets": ["x"], "groepen": [{"naam": "amfibieën", "taxon_key": 131}]}))
    monkeypatch.setenv("GBIF_MCP_DEKKING", str(eigen))
    _facet(monkeypatch, [("x", 6), ("y", 4)])
    (g,) = asyncio.run(dekking.per_groep(geometry=None, gadm_gid="x", jaar_van=None, jaar_tot=None))
    assert g["groep"] == "amfibieën" and g["waarschuwing"]


# Test 7 — dekkingswaarschuwing en methode in het rapport -------------------------------------------------


def test_rapport_bevat_dekking_en_methode(tmp_path):
    import subprocess

    from gbif_mcp.rapport import schrijf_pdf
    from tests.test_rapport import _data, _tekst

    if subprocess.run(["which", "pdftotext"], capture_output=True).returncode != 0:
        pytest.skip("pdftotext niet beschikbaar")
    tekst_dekking, _ = asyncio.run(dekking.kanttekening())
    D = _data()
    D["kern"]["kanttekening"] = "Testkanttekening. " + tekst_dekking
    D["kern"]["dekking"] = [{"groep": "vleermuizen", "wetenschappelijke_naam": "Chiroptera", "status": "ok", "totaal": 20,
                             "per_dataset": [{"dataset_key": dekking.WNM_INBO_DATASET, "aantal": 17, "aandeel": 0.85}],
                             "waarschuwing": "Vleermuizen: 85% van de 20 GBIF-records in het gebied komt uit één INBO-dataset."}]
    D["detail"] = [{"soort": D["kern"]["soorten"][0], "dataset_key": "280674cb-42f8-4959-b6aa-eee663157965", "waarnemingen": {
        "totaal": 1, "per_verificatiestatus": {"(leeg)": 1}, "per_methode": {"batdetector": 1},
        "waarnemingen": [{"datum": "2025-06-01", "plaats": "Testplaats", "gemeente": None, "onzekerheid_m": 707.0,
                          "verificatiestatus": None, "basis": "HUMAN_OBSERVATION", "methode": "batdetector"}]}}]
    pdf = tmp_path / "r.pdf"
    schrijf_pdf(D, str(pdf))
    tekst = " ".join(_tekst(pdf).split())
    assert "Dekking van waarnemingen.be op GBIF" in tekst
    assert "7.2bis Dekking per soortgroep" in tekst and "85%" in tekst
    assert "batdetector" in tekst
