"""Tests voor gbif_mcp/lijsten.py: het register van lijstcodes en groepen."""
from __future__ import annotations

import pytest

from gbif_mcp.lijsten import (
    GROEPEN,
    PER_CODE,
    combineer_categorieen,
    is_kern,
    normaliseer_categorie,
    ontleed_codes,
    relevantie,
)


def test_ontleed_codes_groep_wordt_uitgevouwen():
    codes = ontleed_codes("beschermd")
    assert codes == GROEPEN["beschermd"]


def test_ontleed_codes_losse_code():
    assert ontleed_codes("hrl_iv_vl") == ["hrl_iv_vl"]


def test_ontleed_codes_combinatie_van_groep_en_code():
    codes = ontleed_codes("rodelijst,unielijst")
    assert codes == ["rodelijst_vl", "rodelijst_broedvogels_2016", "unielijst"]


def test_ontleed_codes_ontdubbelt_met_behoud_van_volgorde():
    # 'beschermd' bevat al hrl_iv_vl; expliciet nog eens toevoegen mag niet dupliceren.
    codes = ontleed_codes("hrl_iv_vl,beschermd")
    assert codes.count("hrl_iv_vl") == 1
    assert codes[0] == "hrl_iv_vl"


def test_ontleed_codes_leeg_geeft_lege_lijst():
    assert ontleed_codes(None) == []
    assert ontleed_codes("") == []


def test_ontleed_codes_onbekende_code_geeft_valueerror():
    with pytest.raises(ValueError):
        ontleed_codes("onbestaande_code_xyz")


def test_alle_lijstcodes_bestaan_effectief():
    assert "soortenbesluit" in PER_CODE
    assert "hrl_iv_vl" in PER_CODE
    assert "rodelijst_vl" in PER_CODE
    assert "unielijst" in PER_CODE


def test_ontleed_codes_kern_bevat_rodelijst_broedvogels_2016():
    assert "rodelijst_broedvogels_2016" in ontleed_codes("kern")


def test_groep_beschermd_bevat_geen_hrl_iv():
    assert "hrl_iv" not in GROEPEN["beschermd"]


# --- normaliseer_categorie --------------------------------------------------------------


def test_normaliseer_categorie_annex_naar_bijlage_romeins():
    assert normaliseer_categorie("vrl", "Annex 1") == "bijlage I"


def test_normaliseer_categorie_cat3_naar_cat_punt_3():
    assert normaliseer_categorie("soortenbesluit", "cat3") == "cat. 3"


def test_normaliseer_categorie_wettelijk_bepaald_cat3():
    assert normaliseer_categorie("soortenbesluit", "Wettelijk bepaald:  cat3") == "cat. 3"


def test_normaliseer_categorie_near_threatened_naar_nt():
    assert normaliseer_categorie("rodelijst_vl", "Near Threatened (NT)") == "NT"


def test_normaliseer_categorie_regionally_extinct_naar_re():
    assert normaliseer_categorie("rodelijst_vl", "Regionally Extinct (EX)") == "RE"


# --- combineer_categorieen ---------------------------------------------------------------


def test_combineer_categorieen_soortenbesluit():
    assert combineer_categorieen("soortenbesluit", ["cat. 2", "cat. 4"]) == "cat. 2 en 4"


def test_combineer_categorieen_bijlagen():
    assert combineer_categorieen("vrl", ["bijlage I", "bijlage II.2"]) == "bijlage I, II.2"


def test_combineer_categorieen_enkelvoudig():
    assert combineer_categorieen("rodelijst_vl", ["EN"]) == "EN"


def test_combineer_categorieen_leeg():
    assert combineer_categorieen("rodelijst_vl", []) == "vermeld"


# --- relevantie (op genormaliseerde waarden) -----------------------------------------------


def test_relevantie_soortenbesluit_cat3():
    assert relevantie("soortenbesluit", "cat. 3") == 4


def test_relevantie_vrl_bijlage_i():
    assert relevantie("vrl", "bijlage I") == 3


def test_relevantie_rodelijst_broedvogels_vu():
    assert relevantie("rodelijst_broedvogels_2016", "VU") == 2


# --- is_kern ---------------------------------------------------------------------------


def test_is_kern_vrl_bijlage_ii_2_is_geen_kern():
    assert is_kern("vrl", "bijlage II.2") is False


def test_is_kern_vrl_bijlage_i_is_kern():
    assert is_kern("vrl", "bijlage I") is True


def test_is_kern_rodelijst_nt_alleen_met_met_nt():
    assert is_kern("rodelijst_vl", "NT") is False
    assert is_kern("rodelijst_vl", "NT", met_nt=True) is True
