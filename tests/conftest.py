"""Gedeelde testinstellingen. Geen netwerk: de dekkingsmodule krijgt standaard een opgeslagen
datasetbeschrijving (GBIF, dataset 280674cb…, opgehaald 7 oktober 2026) en een lege occurrence-respons."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATASET_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "gbif_dataset_280674cb.json").read_text())


@pytest.fixture(autouse=True)
def _dekking_zonder_netwerk(monkeypatch):
    from gbif_mcp import dekking

    async def nep_get_json(url, params=None, **kw):
        if "/dataset/" in url:
            return DATASET_FIXTURE
        return {"count": 0, "results": [], "facets": [], "endOfRecords": True}

    monkeypatch.setattr(dekking, "get_json", nep_get_json)
