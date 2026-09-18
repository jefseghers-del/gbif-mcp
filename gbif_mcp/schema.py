# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Intern schema van de connector (Pydantic).

Uitgangspunt: elk teruggegeven feit draagt een controleerbare bron-URL mee (`url`, `bron`).
De MCP-client leidt de JSON-schema's af uit deze modellen en de Field-beschrijvingen.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Soort(BaseModel):
    """Eén taxon, geïdentificeerd door zijn GBIF-backbone-sleutel."""

    taxon_key: int = Field(description="GBIF-backbone taxonKey (identiek aan de INBO-portaal-guid).")
    wetenschappelijke_naam: str
    nederlandse_naam: str | None = None
    rang: str | None = Field(default=None, description="bv. SPECIES, SUBSPECIES, GENUS")
    status: str | None = Field(default=None, description="ACCEPTED, SYNONYM, DOUBTFUL …")
    geaccepteerde_naam: str | None = Field(default=None, description="Ingevuld als de naam een synoniem is.")
    rijk: str | None = None
    klasse: str | None = None
    familie: str | None = None
    match_type: str | None = Field(default=None, description="EXACT, FUZZY, HIGHERRANK, NONE (GBIF) of INBO_NL (Nederlandse naam via INBO).")
    zekerheid: int | None = Field(default=None, description="GBIF-confidence 0-100, indien via naammatching.")
    url: str = Field(description="Controleerbare bronpagina (gbif.org/species/<key>).")
    url_inbo: str | None = Field(default=None, description="Soortpagina op het Vlaams Biodiversiteitsportaal.")


class LijstVermelding(BaseModel):
    """Vermelding van een taxon op één gezaghebbende lijst (INBO-portaal of GBIF-checklist)."""

    lijst_code: str = Field(description="Korte code, zie tool `bronnen` (bv. soortenbesluit, hrl_iv, rodelijst_vl).")
    lijst_naam: str
    categorie: str | None = Field(default=None, description="Categorie/status op die lijst (bv. cat3, EN/Bedreigd, Bijlage I).")
    toelichting: str | None = Field(default=None, description="Letterlijke omschrijving zoals de bron ze geeft.")
    jaar: str | None = None
    bronvermelding: str | None = Field(default=None, description="Wetenschappelijke bron van de beoordeling (bv. Speybroeck et al. 2024).")
    url: str = Field(description="Controleerbare bron-URL van de lijst.")
    extra: dict[str, str] = Field(default_factory=dict, description="Overige velden uit de bron, ongewijzigd.")


class SoortStatus(BaseModel):
    geraadpleegd_op: str | None = None
    soort: Soort
    exoot: bool | None = None
    vermeldingen: list[LijstVermelding] = Field(description="Alle gevonden lijstvermeldingen. Leeg = op geen enkele geraadpleegde lijst gevonden (≠ onbeschermd; zie melding).")
    samenvatting: dict[str, str] = Field(default_factory=dict, description="Per lijst_code de categorie, als snelle samenvatting.")
    koppeling_twijfel: str | None = None
    melding: str | None = None
    kanttekening: str | None = None


class Waarneming(BaseModel):
    gbif_id: int
    soort: str = Field(description="Wetenschappelijke naam zoals GBIF ze interpreteerde.")
    nederlandse_naam: str | None = None
    datum: str | None = Field(default=None, description="ISO-datum (of jaar/maand indien onvolledig).")
    jaar: int | None = None
    lat: float | None = None
    lon: float | None = None
    onzekerheid_m: float | None = Field(default=None, description="coordinateUncertaintyInMeters. Grote waarden = vervaagde locatie.")
    gemeente: str | None = Field(default=None, description="Niet altijd ingevuld; GBIF-veld municipality/locality.")
    plaats: str | None = None
    basis: str | None = Field(default=None, description="basisOfRecord: HUMAN_OBSERVATION, PRESERVED_SPECIMEN …")
    aantal: int | None = None
    dataset: str | None = None
    dataset_key: str | None = None
    levensstadium: str | None = Field(default=None, description="lifeStage")
    voortplanting: str | None = Field(default=None, description="reproductiveCondition")
    gedrag: str | None = Field(default=None, description="behavior")
    geslacht: str | None = Field(default=None, description="sex")
    opmerkingen: str | None = Field(default=None, description="occurrenceRemarks (ingekort)")
    verificatiestatus: str | None = Field(default=None, description="identificationVerificationStatus, letterlijk zoals de bron hem levert (bv. 'approved on expert judgement', 'unverified', 'validated'); leeg bij datasets die het veld niet vullen.")
    broedindicatie: bool = Field(default=False, description="Heuristiek op de velden hierboven (broed-, nest-, territorium-, juveniel-, paring-termen).")
    afstand_m: float | None = Field(default=None, description="Afstand tot het middelpunt (alleen bij cirkelgebied).")
    url: str = Field(description="gbif.org/occurrence/<id>")


class WaarnemingenRespons(BaseModel):
    geraadpleegd_op: str
    soort: Soort | None = None
    gebied: str = Field(description="Omschrijving van het gebruikte gebied (WKT, gemeente of adres+straal).")
    periode: str | None = None
    totaal: int = Field(description="Totaal aantal waarnemingen dat aan de filters voldoet (kan groter zijn dan wat is teruggegeven).")
    teruggegeven: int
    offset: int = 0
    records_met_broedindicatie: int | None = None
    per_verificatiestatus: dict[str, int] = Field(default_factory=dict, description="Telling van identificationVerificationStatus over de teruggegeven records; '(leeg)' = veld niet gevuld door de bron.")
    waarnemingen: list[Waarneming]
    per_dataset: list[dict] = Field(default_factory=list, description="Verdeling over datasets (naam, sleutel, aantal).")
    per_jaar: list[dict] = Field(default_factory=list)
    zoek_url: str = Field(description="Dezelfde zoekopdracht op gbif.org, ter controle.")
    licentiefilter: str | None = None
    waarschuwingen: list[str] = Field(default_factory=list)
    kanttekening: str = Field(description="Verplichte lezing: beperkingen van de data.")


class SoortInGebied(BaseModel):
    """Compacte regel per soort. `vermeldingen` alleen bij `detail=True`."""

    taxon_key: int
    wetenschappelijke_naam: str
    nederlandse_naam: str | None = None
    aantal_waarnemingen: int
    laatste_jaar: int | None = None
    samenvatting: dict[str, str] = Field(default_factory=dict, description="Per lijstcode de (genormaliseerde) categorie.")
    exoot: bool | None = Field(default=None, description="True = uitheems volgens GRIIS België, Unielijst of INBO-exotenlijst; None = niet gecontroleerd.")
    onzekerheid_max_m: float | None = Field(default=None, description="Grootste coordinateUncertaintyInMeters van de records in het gebied.")
    zeker_binnen_straal: int | None = Field(default=None, description="Records waarvan afstand tot middelpunt + onzekerheid ≤ straal (alleen bij cirkelgebied).")
    records_met_broedindicatie: int | None = Field(default=None, description="Records met een broed-/voortplantingsaanwijzing in lifeStage, reproductiveCondition, behavior of occurrenceRemarks.")
    koppeling_twijfel: str | None = Field(default=None, description="Ingevuld als een HRL-vermelding van het INBO-portaal niet strookt met de EU-checklist van die bijlage.")
    datasets: list[dict] | None = Field(default=None, description="Alleen bij per_dataset_per_soort=True: brondatasets van deze soort in dit gebied (dataset_key, dataset, aantal, laatste_jaar), aflopend op aantal. De som van `aantal` is gelijk aan `aantal_waarnemingen`.")
    vermeldingen: list[LijstVermelding] | None = None


class SoortenInGebiedRespons(BaseModel):
    geraadpleegd_op: str
    gebied: str
    periode: str | None = None
    filter: str | None = None
    totaal_waarnemingen: int = Field(description="Alle GBIF-waarnemingen in het gebied en de periode (alle soorten).")
    aantal_soorten_in_gebied: int = Field(description="Aantal soorten met waarnemingen vóór filtering op lijsten.")
    totaal_soorten_met_status: int = Field(description="Aantal soorten dat aan de filter voldoet; `soorten` is daarvan de pagina offset..offset+max_soorten.")
    offset: int = 0
    soorten: list[SoortInGebied] = Field(default_factory=list, description="Leeg bij formaat='tabel'; dan staat alles in `tabel`. Soort-URL = https://www.gbif.org/species/<taxon_key>.")
    tabel: str | None = Field(default=None, description="Markdown-tabel met dezelfde inhoud (formaat='tabel'), ±4x compacter.")
    rodelijst_dekking: dict[str, str] = Field(default_factory=dict, description="Per Rode-Lijstcode de soortengroepen en publicatiejaren die de lijst dekt.")
    legende: dict[str, dict[str, str]] = Field(default_factory=dict, description="Per lijstcode: categorie -> toelichting uit de bron (één keer, niet per soort).")
    lijstversies: dict[str, str | None] = Field(default_factory=dict, description="Per lijstcode het tijdstip waarop de lijst bij het portaal is opgehaald.")
    per_dataset: list[dict] = Field(default_factory=list, description="Datasets in het gebied (sleutel, naam, aantal records), voor citatie.")
    gbif_parameters: dict = Field(default_factory=dict, description="De GBIF-API-parameters van de facetbevraging (reproduceerbaarheid).")
    licentiefilter: str | None = Field(default=None, description="Welke datalicenties zijn meegenomen; standaard alleen CC0 en CC BY.")
    licenties: dict[str, int] = Field(default_factory=dict, description="Records per licentie in het gebied, vóór de filter.")
    uitgesloten_niet_commercieel: int = Field(default=0, description="Records onder CC BY-NC die door de filter zijn weggelaten.")
    zoek_url: str
    volledig: bool = True
    ontbrekend: list[str] = Field(default_factory=list, description="Wat binnen het tijdsbudget niet kon worden opgehaald.")
    waarschuwingen: list[str] = Field(default_factory=list)
    kanttekening: str


class TellingRespons(BaseModel):
    geraadpleegd_op: str
    gebied: str
    periode: str | None = None
    totaal_waarnemingen: int
    totaal_soorten: int
    totaal_soorten_met_status: int = Field(description="Soorten met minstens één vermelding op de geraadpleegde lijsten.")
    per_lijst: dict[str, int] = Field(description="Aantal soorten per lijstcode.")
    per_categorie: dict[str, dict[str, int]] = Field(description="Per lijstcode: categorie -> aantal soorten.")
    per_dataset: list[dict] = Field(default_factory=list, description="Brondatasets in het gebied: dataset_key, dataset, aantal_records, en (alleen met soorten_per_dataset=True) aantal_soorten_met_status.")
    kern: int = Field(description="Soorten met kernstatus (bijlage IV Vl., bijlage II, VRL bijlage I, Rode Lijst RE/CR/EN/VU).")
    exoten: int = Field(description="Soorten met status die tegelijk als uitheems geregistreerd zijn.")
    licentiefilter: str | None = Field(default=None, description="Welke datalicenties zijn meegenomen; standaard alleen CC0 en CC BY.")
    licenties: dict[str, int] = Field(default_factory=dict, description="Records per licentie in het gebied, vóór de filter.")
    uitgesloten_niet_commercieel: int = Field(default=0, description="Records onder CC BY-NC die door de filter zijn weggelaten.")
    rodelijst_dekking: dict[str, str] = Field(default_factory=dict)
    lijstversies: dict[str, str | None] = Field(default_factory=dict)
    zoek_url: str
    waarschuwingen: list[str] = Field(default_factory=list)
    kanttekening: str


class LijstItem(BaseModel):
    soort: Soort
    vermelding: LijstVermelding


class LijstRespons(BaseModel):
    lijst_code: str
    lijst_naam: str
    url: str
    totaal: int
    teruggegeven: int
    items: list[LijstItem]
    melding: str | None = None


class Locatie(BaseModel):
    invoer: str
    adres: str | None = None
    gemeente: str | None = None
    postcode: str | None = None
    lat: float
    lon: float
    x_lambert72: float | None = None
    y_lambert72: float | None = None
    type: str | None = None
    waarschuwing: str | None = Field(default=None, description="bv. geen huisnummer: het resultaat is het straatmidden.")
    bron: str = "geo.api.vlaanderen.be (Digitaal Vlaanderen, geolocation v4)"


class DatasetInfo(BaseModel):
    key: str
    titel: str
    type: str | None = None
    uitgever: str | None = None
    licentie: str | None = None
    doi: str | None = None
    beschrijving: str | None = None
    citatie: str | None = None
    url: str


class GebiedTreffer(BaseModel):
    naam: str | None = None
    code: str | None = Field(default=None, description="bv. SBZ-code BE2300006, VEN-gebiedsnr, registratienummer.")
    overlapt: bool = Field(description="True = het punt ligt erin / de polygoon overlapt ermee.")
    afstand_m: int = Field(description="0 bij overlap, anders afstand tot de dichtstbijzijnde grens (Lambert 72, metrisch).")
    oppervlakte_ha: float | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class GebiedenLaag(BaseModel):
    laag: str
    naam: str
    url: str
    geraadpleegd_op: str
    status: str = Field(description="ok | niet_geraadpleegd (dienst gaf een fout: geen uitspraak mogelijk).")
    aantal_overlappend: int = 0
    aantal_binnen_straal: int = 0
    treffers: list[GebiedTreffer]
    melding: str | None = None


class GebiedenRespons(BaseModel):
    geraadpleegd_op: str
    doel: str
    straal_m: float
    lagen: list[GebiedenLaag]
    samenvatting: dict[str, str] = Field(default_factory=dict, description="Per laag met treffers: 'in <naam>' of 'dichtstbij <naam> op N m'.")
    niet_geraadpleegd: list[str] = Field(default_factory=list)
    waarschuwingen: list[str] = Field(default_factory=list)
    kanttekening: str


class Bron(BaseModel):
    code: str
    naam: str
    type: str = Field(description="inbo_lijst, gbif_checklist, gbif_occurrence, geocoder")
    url: str
    toelichting: str | None = None
