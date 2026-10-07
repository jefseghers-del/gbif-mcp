"""Regressietests BWK-bevraging in `gebieden_rond`, kaart en rapport. Geen netwerk.

Fixture `fixtures/bwk_bourgoyen_r210.json`: opgeslagen respons van BWK:Bwkhab (geo.api.vlaanderen.be,
7 oktober 2026), BBOX van 210 m rond de publieke testlocatie natuurcentrum Bourgoyen-Ossemeersen, Gent
(Lambert 72 x 101896 / y 195419). Het punt ligt daar in een eenheid 'uv + hx' (EVAL m, geen habitat),
met waardevolle en zeer waardevolle eenheden ernaast.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from PIL import Image
from shapely.geometry import Point, box, shape

from gbif_mcp import bwk, gebieden, kaart, server
from gbif_mcp.gebieden import PER_CODE, bevraag_laag
from gbif_mcp.rapport import bwk_kaartnummers, bwk_rijen

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "bwk_bourgoyen_r210.json").read_text())
X, Y = 101896, 195419
DOEL = Point(X, Y)
BWK = PER_CODE["bwk_habitat"]


def _wfs_nabootsen(features: list[dict], aanroepen: list | None = None):
    """Nep-WFS: geeft de features waarvan de omhullende de gevraagde BBOX snijdt, afgekapt op COUNT."""

    async def _get_json(url, params, ttl=1800, **kw):
        x1, y1, x2, y2 = (float(v) for v in params["BBOX"].split(",")[:4])
        vak = box(x1, y1, x2, y2)
        treffers = [f for f in features if box(*shape(f["geometry"]).bounds).intersects(vak)]
        if aanroepen is not None:
            aanroepen.append(params["BBOX"])
        return {"type": "FeatureCollection", "features": treffers[: int(params["COUNT"])]}

    return _get_json


def _props(**over) -> dict:
    """Volledige BWK-attributenset zoals de WFS ze levert."""
    p = {"UIDN": 1, "OIDN": 1, "TAG": "1_v2014", "EVAL": "m", "HERK": "145", "INFO": "", "BWKLABEL": "un",
         "HABLEGENDE": "gh", "HERKHAB": "a", "HERKPHAB": "a", "V1": "", "V2": "", "V3": ""}
    for i in range(1, 9):
        p[f"EENH{i}"] = ""
    for i in range(1, 6):
        p[f"HAB{i}"], p[f"PHAB{i}"] = "", 0
    p.update({"EENH1": "un", "HAB1": "gh", "PHAB1": 100})
    p.update(over)
    return p


def _vak(fid: str, x1: float, y1: float, x2: float, y2: float, **props) -> dict:
    ring = [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]
    return {"type": "Feature", "id": fid, "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": _props(**props)}


def _bevraag(monkeypatch, features, straal=200.0, max_treffers=1000, laag=BWK):
    monkeypatch.setattr(gebieden, "get_json", _wfs_nabootsen(features))
    return asyncio.run(bevraag_laag(laag, DOEL, straal_m=straal, max_treffers=max_treffers))


def _verwacht_binnen(features, straal) -> set[str]:
    return {f["id"] for f in features if shape(f["geometry"]).distance(DOEL) <= straal}


# 1. Punt in een m-eenheid naast w- en z-eenheden (opgeslagen WFS-respons) ------------------------


def test_punt_in_m_eenheid_toont_ook_waardevolle_buren(monkeypatch):
    r = _bevraag(monkeypatch, FIXTURE["features"], straal=200)
    assert r.status == "ok"
    assert {t.id for t in r.treffers} == _verwacht_binnen(FIXTURE["features"], 200)
    assert r.aantal_binnen_straal == 14
    zelf = [t for t in r.treffers if t.overlapt]
    assert len(zelf) == 1 and zelf[0].bwk["eval"] == "m" and zelf[0].bwk["bwklabel"] == "uv + hx"
    assert r.treffers[0].overlapt  # overlap eerst
    buren = [t for t in r.treffers if not t.overlapt]
    assert all(t.afstand_m > 0 for t in buren)
    assert [t.afstand_m for t in buren] == sorted(t.afstand_m for t in buren)
    assert any(bwk.is_waardevol(t.bwk["eval"]) for t in buren)
    # Ook eenheden zonder habitat (gh) en minder waardevolle blijven in de lijst.
    assert any(t.bwk["eval"] == "m" and not t.overlapt for t in r.treffers)

    sb = r.samenvatting_bwk
    assert sb["locatie_zelf"][0]["label"] == "uv + hx"
    assert sb["locatie_zelf"][0]["habitat"] == "geen habitat"
    assert sb["locatie_zelf"][0]["waardering"] == "biologisch minder waardevol"
    assert sb["binnen_straal"]["totaal"] == 14
    assert sb["binnen_straal"]["waardevol"] + sb["binnen_straal"]["zeer_waardevol"] > 0
    assert sb["dichtste_waardevol"]["afstand_m"] == 24  # 'hp* + kn + kbs', EVAL wz
    assert {h["code"] for h in sb["rbb_binnen_straal"]} >= {"rbbhf", "rbbmc", "rbbhc"}


def test_samenvatting_server_noemt_gh_nooit_als_code(monkeypatch):
    r = _bevraag(monkeypatch, FIXTURE["features"], straal=200, max_treffers=5)
    s = server.gebieden_samenvatting([r], 200)
    assert "bwk_habitat" not in s
    assert s["bwk"]["binnen_straal"]["totaal"] == 14  # over alle eenheden, niet alleen de 5 teruggegeven
    assert "gh" not in json.dumps(s["bwk"]["locatie_zelf"])


def test_omschrijving_uit_legende_en_onbekende_code_niet_geraden():
    assert bwk.eenheid_omschrijving("lhb").startswith("populierenbestand op vochtige bodem")
    assert bwk.eenheid_omschrijving("un") == "bebouwing in een (half)natuurlijke omgeving"
    assert bwk.eenheid_omschrijving("ae") == "eutroof water"
    assert bwk.eenheid_omschrijving("zzq") == bwk.ONBEKEND
    assert bwk.waardering("w") == "biologisch waardevol"
    assert bwk.waardering("mw").startswith("complex van biologisch minder waardevolle en waardevolle")
    assert bwk.waardering("xq") == bwk.ONBEKEND
    assert bwk.karteerversie("326375_v2014") == "v2014"


# 2. HAB1 = gh en HAB2 = habitattype -----------------------------------------------------------------


def test_habitat_in_hab2_wordt_herkend(monkeypatch):
    berm = _vak("Bwkhab.2", X + 150, Y - 20, X + 170, Y + 20, UIDN=2, EVAL="mw", BWKLABEL="hu + hp", EENH1="hu", EENH2="hp",
                HAB1="gh", PHAB1=60, HAB2="6510_hu", PHAB2=40, HABLEGENDE="phab", INFO="snelwegberm")
    r = _bevraag(monkeypatch, [_vak("Bwkhab.1", X - 50, Y - 50, X + 50, Y + 50), berm])
    t = next(t for t in r.treffers if t.id == "Bwkhab.2")
    assert t.bwk["bevat_habitat"] is True and t.bwk["bevat_rbb"] is False
    hab = [h for h in t.bwk["habitats"] if h["soort"] == "habitattype"]
    assert hab == [{"veld": "HAB2", "code": "6510_hu", "soort": "habitattype", "naam": bwk.habitatnaam("6510_hu"),
                    "aandeel_pct": 40, "onzeker": False}]
    assert bwk.habitat_tekst(t.bwk) == "6510_hu 40 %"
    assert r.samenvatting_bwk["habitattypes_binnen_straal"][0] == {
        "code": "6510_hu", "naam": bwk.habitatnaam("6510_hu"), "aandeel_pct": 40, "afstand_m": 150, "label": "hu + hp", "aantal_eenheden": 1}
    assert t.bwk["info"] == "snelwegberm" and t.bwk["karteerjaar_of_versie"] == "v2014"


def test_rbb_en_onzekere_combinatie():
    p = _props(HAB1="6430,rbbhf", PHAB1=100, HABLEGENDE="ohab")
    e = bwk.eenheid(p)
    assert e["bevat_habitat"] and e["bevat_rbb"]
    assert all(h["onzeker"] for h in e["habitats"])


# 3. Straal kleiner dan de afstand tot de dichtste waardevolle eenheid -------------------------------


def test_waardevolle_eenheid_buiten_straal_valt_weg(monkeypatch):
    feats = [_vak("Bwkhab.1", X - 50, Y - 50, X + 50, Y + 50),
             _vak("Bwkhab.2", X + 200, Y - 20, X + 260, Y + 20, UIDN=2, EVAL="w", BWKLABEL="lhb", EENH1="lhb")]
    r = _bevraag(monkeypatch, feats, straal=100)
    assert [t.id for t in r.treffers] == ["Bwkhab.1"]
    assert r.samenvatting_bwk["binnen_straal"]["waardevol"] == 0
    assert r.samenvatting_bwk["dichtste_waardevol"] is None
    r2 = _bevraag(monkeypatch, feats, straal=200)
    assert r2.samenvatting_bwk["binnen_straal"]["waardevol"] == 1
    assert r2.samenvatting_bwk["dichtste_waardevol"] == {"label": "lhb", "waardering": "biologisch waardevol", "afstand_m": 200}


# 4. Meer eenheden dan max_treffers_per_laag ----------------------------------------------------------


def test_inkorting_meldt_totaal(monkeypatch):
    feats = [_vak(f"Bwkhab.{i}", X + 10 * i, Y - 5, X + 10 * i + 8, Y + 5, UIDN=i) for i in range(1, 13)]
    r = _bevraag(monkeypatch, feats, straal=500, max_treffers=5)
    assert r.aantal_binnen_straal == 12
    assert r.aantal_teruggegeven == len(r.treffers) == 5
    assert "12" in r.melding and "max_treffers_per_laag" in r.melding
    assert r.samenvatting_bwk["binnen_straal"]["totaal"] == 12


# 5. WFS-paginering: volle pagina -> tegels, ontdubbeld -------------------------------------------------


def test_volle_pagina_wordt_in_tegels_gesplitst(monkeypatch):
    aanroepen: list = []
    klein = dataclasses.replace(BWK, max_features=10)
    monkeypatch.setattr(gebieden, "get_json", _wfs_nabootsen(FIXTURE["features"], aanroepen))
    r = asyncio.run(bevraag_laag(klein, DOEL, straal_m=200, max_treffers=1000))
    assert len(aanroepen) > 1
    assert r.melding is None
    assert {t.id for t in r.treffers} == _verwacht_binnen(FIXTURE["features"], 200)
    assert len({t.id for t in r.treffers}) == len(r.treffers)  # geen dubbels


def test_onvolledige_tegeling_wordt_gemeld(monkeypatch):
    feats = [_vak(f"Bwkhab.{i}", X - 100, Y - 100, X + 100, Y + 100, UIDN=i) for i in range(1, 6)]  # identieke vlakken
    klein = dataclasses.replace(BWK, max_features=3)
    monkeypatch.setattr(gebieden, "get_json", _wfs_nabootsen(feats))
    r = asyncio.run(bevraag_laag(klein, DOEL, straal_m=200, max_treffers=1000))
    assert r.melding and "onvolledig" in r.melding


# 6. Andere lagen: punt in een gebied, tweede gebied binnen de straal ------------------------------------


@pytest.mark.parametrize("code,naamveld,codeveld", [("hrl_gebied", "naam", "gebcode"), ("ven_ivon", "naam", "gebiedsnr")])
def test_andere_lagen_geven_overlap_en_buren(monkeypatch, code, naamveld, codeveld):
    def _gebied(fid, x1, x2, naam, c):
        ring = [[x1, Y - 100], [x2, Y - 100], [x2, Y + 100], [x1, Y + 100], [x1, Y - 100]]
        return {"type": "Feature", "id": fid, "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {naamveld: naam, codeveld: c}}

    feats = [_gebied("g.1", X - 100, X + 100, "Gebied A", "A1"), _gebied("g.2", X + 400, X + 600, "Gebied B", "B2"),
             _gebied("g.3", X + 1200, X + 1300, "Gebied C", "C3")]
    r = _bevraag(monkeypatch, feats, straal=500, laag=PER_CODE[code])
    assert [(t.naam, t.overlapt, t.afstand_m) for t in r.treffers] == [("Gebied A", True, 0), ("Gebied B", False, 400)]
    assert r.treffers[1].url.endswith("RESOURCEID=g.2&OUTPUTFORMAT=application/json&SRSNAME=EPSG:31370")
    s = server.gebieden_samenvatting([r], 500)[code]
    assert "Gebied A" in s and "Gebied B (B2) op 400 m" in s


# Kaart en rapporttabel gebruiken dezelfde nummering ----------------------------------------------------


def test_kaartnummer_in_tabel_komt_overeen_met_legende(tmp_path, monkeypatch):
    feats = [
        _vak("Bwkhab.1", X - 50, Y - 50, X + 50, Y + 50),  # m, gh, overlap -> getekend
        _vak("Bwkhab.2", X + 60, Y - 20, X + 100, Y + 20, UIDN=2, EVAL="w", BWKLABEL="lhb", EENH1="lhb"),
        _vak("Bwkhab.3", X - 120, Y - 20, X - 80, Y + 20, UIDN=3, EVAL="mw", HAB1="gh", PHAB1=60, HAB2="6510_hu", PHAB2=40),
        _vak("Bwkhab.4", X - 20, Y + 80, X + 20, Y + 120, UIDN=4, EVAL="m"),  # m zonder habitat, geen overlap -> niet getekend
    ]

    async def nep_features(laag, doel, straal_m):
        return (feats, None, None) if laag.code == "bwk_habitat" else ([], None, None)

    async def nep_achtergrond(bbox, breedte, hoogte):
        return Image.new("RGBA", (breedte, hoogte), (255, 255, 255, 255))

    monkeypatch.setattr(gebieden, "haal_features", nep_features)
    monkeypatch.setattr(kaart, "achtergrond", nep_achtergrond)
    meta = asyncio.run(kaart.teken(DOEL, [BWK], straal_m=200, pad=str(tmp_path / "k.png"), breedte_px=600))
    legende = {r["laag"]: r["nummer"] for r in meta["legende"] if r["laag"].startswith("bwk_habitat:")}
    assert set(legende) == {"bwk_habitat:eval:m", "bwk_habitat:eval:w", "bwk_habitat:6510_hu"}

    r = _bevraag(monkeypatch, feats, straal=200)
    laag = r.model_dump(mode="json")
    kolom = {t["id"]: rij[0] for t, rij in zip(laag["treffers"], bwk_rijen(laag, [meta]))}
    assert bwk_kaartnummers([meta])["6510_hu"] == legende["bwk_habitat:6510_hu"]
    assert kolom["Bwkhab.1"] == str(legende["bwk_habitat:eval:m"])
    assert kolom["Bwkhab.2"] == str(legende["bwk_habitat:eval:w"])
    assert kolom["Bwkhab.3"] == str(legende["bwk_habitat:6510_hu"])
    assert kolom["Bwkhab.4"] == "—"  # niet getekend, dus geen kaartnummer


# Rapport: tabel 5.1, samenvatting en beperkingen ---------------------------------------------------------


def test_rapport_bevat_bwk_tabel_en_samenvatting(tmp_path, monkeypatch):
    import subprocess

    from tests.test_rapport import _data, _tekst

    if subprocess.run(["which", "pdftotext"], capture_output=True).returncode != 0:
        pytest.skip("pdftotext niet beschikbaar")
    r = _bevraag(monkeypatch, FIXTURE["features"], straal=200)
    D = _data(straal_gebieden=200)
    D["gebieden"]["lagen"].append(r.model_dump(mode="json"))
    D["gebieden"]["samenvatting"] = server.gebieden_samenvatting([r], 200)
    pdf = tmp_path / "r.pdf"
    from gbif_mcp.rapport import schrijf_pdf

    schrijf_pdf(D, str(pdf))
    tekst = " ".join(_tekst(pdf).split())
    assert "5.1 Biologische Waarderingskaart" in tekst
    assert "De projectlocatie ligt in BWK-eenheid uv + hx" in tekst
    assert "habitat: geen habitat" in tekst
    assert "Binnen 200 m liggen 14 BWK-eenheden" in tekst
    assert "rbbhf" in tekst and "Regionaal belangrijke biotopen" in tekst
    assert "geen juridisch statuut" in tekst and "rand van de gepubliceerde polygoon" in tekst
    assert " in gh" not in tekst
