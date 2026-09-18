"""Tests voor het rapportsjabloon (gbif_mcp/rapport.py) en de rapporttool. Geen netwerk."""
from __future__ import annotations

import asyncio
import subprocess

import pytest

from gbif_mcp import server
from gbif_mcp.rapport import _getal, schrijf_pdf


def _data(straal_soorten=500, straal_gebieden=1000) -> dict:
    """Minimale, maar volledige invoer zoals de rapporttool die opbouwt."""
    soort = {
        "taxon_key": 5218465, "wetenschappelijke_naam": "Pipistrellus pipistrellus", "nederlandse_naam": "gewone dwergvleermuis",
        "aantal_waarnemingen": 3, "laatste_jaar": 2024, "samenvatting": {"hrl_iv_vl": "bijlage IV"}, "exoot": False,
        "onzekerheid_max_m": 707.0, "zeker_binnen_straal": 0, "records_met_broedindicatie": 0, "koppeling_twijfel": None,
        "datasets": [{"dataset_key": "280674cb-42f8-4959-b6aa-eee663157965", "dataset": "INBO collaborator …", "aantal": 3, "laatste_jaar": 2024}],
        "vermeldingen": None,
    }
    return {
        "locatie": {"invoer": "Teststraat 1", "adres": "Teststraat 1, 9000 Gent", "gemeente": "Gent", "lat": 51.05, "lon": 3.72,
                    "x_lambert72": 104000.0, "y_lambert72": 193000.0, "type": "test", "bron": "test"},
        "telling": {"totaal_waarnemingen": 12345, "totaal_soorten": 200, "totaal_soorten_met_status": 40, "kern": 1, "exoten": 2,
                    "per_categorie": {"hrl_iv_vl": {"bijlage IV": 1}}, "per_dataset": [{"dataset_key": "x", "dataset": "Testdataset", "aantal_records": 12345}]},
        "kern": {"geraadpleegd_op": "2026-09-18T10:00:00+02:00", "soorten": [soort], "volledig": True, "ontbrekend": [],
                 "lijstversies": {"hrl_iv_vl": "2026-09-18T09:00:00+02:00"}, "rodelijst_dekking": {"rodelijst_vl": "Amfibieen 2024"},
                 "filter": "hrl_iv_vl", "zoek_url": "https://www.gbif.org/occurrence/search?x=1", "kanttekening": "Testkanttekening.",
                 "waarschuwingen": ["Testwaarschuwing."]},
        "gebieden": {"straal_m": straal_gebieden, "samenvatting": {"ven_ivon": "dichtstbij Testgebied op 120 m"}, "kanttekening": "Gebiedskanttekening.",
                     "lagen": [{"laag": "ven_ivon", "naam": "VEN/IVON-gebied", "status": "ok", "aantal_binnen_straal": 1,
                                "treffers": [{"naam": "Testgebied", "code": "7", "overlapt": False, "afstand_m": 120}]}]},
        "kaarten": [], "detail": [], "straal_m": straal_soorten, "jaar_van": 2020, "connector": "gbif-mcp test",
    }


def _tekst(pdf) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout


pdftotext = pytest.mark.skipif(subprocess.run(["which", "pdftotext"], capture_output=True).returncode != 0,
                               reason="pdftotext niet beschikbaar")


def test_pdf_wordt_geschreven(tmp_path):
    uit = schrijf_pdf(_data(), str(tmp_path / "r.pdf"))
    assert (tmp_path / "r.pdf").stat().st_size > 1000
    assert uit["paginas"] >= 3


@pdftotext
@pytest.mark.parametrize("soorten,gebieden,verwacht", [
    (500, 1000, "ruimere straal van 1000 m"),
    (1000, 500, "kleinere straal van 500 m"),
    (750, 750, "Ook de gebiedsstatuten zijn binnen 750 m bevraagd"),
])
def test_stralen_worden_consequent_benoemd(tmp_path, soorten, gebieden, verwacht):
    pdf = tmp_path / "r.pdf"
    schrijf_pdf(_data(soorten, gebieden), str(pdf))
    tekst = " ".join(_tekst(pdf).split())
    assert verwacht in tekst
    if soorten != gebieden:
        assert f"Beschermde soorten binnen {soorten} m, gebiedsstatuten binnen {gebieden} m" in tekst


@pdftotext
def test_terminologie_en_getallen(tmp_path):
    pdf = tmp_path / "r.pdf"
    schrijf_pdf(_data(), str(pdf))
    tekst = " ".join(_tekst(pdf).split())
    assert "zwaar" not in tekst.lower()
    assert "strikt" in tekst.lower()
    assert "12.345" in tekst  # duizendtalscheiding zonder afhankelijkheid van de systeemlocale
    assert "VEN/IVON-gebied: dichtstbij Testgebied op 120 m" in tekst  # laagnaam, niet de interne code
    assert "Testwaarschuwing." in tekst


def test_getal():
    assert _getal(1234567) == "1.234.567"
    assert _getal(12) == "12"
    assert _getal("x") == "x"


def test_rapporttool_en_prompt_zijn_geregistreerd():
    namen = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert "datarapport_natuur" in namen
    prompts = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert prompts == {"datarapport_natuur"}


def test_prompt_noemt_stralen_en_terminologie():
    p = asyncio.run(server.mcp.get_prompt("datarapport_natuur", {"adres": "Teststraat 1, Gent", "straal_soorten_m": "750"}))
    tekst = p.messages[0].content.text
    assert "Teststraat 1, Gent" in tekst and "750 m voor soorten" in tekst and "1000 m voor gebiedsstatuten" in tekst
    assert "nooit van zwaar of zwaarst" in tekst


def test_standaardpad_staat_in_documenten(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    pad = server._standaardpad("Kortrijksesteenweg 100, 9000 Gent")
    assert pad.startswith(str(tmp_path / "Documents"))
    assert "datarapport-natuur-kortrijksesteenweg-100-9000-gent-" in pad and pad.endswith(".pdf")
