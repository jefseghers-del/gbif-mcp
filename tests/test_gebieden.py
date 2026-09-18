"""Tests voor gbif_mcp/gebieden.py: laagregister, projectie en WFS-bevraging (gemockt)."""
from __future__ import annotations

import asyncio

import pytest
from shapely.geometry import Point

from gbif_mcp import gebieden
from gbif_mcp.gebieden import GROEPEN, PER_CODE, bevraag_laag, doelgeometrie, ontleed_lagen


# --- ontleed_lagen -------------------------------------------------------------------------


def test_ontleed_lagen_groep_natura2000():
    lagen = ontleed_lagen("natura2000")
    assert [l.code for l in lagen] == GROEPEN["natura2000"]


def test_ontleed_lagen_onbekende_code_geeft_valueerror():
    with pytest.raises(ValueError):
        ontleed_lagen("onbestaande_laag_xyz")


def test_ontleed_lagen_leeg_geeft_alle_lagen():
    assert len(ontleed_lagen(None)) == len(PER_CODE)


# --- doelgeometrie: WGS84 -> Lambert 72 -----------------------------------------------------


def test_doelgeometrie_zet_wgs84_om_naar_lambert72():
    doel, omschrijving = doelgeometrie(lat=51.06691, lon=3.68249, wkt=None)
    assert isinstance(doel, Point)
    assert doel.x == pytest.approx(101896, abs=2)
    assert doel.y == pytest.approx(195419, abs=2)
    assert "Lambert 72" in omschrijving


def test_doelgeometrie_zonder_lat_lon_of_wkt_geeft_valueerror():
    with pytest.raises(ValueError):
        doelgeometrie(lat=None, lon=None, wkt=None)


# --- bevraag_laag (gemockte WFS-respons) ----------------------------------------------------


def _vierkant_feature(cx: float, cy: float, halve_zijde: float, props: dict | None = None) -> dict:
    ring = [
        [cx - halve_zijde, cy - halve_zijde],
        [cx + halve_zijde, cy - halve_zijde],
        [cx + halve_zijde, cy + halve_zijde],
        [cx - halve_zijde, cy + halve_zijde],
        [cx - halve_zijde, cy - halve_zijde],
    ]
    return {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]}, "properties": props or {}}


DOEL = Point(101896, 195419)


def test_bevraag_laag_overlappend_en_dichtstbijzijnd_binnen_straal(monkeypatch: pytest.MonkeyPatch):
    laag = PER_CODE["hrl_gebied"]
    overlappend = _vierkant_feature(101896, 195419, 25, {"naam": "Overlap-gebied"})
    dichtbij = _vierkant_feature(102206, 195419, 10, {"naam": "Dichtbij-gebied"})  # linkerrand op 300 m
    ver = _vierkant_feature(102506, 195419, 10, {"naam": "Ver-gebied"})  # linkerrand op 600 m, buiten straal

    async def _fake_get_json(url, params, ttl=1800):
        return {"features": [overlappend, dichtbij, ver]}

    monkeypatch.setattr(gebieden, "get_json", _fake_get_json)
    resultaat = asyncio.run(bevraag_laag(laag, DOEL, straal_m=500.0, max_treffers=10))
    assert resultaat.status == "ok"
    namen = {t.naam: t for t in resultaat.treffers}
    assert namen["Overlap-gebied"].overlapt is True
    assert namen["Overlap-gebied"].afstand_m == 0
    assert namen["Dichtbij-gebied"].overlapt is False
    assert namen["Dichtbij-gebied"].afstand_m == pytest.approx(300, abs=1)
    assert "Ver-gebied" not in namen  # buiten straal_m weggelaten


def test_bevraag_laag_bij_exceptie_geeft_niet_geraadpleegd(monkeypatch: pytest.MonkeyPatch):
    laag = PER_CODE["hrl_gebied"]

    async def _fake_get_json_faalt(url, params, ttl=1800):
        raise RuntimeError("WFS onbereikbaar")

    monkeypatch.setattr(gebieden, "get_json", _fake_get_json_faalt)
    resultaat = asyncio.run(bevraag_laag(laag, DOEL, straal_m=500.0, max_treffers=10))
    assert resultaat.status == "niet_geraadpleegd"
    assert resultaat.treffers == []


def test_bevraag_laag_bwk_regel_niet_overlappende_gh_weggelaten(monkeypatch: pytest.MonkeyPatch):
    laag = PER_CODE["bwk_habitat"]
    gh_overlappend = _vierkant_feature(101896, 195419, 25, {"HAB1": "gh"})
    gh_niet_overlappend = _vierkant_feature(102196, 195419, 10, {"HAB1": "gh"})  # binnen straal, niet-overlappend

    async def _fake_get_json(url, params, ttl=1800):
        return {"features": [gh_overlappend, gh_niet_overlappend]}

    monkeypatch.setattr(gebieden, "get_json", _fake_get_json)
    resultaat = asyncio.run(bevraag_laag(laag, DOEL, straal_m=500.0, max_treffers=10))
    assert resultaat.aantal_binnen_straal == 1
    assert resultaat.treffers[0].overlapt is True
