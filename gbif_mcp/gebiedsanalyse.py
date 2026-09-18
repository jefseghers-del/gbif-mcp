# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Gedeelde engine voor `soorten_in_gebied` en `telling_in_gebied`.

Stappen:
  1. één GBIF-facetbevraging per gebied/periode (soorten + aantallen + datasets), gecachet;
  2. INBO-lijsten (schijfgecachet) parallel laden en per soort de vermeldingen koppelen;
  3. filteren (lijstcodes, kern, alleen_bedreigd), sorteren op juridische relevantie, pagineren;
  4. optioneel: de records van de overblijvende soorten in één keer ophalen (meerdere taxa per
     oproep) voor laatste jaar, coördinaatonzekerheid en broedindicaties — binnen een tijdsbudget;
     wat niet lukt, wordt als `ontbrekend` gemeld, nooit stilzwijgend weggelaten.
"""
from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass, field
from typing import Any

from . import gbif, inbo
from .datasets import compact as datasets_compact
from .geo import Gebied, afstand_m
from .http import nu_iso
from .lijsten import HRL_EU_CHECKLISTS, PER_CODE, RODELIJST_BEDREIGD, combineer_categorieen, is_kern, relevantie
from .schema import LijstVermelding, Soort, SoortInGebied

KANTTEKENING_KORT = (
    "GBIF-waarnemingen zijn opportunistische meldingen, geen inventarisatie: geen waarneming ≠ afwezig. "
    "Gevoelige soorten zijn vaak vervaagd (zie onzekerheid_*). Lijstkoppeling op GBIF-taxonsleutel. "
    "Volledige toelichting: tool `bronnen`."
)

EXOOT_CODES = ("unielijst", "invasief_uitgebreid")


@dataclass
class SoortRegel:
    key: int
    aantal: int
    soort: Soort | None = None
    vermeldingen: list[LijstVermelding] = field(default_factory=list)
    laatste_jaar: int | None = None
    onz_max: float | None = None
    onz_med: float | None = None
    zeker: int | None = None
    broed: int | None = None
    exoot: bool | None = None
    twijfel: str | None = None
    datasets: list[dict] | None = None  # alleen gevuld bij per_dataset_per_soort=True

    @property
    def score(self) -> int:
        return max((relevantie(v.lijst_code, v.categorie) for v in self.vermeldingen), default=0)


def samenvatting(vermeldingen: list[LijstVermelding]) -> dict[str, str]:
    per: dict[str, list[str]] = {}
    for v in vermeldingen:
        per.setdefault(v.lijst_code, []).append(v.categorie or "vermeld")
    return {code: combineer_categorieen(code, cats) for code, cats in per.items()}


def datasets_per_soort(records: list[dict[str, Any]], namen: dict[str, str] | None = None) -> list[dict]:
    """Records van ÉÉN soort -> uitsplitsing per brondataset, aflopend op aantal.

    Geeft [{dataset_key, dataset, aantal, laatste_jaar}, …]. De som van `aantal` is per definitie
    gelijk aan het aantal records dat binnenkomt (records zonder datasetKey krijgen sleutel '?').
    Puur rekenwerk, geen netwerk; `namen` vult desgewenst titels aan die niet in de records staan."""
    per: dict[str, dict] = {}
    for o in records:
        k = o.get("datasetKey") or "?"
        d = per.setdefault(k, {"dataset_key": k, "dataset": None, "aantal": 0, "laatste_jaar": None})
        d["aantal"] += 1
        if not d["dataset"] and o.get("datasetName"):
            d["dataset"] = o["datasetName"]
        jaar = o.get("year")
        if jaar and (d["laatste_jaar"] is None or jaar > d["laatste_jaar"]):
            d["laatste_jaar"] = jaar
    if namen:
        for d in per.values():
            if not d["dataset"]:
                d["dataset"] = namen.get(d["dataset_key"])
    return sorted(per.values(), key=lambda d: (-d["aantal"], d["dataset_key"]))


async def hrl_eu_keys() -> tuple[dict[str, set[int]], list[str]]:
    """Per HRL-lijstcode de backbone-sleutels van de EU-brede bijlagechecklist (kruiscontrole)."""
    uit: dict[str, set[int]] = {}
    fouten: list[str] = []
    for code, ds in HRL_EU_CHECKLISTS.items():
        try:
            uit[code] = await gbif.checklist_keys(ds)
        except Exception as e:
            fouten.append(f"EU-checklist {code} ({type(e).__name__})")
    return uit, fouten


def kruiscontrole_hrl(key: int, vermeldingen: list[LijstVermelding], eu: dict[str, set[int]]) -> str | None:
    """Wijkt een HRL-vermelding van het portaal af van de EU-checklist? Geeft de reden, anders None."""
    redenen: list[str] = []
    for v in vermeldingen:
        keys = eu.get(v.lijst_code)
        if keys is not None and key not in keys:
            reden = f"portaal zegt {v.lijst_code} ({v.categorie}), maar de soort staat niet in de EU-checklist van die bijlage"
            if reden not in redenen:
                redenen.append(reden)
    return "; ".join(redenen) or None


async def _exoot_keys() -> tuple[set[int], list[str]]:
    """Sleutels van uitheemse soorten (Unielijst, INBO-exotenlijst, GRIIS België). Geeft ook welke bronnen faalden."""
    keys: set[int] = set()
    fouten: list[str] = []
    for code in EXOOT_CODES:
        try:
            keys.update((await inbo.lijst_index(PER_CODE[code])).keys())
        except Exception as e:
            fouten.append(f"{code} ({type(e).__name__})")
    try:
        keys.update(await gbif.griis_belgie_keys())
    except Exception as e:
        fouten.append(f"gbif_griis_be ({type(e).__name__})")
    return keys, fouten


@dataclass
class Analyse:
    geraadpleegd_op: str
    gebied: Gebied
    codes: list[str]
    totaal_waarnemingen: int
    aantal_soorten: int
    regels: list[SoortRegel]  # gefilterd en gesorteerd (alle, vóór paginering)
    per_dataset: list[dict]
    gbif_parameters: dict
    zoek_url: str
    lijstversies: dict[str, str | None]
    legende: dict[str, dict[str, str]]
    waarschuwingen: list[str]
    ontbrekend: list[str]
    exoot_keys: set[int]
    rodelijst_dekking: dict[str, str] = field(default_factory=dict)
    licentiefilter: str = ""
    licenties: dict[str, int] = field(default_factory=dict)
    uitgesloten_niet_commercieel: int = 0


async def analyseer(
    gebied: Gebied, codes: list[str], *, jaar_van: int | None, jaar_tot: int | None,
    kern: bool = False, kern_met_nt: bool = False, alleen_bedreigd: bool = False, max_soorten_zonder_filter: int = 200,
) -> Analyse:
    """Stappen 1-3: facet, lijstkoppeling, filteren en sorteren."""
    geraadpleegd = nu_iso()
    waarschuwingen: list[str] = []
    ontbrekend: list[str] = []
    if gebied.waarschuwing:
        waarschuwingen.append(gebied.waarschuwing)

    (totaal, tellingen, per_dataset, params, url), licenties = await asyncio.gather(
        gbif.soorten_facet(
            geometry=gebied.wkt, gadm_gid=gebied.gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot,
            max_soorten=5000 if codes else max_soorten_zonder_filter,
        ),
        gbif.licentieverdeling(geometry=gebied.wkt, gadm_gid=gebied.gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot),
    )
    filter_actief = "license" in params
    toegelaten = set(params.get("license") or [])
    uitgesloten = sum(n for lic, n in licenties.items() if filter_actief and lic not in toegelaten)
    if uitgesloten:
        waarschuwingen.append(
            f"{uitgesloten} records onder een niet-commerciële of onbekende licentie zijn weggelaten "
            "(standaardinstelling). Zet ook_niet_commercieel=True om ze mee te nemen, als het gebruik dat toelaat."
        )

    # Lijsten parallel laden; een lijst die faalt wordt gemeld, niet verzwegen.
    async def _laad(code: str):
        try:
            return code, await inbo.lijst_index(PER_CODE[code])
        except Exception as e:
            return code, e

    geladen = await asyncio.gather(*(_laad(c) for c in codes))
    indexen: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for code, idx in geladen:
        if isinstance(idx, Exception):
            ontbrekend.append(f"lijst {code} niet geladen ({type(idx).__name__})")
        else:
            indexen[code] = idx
    exoot_keys, exoot_fouten = await _exoot_keys()
    ontbrekend.extend(f"exotenbron {f}" for f in exoot_fouten)
    eu_keys: dict[str, set[int]] = {}
    if any(c in HRL_EU_CHECKLISTS for c in indexen):
        eu_keys, eu_fouten = await hrl_eu_keys()
        ontbrekend.extend(eu_fouten)

    legende: dict[str, dict[str, str]] = {}
    regels: list[SoortRegel] = []
    for key, n in tellingen:
        r = SoortRegel(key=key, aantal=n)
        for code, idx in indexen.items():
            for item in idx.get(key, []):
                v = inbo.vermelding_uit_item(PER_CODE[code], item)
                r.vermeldingen.append(v)
                r.soort = r.soort or inbo.soort_uit_item(item)
                if v.categorie and v.toelichting:
                    legende.setdefault(code, {}).setdefault(v.categorie, v.toelichting)
        if codes and not r.vermeldingen:
            continue
        if kern:
            r.vermeldingen = [v for v in r.vermeldingen if is_kern(v.lijst_code, v.categorie, met_nt=kern_met_nt)]
            if not r.vermeldingen:
                continue
        if alleen_bedreigd:
            rl = [v for v in r.vermeldingen if v.lijst_code.startswith("rodelijst") and (v.categorie or "").upper() in RODELIJST_BEDREIGD]
            niet_rl = [v for v in r.vermeldingen if not v.lijst_code.startswith("rodelijst")]
            if not rl and not niet_rl:
                continue
            r.vermeldingen = rl + niet_rl
        r.exoot = key in exoot_keys if not exoot_fouten else (True if key in exoot_keys else None)
        r.twijfel = kruiscontrole_hrl(key, r.vermeldingen, eu_keys) if eu_keys else None
        regels.append(r)
    regels.sort(key=lambda r: (-r.score, -r.aantal))

    lijstversies = {code: inbo.lijstversie(PER_CODE[code]) for code in indexen}
    rl_dekking = {}
    for code in indexen:
        if code.startswith("rodelijst"):
            rl_dekking[code] = inbo.dekking([it for items in indexen[code].values() for it in items])
    return Analyse(rodelijst_dekking=rl_dekking, licentiefilter=gbif.licentiefilter_omschrijving(),
        licenties={gbif.licentie_kort(k): v for k, v in licenties.items()}, uitgesloten_niet_commercieel=uitgesloten,
        geraadpleegd_op=geraadpleegd, gebied=gebied, codes=codes, totaal_waarnemingen=totaal, aantal_soorten=len(tellingen),
        regels=regels, per_dataset=per_dataset, gbif_parameters=params, zoek_url=url, lijstversies=lijstversies,
        legende=legende, waarschuwingen=waarschuwingen, ontbrekend=ontbrekend, exoot_keys=exoot_keys,
    )


async def vul_licenties(per_dataset: list[dict], max_opzoeken: int = 15) -> None:
    """Licentie per dataset (voor naamsvermelding bij CC BY en controle op CC BY-NC); dataset_info is gecachet."""
    async def _een(d: dict) -> None:
        try:
            info = await gbif.dataset_info(d["dataset_key"])
            d["licentie"] = info.licentie
            d.setdefault("dataset", info.titel)
        except Exception:
            d["licentie"] = "onbekend"

    await asyncio.gather(*(_een(d) for d in per_dataset[:max_opzoeken] if "licentie" not in d))


async def vul_datasetnamen(per_dataset: list[dict], records: list[dict[str, Any]], max_opzoeken: int = 8) -> None:
    namen = {o.get("datasetKey"): o.get("datasetName") for o in records if o.get("datasetName")}
    opzoeken = []
    for d in per_dataset:
        if d["dataset_key"] in namen:
            d["dataset"] = namen[d["dataset_key"]]
        elif len(opzoeken) < max_opzoeken:
            opzoeken.append(d)
    if opzoeken:
        async def _naam(d: dict) -> None:
            try:
                d["dataset"] = (await gbif.dataset_info(d["dataset_key"])).titel
            except Exception:
                pass
        await asyncio.gather(*(_naam(d) for d in opzoeken))


async def verrijk_met_records(
    an: Analyse, regels: list[SoortRegel], *, jaar_van: int | None, jaar_tot: int | None, budget_s: float,
    max_onzekerheid_m: float | None = None, per_dataset_per_soort: bool = False,
) -> tuple[bool, list[dict[str, Any]]]:
    """Stap 4: records ophalen en per soort laatste jaar, onzekerheid, zekerheid binnen straal en broedindicatie afleiden."""
    keys = [r.key for r in regels]
    if not keys:
        return True, []
    records, volledig, zonder = await gbif.records_in_gebied(
        keys, geometry=an.gebied.wkt, gadm_gid=an.gebied.gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot, budget_s=budget_s,
    )
    per_soort: dict[int, list[dict[str, Any]]] = {}
    for o in records:
        k = o.get("speciesKey") or o.get("taxonKey")
        if k:
            per_soort.setdefault(int(k), []).append(o)
    centrum, straal = an.gebied.centrum, an.gebied.straal_m
    for r in regels:
        recs = per_soort.get(r.key, [])
        if max_onzekerheid_m is not None:
            recs = [o for o in recs if o.get("coordinateUncertaintyInMeters") is None or o["coordinateUncertaintyInMeters"] <= max_onzekerheid_m]
        if not recs:
            if r.key in zonder:
                continue
            if max_onzekerheid_m is not None:
                r.aantal = 0
            continue
        if max_onzekerheid_m is not None:
            r.aantal = len(recs)
        jaren = [o["year"] for o in recs if o.get("year")]
        r.laatste_jaar = max(jaren) if jaren else None
        onz = [float(o["coordinateUncertaintyInMeters"]) for o in recs if o.get("coordinateUncertaintyInMeters") is not None]
        if onz:
            r.onz_max = max(onz)
            r.onz_med = float(statistics.median(onz))
        if centrum and straal:
            zeker = 0
            for o in recs:
                if o.get("decimalLatitude") is None:
                    continue
                d = afstand_m(centrum[0], centrum[1], o["decimalLatitude"], o["decimalLongitude"])
                if d + float(o.get("coordinateUncertaintyInMeters") or 0) <= straal:
                    zeker += 1
            r.zeker = zeker
        r.broed = sum(1 for o in recs if gbif.broedindicatie(o))
        if per_dataset_per_soort:
            r.datasets = datasets_per_soort(recs)
            # De uitsplitsing komt uit dezelfde records als `aantal`; ze moeten dus sluiten.
            assert sum(d["aantal"] for d in r.datasets) == len(recs)
    if zonder:
        an.ontbrekend.append(
            f"laatste_jaar/onzekerheid/broedindicatie niet opgehaald voor {len(zonder)} soort(en) (tijdsbudget {budget_s:.0f} s overschreden of GBIF-fout)"
        )
    return volledig, records


def signaleer_vervaging(regels: list[SoortRegel], straal_m: float | None = None) -> list[str]:
    """Waarschuw wanneer alle records van een strikt beschermde soort (score 4/3) onzeker liggen t.o.v. de straal.

    `straal_m` wordt in de tekst genoemd: een rapport bevraagt soorten en gebieden vaak met een
    eigen straal, dus 'de zoekstraal' zonder getal is dubbelzinnig."""
    omschrijving = f"de zoekstraal van {straal_m:.0f} m" if straal_m else "de zoekstraal"
    uit = []
    for r in regels:
        if r.score >= 3 and r.zeker == 0 and r.aantal > 0 and r.onz_max:
            naam = r.soort.nederlandse_naam if r.soort and r.soort.nederlandse_naam else (r.soort.wetenschappelijke_naam if r.soort else str(r.key))
            uit.append(f"{naam}: geen enkel record ligt zeker binnen {omschrijving} (onzekerheid tot {r.onz_max:.0f} m); de werkelijke locatie kan buiten het gebied liggen.")
    return uit


def naar_uitvoer(r: SoortRegel, *, detail: bool) -> SoortInGebied:
    s = r.soort
    return SoortInGebied(
        taxon_key=r.key,
        wetenschappelijke_naam=s.wetenschappelijke_naam if s else "",
        nederlandse_naam=s.nederlandse_naam if s else None,
        aantal_waarnemingen=r.aantal,
        laatste_jaar=r.laatste_jaar,
        samenvatting=samenvatting(r.vermeldingen),
        exoot=r.exoot,
        onzekerheid_max_m=r.onz_max,
        zeker_binnen_straal=r.zeker,
        records_met_broedindicatie=r.broed,
        koppeling_twijfel=r.twijfel,
        datasets=r.datasets,
        vermeldingen=r.vermeldingen if detail else None,
    )


def naar_tabel(regels: list[SoortRegel], *, met_straal: bool, met_datasets: bool = False) -> str:
    """Markdown-tabel: één rij per soort, statussen als 'code: categorie' gescheiden door ' | '."""
    kop = ["taxon_key", "nederlandse_naam", "wetenschappelijke_naam", "n", "laatste_jaar", "status", "exoot", "onz_max_m"]
    if met_straal:
        kop.append("zeker_in_straal")
    kop += ["broed", "twijfel"]
    if met_datasets:
        kop.append("datasets")
    rijen = ["| " + " | ".join(kop) + " |", "|" + "---|" * len(kop)]
    for r in regels:
        s = r.soort
        status = "; ".join(f"{c} {v}" for c, v in samenvatting(r.vermeldingen).items())
        cel = [str(r.key), (s.nederlandse_naam if s else "") or "", s.wetenschappelijke_naam if s else "", str(r.aantal), str(r.laatste_jaar or ""),
               status, "ja" if r.exoot else ("" if r.exoot is None else "nee"), f"{r.onz_max:.0f}" if r.onz_max else ""]
        if met_straal:
            cel.append("" if r.zeker is None else str(r.zeker))
        cel += ["" if r.broed is None else str(r.broed), "ja" if r.twijfel else ""]
        if met_datasets:
            cel.append(datasets_compact(r.datasets) if r.datasets else "")
        rijen.append("| " + " | ".join(c.replace("|", "/") for c in cel) + " |")
    return "\n".join(rijen)


def telling(an: Analyse) -> tuple[dict[str, int], dict[str, dict[str, int]], int, int]:
    per_lijst: dict[str, int] = {}
    per_cat: dict[str, dict[str, int]] = {}
    kern_n = 0
    exoten = 0
    for r in an.regels:
        gezien_lijst: set[str] = set()
        gezien_cat: set[tuple[str, str]] = set()
        for v in r.vermeldingen:
            if v.lijst_code not in gezien_lijst:
                gezien_lijst.add(v.lijst_code)
                per_lijst[v.lijst_code] = per_lijst.get(v.lijst_code, 0) + 1
            cat = v.categorie or "vermeld"
            if (v.lijst_code, cat) not in gezien_cat:
                gezien_cat.add((v.lijst_code, cat))
                per_cat.setdefault(v.lijst_code, {})[cat] = per_cat.setdefault(v.lijst_code, {}).get(cat, 0) + 1
        if any(is_kern(v.lijst_code, v.categorie) for v in r.vermeldingen):
            kern_n += 1
        if r.exoot:
            exoten += 1
    return per_lijst, per_cat, kern_n, exoten
