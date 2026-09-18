"""Client voor het Vlaams Biodiversiteitsportaal (natuurdata.inbo.be; Atlas of Living Australia-stack).

Gebruikte webservices (allemaal publiek, zonder sleutel):
  - /bie-index/search?q=…                  naamzoeken, ook op Nederlandse naam (commonNameSingle)
  - /bie-index/species/<guid>              soortprofiel (Nederlandse namen, classificatie)
  - /species-list/ws/species/<guid>        alle lijsten waarop het taxon staat, met KVP-velden
  - /species-list/ws/speciesListItems/<dr> items van één lijst, met KVP-velden
De guid is de GBIF-backbone-taxonKey.
"""
from __future__ import annotations

from typing import Any

from .http import get_json
from .lijsten import INBO_PORTAAL, PER_DR, Lijst, normaliseer_categorie
from .schema import LijstVermelding, Soort


def soortpagina(taxon_key: int) -> str:
    return f"{INBO_PORTAAL}/species/{taxon_key}"


async def zoek(naam: str, limit: int = 10) -> list[Soort]:
    """Zoek op wetenschappelijke of Nederlandse naam. Geeft geaccepteerde taxa in rangorde van het portaal."""
    d = await get_json(f"{INBO_PORTAAL}/bie-index/search", {"q": naam, "fq": "idxtype:TAXON", "pageSize": limit})
    out: list[Soort] = []
    for r in d.get("searchResults", {}).get("results", []):
        guid = r.get("guid")
        if not guid or not str(guid).isdigit():
            continue
        out.append(
            Soort(
                taxon_key=int(guid),
                wetenschappelijke_naam=r.get("scientificName") or r.get("name") or "",
                nederlandse_naam=r.get("commonNameSingle"),
                rang=(r.get("rank") or "").upper() or None,
                status=(r.get("taxonomicStatus") or "").upper() or None,
                geaccepteerde_naam=r.get("acceptedConceptName"),
                rijk=r.get("kingdom"),
                klasse=r.get("classs") or r.get("class"),
                familie=r.get("family"),
                match_type="INBO",
                url=f"https://www.gbif.org/species/{guid}",
                url_inbo=soortpagina(int(guid)),
            )
        )
    return out


async def nederlandse_namen(taxon_key: int) -> list[str]:
    try:
        d = await get_json(f"{INBO_PORTAAL}/bie-index/species/{taxon_key}")
    except Exception:
        return []
    namen: list[str] = []
    for c in d.get("commonNames", []):
        if (c.get("language") or "").lower().startswith("nl"):
            n = c.get("nameString")
            if n and n.lower() not in (x.lower() for x in namen):
                namen.append(n)
    return namen


def _kvp(item: dict[str, Any]) -> dict[str, str]:
    return {k["key"]: str(k["value"]) for k in item.get("kvpValues", []) if k.get("value") not in (None, "", "NULL")}


def _eerste(kvp: dict[str, str], velden: tuple[str, ...]) -> str | None:
    for v in velden:
        if kvp.get(v):
            return kvp[v]
    return None


def vermelding_uit_item(lijst: Lijst, item: dict[str, Any]) -> LijstVermelding:
    kvp = _kvp(item)
    ruw = _eerste(kvp, lijst.categorie_velden)
    if ruw:
        kvp = dict(kvp, categorie_bron=ruw)
    return LijstVermelding(
        lijst_code=lijst.code,
        lijst_naam=lijst.naam,
        categorie=normaliseer_categorie(lijst.code, ruw),
        toelichting=_eerste(kvp, lijst.toelichting_velden),
        jaar=_eerste(kvp, lijst.jaar_velden),
        bronvermelding=_eerste(kvp, lijst.bron_velden),
        url=lijst.url,
        extra={k: v for k, v in kvp.items() if k not in ("license", "kingdom", "countryCode", "stateProvince", "datasetName", "scientificNameAuthorship")},
    )


async def lijsten_van_taxon(taxon_key: int) -> list[LijstVermelding]:
    """Alle geregistreerde (gezaghebbende) lijsten waarop het taxon voorkomt."""
    d = await get_json(f"{INBO_PORTAAL}/species-list/ws/species/{taxon_key}")
    out: list[LijstVermelding] = []
    for item in d if isinstance(d, list) else []:
        for lijst in (l for l in PER_DR.values() if l.dr == item.get("dataResourceUid")):
            if lijst.kvp_filter and _kvp(item).get(lijst.kvp_filter[0]) != lijst.kvp_filter[1]:
                continue
            out.append(vermelding_uit_item(lijst, item))
    return out


async def lijst_items(lijst: Lijst) -> list[dict[str, Any]]:
    """Alle items van een lijst (gecachet; lijsten tellen hoogstens enkele duizenden regels)."""
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        d = await get_json(
            f"{INBO_PORTAAL}/species-list/ws/speciesListItems/{lijst.dr}",
            {"max": 1000, "offset": offset, "includeKVP": "true"},
            ttl=6 * 3600,
            schijf_ttl=7 * 86400,
        )
        if not d:
            break
        items.extend(d)
        if len(d) < 1000:
            break
        offset += 1000
    if lijst.kvp_filter:
        veld, waarde = lijst.kvp_filter
        items = [it for it in items if _kvp(it).get(veld) == waarde]
    return items


def dekking(items: list[dict[str, Any]]) -> str:
    """Soortengroepen en publicatiejaren die een (Rode) lijst effectief dekt, bv. 'Amfibieen 2024; Libellen 2021'."""
    combi: dict[str, set[str]] = {}
    for it in items:
        k = _kvp(it)
        groep = k.get("taxonomische_groep") or k.get("taxongroep") or k.get("class") or "?"
        jaar = k.get("JaarPublicatie") or k.get("eventDate") or k.get("year") or "?"
        combi.setdefault(groep, set()).add(jaar)
    return "; ".join(f"{g} {'/'.join(sorted(j))}" for g, j in sorted(combi.items()))


def lijstversie(lijst: Lijst) -> str | None:
    """ISO-tijdstip waarop de (eerste pagina van de) lijst bij het portaal is opgehaald."""
    from .http import ophaaltijd

    return ophaaltijd(f"{INBO_PORTAAL}/species-list/ws/speciesListItems/{lijst.dr}", {"max": 1000, "offset": 0, "includeKVP": "true"})


async def lijst_index(lijst: Lijst) -> dict[int, list[dict[str, Any]]]:
    """taxonKey -> lijstitems (één taxon kan meermaals voorkomen, bv. per bijlage)."""
    idx: dict[int, list[dict[str, Any]]] = {}
    for it in await lijst_items(lijst):
        lsid = it.get("lsid")
        if lsid and str(lsid).isdigit():
            idx.setdefault(int(lsid), []).append(it)
    return idx


def soort_uit_item(item: dict[str, Any]) -> Soort:
    kvp = _kvp(item)
    key = int(item["lsid"])
    return Soort(
        taxon_key=key,
        wetenschappelijke_naam=item.get("scientificName") or item.get("name") or "",
        nederlandse_naam=item.get("commonName") or kvp.get("vernacularName"),
        rijk=kvp.get("kingdom"),
        klasse=kvp.get("class"),
        familie=kvp.get("family"),
        match_type="INBO_LIJST",
        url=f"https://www.gbif.org/species/{key}",
        url_inbo=soortpagina(key),
    )
