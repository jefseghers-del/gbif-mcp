# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Register van gezaghebbende lijsten op het Vlaams Biodiversiteitsportaal (INBO, natuurdata.inbo.be).

Het portaal is een Atlas of Living Australia-instantie; elke lijst heeft een `dataResourceUid`
(dr…). De sleutels (`lsid`) van de lijstitems zijn GBIF-backbone-taxonKeys, zodat lijsten en
GBIF-waarnemingen zonder naammatching te koppelen zijn.

Alleen lijsten met `isAuthoritative = true` op het portaal (en de niet-gevalideerde Rode Lijst,
expliciet zo benoemd) zijn opgenomen. Persoonlijke of test-lijsten ("Mijn soortenlijst") niet.
Peildatum inventaris: 17 september 2026.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


INBO_PORTAAL = "https://natuurdata.inbo.be"


@dataclass(frozen=True)
class Lijst:
    code: str
    dr: str
    naam: str
    toelichting: str
    # Welk KVP-veld de categorie bevat, in volgorde van voorkeur.
    categorie_velden: tuple[str, ...] = ()
    toelichting_velden: tuple[str, ...] = ()
    jaar_velden: tuple[str, ...] = ()
    bron_velden: tuple[str, ...] = ()
    groep: str = "overig"  # bescherming | rodelijst | invasief | beleid | verdrag
    # Alleen items behouden waarvan KVP-veld == waarde (bv. één Rode Lijst uit een verzamellijst).
    kvp_filter: tuple[str, str] | None = None

    @property
    def url(self) -> str:
        return f"{INBO_PORTAAL}/species-list/speciesListItem/list/{self.dr}"


LIJSTEN: list[Lijst] = [
    # --- Vlaamse wetgeving ---
    Lijst("soortenbesluit", "dr542", "Soortenbesluit (bijlage 1, categorieën 1-3)",
          "Besluit Vl. Reg. 15 mei 2009 met betrekking tot soortenbescherming en soortenbeheer, bijlage 1. "
          "cat1 = basisbescherming; cat2 = bijlage II/IV HRL of bijlage I VRL, strengere regeling; "
          "cat3 = bijlage IV HRL, strengste regeling (art. 20 §1 en §4).",
          categorie_velden=("kenmerkwaardecode", "status"), toelichting_velden=("kenmerkwaarde",), groep="bescherming"),
    Lijst("jachtdecreet", "dr492", "Jachtdecreet — jachtwild (checklist)",
          "Soorten die als wild worden aangemerkt onder het Jachtdecreet van 24 juli 1991.",
          categorie_velden=("attributeValue", "taxonListGroup"), toelichting_velden=("attribute",), jaar_velden=("YearOfPublication",), groep="bescherming"),
    # --- EU-richtlijnen ---
    Lijst("hrl_ii", "dr565", "Habitatrichtlijn bijlage II",
          "Dier- en plantensoorten van communautair belang waarvoor speciale beschermingszones moeten worden aangewezen.",
          categorie_velden=("Species group",), groep="bescherming"),
    Lijst("hrl_iv_vl", "dr525", "Habitatrichtlijn bijlage IV — soorten die in het Vlaamse Gewest voorkomen of kunnen voorkomen (Soortenbesluit, categorie 3)",
          "Bijlage 1, categorie 3 van het Soortenbesluit: bijlage IV-soorten die in Vlaanderen (kunnen) voorkomen; strengste beschermingsregeling. "
          "Dit is de bruikbare bijlage IV-lijst voor Vlaamse dossiers.",
          categorie_velden=("kenmerkwaardecode", "status"), toelichting_velden=("kenmerkwaarde",), groep="bescherming"),
    Lijst("hrl_iv", "dr570", "Habitatrichtlijn bijlage IV (portaal-lijst, 83 soorten; ONVOLLEDIG)",
          "Strikt te beschermen soorten (art. 12-13 HRL). LET OP: deze portaal-lijst is afgeleid van de Britse NBN-lijst en mist "
          "o.m. wolf en bever; gebruik voor Vlaanderen `hrl_iv_vl` (Soortenbesluit cat. 3) als primaire bron.",
          categorie_velden=("Species group", "status"), groep="bescherming"),
    Lijst("hrl_v", "dr569", "Habitatrichtlijn bijlage V",
          "Soorten waarvan het onttrekken aan de natuur en de exploitatie aan beheersmaatregelen kunnen worden onderworpen.",
          categorie_velden=("Species group", "Designation"), groep="bescherming"),
    Lijst("vrl", "dr563", "Vogelrichtlijn bijlagen I, II.1 en II.2 (gecombineerd)",
          "Bijlage I = speciale beschermingsmaatregelen (SBZ-V); bijlage II = bejaagbaar.",
          categorie_velden=("Designation",), groep="bescherming"),
    Lijst("vrl_iii", "dr571", "Vogelrichtlijn bijlage III",
          "Vogels die onder voorwaarden mogen worden verhandeld.",
          categorie_velden=("Designation",), groep="bescherming"),
    # --- Verdragen ---
    Lijst("bern", "dr566", "Verdrag van Bern — bijlagen I, II en III",
          "Verdrag inzake het behoud van wilde dieren en planten en hun natuurlijk leefmilieu in Europa (1979).",
          categorie_velden=("Designation",), groep="verdrag"),
    Lijst("bonn", "dr567", "Verdrag van Bonn (CMS) — trekkende soorten",
          "Convention on the Conservation of Migratory Species of Wild Animals (1979).",
          categorie_velden=("Designation",), groep="verdrag"),
    Lijst("cites", "dr568", "EU CITES-verordening (Verordening (EG) nr. 338/97) — bijlagen",
          "Handel in bedreigde soorten.",
          categorie_velden=("Designation",), groep="verdrag"),
    # --- Invasieve exoten ---
    Lijst("unielijst", "dr561", "Unielijst invasieve uitheemse soorten (Verordening (EU) nr. 1143/2014), stand 2025",
          "Voor de Unie zorgwekkende invasieve uitheemse soorten.",
          categorie_velden=("Kenmerkwaarde", "IAScode"), toelichting_velden=("degreesOfEstablishment",), groep="invasief"),
    Lijst("invasief_uitgebreid", "dr358", "Uitgebreide lijst invasieve uitheemse soorten (INBO, versie 2026-02-12)",
          "Bredere INBO-lijst van invasieve exoten, incl. soorten buiten de Unielijst.",
          categorie_velden=("ANB_Beleidscategorisering", "Soortgroep"), toelichting_velden=("Europese_unielijst",), groep="invasief"),
    # --- Rode Lijsten ---
    Lijst("rodelijst_vl", "dr606", "Meest recente gevalideerde Rode Lijsten van Vlaanderen (INBO)",
          "Officieel gevalideerde Rode-Lijstcategorie per soortengroep (IUCN-criteria). RLC: RE, CR, EN, VU, NT, LC, DD, NA.",
          categorie_velden=("RLC", "status"), toelichting_velden=("RLC_gepubliceerd", "threatStatus"),
          jaar_velden=("JaarPublicatie",), bron_velden=("source",), groep="rodelijst"),
    Lijst("rodelijst_broedvogels_2016", "dr552", "Rode Lijst van de broedvogels in Vlaanderen 2016 (Devos et al. 2016; gevalideerd)",
          "Enige beschikbare Rode Lijst voor vogels; zit op het portaal in de verzamellijst 'Validated red lists 2015' (bron Devos_etal_2016). "
          "Categorieën: RE (regionaal uitgestorven), CR, EN, VU, NT, LC, DD, NA (niet van toepassing), NE (niet geëvalueerd).",
          categorie_velden=("threatStatus", "status"), toelichting_velden=("threatStatus",), jaar_velden=("eventDate",), bron_velden=("source",),
          groep="rodelijst", kvp_filter=("source", "Devos_etal_2016")),
    Lijst("rodelijst_vl_nietgevalideerd", "dr572", "Niet-gevalideerde Rode Lijsten van Vlaanderen (INBO)",
          "Rode Lijsten die (nog) niet formeel gevalideerd zijn; gebruiken met dat voorbehoud.",
          categorie_velden=("RLC", "status", "threatStatus"), toelichting_velden=("RLC_gepubliceerd", "threatStatus"),
          jaar_velden=("JaarPublicatie", "year"), bron_velden=("source", "references"), groep="rodelijst"),
    Lijst("iucn", "dr574", "IUCN Red List (wereldwijd)",
          "Wereldwijde IUCN-status; niet de Vlaamse status.",
          categorie_velden=("redlistCategory", "status"), jaar_velden=("yearPublished",), groep="rodelijst"),
    # --- Beleid ---
    Lijst("prioritair_vl", "dr545", "Prioritaire soorten Vlaanderen",
          "Soorten waarvoor Vlaanderen een bijzondere verantwoordelijkheid draagt (Europees te rapporteren soorten).",
          categorie_velden=("status",), groep="beleid"),
    Lijst("prov_antwerpen", "dr493", "Provinciaal belangrijke soorten — Antwerpen", "", categorie_velden=("taxongroep",), groep="beleid"),
    Lijst("prov_limburg", "dr494", "Provinciaal belangrijke soorten — Limburg", "", categorie_velden=("taxongroep",), groep="beleid"),
    Lijst("prov_oost_vlaanderen", "dr495", "Provinciaal belangrijke soorten — Oost-Vlaanderen", "", categorie_velden=("taxongroep",), groep="beleid"),
    Lijst("prov_vlaams_brabant", "dr496", "Provinciaal belangrijke soorten — Vlaams-Brabant", "", categorie_velden=("taxongroep",), groep="beleid"),
    Lijst("prov_west_vlaanderen", "dr497", "Provinciaal belangrijke soorten — West-Vlaanderen", "", categorie_velden=("taxongroep",), groep="beleid"),
    Lijst("soortenmeetnetten", "dr498", "Checklist Soortenmeetnetten INBO", "Soorten die INBO via meetnetten opvolgt.",
          categorie_velden=("taxonListGroup",), groep="beleid"),
]

PER_CODE: dict[str, Lijst] = {l.code: l for l in LIJSTEN}
PER_DR: dict[str, Lijst] = {l.code: l for l in LIJSTEN}  # sleutel = code; meerdere codes kunnen dezelfde dr delen

# Handige groepen voor de filter in `soorten_in_gebied`.
GROEPEN: dict[str, list[str]] = {
    # `kern`: wat in een natuurtoets/m.e.r. telt — bijlage IV (Vlaanderen), bijlage II, VRL bijlage I,
    # Rode Lijst RE/CR/EN/VU. De engine filtert daarbij op categorie (zie `is_kern`).
    "kern": ["hrl_iv_vl", "hrl_ii", "vrl", "rodelijst_vl", "rodelijst_broedvogels_2016"],
    "beschermd": ["soortenbesluit", "hrl_ii", "hrl_iv_vl", "hrl_v", "vrl", "bern", "bonn"],
    "europees": ["hrl_ii", "hrl_iv_vl", "hrl_v", "vrl"],
    "rodelijst": ["rodelijst_vl", "rodelijst_broedvogels_2016"],
    "invasief": ["unielijst", "invasief_uitgebreid"],
    "prioritair": ["prioritair_vl"],
    "provinciaal": ["prov_antwerpen", "prov_limburg", "prov_oost_vlaanderen", "prov_vlaams_brabant", "prov_west_vlaanderen"],
}

_ROMEINS = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}


def normaliseer_categorie(lijst_code: str, categorie: str | None) -> str | None:
    """Eén Nederlandse notatie voor `samenvatting`; de ruwe portaalwaarde blijft in `extra['categorie_bron']`."""
    c = (categorie or "").strip()
    if lijst_code in ("hrl_ii",):
        return "bijlage II"
    if lijst_code in ("hrl_iv_vl", "hrl_iv"):
        return "bijlage IV"
    if lijst_code == "hrl_v":
        return "bijlage V"
    if lijst_code in ("vrl", "vrl_iii", "bern", "bonn", "cites"):
        m = re.match(r"(?:Annex|Appendix|Bijlage)\s*([0-9A-Z])(?:\.(\d))?", c, re.I)
        if m:
            hoofd = _ROMEINS.get(m.group(1), m.group(1))
            return f"bijlage {hoofd}" + (f".{m.group(2)}" if m.group(2) else "")
        return c or "vermeld"
    if lijst_code == "soortenbesluit":
        m = re.search(r"cat\s*\.?\s*(\d)", c, re.I)
        return f"cat. {m.group(1)}" if m else (c or "vermeld")
    if lijst_code == "unielijst":
        return "Unielijst"
    if lijst_code == "invasief_uitgebreid":
        return "invasieve exoot (INBO-lijst)"
    if lijst_code == "prioritair_vl":
        return "prioritaire soort"
    if lijst_code.startswith("prov_"):
        return "provinciaal belangrijk"
    if lijst_code == "jachtdecreet":
        return c or "jachtwild"
    if lijst_code.startswith("rodelijst") or lijst_code == "iucn":
        m = re.search(r"\(([A-Z]{2})\)", c)
        if m:
            code = m.group(1)
            return "RE" if code == "EX" and lijst_code != "iucn" else code
        laag = c.lower()
        if "uitgestorven" in laag or laag.startswith("regionally extinct"):
            return "RE"
        if "niet van toepassing" in laag:
            return "NA"
        if "valueerd" in laag or "not evaluated" in laag:
            return "NE"
        if "onvoldoende" in laag or "data deficient" in laag:
            return "DD"
        return c or "vermeld"
    return c or "vermeld"


def combineer_categorieen(lijst_code: str, cats: list[str]) -> str:
    """['cat. 2', 'cat. 4'] -> 'cat. 2 en 4'; ['bijlage I', 'bijlage II.2'] -> 'bijlage I, II.2'."""
    uniek = list(dict.fromkeys(c for c in cats if c))
    if len(uniek) <= 1:
        return uniek[0] if uniek else "vermeld"
    if lijst_code == "soortenbesluit" and all(u.startswith("cat. ") for u in uniek):
        nrs = sorted(u[5:] for u in uniek)
        return "cat. " + ", ".join(nrs[:-1]) + " en " + nrs[-1]
    if all(u.startswith("bijlage ") for u in uniek):
        return "bijlage " + ", ".join(u[8:] for u in uniek)
    return "; ".join(uniek)


def relevantie(lijst_code: str, categorie: str | None) -> int:
    """Grove rangorde voor sortering in `soorten_in_gebied`: hoger = strikter beschermd. Werkt op de genormaliseerde categorie.

    Terminologie: spreek van strikt of striktst beschermd, niet van zwaar of zwaarst beschermd."""
    c = (categorie or "").strip()
    cu = c.upper()
    if lijst_code in ("hrl_iv_vl", "hrl_iv") or (lijst_code == "soortenbesluit" and c == "cat. 3"):
        return 4
    if lijst_code == "hrl_ii" or (lijst_code == "vrl" and cu == "BIJLAGE I") or (lijst_code.startswith("rodelijst") and cu in ("RE", "CR", "EN")):
        return 3
    if (lijst_code == "soortenbesluit" and c == "cat. 2") or (lijst_code.startswith("rodelijst") and cu == "VU") or lijst_code in ("unielijst", "prioritair_vl"):
        return 2
    if lijst_code in ("bern", "bonn", "hrl_v", "invasief_uitgebreid") or lijst_code.startswith("prov_") or (lijst_code.startswith("rodelijst") and cu == "NT"):
        return 1
    return 0


def is_kern(lijst_code: str, categorie: str | None, *, met_nt: bool = False) -> bool:
    """Kernstatus voor een natuurtoets: bijlage IV (Vl.), bijlage II, VRL bijlage I, Rode Lijst RE/CR/EN/VU (optioneel NT)."""
    cu = (categorie or "").strip().upper()
    if lijst_code in ("hrl_iv_vl", "hrl_ii"):
        return True
    if lijst_code == "vrl":
        return cu == "BIJLAGE I"
    if lijst_code.startswith("rodelijst") and lijst_code != "rodelijst_vl_nietgevalideerd":
        return cu in RODELIJST_BEDREIGD or (met_nt and cu == "NT")
    return False


# Rode-Lijstcategorieën die als 'bedreigd' gelden (IUCN).
RODELIJST_BEDREIGD = {"RE", "CR", "EN", "VU"}

# GBIF-checklists, als aanvulling/controle op de INBO-lijsten.
# EU-brede checklists van de Habitatrichtlijnbijlagen (Ukrainian Nature Conservation Group, GBIF); alleen als kruiscontrole.
HRL_EU_CHECKLISTS: dict[str, str] = {
    "hrl_ii": "2f845607-9b6a-4b31-b283-b87b89241e20",
    "hrl_iv_vl": "d1baf4e0-db47-4802-bce0-87881bc105d5",
    "hrl_iv": "d1baf4e0-db47-4802-bce0-87881bc105d5",
    "hrl_v": "0bc4fb0e-a8f2-4e77-a3cf-be1ed4c028bb",
}

GBIF_CHECKLISTS: dict[str, tuple[str, str]] = {
    "gbif_rodelijst_vl": ("fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9", "Validated red lists of Flanders, Belgium (INBO, GBIF)"),
    "gbif_griis_be": ("6d9e952f-948c-4483-9807-575348147c7e", "Global Register of Introduced and Invasive Species — Belgium (GBIF)"),
    "gbif_unielijst": ("79d65658-526c-4c78-9d24-1870d67f8439", "List of Invasive Alien Species of Union concern (GBIF)"),
    "gbif_belgian_species_list": ("39653f3e-8d6b-4a94-a202-859359c164c5", "Belgian Species List (Belgian Biodiversity Platform)"),
}


def ontleed_codes(filter_: str | None) -> list[str]:
    """'beschermd,rodelijst' of 'hrl_iv' -> lijst van lijst_codes. Onbekende codes geven ValueError."""
    if not filter_:
        return []
    codes: list[str] = []
    for deel in (d.strip() for d in filter_.split(",")):
        if not deel:
            continue
        if deel in GROEPEN:
            codes.extend(GROEPEN[deel])
        elif deel in PER_CODE:
            codes.append(deel)
        else:
            raise ValueError(f"Onbekende lijst- of groepscode '{deel}'. Geldig: {', '.join(list(GROEPEN) + list(PER_CODE))}")
    # ontdubbelen, volgorde behouden
    return list(dict.fromkeys(codes))
