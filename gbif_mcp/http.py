# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Gedeelde httpx-client: herkenbare User-Agent, time-outs, eenvoudige retry en in-memory cache."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)

from . import __version__

USER_AGENT = f"gbif-mcp/{__version__} (+https://github.com/jefseghers-del/gbif-mcp)"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

_clients: dict[int, httpx.AsyncClient] = {}
_cache: dict[str, tuple[float, Any]] = {}
# Wanneer een antwoord effectief bij de bron is opgehaald (ISO-tijdstip), per cache-sleutel.
_ophaaltijd: dict[str, str] = {}
SCHIJFCACHE = Path(os.environ.get("GBIF_MCP_CACHE", Path.home() / ".cache" / "gbif-mcp"))


def nu_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sleutel(url: str, params: dict[str, Any] | None) -> str:
    return url + "?" + str(sorted((params or {}).items()))


def ophaaltijd(url: str, params: dict[str, Any] | None = None) -> str | None:
    """ISO-tijdstip waarop dit antwoord bij de bron is opgehaald (uit geheugen- of schijfcache)."""
    return _ophaaltijd.get(_sleutel(url, params))


def _schijfpad(sleutel: str) -> Path:
    return SCHIJFCACHE / (hashlib.sha1(sleutel.encode()).hexdigest() + ".json")


def client() -> httpx.AsyncClient:
    """Eén client per event loop.

    Een httpx-client bindt zich aan de loop waarin hij is aangemaakt; een module-singleton breekt
    daarom ('Event loop is closed') zodra een tweede loop wordt gestart — bij tests met meerdere
    asyncio.run()-oproepen en bij elke host die de loop herstart. De server zelf draait op één loop,
    dus in het normale geval verandert er niets."""
    try:
        sleutel = id(asyncio.get_running_loop())
    except RuntimeError:
        sleutel = 0
    bestaand = _clients.get(sleutel)
    if bestaand is None or bestaand.is_closed:
        bestaand = httpx.AsyncClient(headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=TIMEOUT, follow_redirects=True)
        _clients[sleutel] = bestaand
    return bestaand


def _verwijder(data: Any, velden: tuple[str, ...]) -> Any:
    """Verwijder velden uit elk record in `results` (en uit het object zelf)."""
    if isinstance(data, dict):
        for v in velden:
            data.pop(v, None)
        for r in data.get("results") or []:
            if isinstance(r, dict):
                for v in velden:
                    r.pop(v, None)
    return data


async def get_json(
    url: str, params: dict[str, Any] | None = None, *, ttl: float = 3600, pogingen: int = 3, schijf_ttl: float | None = None,
    verwijder_velden: tuple[str, ...] = (),
) -> Any:
    """GET met JSON-antwoord. Antwoorden worden `ttl` seconden in het geheugen gecachet; met
    `schijf_ttl` (seconden) ook op schijf (voor lijsten die zelden wijzigen), zodat een herstart
    van de server geen nieuwe download vergt. `ophaaltijd()` geeft de versiedatum terug."""
    sleutel = _sleutel(url, params)
    nu = time.monotonic()
    hit = _cache.get(sleutel)
    if hit and hit[0] > nu:
        return hit[1]
    if schijf_ttl:
        pad = _schijfpad(sleutel)
        try:
            if pad.exists():
                inhoud = json.loads(pad.read_text())
                if time.time() - inhoud["t"] < schijf_ttl:
                    _cache[sleutel] = (nu + ttl, inhoud["data"])
                    _ophaaltijd[sleutel] = inhoud["iso"]
                    return inhoud["data"]
        except (OSError, ValueError, KeyError):
            pass
    laatste: Exception | None = None
    for poging in range(pogingen):
        try:
            r = await client().get(url, params=params)
            if r.status_code in (429, 502, 503, 504):
                raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            # Velden die niet verwerkt mogen worden (persoonsgegevens) gaan weg vóór er iets wordt
            # gecachet, getoond of doorgegeven.
            data = _verwijder(r.json(), verwijder_velden) if verwijder_velden else r.json()
            iso = nu_iso()
            _ophaaltijd[sleutel] = iso
            if ttl > 0:
                _cache[sleutel] = (nu + ttl, data)
            if schijf_ttl:
                try:
                    SCHIJFCACHE.mkdir(parents=True, exist_ok=True)
                    _schijfpad(sleutel).write_text(json.dumps({"t": time.time(), "iso": iso, "data": data}))
                except OSError:
                    pass
            return data
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            laatste = e
            await asyncio.sleep(0.5 * (2**poging))
    assert laatste is not None
    raise laatste


def leeg_cache() -> None:
    _cache.clear()
