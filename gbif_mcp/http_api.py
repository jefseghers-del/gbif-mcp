# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Dunne REST-schil rond dezelfde tools, voor een latere webinterface voor collega's.

Elke tool is bereikbaar als POST /tools/<naam> met een JSON-body met de tool-parameters, en
GET /tools geeft de lijst met beschrijvingen en JSON-schema's. Geen authenticatie: bedoeld voor
een intern netwerk of achter een reverse proxy.

Draaien:  gbif-mcp-http  (standaard 127.0.0.1:8765; GBIF_MCP_HOST / GBIF_MCP_PORT)
"""
from __future__ import annotations

import inspect
import os

import uvicorn
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import server

TOOLS = {
    naam: fn
    for naam, fn in (
        ("zoek_soort", server.zoek_soort),
        ("soort_status", server.soort_status),
        ("waarnemingen", server.waarnemingen),
        ("soorten_in_gebied", server.soorten_in_gebied),
        ("telling_in_gebied", server.telling_in_gebied),
        ("gebieden_rond", server.gebieden_rond),
        ("kaart_gebieden", server.kaart_gebieden),
        ("exporteer_bevraging", server.exporteer_bevraging),
        ("datarapport_natuur", server.datarapport_natuur),
        ("lijst", server.lijst),
        ("geocodeer_adres", server.geocodeer_adres),
        ("dataset_info", server.dataset_info),
        ("bronnen", server.bronnen),
    )
}


def _dump(x):
    if isinstance(x, BaseModel):
        return x.model_dump(mode="json")
    if isinstance(x, list):
        return [_dump(i) for i in x]
    return x


async def lijst_tools(_: Request) -> JSONResponse:
    tools = await server.mcp.list_tools()
    return JSONResponse([{"naam": t.name, "beschrijving": t.description, "schema": t.inputSchema} for t in tools])


async def roep_tool(request: Request) -> JSONResponse:
    naam = request.path_params["naam"]
    fn = TOOLS.get(naam)
    if fn is None:
        return JSONResponse({"fout": f"onbekende tool '{naam}'"}, status_code=404)
    try:
        body = await request.json() if await request.body() else {}
    except ValueError:
        return JSONResponse({"fout": "ongeldige JSON"}, status_code=400)
    try:
        uit = fn(**body)
        if inspect.isawaitable(uit):
            uit = await uit
    except (TypeError, ValueError) as e:
        return JSONResponse({"fout": str(e)}, status_code=400)
    except Exception as e:  # bronfout: benoemen, niet verbergen
        return JSONResponse({"fout": f"{type(e).__name__}: {e}"}, status_code=502)
    return JSONResponse(_dump(uit))


app = Starlette(routes=[Route("/tools", lijst_tools), Route("/tools/{naam}", roep_tool, methods=["POST"])])


def main() -> None:
    uvicorn.run(app, host=os.environ.get("GBIF_MCP_HOST", "127.0.0.1"), port=int(os.environ.get("GBIF_MCP_PORT", "8765")))


if __name__ == "__main__":
    main()
