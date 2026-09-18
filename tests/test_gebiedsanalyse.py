"""Tests voor gbif_mcp/gebiedsanalyse.py: samenvatting, kruiscontrole HRL, tabel, telling, vervaging.

Geen netwerk: puur functionele stukken en een handgemaakte Analyse.
"""
from __future__ import annotations

from gbif_mcp import gebiedsanalyse as ga
from gbif_mcp.gebiedsanalyse import Analyse, SoortRegel
from gbif_mcp.geo import Gebied
from gbif_mcp.schema import LijstVermelding, Soort


def _v(lijst_code: str, categorie: str | None) -> LijstVermelding:
    return LijstVermelding(lijst_code=lijst_code, lijst_naam=lijst_code, categorie=categorie, url="https://example.org")


# --- samenvatting --------------------------------------------------------------------------


def test_samenvatting_combineert_categorieen_per_lijst():
    vermeldingen = [_v("soortenbesluit", "cat. 2"), _v("soortenbesluit", "cat. 4"), _v("vrl", "bijlage I")]
    s = ga.samenvatting(vermeldingen)
    assert s["soortenbesluit"] == "cat. 2 en 4"
    assert s["vrl"] == "bijlage I"


def test_samenvatting_leeg():
    assert ga.samenvatting([]) == {}


# --- kruiscontrole_hrl -----------------------------------------------------------------------


def test_kruiscontrole_hrl_geeft_tekst_als_key_niet_in_eu_set():
    vermeldingen = [_v("hrl_iv_vl", "bijlage IV")]
    eu = {"hrl_iv_vl": {1, 2, 3}}
    reden = ga.kruiscontrole_hrl(999, vermeldingen, eu)
    assert reden is not None
    assert "hrl_iv_vl" in reden


def test_kruiscontrole_hrl_geeft_none_als_key_wel_in_eu_set():
    vermeldingen = [_v("hrl_iv_vl", "bijlage IV")]
    eu = {"hrl_iv_vl": {999}}
    assert ga.kruiscontrole_hrl(999, vermeldingen, eu) is None


def test_kruiscontrole_hrl_geen_dubbele_reden_bij_twee_vermeldingen_zelfde_lijst():
    vermeldingen = [_v("hrl_ii", "bijlage II"), _v("hrl_ii", "bijlage II")]
    eu = {"hrl_ii": {1, 2, 3}}
    reden = ga.kruiscontrole_hrl(999, vermeldingen, eu)
    assert reden is not None
    assert reden.count("hrl_ii") == 1


def test_kruiscontrole_hrl_geen_lijst_bekend_bij_eu_geeft_none():
    vermeldingen = [_v("soortenbesluit", "cat. 3")]
    assert ga.kruiscontrole_hrl(999, vermeldingen, {}) is None


# --- naar_tabel ----------------------------------------------------------------------------


def _regel(key: int, aantal: int, naam: str | None = None, vermeldingen=None) -> SoortRegel:
    s = Soort(taxon_key=key, wetenschappelijke_naam=f"Species {key}", nederlandse_naam=naam, url="https://example.org")
    return SoortRegel(key=key, aantal=aantal, soort=s, vermeldingen=vermeldingen or [])


def test_naar_tabel_heeft_kopregel_en_rijen():
    regels = [_regel(1, 5, "soort een"), _regel(2, 3, "soort twee")]
    tabel = ga.naar_tabel(regels, met_straal=False)
    regels_uit = tabel.splitlines()
    assert regels_uit[0].startswith("| taxon_key")
    assert regels_uit[1].startswith("|---")
    assert len(regels_uit) == 4  # kop + scheiding + 2 rijen


def test_naar_tabel_geen_pipe_in_cellen():
    v = _v("soortenbesluit", "cat. 2 | cat. 4")
    regels = [_regel(1, 5, vermeldingen=[v])]
    tabel = ga.naar_tabel(regels, met_straal=False)
    datarij = tabel.splitlines()[-1]
    # de kop- en scheidingslijnen bevatten pipes als kolomscheiding; per cel mag geen pipe meer zitten
    binnenkant = datarij.strip("|").split(" | ")
    assert all("|" not in cel for cel in binnenkant)


def test_naar_tabel_met_straal_voegt_kolom_toe():
    regels = [_regel(1, 5)]
    zonder = ga.naar_tabel(regels, met_straal=False)
    met = ga.naar_tabel(regels, met_straal=True)
    assert "zeker_in_straal" not in zonder
    assert "zeker_in_straal" in met


# --- telling ---------------------------------------------------------------------------------


def _maak_analyse(regels: list[SoortRegel]) -> Analyse:
    gebied = Gebied(wkt="POLYGON((0 0,0 1,1 1,1 0,0 0))", omschrijving="test")
    return Analyse(
        geraadpleegd_op="2026-09-17T00:00:00+02:00", gebied=gebied, codes=["kern"], totaal_waarnemingen=10,
        aantal_soorten=2, regels=regels, per_dataset=[], gbif_parameters={}, zoek_url="https://example.org",
        lijstversies={}, legende={}, waarschuwingen=[], ontbrekend=[], exoot_keys=set(),
    )


def test_telling_op_twee_regels():
    r1 = _regel(1, 5, vermeldingen=[_v("hrl_iv_vl", "bijlage IV")])
    r1.exoot = False
    r2 = _regel(2, 3, vermeldingen=[_v("rodelijst_vl", "VU")])
    r2.exoot = True
    an = _maak_analyse([r1, r2])
    per_lijst, per_cat, kern_n, exoten = ga.telling(an)
    assert per_lijst == {"hrl_iv_vl": 1, "rodelijst_vl": 1}
    assert per_cat == {"hrl_iv_vl": {"bijlage IV": 1}, "rodelijst_vl": {"VU": 1}}
    assert kern_n == 2  # bijlage IV en RL VU tellen beide als kern
    assert exoten == 1


# --- signaleer_vervaging ----------------------------------------------------------------------


def test_signaleer_vervaging_waarschuwt_bij_score_hoog_en_niets_zeker():
    r = _regel(1, 5, naam="testsoort", vermeldingen=[_v("hrl_iv_vl", "bijlage IV")])
    r.zeker = 0
    r.onz_max = 5000.0
    waarschuwingen = ga.signaleer_vervaging([r])
    assert len(waarschuwingen) == 1
    assert "testsoort" in waarschuwingen[0]


def test_signaleer_vervaging_geen_waarschuwing_bij_lage_score():
    r = _regel(1, 5, vermeldingen=[_v("bern", "bijlage II")])
    r.zeker = 0
    r.onz_max = 5000.0
    assert ga.signaleer_vervaging([r]) == []


def test_signaleer_vervaging_geen_waarschuwing_als_er_zekere_records_zijn():
    r = _regel(1, 5, vermeldingen=[_v("hrl_iv_vl", "bijlage IV")])
    r.zeker = 2
    r.onz_max = 5000.0
    assert ga.signaleer_vervaging([r]) == []
