# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Dekking van waarnemingen.be op GBIF: kanttekening en indicator per soortgroep.

De kanttekening wordt niet uit het geheugen geschreven: ze citeert de beschrijving van de GBIF-dataset
met de waarnemingen.be-gegevens van INBO, met titel, versie, publicatiedatum en DOI zoals GBIF ze
levert. Lukt het ophalen niet, dan zegt de kanttekening dat de dekking niet is nagegaan.

De indicator per soortgroep (configuratie in `data/dekking.json`, of het bestand in de omgevingsvariabele
GBIF_MCP_DEKKING) telt per groep de records in het gebied per brondataset (één facetoproep per groep)
en waarschuwt wanneer meer dan de drempel uit één INBO-dataset komt, of wanneer er geen enkel record is.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import gbif
from .http import get_json

WNM_INBO_DATASET = "280674cb-42f8-4959-b6aa-eee663157965"
_CITAAT_RE = re.compile(r"INBO|tagged|kept out", re.I)


def configuratie() -> dict[str, Any]:
    pad = os.environ.get("GBIF_MCP_DEKKING")
    bron = Path(pad).expanduser() if pad else Path(__file__).parent / "data" / "dekking.json"
    return json.loads(bron.read_text(encoding="utf-8"))


def _zinnen(tekst: str) -> list[str]:
    # Zinsgrens: punt + spatie + hoofdletter; URL's met punten blijven heel.
    return [z.strip() for z in re.split(r"(?<=\.)\s+(?=[A-Z])", tekst.replace("\n", " ")) if z.strip()]


async def kanttekening() -> tuple[str, dict[str, Any]]:
    """(tekst, bronmetadata) voor de dekkingswaarschuwing waarnemingen.be op GBIF."""
    url = f"https://www.gbif.org/dataset/{WNM_INBO_DATASET}"
    groepen = [g["naam"] for g in configuratie().get("groepen", [])]
    gevolg = ("Voor soortgroepen die vooral via waarnemingen.be gemeld worden"
              + (f", zoals {', '.join(groepen)}," if groepen else "")
              + " kan de werkelijke meldingsdichtheid veel hoger liggen dan wat GBIF toont.")
    try:
        d = await get_json(f"{gbif.API}/dataset/{WNM_INBO_DATASET}", ttl=86400, schijf_ttl=7 * 86400)
    except Exception as e:
        meta = {"dataset_key": WNM_INBO_DATASET, "url": url, "fout": f"{type(e).__name__}"}
        return (f"Dekking van waarnemingen.be op GBIF niet nagegaan: de beschrijving van GBIF-dataset {WNM_INBO_DATASET} "
                f"kon niet worden opgehaald ({type(e).__name__}). {gevolg}"), meta
    meta = {
        "dataset_key": WNM_INBO_DATASET, "titel": d.get("title"), "versie": d.get("version"),
        "gepubliceerd": (d.get("pubDate") or "")[:10] or None, "doi": d.get("doi"), "url": url,
    }
    citaat = " ".join(z for z in _zinnen(d.get("description") or "") if _CITAAT_RE.search(z))
    tekst = (f"Dekking van waarnemingen.be op GBIF. De GBIF-dataset '{meta['titel']}' (versie {meta['versie'] or '?'}, "
             f"gepubliceerd {meta['gepubliceerd'] or '?'}" + (f", doi:{meta['doi']}" if meta["doi"] else "") + ") beschrijft "
             f"zichzelf als volgt: \"{citaat}\" Waarnemingen.be-gegevens die niet aan INBO gekoppeld zijn, vallen buiten "
             f"die dataset; wat ervan niet via een andere dataset op GBIF staat, ontbreekt in deze resultaten. {gevolg}")
    return tekst, meta


async def per_groep(*, geometry: str | None, gadm_gid: str | None, jaar_van: int | None, jaar_tot: int | None) -> list[dict[str, Any]]:
    """Per geconfigureerde soortgroep: records in het gebied per brondataset, met waarschuwing."""
    cfg = configuratie()
    drempel = float(cfg.get("drempel", 0.8))
    inbo = set(cfg.get("inbo_datasets", []))
    uit: list[dict[str, Any]] = []
    for g in cfg.get("groepen", []):
        p = gbif._occurrence_params(taxon_key=int(g["taxon_key"]), geometry=geometry, gadm_gid=gadm_gid, jaar_van=jaar_van, jaar_tot=jaar_tot)
        p.update({"limit": 0, "facet": "datasetKey", "facetLimit": 20})
        regel: dict[str, Any] = {"groep": g["naam"], "taxon_key": g["taxon_key"], "wetenschappelijke_naam": g.get("wetenschappelijke_naam"),
                                 "reden_in_lijst": g.get("reden"), "zoek_url": gbif.gbif_zoek_url(p)}
        try:
            d = await get_json(f"{gbif.API}/occurrence/search", p, ttl=600, verwijder_velden=gbif.PERSOONSVELDEN)
        except Exception as e:
            regel.update({"status": "niet_geraadpleegd", "melding": f"{type(e).__name__}", "waarschuwing": None})
            uit.append(regel)
            continue
        totaal = int(d.get("count") or 0)
        per_ds = [{"dataset_key": c["name"], "aantal": c["count"], "aandeel": round(c["count"] / totaal, 3) if totaal else 0.0}
                  for f in d.get("facets", []) for c in f.get("counts", [])]
        waarschuwing = None
        if totaal == 0:
            waarschuwing = (f"{g['naam'].capitalize()}: geen enkel GBIF-record in het gebied. Deze groep staat gemarkeerd als "
                            "onvolledig gedekt op GBIF; nul records betekent hier niet dat de groep afwezig is.")
        elif per_ds and per_ds[0]["dataset_key"] in inbo and per_ds[0]["aandeel"] > drempel:
            waarschuwing = (f"{g['naam'].capitalize()}: {per_ds[0]['aandeel']:.0%} van de {totaal} GBIF-records in het gebied komt "
                            f"uit één INBO-dataset ({per_ds[0]['dataset_key']}). Deze groep staat gemarkeerd als onvolledig gedekt "
                            "op GBIF; de werkelijke meldingsdichtheid op waarnemingen.be kan veel hoger liggen.")
        regel.update({"status": "ok", "totaal": totaal, "per_dataset": per_ds, "waarschuwing": waarschuwing})
        uit.append(regel)
    return uit
