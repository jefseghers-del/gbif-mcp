"""Tests voor de ecotoopkwetsbaarheidskaarten (INBO): interpretatie, WFS-bevraging, samenvatting en rapport.
Geen netwerk: vaste fixture van de publieke locatie Bourgoyen-Ossemeersen (Gent), opgehaald op 8 oktober 2026."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

from shapely.geometry import Point, shape

from gbif_mcp import ecokwets, gebieden, server
from gbif_mcp.gebieden import PER_CODE, bevraag_laag
from tests.test_bwk import _wfs_nabootsen

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ecokwets_bourgoyen_r210.json").read_text())
DOEL = Point(101896, 195419)
LAAG = PER_CODE["ecotoopkwetsbaarheid"]


def _bevraag(monkeypatch, straal=200.0, features=None, aanroepen=None):
    gezien: list[dict] = []
    nep = _wfs_nabootsen(copy.deepcopy(features if features is not None else FIXTURE["features"]), aanroepen)

    async def _get_json(url, params, **kw):
        gezien.append(dict(params, _url=url))
        return await nep(url, params, **kw)

    monkeypatch.setattr(gebieden, "get_json", _get_json)
    return asyncio.run(bevraag_laag(LAAG, DOEL, straal_m=straal, max_treffers=1000)), gezien


# Interpretatie -----------------------------------------------------------------------------------------------


def test_eenheid_neemt_velden_letterlijk_over():
    props = next(f["properties"] for f in FIXTURE["features"] if f["properties"]["GmlID"] == "verdroging.111620")
    e = ecokwets.eenheid(props)
    assert e["bwklabel"] == "uv + hx" and e["eval"] == "m" and e["waardering"] == "biologisch minder waardevol"
    # ' ' en 'null' van de dienst worden weggelaten, niet als eenheid getoond
    assert e["eenheden"] == [{"code": "uv", "omschrijving": "recreatiezone"},
                             {"code": "hx", "omschrijving": "zeer soortenarm, vaak tijdelijk grasland"}]
    assert e["versie_bwk"] == "v2014" and e["herk"] == "038"
    assert e["kwetsbaarheid"]["verdroging"] == {"waarde": 1.0, "klasse": "niet kwetsbaar"}


def test_klasse_komt_uit_legendeveld_nooit_uit_het_getal():
    props = {"kwetsverd": 4.0, "kwetsverdr_legende": "", "kwetseutr": 1.0, "kwetseutr_legende": "eigen bronlabel",
             "kwetsverz": None, "kwetsverz_legende": None}
    k = ecokwets.eenheid(props)["kwetsbaarheid"]
    assert k["verdroging"] == {"waarde": 4.0, "klasse": ecokwets.ONBEKEND}
    assert k["eutrofiëring"]["klasse"] == "eigen bronlabel"
    assert k["verzuring"] == {"waarde": None, "klasse": ecokwets.ONBEKEND}


# WFS-bevraging -----------------------------------------------------------------------------------------------


def test_bevraging_geeft_alle_polygonen_binnen_de_straal(monkeypatch):
    r, gezien = _bevraag(monkeypatch)
    assert r.status == "ok"
    verwacht = {f["properties"]["GmlID"] for f in FIXTURE["features"] if shape(f["geometry"]).distance(DOEL) <= 200}
    assert {t.id for t in r.treffers} == verwacht and r.aantal_binnen_straal == len(verwacht) == 14
    # De ArcGIS-WFS van INBO aanvaardt alleen GEOJSON; één laag volstaat (drie lagen, zelfde polygonen).
    assert gezien[0]["OUTPUTFORMAT"] == "GEOJSON" and gezien[0]["TYPENAMES"] == "Ecotoopkwetsbaarheid:verdroging"
    eerste = r.treffers[0]
    assert eerste.overlapt and eerste.naam == "uv + hx" and eerste.code == "326375_v2014"
    assert eerste.url.endswith("RESOURCEID=verdroging.111620&OUTPUTFORMAT=GEOJSON&SRSNAME=EPSG:31370")
    assert all(t.ecotoop for t in r.treffers)


def test_samenvatting(monkeypatch):
    r, _ = _bevraag(monkeypatch)
    sb = r.samenvatting_ecotoop
    assert [z["label"] for z in sb["locatie_zelf"]] == ["uv + hx"]
    assert sb["locatie_zelf"][0]["kwetsbaarheid"]["verzuring"]["klasse"] == "niet kwetsbaar"
    pd = sb["binnen_straal"]["per_druk"]
    assert pd["verdroging"]["hoogste"] == {"waarde": 4.0, "klasse": "zeer kwetsbaar", "label": "hf + mc + hc + khs", "afstand_m": 117}
    assert pd["eutrofiëring"]["hoogste"]["klasse"] == "kwetsbaar"
    assert sum(pd["verdroging"]["per_klasse"].values()) == 14
    # klassen geordend volgens de bronwaarden
    assert list(pd["verdroging"]["per_klasse"]) == ["niet kwetsbaar", "nauwelijks kwetsbaar", "weinig kwetsbaar", "kwetsbaar", "zeer kwetsbaar"]
    assert "signaalkaarten" in sb["toelichting"]


def test_falende_dienst_is_niet_geraadpleegd(monkeypatch):
    async def _fout(url, params, **kw):
        raise RuntimeError("503")

    monkeypatch.setattr(gebieden, "get_json", _fout)
    r = asyncio.run(bevraag_laag(LAAG, DOEL, straal_m=200, max_treffers=1000))
    assert r.status == "niet_geraadpleegd" and r.treffers == [] and "503" in r.melding


def test_laag_zit_standaard_in_elke_bevraging():
    # gebieden_rond zonder `lagen` (zo roept datarapport_natuur het op) neemt de laag mee
    assert LAAG in gebieden.ontleed_lagen(None)
    assert gebieden.ontleed_lagen("ecotoop") == [LAAG]


def test_gebieden_samenvatting_bevat_blok(monkeypatch):
    r, _ = _bevraag(monkeypatch)
    s = server.gebieden_samenvatting([r], 200)
    assert s["ecotoopkwetsbaarheid"] is r.samenvatting_ecotoop
    assert "ecotoopkwetsbaarheid" not in [k for k, v in s.items() if isinstance(v, str)]


# Rapport -----------------------------------------------------------------------------------------------------


def _rapportdata(monkeypatch):
    from tests.test_rapport import _data

    r, _ = _bevraag(monkeypatch)
    D = _data(straal_gebieden=200)
    D["gebieden"]["lagen"].append(r.model_dump(mode="json"))
    D["gebieden"]["samenvatting"] = {**D["gebieden"]["samenvatting"], **server.gebieden_samenvatting([r], 200)}
    return D


def test_rapport_pdf_bevat_tabel_52(tmp_path, monkeypatch):
    import subprocess

    import pytest

    from gbif_mcp.rapport import schrijf_pdf
    from tests.test_rapport import _tekst

    if subprocess.run(["which", "pdftotext"], capture_output=True).returncode != 0:
        pytest.skip("pdftotext niet beschikbaar")
    pdf = tmp_path / "r.pdf"
    schrijf_pdf(_rapportdata(monkeypatch), str(pdf))
    tekst = " ".join(_tekst(pdf).split())
    assert "5.2 Ecotoopkwetsbaarheid: alle polygonen binnen de straal" in tekst
    assert "Ecotoopkwetsbaarheid (INBO) op de projectlocatie" in tekst
    assert "verdroging zeer kwetsbaar (hf + mc + hc + khs, op 117 m)" in tekst
    assert "signaalkaarten op schaal Vlaanderen" in tekst
    assert "Bron: Instituut voor Natuur- en Bosonderzoek (INBO)" in tekst


def test_rapport_docx_bevat_tabel_52(tmp_path, monkeypatch):
    from docx import Document

    from gbif_mcp.rapport_docx import schrijf_docx
    from tests.test_rapport_docx import _alle_tekst

    pad = tmp_path / "r.docx"
    schrijf_docx(_rapportdata(monkeypatch), str(pad))
    doc = Document(str(pad))
    tekst = _alle_tekst(doc)
    assert "5.2 Ecotoopkwetsbaarheid: alle polygonen binnen de straal" in [p.text for p in doc.paragraphs]
    assert "zeer kwetsbaar (4)" in tekst and "niet kwetsbaar (1)" in tekst
    assert "14 polygonen binnen 200 m; hoogste kwetsbaarheid: verdroging zeer kwetsbaar" in tekst  # rij in hoofdstuk 5
    assert "zie tabel 5.2" in tekst
