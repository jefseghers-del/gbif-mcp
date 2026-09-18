# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""gbif-mcp: MCP-connector voor Belgische biodiversiteitsdata (GBIF + INBO Vlaams Biodiversiteitsportaal)."""

__version__ = "0.9.0"

# Eén bron voor de disclaimer en de privacyverklaring; README, handleiding, manifest, rapport en
# tool-antwoorden nemen deze teksten over. Wijzig ze hier, niet op de afzonderlijke plaatsen.
DISCLAIMER_KORT = (
    "Betaversie, geen product — zonder enige garantie en zonder aansprakelijkheid; de gebruiker is zelf "
    "verantwoordelijk voor het gebruik van de resultaten."
)

DISCLAIMER = (
    "Betaversie — geen product, geen garantie, geen aansprakelijkheid. Deze software is een experimenteel "
    "hulpmiddel in ontwikkeling, geen commercieel product of dienst. De software en de rapporten die ze maakt, "
    "worden kosteloos aangeboden zoals ze zijn, "
    "zonder enige uitdrukkelijke of stilzwijgende garantie, onder meer over juistheid, volledigheid, actualiteit "
    "of geschiktheid voor een bepaald doel. De resultaten zijn een geautomatiseerde bronnenscan van publieke "
    "databanken; ze vervangen geen terreininventarisatie, deskundige beoordeling of juridisch advies. De gebruiker "
    "is zelf volledig verantwoordelijk voor het controleren van de resultaten en voor elk gebruik dat ervan wordt "
    "gemaakt. De auteur is niet aansprakelijk voor schade die voortvloeit uit het gebruik van de software of de "
    "resultaten."
)

PRIVACY = (
    "Geen verwerking van persoonsgegevens van waarnemers. GBIF levert bij een waarneming ook de naam van de "
    "waarnemer en van wie de soort determineerde. De connector verwijdert die gegevens bij ontvangst, nog vóór ze "
    "worden bewaard, en neemt ze niet op in antwoorden, exports of rapporten."
)
