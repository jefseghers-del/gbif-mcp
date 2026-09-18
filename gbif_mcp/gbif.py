# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Client voor de publieke GBIF-API (api.gbif.org/v1). Geen authenticatie vereist."""
from __future__ import annotations

import asyncio
import re
from contextvars import ContextVar
from typing import Any

from .http import get_json
from .schema import DatasetInfo, Soort, Waarneming

API = "https://api.gbif.org/v1"

# Datalicenties. GBIF kent per dataset één licentie: CC0 1.0, CC BY 4.0 of CC BY-NC 4.0. Standaard
# worden alle licenties meegenomen: de rapporten zijn bedoeld als intern werkdocument. Wie een rapport
# deelt of publiceert, kan de datasets onder CC BY-NC (alleen niet-commercieel gebruik) uitsluiten;
# de filter werkt dan aan de bron (GBIF-parameter `license`), zodat tellingen, facetten en records
# onderling consistent blijven. Records zonder bruikbare licentie vallen dan ook weg.
VRIJE_LICENTIES: tuple[str, ...] = ("CC0_1_0", "CC_BY_4_0")
LICENTIENAMEN = {"CC0_1_0": "CC0 1.0", "CC_BY_4_0": "CC BY 4.0", "CC_BY_NC_4_0": "CC BY-NC 4.0",
                 "UNSPECIFIED": "niet opgegeven", "UNSUPPORTED": "niet ondersteund"}
_licentiefilter: ContextVar[tuple[str, ...] | None] = ContextVar("licentiefilter", default=None)


def zet_licentiefilter(ook_niet_commercieel: bool) -> None:
    """Per tool-oproep: alle licenties, ook CC BY-NC (standaard), of alleen CC0 en CC BY."""
    _licentiefilter.set(None if ook_niet_commercieel else VRIJE_LICENTIES)


def licentiefilter_omschrijving() -> str:
    f = _licentiefilter.get()
    if not f:
        return "alle licenties, ook niet-commercieel (CC BY-NC)"
    return "alleen " + " en ".join(LICENTIENAMEN.get(x, x) for x in f) + "; niet-commerciële datasets (CC BY-NC) uitgesloten"


def licentie_kort(url_of_code: str | None) -> str:
    """'http://creativecommons.org/licenses/by-nc/4.0/legalcode' of 'CC_BY_NC_4_0' -> 'CC BY-NC 4.0'."""
    if not url_of_code:
        return "onbekend"
    if url_of_code in LICENTIENAMEN:
        return LICENTIENAMEN[url_of_code]
    u = url_of_code.lower()
    if "zero" in u or "cc0" in u:
        return "CC0 1.0"
    if "by-nc" in u:
        return "CC BY-NC 4.0"
    if "/by/" in u:
        return "CC BY 4.0"
    return url_of_code


# Persoonsgegevens in GBIF-records. De connector verwerkt die niet: ze worden bij ontvangst uit elk
# record verwijderd, nog vóór caching, en komen dus nooit in een antwoord, export of rapport terecht.
PERSOONSVELDEN: tuple[str, ...] = (
    "recordedBy", "recordedByID", "recordedByIDs", "identifiedBy", "identifiedByID", "identifiedByIDs",
    "georeferencedBy", "verbatimRecordedBy", "rightsHolder",
)


def soort_url(taxon_key: int) -> str:
    return f"https://www.gbif.org/species/{taxon_key}"


def _soort_uit_backbone(d: dict[str, Any], *, match_type: str | None = None, zekerheid: int | None = None) -> Soort:
    key = d.get("usageKey") or d.get("key") or d.get("nubKey")
    return Soort(
        taxon_key=int(key),
        wetenschappelijke_naam=d.get("canonicalName") or d.get("scientificName") or "",
        rang=d.get("rank"),
        status=d.get("status") or d.get("taxonomicStatus"),
        geaccepteerde_naam=d.get("accepted") if d.get("status") not in (None, "ACCEPTED") else None,
        rijk=d.get("kingdom"),
        klasse=d.get("class"),
        familie=d.get("family"),
        match_type=match_type or d.get("matchType"),
        zekerheid=zekerheid if zekerheid is not None else d.get("confidence"),
        url=soort_url(int(key)),
    )


async def match_naam(naam: str) -> Soort | None:
    """Wetenschappelijke naam -> backbone-taxon via /species/match. None bij matchType NONE."""
    d = await get_json(f"{API}/species/match", {"name": naam, "strict": "false"})
    if d.get("matchType") in (None, "NONE") or not d.get("usageKey"):
        return None
    return _soort_uit_backbone(d)


async def haal_soort(taxon_key: int) -> Soort:
    d = await get_json(f"{API}/species/{taxon_key}")
    return _soort_uit_backbone(d, match_type="KEY", zekerheid=100)


async def nederlandse_namen(taxon_key: int) -> list[str]:
    """Nederlandse volksnamen uit GBIF (Belgian Species List, Catalogue of Life …)."""
    d = await get_json(f"{API}/species/{taxon_key}/vernacularNames", {"limit": 100})
    namen: list[str] = []
    for v in d.get("results", []):
        if v.get("language") in ("nld", "dut", "nl"):
            n = v.get("vernacularName")
            if n and n.lower() not in (x.lower() for x in namen):
                namen.append(n)
    return namen


async def zoek_nederlandse_naam(naam: str, limit: int = 10) -> list[Soort]:
    """Zoek op Nederlandse volksnaam in de Belgian Species List (BBPF) en vertaal naar backbone-sleutels."""
    from .lijsten import GBIF_CHECKLISTS

    ds, _ = GBIF_CHECKLISTS["gbif_belgian_species_list"]
    d = await get_json(f"{API}/species/search", {"datasetKey": ds, "q": naam, "qField": "VERNACULAR", "limit": limit})
    out: list[Soort] = []
    for r in d.get("results", []):
        nub = r.get("nubKey")
        if not nub:
            continue
        nl = [v["vernacularName"] for v in r.get("vernacularNames", []) if v.get("language") in ("nld", "dut")]
        out.append(
            Soort(
                taxon_key=int(nub),
                wetenschappelijke_naam=r.get("canonicalName") or r.get("scientificName") or "",
                nederlandse_naam=nl[0] if nl else None,
                rang=r.get("rank"),
                status=r.get("taxonomicStatus"),
                rijk=r.get("kingdom"),
                klasse=r.get("class"),
                familie=r.get("family"),
                match_type="BSL_NL",
                url=soort_url(int(nub)),
            )
        )
    return out


async def checklist_verspreiding(dataset_key: str, taxon_key: int) -> list[dict[str, Any]]:
    """Distributions-records van een backbone-taxon in een GBIF-checklist (bv. Rode Lijst, GRIIS)."""
    rel = await get_json(f"{API}/species/{taxon_key}/related", {"datasetKey": dataset_key, "limit": 5})
    out: list[dict[str, Any]] = []
    for r in rel.get("results", []):
        dist = await get_json(f"{API}/species/{r['key']}/distributions", {"limit": 50})
        for x in dist.get("results", []):
            x["_checklist_taxon_key"] = r["key"]
            x["_scientificName"] = r.get("scientificName")
            out.append(x)
    return out


_BROED_RE = re.compile(
    r"broed|nest|territori|juvenie|juvenil|pull(us|i)\b|paring|paren|copul|baltsen|balts|zingend|zang\b|eieren|jongen|kuiken|"
    r"breeding|nesting|fledg|egg|mating|courtship|singing|larva|larve|paai|ei-?afzet|kikkerdril|dril\b",
    re.I,
)


def broedindicatie(o: dict[str, Any]) -> bool:
    """Heuristiek: wijst een record op broeden/voortplanting? Velden: lifeStage, reproductiveCondition, behavior, occurrenceRemarks."""
    tekst = " ".join(str(o.get(k) or "") for k in ("lifeStage", "reproductiveCondition", "behavior", "occurrenceRemarks"))
    return bool(_BROED_RE.search(tekst))


def _waarneming(o: dict[str, Any]) -> Waarneming:
    datum = o.get("eventDate")
    if datum and "T" in datum:
        datum = datum.split("T")[0]
    if not datum and o.get("year"):
        datum = "-".join(str(o[k]).zfill(2) for k in ("year", "month", "day") if o.get(k))
    return Waarneming(
        gbif_id=o["key"],
        soort=o.get("species") or o.get("scientificName") or "",
        datum=datum,
        jaar=o.get("year"),
        lat=o.get("decimalLatitude"),
        lon=o.get("decimalLongitude"),
        onzekerheid_m=o.get("coordinateUncertaintyInMeters"),
        gemeente=o.get("municipality"),
        plaats=o.get("locality") or o.get("verbatimLocality"),
        basis=o.get("basisOfRecord"),
        aantal=o.get("individualCount"),
        dataset=o.get("datasetName"),
        dataset_key=o.get("datasetKey"),
        levensstadium=o.get("lifeStage"),
        voortplanting=o.get("reproductiveCondition"),
        gedrag=o.get("behavior"),
        geslacht=o.get("sex"),
        opmerkingen=(o.get("occurrenceRemarks") or "")[:200] or None,
        verificatiestatus=o.get("identificationVerificationStatus"),
        broedindicatie=broedindicatie(o),
        url=f"https://www.gbif.org/occurrence/{o['key']}",
    )


def _occurrence_params(
    *,
    taxon_key: int | list[int] | None,
    geometry: str | None,
    gadm_gid: str | None,
    jaar_van: int | None,
    jaar_tot: int | None,
    dataset_key: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p: dict[str, Any] = {"country": "BE", "hasCoordinate": "true", "occurrenceStatus": "PRESENT"}
    licenties = _licentiefilter.get()
    if licenties:
        p["license"] = list(licenties)
    if dataset_key:
        p["datasetKey"] = dataset_key
    if taxon_key:
        p["taxonKey"] = taxon_key
    if geometry:
        p["geometry"] = geometry
        p.pop("country")  # geometrie kan de grens overschrijden; GBIF filtert op geometrie
    if gadm_gid:
        p["gadmGid"] = gadm_gid
    if jaar_van or jaar_tot:
        p["year"] = f"{jaar_van or '*'},{jaar_tot or '*'}"
    if extra:
        p.update(extra)
    return p


def gbif_zoek_url(params: dict[str, Any]) -> str:
    import urllib.parse

    q = []
    for k, v in params.items():
        if k in ("limit", "offset", "facet", "facetLimit", "facetOffset"):
            continue
        if isinstance(v, list):
            q.extend((k, str(x)) for x in v)
        else:
            q.append((k, str(v)))
    return "https://www.gbif.org/occurrence/search?" + urllib.parse.urlencode(q)


async def zoek_waarnemingen(
    *,
    taxon_key: int | None,
    geometry: str | None,
    gadm_gid: str | None,
    jaar_van: int | None,
    jaar_tot: int | None,
    limit: int,
    offset: int = 0,
    dataset_key: str | None = None,
) -> tuple[int, list[Waarneming], list[dict], list[dict], str]:
    p = _occurrence_params(taxon_key=taxon_key, geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot, dataset_key=dataset_key)
    p.update({"limit": min(limit, 300), "offset": offset, "facet": ["datasetKey", "year"], "facetLimit": 25})
    d = await get_json(f"{API}/occurrence/search", p, ttl=600, verwijder_velden=PERSOONSVELDEN)
    per_dataset: list[dict] = []
    per_jaar: list[dict] = []
    for f in d.get("facets", []):
        if f["field"] == "DATASET_KEY":
            for c in f["counts"]:
                per_dataset.append({"dataset_key": c["name"], "aantal": c["count"]})
        elif f["field"] == "YEAR":
            per_jaar = sorted(({"jaar": int(c["name"]), "aantal": c["count"]} for c in f["counts"]), key=lambda x: x["jaar"])
    # datasetnamen invullen uit de records zelf (spaart API-calls)
    namen = {o.get("datasetKey"): o.get("datasetName") for o in d.get("results", []) if o.get("datasetName")}
    for pd_ in per_dataset:
        if pd_["dataset_key"] in namen:
            pd_["dataset"] = namen[pd_["dataset_key"]]
    waarnemingen = [_waarneming(o) for o in d.get("results", [])]
    return d.get("count", 0), waarnemingen, per_dataset, per_jaar, gbif_zoek_url(p)


async def soorten_facet(
    *, geometry: str | None, gadm_gid: str | None, jaar_van: int | None, jaar_tot: int | None, max_soorten: int = 5000
) -> tuple[int, list[tuple[int, int]], list[dict], dict[str, Any], str]:
    """Aantal waarnemingen per speciesKey in een gebied (facet), plus datasetverdeling.

    Geeft (totaal, [(speciesKey, n)], per_dataset, parameters, zoek_url). Gecachet (10 min) via get_json."""
    p = _occurrence_params(taxon_key=None, geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot)
    tellingen: list[tuple[int, int]] = []
    per_dataset: list[dict] = []
    totaal = 0
    offset = 0
    while len(tellingen) < max_soorten:
        pp = dict(p, limit=0, facet=["speciesKey", "datasetKey"], facetLimit=min(1000, max_soorten - len(tellingen)), facetOffset=offset)
        d = await get_json(f"{API}/occurrence/search", pp, ttl=600, verwijder_velden=PERSOONSVELDEN)
        totaal = d.get("count", 0)
        counts: list = []
        for f in d.get("facets", []):
            if f["field"] == "SPECIES_KEY":
                counts = f.get("counts", [])
            elif f["field"] == "DATASET_KEY" and not per_dataset:
                per_dataset = [{"dataset_key": c["name"], "aantal": c["count"]} for c in f.get("counts", [])[:50]]
        if not counts:
            break
        tellingen.extend((int(c["name"]), c["count"]) for c in counts)
        if len(counts) < pp["facetLimit"]:
            break
        offset += len(counts)
    return totaal, tellingen, per_dataset, p, gbif_zoek_url(p)


RECORD_VELDEN = (
    "key", "speciesKey", "taxonKey", "year", "eventDate", "decimalLatitude", "decimalLongitude", "coordinateUncertaintyInMeters",
    "datasetKey", "datasetName", "basisOfRecord", "lifeStage", "reproductiveCondition", "behavior", "sex", "occurrenceRemarks",
    "identificationVerificationStatus",
)


async def records_in_gebied(
    taxon_keys: list[int], *, geometry: str | None, gadm_gid: str | None, jaar_van: int | None, jaar_tot: int | None,
    budget_s: float = 40.0, max_records: int = 9000, chunk: int = 60, parallel: int = 4,
) -> tuple[list[dict[str, Any]], bool, list[int]]:
    """Alle records van de opgegeven taxa in het gebied (ingekorte velden), in pagina's van 300, meerdere taxa per oproep.

    Geeft (records, volledig, taxa_zonder_records_opgehaald). Stopt netjes bij het tijdsbudget:
    wat al binnen is, wordt teruggegeven en `volledig` is dan False."""
    records: list[dict[str, Any]] = []
    onvolledig: set[int] = set()
    sem = asyncio.Semaphore(parallel)
    deadline = asyncio.get_running_loop().time() + budget_s

    async def _pagina(keys: list[int], offset: int) -> dict[str, Any]:
        p = _occurrence_params(taxon_key=keys, geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot)
        p.update({"limit": 300, "offset": offset})
        async with sem:
            return await get_json(f"{API}/occurrence/search", p, ttl=600, verwijder_velden=PERSOONSVELDEN)

    async def _chunk(keys: list[int]) -> None:
        offset = 0
        while True:
            if asyncio.get_running_loop().time() > deadline or len(records) >= max_records:
                onvolledig.update(keys)
                return
            d = await _pagina(keys, offset)
            for o in d.get("results", []):
                records.append({k: o.get(k) for k in RECORD_VELDEN})
            if d.get("endOfRecords", True) or offset + 300 >= 100_000:
                return
            offset += 300

    chunks = [taxon_keys[i : i + chunk] for i in range(0, len(taxon_keys), chunk)]
    taken = [asyncio.ensure_future(_chunk(c)) for c in chunks]
    done, pending = await asyncio.wait(taken, timeout=budget_s + 5)
    for t in pending:
        t.cancel()
    for t, c in zip(taken, chunks):
        if t in pending or (t.done() and t.exception()):
            onvolledig.update(c)
    return records, not onvolledig, sorted(onvolledig)


async def soortkeys_per_dataset(
    dataset_keys: list[str], *, geometry: str | None, gadm_gid: str | None, jaar_van: int | None, jaar_tot: int | None, parallel: int = 5
) -> dict[str, set[int]]:
    """Per dataset de speciesKeys in het gebied (één facetoproep per dataset, parallel).

    Bedoeld voor `telling_in_gebied` met soorten_per_dataset=True; kost één extra GBIF-oproep per
    dataset. Een dataset die faalt, ontbreekt in het resultaat (de oproeper meldt dat)."""
    sem = asyncio.Semaphore(parallel)
    uit: dict[str, set[int]] = {}

    async def _een(ds: str) -> None:
        p = _occurrence_params(taxon_key=None, geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot, dataset_key=ds)
        p.update({"limit": 0, "facet": "speciesKey", "facetLimit": 1000})
        async with sem:
            try:
                d = await get_json(f"{API}/occurrence/search", p, ttl=600, verwijder_velden=PERSOONSVELDEN)
            except Exception:
                return
        uit[ds] = {int(c["name"]) for f in d.get("facets", []) for c in f.get("counts", []) if str(c["name"]).isdigit()}

    await asyncio.gather(*(_een(ds) for ds in dataset_keys))
    return uit


async def licentieverdeling(*, geometry: str | None, gadm_gid: str | None, jaar_van: int | None, jaar_tot: int | None) -> dict[str, int]:
    """Aantal records per licentie in het gebied, ZONDER licentiefilter: toont wat is uitgesloten."""
    p = _occurrence_params(taxon_key=None, geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot)
    p.pop("license", None)
    p.update({"limit": 0, "facet": "license", "facetLimit": 10})
    d = await get_json(f"{API}/occurrence/search", p, ttl=600, verwijder_velden=PERSOONSVELDEN)
    return {c["name"]: c["count"] for f in d.get("facets", []) for c in f.get("counts", [])}


async def checklist_keys(dataset_key: str) -> set[int]:
    """Backbone-sleutels van alle taxa in een GBIF-checklist, schijfgecachet (7 dagen)."""
    keys: set[int] = set()
    offset = 0
    while True:
        d = await get_json(f"{API}/species/search", {"datasetKey": dataset_key, "limit": 1000, "offset": offset}, ttl=6 * 3600, schijf_ttl=7 * 86400)
        for r in d.get("results", []):
            if r.get("nubKey"):
                keys.add(int(r["nubKey"]))
        if d.get("endOfRecords", True) or offset > 20_000:
            break
        offset += 1000
    return keys


async def griis_belgie_keys() -> set[int]:
    """Backbone-sleutels van alle taxa in GRIIS België (uitheemse soorten), schijfgecachet (7 dagen)."""
    from .lijsten import GBIF_CHECKLISTS

    ds, _ = GBIF_CHECKLISTS["gbif_griis_be"]
    keys: set[int] = set()
    offset = 0
    while True:
        d = await get_json(f"{API}/species/search", {"datasetKey": ds, "limit": 1000, "offset": offset}, ttl=6 * 3600, schijf_ttl=7 * 86400)
        for r in d.get("results", []):
            if r.get("nubKey"):
                keys.add(int(r["nubKey"]))
        if d.get("endOfRecords", True) or offset > 20_000:
            break
        offset += 1000
    return keys


async def laatste_jaar(taxon_key: int, *, geometry: str | None, gadm_gid: str | None, jaar_van: int | None, jaar_tot: int | None) -> int | None:
    """Meest recente jaar met een waarneming van het taxon in het gebied (via jaar-facet)."""
    p = _occurrence_params(taxon_key=taxon_key, geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot)
    p.update({"limit": 0, "facet": "year", "facetLimit": 300})
    d = await get_json(f"{API}/occurrence/search", p, ttl=600, verwijder_velden=PERSOONSVELDEN)
    jaren = [int(c["name"]) for f in d.get("facets", []) for c in f.get("counts", []) if str(c["name"]).isdigit()]
    return max(jaren) if jaren else None


async def dataset_info(key: str) -> DatasetInfo:
    d = await get_json(f"{API}/dataset/{key}", ttl=86400)
    beschrijving = d.get("description")
    if beschrijving and len(beschrijving) > 1200:
        beschrijving = beschrijving[:1200] + " …"
    return DatasetInfo(
        key=key,
        titel=d.get("title", ""),
        type=d.get("type"),
        uitgever=d.get("publishingOrganizationTitle") or d.get("publishingOrganizationKey"),
        licentie=licentie_kort(d.get("license")),
        doi=d.get("doi"),
        beschrijving=beschrijving,
        citatie=(d.get("citation") or {}).get("text"),
        url=f"https://www.gbif.org/dataset/{key}",
    )


async def gadm_gemeente(naam: str) -> tuple[str, str] | None:
    """Belgische gemeente -> GADM-gid (niveau 3 in GADM voor België = gemeente)."""
    d = await get_json(f"{API}/geocode/gadm/search", {"q": naam, "gadmGid": "BEL", "limit": 10}, ttl=86400)
    kandidaten = [r for r in d.get("results", []) if r.get("gadmLevel") == 3]
    if not kandidaten:
        return None
    exact = [r for r in kandidaten if r["name"].lower() == naam.lower()]
    r = (exact or kandidaten)[0]
    pad = " > ".join(h["name"] for h in r.get("higherRegions", [])[1:])
    return r["id"], f"{r['name']} ({pad})"
