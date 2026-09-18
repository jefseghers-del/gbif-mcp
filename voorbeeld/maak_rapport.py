"""Bouw een datarapport natuur opnieuw uit een bewaarde JSON-bevraging.

Het sjabloon zelf zit in de connector (gbif_mcp/rapport.py); in Claude gebruikt u gewoon de tool
`datarapport_natuur` of het prompt-sjabloon met dezelfde naam. Dit script is er voor wie een
eerder bewaarde bevraging opnieuw wil opmaken, bv. na een wijziging aan het sjabloon.

Gebruik:  python voorbeeld/maak_rapport.py bevraging.json rapport.pdf
"""
import json
import sys

from gbif_mcp.rapport import schrijf_pdf

if __name__ == "__main__":
    bron, doel = sys.argv[1], sys.argv[2]
    print(schrijf_pdf(json.load(open(bron, encoding="utf-8")), doel))
