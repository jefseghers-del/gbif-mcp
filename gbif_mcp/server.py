"""MCP-server voor Belgische biodiversiteitsdata (GBIF + INBO Vlaams Biodiversiteitsportaal).

Tools:
  - zoek_soort          : naam (wetenschappelijk of Nederlands) -> taxon met GBIF-sleutel
  - soort_status        : beschermings-, Rode-Lijst- en exotenstatus van één soort
  - waarnemingen        : waarnemingen van een soort in een gebied/periode
  - soorten_in_gebied   : alle soorten in een gebied, optioneel gefilterd op lijsten (bv. bijlage IV, Rode Lijst)
  - lijst               : inhoud van één gezaghebbende lijst (Soortenbesluit, bijlagen, Rode Lijst …)
  - geocodeer           : adres -> coördinaten (Digitaal Vlaanderen)
  - dataset_info        : herkomst, licentie en citatie van een GBIF-dataset
  - bronnen             : overzicht van de geraadpleegde bronnen en lijstcodes

Anti-hallucinatie: elke tool geeft uitsluitend terug wat de bron effectief oplevert, telkens met
een controleerbare URL. Nul treffers betekent 'niet gevonden in deze bron', niet 'afwezig'.

Lokaal draaien (stdio): python -m gbif_mcp.server
"""
from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

from . import DISCLAIMER, PRIVACY, __version__, gbif, gebieden, gebiedsanalyse as ga, inbo, kaart as kaartmodule
from .datasets import compact as datasets_compact
from .geo import afstand_m, bepaal_gebied, geocodeer
from .http import nu_iso
from .lijsten import GBIF_CHECKLISTS, GROEPEN, LIJSTEN, PER_CODE, ontleed_codes
from .schema import (
    Bron,
    DatasetInfo,
    GebiedenRespons,
    LijstItem,
    LijstRespons,
    LijstVermelding,
    Locatie,
    Soort,
    SoortenInGebiedRespons,
    SoortInGebied,
    SoortStatus,
    TellingRespons,
    WaarnemingenRespons,
)

mcp = MCPServer("be-biodiversiteit", version=__version__)

KANTTEKENING_WAARNEMINGEN = (
    "GBIF-waarnemingen zijn opportunistische meldingen (vooral waarnemingen.be), geen systematische inventarisatie. "
    "Afwezigheid van waarnemingen bewijst geen afwezigheid van de soort. Locaties van gevoelige soorten zijn vaak "
    "opzettelijk vervaagd (zie onzekerheid_m; waarden van 1-10 km wijzen op vervaging naar een hok). Waarnemingen.be "
    "publiceert met vertraging en niet alle validatieklassen. Voor een dossier blijft een terreininventarisatie nodig."
)


KANTTEKENING_KAART = (
    "De kaart toont uitsluitend de vlakken die de WFS-diensten teruggaven, op de GRB-basiskaart. "
    "Erkende natuurreservaten (kernzones) en bosreservaten zitten niet in die diensten. "
    "BWK-karteringseenheden zijn geen juridisch statuut. Geen vervanging van een uittreksel op Geopunt."
)

KANTTEKENING_HERKOMST = (
    "De brondataset zegt iets over de HERKOMST van de determinatie (wie ze deed en via welk platform), "
    "niet over de validatiestatus van het individuele record. Waarnemingen.be stuurt niet alle "
    "validatieklassen door naar GBIF, en verscheidene datasets (eBird, iNaturalist, Pl@ntNet) vullen "
    "het veld identificationVerificationStatus niet in. Weeg de herkomst zelf; de connector doet dat niet."
)

_samenvatting = ga.samenvatting


def _tel_verificatie(waarnemingen_lijst) -> dict[str, int]:
    """Telling van identificationVerificationStatus over records; niet-ingevulde waarden als '(leeg)'."""
    uit: dict[str, int] = {}
    for w in waarnemingen_lijst:
        sleutel = w.verificatiestatus or "(leeg)"
        uit[sleutel] = uit.get(sleutel, 0) + 1
    return dict(sorted(uit.items(), key=lambda kv: -kv[1]))


async def _resolve(naam_of_key: str | int) -> Soort | None:
    """Naam of taxonKey -> Soort. Volgorde: sleutel > INBO (NL + wetenschappelijk) > GBIF-backbone-match > Belgian Species List (NL)."""
    if isinstance(naam_of_key, int) or str(naam_of_key).strip().isdigit():
        return await gbif.haal_soort(int(naam_of_key))
    naam = str(naam_of_key).strip()
    kandidaten = await inbo.zoek(naam, limit=5)
    exact = [
        k for k in kandidaten
        if naam.lower() in ((k.nederlandse_naam or "").lower(), k.wetenschappelijke_naam.lower())
    ]
    if exact:
        return exact[0]
    m = await gbif.match_naam(naam)
    if m and m.match_type == "EXACT":
        return m
    bsl = await gbif.zoek_nederlandse_naam(naam, limit=5)
    exact_bsl = [k for k in bsl if (k.nederlandse_naam or "").lower() == naam.lower()]
    if exact_bsl:
        return exact_bsl[0]
    if kandidaten:
        return kandidaten[0]
    if m:
        return m
    return bsl[0] if bsl else None


async def _vul_nl_naam(s: Soort) -> Soort:
    if not s.nederlandse_naam:
        namen = await inbo.nederlandse_namen(s.taxon_key) or await gbif.nederlandse_namen(s.taxon_key)
        if namen:
            s.nederlandse_naam = namen[0]
    if not s.url_inbo:
        s.url_inbo = inbo.soortpagina(s.taxon_key)
    return s


@mcp.tool()
async def zoek_soort(naam: str, max_resultaten: int = 10) -> list[Soort]:
    """Zoek een soort op wetenschappelijke of Nederlandse naam en geef de GBIF-taxonsleutel(s).

    Zoekt eerst in het Vlaams Biodiversiteitsportaal (INBO; kent Nederlandse namen), daarna in de
    GBIF-backbone en de Belgian Species List. Gebruik de `taxon_key` uit het resultaat in de andere tools.
    Meerdere treffers = ambigu (bv. 'kamsalamander' geeft ook 'Italiaanse kamsalamander'); kies bewust.

    Args:
        naam: bv. 'vroedmeesterpad', 'Alytes obstetricans', 'Triturus'.
        max_resultaten: hoogstens dit aantal kandidaten.
    """
    naam = naam.strip()
    gezien: dict[int, Soort] = {}
    if naam.isdigit():
        s = await gbif.haal_soort(int(naam))
        return [await _vul_nl_naam(s)]
    for s in await inbo.zoek(naam, limit=max_resultaten):
        gezien.setdefault(s.taxon_key, s)
    m = await gbif.match_naam(naam)
    if m and m.match_type in ("EXACT", "FUZZY") and m.taxon_key not in gezien:
        gezien[m.taxon_key] = m
    if len(gezien) < max_resultaten:
        for s in await gbif.zoek_nederlandse_naam(naam, limit=max_resultaten):
            gezien.setdefault(s.taxon_key, s)
    uit = list(gezien.values())[:max_resultaten]
    return [await _vul_nl_naam(s) for s in uit]


@mcp.tool()
async def soort_status(soort: str) -> SoortStatus:
    """Beschermings-, Rode-Lijst- en exotenstatus van één soort in Vlaanderen/België, met bron per vermelding.

    Raadpleegt de gezaghebbende lijsten op het Vlaams Biodiversiteitsportaal (Soortenbesluit met
    categorie 1-3, Habitatrichtlijn bijlagen II/IV/V, Vogelrichtlijn, Bern, Bonn, CITES, Unielijst
    invasieve soorten, gevalideerde en niet-gevalideerde Vlaamse Rode Lijsten, IUCN, prioritaire en
    provinciaal belangrijke soorten) én de GBIF-checklists (Rode Lijst Vlaanderen, GRIIS België).
    `samenvatting` geeft per lijstcode de categorie; `vermeldingen` de details en URL's.

    Lege `vermeldingen` = op geen van deze lijsten aangetroffen; dat is geen uitspraak over het
    werkelijke beschermingsstatuut (bv. alle inheemse vogels genieten basisbescherming via het
    Soortenbesluit, ook al staan ze niet als aparte regel op de lijst). Zeg dat er dan bij.

    Args:
        soort: Nederlandse of wetenschappelijke naam, of GBIF-taxonKey.
    """
    s = await _resolve(soort)
    if s is None:
        raise ValueError(f"Soort niet gevonden: '{soort}'. Probeer `zoek_soort` voor kandidaten.")
    s = await _vul_nl_naam(s)
    vermeldingen = await inbo.lijsten_van_taxon(s.taxon_key)
    meldingen: list[str] = []
    # GBIF-checklists als aanvulling (Rode Lijst-verspreidingsrecord, GRIIS)
    for code in ("gbif_rodelijst_vl", "gbif_griis_be"):
        ds, naam = GBIF_CHECKLISTS[code]
        try:
            for d in await gbif.checklist_verspreiding(ds, s.taxon_key):
                vermeldingen.append(
                    LijstVermelding(
                        lijst_code=code,
                        lijst_naam=naam,
                        categorie=d.get("threatStatus") or d.get("establishmentMeans"),
                        toelichting=d.get("remarks"),
                        jaar=d.get("temporal"),
                        bronvermelding=(d.get("source") or "")[:300] or None,
                        url=f"https://www.gbif.org/species/{d['_checklist_taxon_key']}",
                        extra={k: str(v) for k, v in d.items() if k in ("locality", "locationId", "status", "establishmentMeans", "degreeOfEstablishment")},
                    )
                )
        except Exception as e:  # bron tijdelijk onbereikbaar: melden, niet verzwijgen
            meldingen.append(f"{naam}: niet geraadpleegd ({type(e).__name__}).")
    if not vermeldingen:
        meldingen.append("Op geen enkele geraadpleegde lijst aangetroffen. Dit is geen bewijs dat de soort onbeschermd is.")
    exoot_keys, exoot_fouten = await ga._exoot_keys()
    exoot: bool | None = s.taxon_key in exoot_keys if not exoot_fouten else (True if s.taxon_key in exoot_keys else None)
    twijfel = None
    if any(v.lijst_code in ("hrl_ii", "hrl_iv_vl", "hrl_iv", "hrl_v") for v in vermeldingen):
        eu, eu_fouten = await ga.hrl_eu_keys()
        twijfel = ga.kruiscontrole_hrl(s.taxon_key, vermeldingen, eu)
        meldingen.extend(eu_fouten)
    kant = (
        "Het Soortenbesluit beschermt alle inheemse vogels, zoogdieren, amfibieën en reptielen (basisbescherming, bijlage 1 cat. 1-3); "
        "een soort die hier niet op een lijst staat, kan dus toch beschermd zijn. Rode-Lijstcategorieën gelden per soortengroep en publicatiejaar (zie `jaar`)."
    )
    if exoot:
        kant += " Deze soort is als uitheems geregistreerd (GRIIS België/Unielijst/INBO-exotenlijst); een beschermingsstatus op een lijst betekent dan niet dat de soort in Vlaanderen beschermd is."
    return SoortStatus(
        geraadpleegd_op=nu_iso(), soort=s, exoot=exoot, vermeldingen=vermeldingen, samenvatting=_samenvatting(vermeldingen),
        koppeling_twijfel=twijfel, melding=" ".join(meldingen) or None, kanttekening=kant,
    )


@mcp.tool()
async def waarnemingen(
    soort: str,
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    straal_m: float | None = None,
    wkt: str | None = None,
    gemeente: str | None = None,
    jaar_van: int | None = None,
    jaar_tot: int | None = None,
    max_resultaten: int = 50,
    offset: int = 0,
    dataset_key: str | None = None,
) -> WaarnemingenRespons:
    """Waarnemingen van één soort in een gebied en periode (GBIF, België), met datum, locatie, dataset en URL.

    Gebied opgeven op één van vier manieren: `adres` (+ `straal_m`, standaard 500 m), `lat`/`lon`
    (+ `straal_m`), `wkt` (POLYGON in WGS84, lon lat) of `gemeente`. Zonder gebied: heel België.
    `totaal` is het aantal dat aan de filters voldoet; `waarnemingen` is een steekproef (max 300).
    Gebruik `per_jaar` en `per_dataset` voor het beeld; `zoek_url` toont dezelfde zoekopdracht op gbif.org.
    Met `dataset_key` worden alleen records van één brondataset getoond: zo klik je door vanuit de
    uitsplitsing per soort van `soorten_in_gebied` (veld `datasets`) naar de onderliggende records.
    `per_verificatiestatus` telt het veld identificationVerificationStatus over de teruggegeven records;
    waarnemingen.be en Florabank vullen dat, eBird, iNaturalist en Pl@ntNet niet ('(leeg)').
    Lees `kanttekening` en neem ze over in het advies.

    Args:
        soort: Nederlandse of wetenschappelijke naam, of GBIF-taxonKey.
        adres: bv. 'Kortrijksesteenweg 100, Gent'.
        straal_m: straal in meter rond adres of lat/lon (standaard 500).
        wkt: bv. 'POLYGON((3.70 51.03,3.75 51.03,3.75 51.07,3.70 51.07,3.70 51.03))'.
        gemeente: naam van een Belgische gemeente (GADM).
        jaar_van: eerste jaar (inclusief). jaar_tot: laatste jaar (inclusief).
        max_resultaten: aantal individuele waarnemingen dat wordt teruggegeven (max 300 per oproep).
        offset: startpositie voor paginering (bv. 300 voor de tweede pagina).
        dataset_key: beperk tot één GBIF-brondataset (UUID uit `per_dataset` of uit het veld `datasets`).
    """
    s = await _resolve(soort)
    if s is None:
        raise ValueError(f"Soort niet gevonden: '{soort}'. Probeer `zoek_soort`.")
    s = await _vul_nl_naam(s)
    waarschuwingen: list[str] = []
    centrum = None
    if any(x is not None for x in (adres, lat, lon, wkt, gemeente)):
        gebied = await bepaal_gebied(adres=adres, lat=lat, lon=lon, straal_m=straal_m, wkt=wkt, gemeente=gemeente)
        geometry, gadm, omschrijving, centrum = gebied.wkt, gebied.gadm_gid, gebied.omschrijving, gebied.centrum
        if gebied.waarschuwing:
            waarschuwingen.append(gebied.waarschuwing)
    else:
        geometry, gadm, omschrijving = None, None, "België (landsfilter)"
    totaal, lijst, per_dataset, per_jaar, url = await gbif.zoek_waarnemingen(
        taxon_key=s.taxon_key, geometry=geometry, gadm_gid=gadm, jaar_van=jaar_van, jaar_tot=jaar_tot, limit=max_resultaten, offset=offset,
        dataset_key=dataset_key,
    )
    for w in lijst:
        w.nederlandse_naam = s.nederlandse_naam
        if centrum and w.lat is not None and w.lon is not None:
            w.afstand_m = round(afstand_m(centrum[0], centrum[1], w.lat, w.lon))
    periode = f"{jaar_van or '…'}–{jaar_tot or '…'}" if (jaar_van or jaar_tot) else None
    return WaarnemingenRespons(
        geraadpleegd_op=nu_iso(), soort=s, gebied=omschrijving, periode=periode, totaal=totaal, teruggegeven=len(lijst), offset=offset,
        records_met_broedindicatie=sum(1 for w in lijst if w.broedindicatie),
        per_verificatiestatus=_tel_verificatie(lijst), waarnemingen=lijst, per_dataset=per_dataset,
        per_jaar=per_jaar, zoek_url=url, waarschuwingen=waarschuwingen, kanttekening=KANTTEKENING_WAARNEMINGEN + " " + KANTTEKENING_HERKOMST,
    )


@mcp.tool()
async def soorten_in_gebied(
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    straal_m: float | None = None,
    wkt: str | None = None,
    gemeente: str | None = None,
    jaar_van: int | None = None,
    jaar_tot: int | None = None,
    filter: str | None = "beschermd,rodelijst",
    alleen_bedreigd: bool = False,
    max_onzekerheid_m: float | None = None,
    alleen_broedindicatie: bool = False,
    per_dataset_per_soort: bool = False,
    detail: bool = False,
    formaat: str = "json",
    max_soorten: int = 200,
    offset: int = 0,
    tijdsbudget_s: float = 40.0,
) -> SoortenInGebiedRespons:
    """Welke soorten zijn in een gebied waargenomen, gekoppeld aan hun beschermings- en Rode-Lijststatus.

    Typische vraag in m.e.r./passende beoordeling: "welke bijlage IV-soorten en Rode-Lijstsoorten zijn
    binnen 750 m van dit perceel gemeld sinds 2020?". Compacte regel per soort (namen, aantal, laatste
    jaar, samenvatting van statussen, exotenvlag, coördinaatonzekerheid, broedindicaties); `detail=True`
    geeft ook de volledige lijstvermeldingen. Categorie-toelichtingen staan één keer in `legende`.
    Gesorteerd van strikt naar minder strikt beschermd (bijlage IV / cat. 3 > bijlage II, VRL bijlage I, RL RE/CR/EN >
    cat. 2, VU, Unielijst > …), daarna op aantal. Voor enkel aantallen: `telling_in_gebied`.

    `filter`: kommagescheiden lijst- of groepscodes (zie `bronnen`). Groepen: kern (bijlage IV Vl.,
    bijlage II, VRL bijlage I, Rode Lijst RE/CR/EN/VU — wat in een natuurtoets telt), beschermd
    (Soortenbesluit, HRL II/IV/V, VRL, Bern, Bonn), europees, rodelijst, invasief, prioritair, provinciaal.
    Leeg = alle soorten (max `max_soorten`). `alleen_bedreigd` beperkt Rode-Lijstsoorten tot RE/CR/EN/VU.
    `max_onzekerheid_m` sluit vervaagde records uit (aantallen worden dan herteld). `alleen_broedindicatie`
    houdt alleen soorten met minstens één record met broed-/voortplantingsaanwijzing.

    `per_dataset_per_soort=True` geeft per soort het veld `datasets`: uit welke brondatasets haar
    waarnemingen komen (dataset_key, dataset, aantal, laatste_jaar), aflopend op aantal; de som is
    gelijk aan `aantal_waarnemingen`. Dat kost geen extra GBIF-oproepen (de records zijn er al). Bij
    `formaat='tabel'` komt er een kolom `datasets` met de compacte notatie 'wnm.be-gewervelden 5 /
    eBird 2'. Doorklikken naar de records kan met `waarnemingen(..., dataset_key=...)`.

    `volledig=False` betekent dat records voor sommige soorten niet binnen `tijdsbudget_s` konden worden
    opgehaald; zie `ontbrekend`. Lees `waarschuwingen` en `kanttekening`.

    Args:
        adres: adres of plaatsnaam (Digitaal Vlaanderen). straal_m: standaard 500 m.
        wkt: POLYGON in WGS84 (lon lat), tegenwijzerzin. gemeente: Vlaamse gemeente (elders: arrondissement).
        filter: bv. 'kern', 'beschermd,rodelijst' (standaard), 'hrl_iv_vl', 'invasief', '' voor alles.
        per_dataset_per_soort: uitsplitsing van de waarnemingen per brondataset, per soort.
        formaat: 'json' (objecten in `soorten`) of 'tabel' (markdown-tabel in `tabel`, ±4x compacter; aanbevolen bij >50 soorten).
        max_soorten / offset: paginering; `totaal_soorten_met_status` zegt hoeveel er in totaal zijn.
    """
    gebied = await bepaal_gebied(adres=adres, lat=lat, lon=lon, straal_m=straal_m, wkt=wkt, gemeente=gemeente)
    kern = bool(filter) and "kern" in [d.strip() for d in filter.split(",")]
    codes = ontleed_codes(filter)
    an = await ga.analyseer(gebied, codes, jaar_van=jaar_van, jaar_tot=jaar_tot, kern=kern, alleen_bedreigd=alleen_bedreigd, max_soorten_zonder_filter=max(max_soorten + offset, 200))
    pagina = an.regels[offset : offset + max_soorten]
    volledig, records = await ga.verrijk_met_records(
        an, pagina, jaar_van=jaar_van, jaar_tot=jaar_tot, budget_s=tijdsbudget_s, max_onzekerheid_m=max_onzekerheid_m,
        per_dataset_per_soort=per_dataset_per_soort,
    )
    if max_onzekerheid_m is not None:
        pagina = [r for r in pagina if r.aantal > 0]
    if alleen_broedindicatie:
        pagina = [r for r in pagina if r.broed]
    for r in pagina:
        if r.soort is None:
            r.soort = await gbif.haal_soort(r.key)
        if not r.soort.nederlandse_naam:
            r.soort = await _vul_nl_naam(r.soort)
    await ga.vul_datasetnamen(an.per_dataset, records)
    if per_dataset_per_soort:
        titels = {d["dataset_key"]: d.get("dataset") for d in an.per_dataset if d.get("dataset")}
        for r in pagina:
            for d in r.datasets or []:
                if not d.get("dataset"):
                    d["dataset"] = titels.get(d["dataset_key"])
    waarschuwingen = an.waarschuwingen + ga.signaleer_vervaging(pagina, gebied.straal_m)
    periode = f"{jaar_van or '…'}–{jaar_tot or '…'}" if (jaar_van or jaar_tot) else None
    return SoortenInGebiedRespons(
        geraadpleegd_op=an.geraadpleegd_op, gebied=gebied.omschrijving, periode=periode, filter=",".join(codes) or None,
        totaal_waarnemingen=an.totaal_waarnemingen, aantal_soorten_in_gebied=an.aantal_soorten, totaal_soorten_met_status=len(an.regels),
        offset=offset, soorten=[] if formaat == "tabel" else [ga.naar_uitvoer(r, detail=detail) for r in pagina],
        tabel=ga.naar_tabel(pagina, met_straal=bool(gebied.centrum), met_datasets=per_dataset_per_soort) if formaat == "tabel" else None,
        rodelijst_dekking=an.rodelijst_dekking, legende=an.legende, lijstversies=an.lijstversies,
        per_dataset=an.per_dataset, gbif_parameters=an.gbif_parameters, zoek_url=an.zoek_url, volledig=volledig and not an.ontbrekend,
        ontbrekend=an.ontbrekend, waarschuwingen=waarschuwingen,
        kanttekening=ga.KANTTEKENING_KORT + (" " + KANTTEKENING_HERKOMST if per_dataset_per_soort else ""),
    )


@mcp.tool()
async def exporteer_bevraging(
    pad: str,
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    straal_m: float | None = None,
    wkt: str | None = None,
    gemeente: str | None = None,
    jaar_van: int | None = None,
    jaar_tot: int | None = None,
    filter: str | None = "beschermd,rodelijst",
    alleen_bedreigd: bool = False,
    met_records: bool = False,
    tijdsbudget_s: float = 60.0,
) -> dict:
    """Schrijf een volledige gebiedsbevraging weg als CSV of JSON (alle soorten, optioneel alle records), met metadata.

    Bestemd voor datarapporten: `pad` eindigt op .csv (soortentabel; met `met_records=True` komt er een tweede
    bestand <pad>_records.csv) of .json (alles in één bestand, incl. metadata: geraadpleegd_op, gebied,
    GBIF-parameters, lijstversies, datasets, legende). Zelfde filters als `soorten_in_gebied`.

    De soortentabel bevat altijd de uitsplitsing per brondataset: in CSV als de kolommen `datasets`
    (compacte notatie 'wnm.be-gewervelden 5 / eBird 2') en `n_datasets`, in JSON als de volledige lijst
    `datasets` per soort. De brondataset zegt iets over de herkomst van de determinatie, niet over de
    validatiestatus van het record.

    Args:
        pad: doelbestand (.csv of .json), absoluut of relatief aan de werkmap van de server.
        met_records: ook alle individuele GBIF-records van de geselecteerde soorten wegschrijven.
    """
    import csv
    import json
    from pathlib import Path

    gebied = await bepaal_gebied(adres=adres, lat=lat, lon=lon, straal_m=straal_m, wkt=wkt, gemeente=gemeente)
    kern = bool(filter) and "kern" in [d.strip() for d in filter.split(",")]
    codes = ontleed_codes(filter)
    an = await ga.analyseer(gebied, codes, jaar_van=jaar_van, jaar_tot=jaar_tot, kern=kern, alleen_bedreigd=alleen_bedreigd)
    regels = an.regels
    volledig, records = await ga.verrijk_met_records(
        an, regels, jaar_van=jaar_van, jaar_tot=jaar_tot, budget_s=tijdsbudget_s, per_dataset_per_soort=True
    )
    for r in regels:
        if r.soort is None:
            r.soort = await gbif.haal_soort(r.key)
    await ga.vul_datasetnamen(an.per_dataset, records)
    titels = {d["dataset_key"]: d.get("dataset") for d in an.per_dataset if d.get("dataset")}
    for r in regels:
        for d in r.datasets or []:
            if not d.get("dataset"):
                d["dataset"] = titels.get(d["dataset_key"])
    meta = {
        "geraadpleegd_op": an.geraadpleegd_op, "gebied": gebied.omschrijving, "periode": f"{jaar_van or ''}-{jaar_tot or ''}",
        "filter": ",".join(codes), "gbif_parameters": an.gbif_parameters, "zoek_url": an.zoek_url, "lijstversies": an.lijstversies,
        "rodelijst_dekking": an.rodelijst_dekking, "per_dataset": an.per_dataset, "legende": an.legende, "volledig": volledig and not an.ontbrekend,
        "ontbrekend": an.ontbrekend, "waarschuwingen": an.waarschuwingen + ga.signaleer_vervaging(regels, gebied.straal_m), "connector": f"gbif-mcp {__version__}",
    }
    soorten = [ga.naar_uitvoer(r, detail=True).model_dump(mode="json") for r in regels]
    doel = Path(pad).expanduser()
    doel.parent.mkdir(parents=True, exist_ok=True)
    geschreven = [str(doel)]
    if doel.suffix.lower() == ".json":
        doel.write_text(json.dumps({"metadata": meta, "soorten": soorten, "records": records if met_records else None}, ensure_ascii=False, indent=1))
    else:
        with doel.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            for k in ("geraadpleegd_op", "gebied", "periode", "filter", "zoek_url", "connector"):
                w.writerow([f"# {k}", meta[k]])
            w.writerow([f"# lijstversies", json.dumps(an.lijstversies, ensure_ascii=False)])
            w.writerow(["taxon_key", "nederlandse_naam", "wetenschappelijke_naam", "aantal_waarnemingen", "laatste_jaar", "status", "exoot",
                        "onzekerheid_max_m", "zeker_binnen_straal", "records_met_broedindicatie", "koppeling_twijfel",
                        "datasets", "n_datasets", "gbif_url"])
            for x in soorten:
                w.writerow([x["taxon_key"], x["nederlandse_naam"] or "", x["wetenschappelijke_naam"], x["aantal_waarnemingen"], x["laatste_jaar"] or "",
                            "; ".join(f"{c} {v}" for c, v in x["samenvatting"].items()), "" if x["exoot"] is None else ("ja" if x["exoot"] else "nee"),
                            x["onzekerheid_max_m"] or "", "" if x["zeker_binnen_straal"] is None else x["zeker_binnen_straal"],
                            "" if x["records_met_broedindicatie"] is None else x["records_met_broedindicatie"], x["koppeling_twijfel"] or "",
                            datasets_compact(x["datasets"]) if x["datasets"] else "", len(x["datasets"] or []),
                            f"https://www.gbif.org/species/{x['taxon_key']}"])
        if met_records:
            rpad = doel.with_name(doel.stem + "_records.csv")
            with rpad.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(gbif.RECORD_VELDEN) + ["gbif_url"], delimiter=";")
                w.writeheader()
                for o in records:
                    w.writerow({**o, "gbif_url": f"https://www.gbif.org/occurrence/{o['key']}"})
            geschreven.append(str(rpad))
    return {"bestanden": geschreven, "aantal_soorten": len(soorten), "aantal_records": len(records) if met_records else None, "metadata": meta}


@mcp.tool()
async def telling_in_gebied(
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    straal_m: float | None = None,
    wkt: str | None = None,
    gemeente: str | None = None,
    jaar_van: int | None = None,
    jaar_tot: int | None = None,
    filter: str | None = "beschermd,rodelijst,invasief",
    soorten_per_dataset: bool = False,
) -> TellingRespons:
    """Hoeveel beschermde, Rode-Lijst- en invasieve soorten zijn in een gebied gemeld — alleen aantallen, snel.

    Zelfde gebiedsparameters als `soorten_in_gebied`. Geeft per lijstcode en per categorie het aantal
    soorten, het aantal kernsoorten (bijlage IV Vl., bijlage II, VRL bijlage I, RL RE/CR/EN/VU), het
    aantal soorten met status dat tegelijk exoot is, en de totalen. Gebruik daarna `soorten_in_gebied`
    (bv. met filter='kern') voor de namen.

    `per_dataset` toont de brondatasets met hun aantal records (komt gratis uit dezelfde facetbevraging).
    Het aantal soorten met status per dataset vergt één extra GBIF-oproep per dataset en staat daarom
    achter `soorten_per_dataset=True` (tien parallelle oproepen voor de tien grootste datasets, in de
    praktijk ±2 s extra); standaard uit, zodat de tool snel blijft.

    Args:
        filter: lijst-/groepscodes (zie `bronnen`); standaard 'beschermd,rodelijst,invasief'.
        soorten_per_dataset: vul ook `aantal_soorten_met_status` per dataset in (trager, zie hierboven).
    """
    gebied = await bepaal_gebied(adres=adres, lat=lat, lon=lon, straal_m=straal_m, wkt=wkt, gemeente=gemeente)
    codes = ontleed_codes(filter)
    an = await ga.analyseer(gebied, codes, jaar_van=jaar_van, jaar_tot=jaar_tot)
    per_lijst, per_cat, kern_n, exoten = ga.telling(an)
    per_dataset = [{"dataset_key": d["dataset_key"], "dataset": d.get("dataset"), "aantal_records": d["aantal"]} for d in an.per_dataset[:25]]
    await ga.vul_datasetnamen(an.per_dataset, [])
    for d, bron in zip(per_dataset, an.per_dataset):
        d["dataset"] = bron.get("dataset")
    if soorten_per_dataset and per_dataset:
        met_status = {r.key for r in an.regels}
        gevonden = await gbif.soortkeys_per_dataset(
            [d["dataset_key"] for d in per_dataset[:10]], geometry=gebied.wkt, gadm_gid=gebied.gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot
        )
        for d in per_dataset:
            keys = gevonden.get(d["dataset_key"])
            if keys is None:
                if d["dataset_key"] in [x["dataset_key"] for x in per_dataset[:10]]:
                    an.ontbrekend.append(f"aantal soorten voor dataset {d['dataset_key']} niet opgehaald")
                continue
            d["aantal_soorten_met_status"] = len(keys & met_status)
    periode = f"{jaar_van or '…'}–{jaar_tot or '…'}" if (jaar_van or jaar_tot) else None
    return TellingRespons(
        geraadpleegd_op=an.geraadpleegd_op, gebied=gebied.omschrijving, periode=periode, totaal_waarnemingen=an.totaal_waarnemingen,
        totaal_soorten=an.aantal_soorten, totaal_soorten_met_status=len(an.regels), per_lijst=per_lijst, per_categorie=per_cat,
        per_dataset=per_dataset, kern=kern_n, exoten=exoten, rodelijst_dekking=an.rodelijst_dekking,
        lijstversies=an.lijstversies, zoek_url=an.zoek_url,
        waarschuwingen=an.waarschuwingen + [f"ontbrekend: {o}" for o in an.ontbrekend],
        kanttekening=ga.KANTTEKENING_KORT + " " + KANTTEKENING_HERKOMST,
    )


@mcp.tool()
async def gebieden_rond(
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    wkt: str | None = None,
    straal_m: float = 1000.0,
    lagen: str | None = None,
    max_treffers_per_laag: int = 5,
) -> GebiedenRespons:
    """Beschermde gebieden en gebiedsstatuten rond een punt of polygoon: Natura 2000 (SBZ-H/SBZ-V, Ramsar),
    VEN/IVON, nationale parken, natuurreservaat-uitbreidingszones, natuurbeheerplannen, natuurrichtplannen,
    Sigma-natuurdoelen, ANB-domeinen, HPG/beschermde graslanden, Duinendecreet, beschermd erfgoed
    (landschap, dorpsgezicht, monument) en BWK (habitat, fauna, 3260).

    Per laag: de gebieden die het punt bevatten of de polygoon overlappen (`overlapt`, afstand 0), anders
    de dichtstbijzijnde binnen `straal_m` met de afstand in meter (Lambert 72). Een laag met status
    `niet_geraadpleegd` gaf een fout: dat is geen 'geen gebied'. Bronnen: WFS Departement Omgeving
    (Mercator) en Digitaal Vlaanderen (BWK); alleen Vlaanderen.

    Args:
        adres: adres of plaatsnaam (Digitaal Vlaanderen); of lat/lon (WGS84); of wkt (POLYGON, WGS84 lon lat).
        straal_m: zoekstraal (standaard 1000 m).
        lagen: kommagescheiden laag- of groepscodes: natura2000, natuur, beheer, erfgoed, bwk, of losse codes
            (hrl_gebied, vrl_gebied, ven_ivon, natuurbeheerplan, hpg, bwk_habitat, …). Leeg = alle lagen.
        max_treffers_per_laag: hoeveel treffers per laag worden teruggegeven (gesorteerd: overlap eerst, dan afstand).
    """
    waarschuwingen: list[str] = []
    omschrijving_extra = ""
    if adres and lat is None and wkt is None:
        loc = await geocodeer(adres)
        if loc is None:
            raise ValueError(f"Adres niet gevonden: '{adres}'.")
        lat, lon = loc.lat, loc.lon
        omschrijving_extra = f" — {loc.adres or adres}"
        if loc.waarschuwing:
            waarschuwingen.append(loc.waarschuwing)
    doel, omschrijving = gebieden.doelgeometrie(lat=lat, lon=lon, wkt=wkt)
    keuze = gebieden.ontleed_lagen(lagen)
    uit = await gebieden.gebieden_rond(doel, keuze, straal_m, max_treffers_per_laag)
    samenvatting: dict[str, str] = {}
    for l in uit:
        if l.treffers:
            t = l.treffers[0]
            naam = t.naam or t.code or "(zonder naam)"
            samenvatting[l.laag] = f"in {naam}" if t.overlapt else f"dichtstbij {naam} op {t.afstand_m} m"
            if l.aantal_overlappend > 1:
                samenvatting[l.laag] += f" (+{l.aantal_overlappend - 1} andere overlappend)"
    return GebiedenRespons(
        geraadpleegd_op=nu_iso(), doel=omschrijving + omschrijving_extra, straal_m=straal_m, lagen=uit, samenvatting=samenvatting,
        niet_geraadpleegd=[l.laag for l in uit if l.status != "ok"], waarschuwingen=waarschuwingen,
        kanttekening="Afstanden zijn tot de gebiedsgrens zoals gepubliceerd in de WFS-laag (Lambert 72). Erkende natuurreservaten (kernzones) en "
        "bosreservaten zitten niet in deze diensten; BWK-habitatcodes zijn karteringseenheden, geen juridisch statuut. Verifieer voor een dossier op Geopunt.",
    )


@mcp.tool()
async def kaart_gebieden(
    pad: str,
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    wkt: str | None = None,
    straal_m: float = 1000.0,
    lagen: str | None = "natura2000,natuur,beheer",
    breedte_px: int = 1500,
    met_legende: bool = True,
    per_groep: bool = False,
) -> dict:
    """Situeringskaart: de projectlocatie met de beschermde gebieden eromheen.

    Tekent de gebieden uit `gebieden_rond` op de GRB-basiskaart van Digitaal Vlaanderen, in
    Lambert 72, met legende, schaalbalk, noordpijl en de zoekcirkel. Bedoeld als situeringsfiguur
    in een datarapport of nota. Alleen Vlaanderen.

    Geeft het bestandspad terug plus de legende (per laag: kleur, aantal getekende vlakken,
    status). Een laag met status `niet_geraadpleegd` gaf een fout: daaruit volgt niet dat er geen
    gebied ligt. Lagen zonder vlak binnen de straal komen niet in de legende.

    Args:
        pad: doelbestand; `.png` of `.jpg`. Voor een rapport met meerdere kaarten is `.jpg` aan te
            raden: de GRB-ondergrond is rasterbeeld, waardoor JPEG tot tienmaal kleiner uitvalt.
        adres: adres of plaatsnaam; of `lat`/`lon` (WGS84); of `wkt` (POLYGON in WGS84, lon lat).
        straal_m: zoekstraal én maat voor de kaartuitsnede (de kaart toont ±25 % meer).
        lagen: laag- of groepscodes zoals bij `gebieden_rond`; standaard natura2000, natuur en beheer.
            Voeg 'erfgoed' of 'bwk' toe voor beschermd erfgoed of de Biologische Waarderingskaart.
        breedte_px: beeldbreedte in pixels (600 tot 2400).
        met_legende: legende onder de kaart inbakken. Zet op False wanneer de kaart verkleind in een
            document komt: gebruik dan het veld `legende` uit de respons om ze in het document zelf
            op te maken, anders is de ingebakken tekst onleesbaar.
        per_groep: één kaart per thema in plaats van alles op elkaar. Aan te raden zodra de
            Biologische Waarderingskaart meedoet: die dekt het hele beeld en maakt de
            beschermingsgebieden onleesbaar. De bestandsnamen krijgen de groep als achtervoegsel
            (bv. situering-bwk.jpg) en de respons bevat dan een lijst `kaarten`.
    """
    from pathlib import Path

    waarschuwingen: list[str] = []
    omschrijving = ""
    if adres and lat is None and wkt is None:
        loc = await geocodeer(adres)
        if loc is None:
            raise ValueError(f"Adres niet gevonden: '{adres}'.")
        lat, lon = loc.lat, loc.lon
        omschrijving = loc.adres or adres
        if loc.waarschuwing:
            waarschuwingen.append(loc.waarschuwing)
    doel, doel_omschrijving = gebieden.doelgeometrie(lat=lat, lon=lon, wkt=wkt)
    keuze = gebieden.ontleed_lagen(lagen)
    doelpad = Path(pad).expanduser()
    doelpad.parent.mkdir(parents=True, exist_ok=True)

    async def _een(lagenkeuze, bestand: Path) -> dict:
        m = await kaartmodule.teken(doel, lagenkeuze, straal_m=straal_m, pad=str(bestand), breedte_px=breedte_px, met_legende=met_legende)
        m["doel"] = doel_omschrijving + (f" — {omschrijving}" if omschrijving else "")
        m["straal_m"] = straal_m
        return m

    if per_groep:
        # Per thema één kaart: de groepen in de volgorde waarin ze gevraagd zijn.
        gevraagd = [g for g in gebieden.GROEPEN if any(l.groep == g for l in keuze)]
        kaarten = []
        for groep in gevraagd:
            deel = [l for l in keuze if l.groep == groep]
            bestand = doelpad.with_name(f"{doelpad.stem}-{groep}{doelpad.suffix}")
            k = await _een(deel, bestand)
            k["groep"] = groep
            kaarten.append(k)
        return {
            "kaarten": kaarten, "groepen": gevraagd, "doel": doel_omschrijving + (f" — {omschrijving}" if omschrijving else ""),
            "straal_m": straal_m, "geraadpleegd_op": nu_iso(), "waarschuwingen": waarschuwingen,
            "kanttekening": "Eén kaart per thema. De kaarten hebben dezelfde uitsnede en schaal en zijn dus over "
            "elkaar te leggen. " + KANTTEKENING_KAART,
        }

    meta = await _een(keuze, doelpad)
    meta["waarschuwingen"] = waarschuwingen
    meta["kanttekening"] = KANTTEKENING_KAART
    return meta


def _standaardpad(label: str) -> str:
    """~/Documents/datarapport-natuur-<label>-<datum>.pdf (map wordt aangemaakt indien nodig)."""
    import re
    from datetime import date
    from pathlib import Path

    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "locatie"
    map_ = Path.home() / "Documents"
    map_.mkdir(parents=True, exist_ok=True)
    return str(map_ / f"datarapport-natuur-{slug}-{date.today().isoformat()}.pdf")


@mcp.tool()
async def datarapport_natuur(
    adres: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    pad: str | None = None,
    straal_soorten_m: float = 500.0,
    straal_gebieden_m: float = 1000.0,
    jaar_van: int | None = 2020,
    jaar_tot: int | None = None,
    kaarten: bool = True,
    bwk_kaart: bool = True,
    detail_soorten: int = 3,
    bewaar_kaarten: bool = True,
) -> dict:
    """Maak in één stap het vaste DATARAPPORT NATUUR als PDF voor een projectlocatie.

    Gebruik deze tool wanneer de gebruiker om een datarapport, natuurrapport, bronnenscan of
    "rapport zoals het vorige" vraagt. Het sjabloon ligt vast, zodat elk rapport dezelfde opbouw
    heeft: titelblad met coördinaten en beide zoekstralen, samenvatting, situering met kaart(en),
    statussen in cijfers, kernsoorten met hun herkomst per brondataset, beschermde gebieden en
    gebiedsstatuten met afstand, de onderliggende waarnemingen van de striktst beschermde soorten,
    verantwoording van de bronnen (lijstversies, GBIF-zoekopdracht) en beperkingen.

    Soorten en gebieden hebben elk een eigen zoekstraal; dat is een bewuste keuze die afhangt van
    het project en het type natuur. Het rapport noemt beide stralen overal expliciet.

    De kaarten zijn leesbaar zonder kleuronderscheid (nummers en arceringen). Met `bwk_kaart` komt
    er een tweede kaart met de habitattypes van de Biologische Waarderingskaart.

    Na afloop: vat voor de gebruiker kort samen wat het rapport vond (aantal kernsoorten, de
    striktst beschermde soorten, gebieden waarin of nabij de locatie ligt, waarschuwingen letterlijk)
    en geef het pad. Voeg niets toe dat niet uit de respons komt. Spreek van strikt of striktst
    beschermd, nooit van zwaar of zwaarst beschermd.

    Args:
        adres: adres in Vlaanderen (bij voorkeur met huisnummer); of `lat`/`lon` in WGS84.
        pad: doelbestand (.pdf). Zonder pad: Documenten/datarapport-natuur-<locatie>-<datum>.pdf.
        straal_soorten_m: zoekstraal voor soortwaarnemingen (standaard 500 m).
        straal_gebieden_m: zoekstraal voor gebiedsstatuten en kaarten (standaard 1000 m).
        jaar_van / jaar_tot: periode van de waarnemingen (standaard vanaf 2020).
        kaarten: situeringskaart met de beschermde gebieden opnemen.
        bwk_kaart: tweede kaart met de Biologische Waarderingskaart opnemen.
        detail_soorten: van hoeveel striktst beschermde soorten de individuele records worden getoond.
        bewaar_kaarten: de kaartafbeeldingen naast de PDF bewaren (handig om in een nota te gebruiken).
    """
    from pathlib import Path

    from .gebieden import _naar_l72
    from .rapport import schrijf_pdf

    waarschuwingen: list[str] = []
    if adres and (lat is None or lon is None):
        loc = await geocodeer(adres)
        if loc is None:
            raise ValueError(f"Adres niet gevonden: '{adres}'. Geef een adres in Vlaanderen of lat/lon.")
        lat, lon = loc.lat, loc.lon
        locatie = loc.model_dump(mode="json")
        if loc.waarschuwing:
            waarschuwingen.append(loc.waarschuwing)
        label = loc.adres or adres
    elif lat is not None and lon is not None:
        x, y = _naar_l72.transform(lon, lat)
        locatie = {"invoer": f"{lat}, {lon}", "adres": f"{lat:.5f} N, {lon:.5f} O", "gemeente": "—", "postcode": None,
                   "lat": lat, "lon": lon, "x_lambert72": x, "y_lambert72": y, "type": "opgegeven coördinaten",
                   "bron": "coördinaten opgegeven door de gebruiker"}
        label = f"{lat:.4f}-{lon:.4f}"
    else:
        raise ValueError("Geef een `adres` of `lat` en `lon`.")

    doelpad = Path(pad).expanduser() if pad else Path(_standaardpad(label))
    if doelpad.suffix.lower() != ".pdf":
        doelpad = doelpad.with_suffix(".pdf")
    doelpad.parent.mkdir(parents=True, exist_ok=True)

    # Eén keer geocoderen; alle bevragingen gebruiken daarna dezelfde coördinaten.
    async def _kaart(lagen: str, achtervoegsel: str, titel: str):
        k = await kaart_gebieden(str(doelpad.with_name(f"{doelpad.stem}-{achtervoegsel}.jpg")), lat=lat, lon=lon,
                                 straal_m=straal_gebieden_m, lagen=lagen, breedte_px=1600, met_legende=False)
        k["titel"] = titel
        return k

    taken = [
        telling_in_gebied(lat=lat, lon=lon, straal_m=straal_soorten_m, jaar_van=jaar_van, jaar_tot=jaar_tot, soorten_per_dataset=True),
        soorten_in_gebied(lat=lat, lon=lon, straal_m=straal_soorten_m, jaar_van=jaar_van, jaar_tot=jaar_tot, filter="kern",
                          per_dataset_per_soort=True, max_soorten=150),
        gebieden_rond(lat=lat, lon=lon, straal_m=straal_gebieden_m),
    ]
    if kaarten:
        taken.append(_kaart("natura2000,natuur,beheer", "kaart-gebieden", "Beschermde gebieden en gebiedsstatuten"))
    if kaarten and bwk_kaart:
        taken.append(_kaart("bwk", "kaart-bwk", "Biologische Waarderingskaart: habitattypes en karteringseenheden"))
    resultaten = await asyncio.gather(*taken)
    telling, kern, geb = resultaten[0], resultaten[1], resultaten[2]
    kaartlijst = list(resultaten[3:])

    detail = []
    for sp in kern.soorten[: max(0, detail_soorten)]:
        ds = sp.datasets[0]["dataset_key"] if sp.datasets else None
        w = await waarnemingen(str(sp.taxon_key), lat=lat, lon=lon, straal_m=straal_soorten_m, jaar_van=jaar_van,
                               jaar_tot=jaar_tot, max_resultaten=8, dataset_key=ds)
        detail.append({"soort": sp.model_dump(mode="json"), "dataset_key": ds, "waarnemingen": w.model_dump(mode="json")})

    kern_d = kern.model_dump(mode="json")
    kern_d["waarschuwingen"] = waarschuwingen + kern_d.get("waarschuwingen", [])
    data = {
        "locatie": locatie, "telling": telling.model_dump(mode="json"), "kern": kern_d, "gebieden": geb.model_dump(mode="json"),
        "kaarten": kaartlijst, "detail": detail, "straal_m": straal_soorten_m, "jaar_van": jaar_van or "begin van de registratie",
        "connector": f"gbif-mcp {__version__}",
    }
    uit = await asyncio.to_thread(schrijf_pdf, data, str(doelpad))
    if not bewaar_kaarten:
        for k in kaartlijst:
            Path(k["pad"]).unlink(missing_ok=True)

    striktst = [s for s in kern.soorten if "hrl_iv_vl" in s.samenvatting]
    return {
        "pad": uit["pad"],
        "paginas": uit["paginas"],
        "kaarten": [k["pad"] for k in kaartlijst] if bewaar_kaarten else [],
        "locatie": locatie.get("adres"),
        "straal_soorten_m": straal_soorten_m,
        "straal_gebieden_m": straal_gebieden_m,
        "periode": f"{jaar_van or '…'}–{jaar_tot or 'heden'}",
        "samenvatting": {
            "waarnemingen": telling.totaal_waarnemingen,
            "soorten": telling.totaal_soorten,
            "soorten_met_status": telling.totaal_soorten_met_status,
            "kernsoorten": telling.kern,
            "bijlage_iv_soorten": [s.nederlandse_naam or s.wetenschappelijke_naam for s in striktst],
            "gebieden": geb.samenvatting,
            "niet_geraadpleegde_lagen": geb.niet_geraadpleegd,
        },
        "volledig": kern.volledig,
        "waarschuwingen": kern_d["waarschuwingen"],
        "geraadpleegd_op": kern.geraadpleegd_op,
        "disclaimer": DISCLAIMER,
        "privacy": PRIVACY,
    }


@mcp.prompt(
    name="datarapport_natuur",
    title="Datarapport natuur",
    description="Vast rapportsjabloon: beschermde soorten, gebiedsstatuten en kaarten rond een projectlocatie, als PDF.",
)
def prompt_datarapport_natuur(
    adres: str,
    straal_soorten_m: str = "500",
    straal_gebieden_m: str = "1000",
    vanaf_jaar: str = "2020",
) -> str:
    """Het standaardverzoek voor een datarapport natuur, klaar om te versturen."""
    return (
        f"Maak een datarapport natuur voor de projectlocatie {adres}. Gebruik de tool datarapport_natuur met "
        f"een zoekstraal van {straal_soorten_m} m voor soorten en {straal_gebieden_m} m voor gebiedsstatuten, "
        f"waarnemingen vanaf {vanaf_jaar}, met de situeringskaart en de kaart van de Biologische Waarderingskaart.\n\n"
        "Geef daarna een korte samenvatting in lopende tekst:\n"
        "- hoeveel kernsoorten er zijn, en welke daarvan strikt beschermd zijn (bijlage IV van de Habitatrichtlijn);\n"
        "- in of nabij welke beschermde gebieden de locatie ligt, met de afstand;\n"
        "- de waarschuwingen uit de respons, letterlijk;\n"
        "- waar de PDF en de kaarten staan.\n\n"
        "Vermeld dat het om een betaversie gaat, zonder garantie op de resultaten, en dat de gebruiker zelf "
        "verantwoordelijk blijft voor het gebruik ervan.\n\n"
        "Noem beide zoekstralen expliciet. Spreek van strikt of striktst beschermd, nooit van zwaar of zwaarst. "
        "Vermeld alleen wat de tool teruggeeft en markeer wat ontbreekt als lacune."
    )


@mcp.tool()
async def lijst(code: str, zoek: str | None = None, categorie: str | None = None, max_resultaten: int = 200) -> LijstRespons:
    """Inhoud van één gezaghebbende soortenlijst (Soortenbesluit, HRL-bijlagen, Rode Lijst, Unielijst …).

    Args:
        code: lijstcode uit `bronnen` (bv. 'soortenbesluit', 'hrl_iv', 'rodelijst_vl', 'unielijst').
        zoek: optionele tekstfilter op naam, Nederlandse naam of taxongroep (hoofdletterongevoelig).
        categorie: optionele filter op categorie (bv. 'cat3', 'EN', 'Amfibieen').
        max_resultaten: bovengrens.
    """
    if code not in PER_CODE:
        raise ValueError(f"Onbekende lijstcode '{code}'. Geldig: {', '.join(PER_CODE)}")
    l = PER_CODE[code]
    items = await inbo.lijst_items(l)
    uit: list[LijstItem] = []
    z = (zoek or "").lower()
    c = (categorie or "").lower()
    for it in items:
        if not str(it.get("lsid", "")).isdigit():
            continue
        v = inbo.vermelding_uit_item(l, it)
        s = inbo.soort_uit_item(it)
        if z and z not in " ".join([s.wetenschappelijke_naam, s.nederlandse_naam or "", " ".join(v.extra.values())]).lower():
            continue
        if c and c not in " ".join(filter(None, [v.categorie, v.toelichting, " ".join(v.extra.values())])).lower():
            continue
        uit.append(LijstItem(soort=s, vermelding=v))
    melding = None
    if len(uit) > max_resultaten:
        melding = f"Afgekapt op {max_resultaten}; verfijn met `zoek` of `categorie`."
    elif not uit and (z or c):
        groepen = sorted({inbo._kvp(it).get("taxonomische_groep") or inbo._kvp(it).get("taxongroep") or inbo._kvp(it).get("Species group") or "" for it in items} - {""})
        melding = "Geen treffer. Mogelijk zit de soortengroep niet in deze lijst" + (f"; aanwezige groepen: {', '.join(groepen[:40])}." if groepen else ".")
    return LijstRespons(
        lijst_code=code, lijst_naam=l.naam, url=l.url, totaal=len(uit), teruggegeven=min(len(uit), max_resultaten), items=uit[:max_resultaten], melding=melding,
    )


@mcp.tool()
async def geocodeer_adres(adres: str) -> Locatie:
    """Adres of plaatsnaam in Vlaanderen/Brussel -> WGS84-coördinaten en gemeente (Digitaal Vlaanderen, geolocation v4).

    Args:
        adres: bv. 'Kortrijksesteenweg 100, 9000 Gent' of 'Bourgoyen, Gent'.
    """
    loc = await geocodeer(adres)
    if loc is None:
        raise ValueError(f"Niet gevonden: '{adres}'.")
    return loc


@mcp.tool()
async def dataset_info(dataset_key: str) -> DatasetInfo:
    """Herkomst, uitgever, licentie, DOI en citatie van een GBIF-dataset (uit `per_dataset` of een waarneming).

    Args:
        dataset_key: GBIF-dataset-UUID.
    """
    return await gbif.dataset_info(dataset_key)


@mcp.tool()
def bronnen() -> list[Bron]:
    """Overzicht van alle geraadpleegde bronnen en de lijst-/groepscodes voor `soorten_in_gebied` en `lijst`."""
    uit = [
        Bron(code="disclaimer", naam="Betaversie — geen garantie", type="disclaimer", url="https://github.com/jefseghers-del/gbif-mcp",
             toelichting=DISCLAIMER + " " + PRIVACY),
        Bron(code="gbif_occurrence", naam="GBIF occurrence API (api.gbif.org), landsfilter België", type="gbif_occurrence",
             url="https://www.gbif.org/occurrence/search?country=BE", toelichting="Zelfde data als gbif.biodiversity.be (hosted portal van Belspo/BBPF)."),
        Bron(code="geocoder", naam="Digitaal Vlaanderen geolocation v4", type="geocoder", url="https://geo.api.vlaanderen.be/geolocation/v4/Location"),
        Bron(code="inbo_portaal", naam="Vlaams Biodiversiteitsportaal (INBO)", type="inbo_lijst", url="https://natuurdata.inbo.be",
             toelichting="Naamzoeken (Nederlandse namen) en gezaghebbende lijsten hieronder."),
    ]
    for l in LIJSTEN:
        uit.append(Bron(code=l.code, naam=l.naam, type="inbo_lijst", url=l.url, toelichting=(l.toelichting or None) and f"[{l.groep}] {l.toelichting}"))
    for code, (ds, naam) in GBIF_CHECKLISTS.items():
        uit.append(Bron(code=code, naam=naam, type="gbif_checklist", url=f"https://www.gbif.org/dataset/{ds}"))
    for g, codes in GROEPEN.items():
        uit.append(Bron(code=g, naam=f"groep: {', '.join(codes)}", type="groep", url="", toelichting="Bruikbaar als `filter` in soorten_in_gebied."))
    return uit


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
