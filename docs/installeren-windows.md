# Installeren op Windows

> **Betaversie, geen product, zonder garantie of aansprakelijkheid.** De gebruiker is zelf verantwoordelijk voor
> het gebruik van de resultaten.
> Zie de disclaimer in de [README](../README.md#disclaimer-en-privacy).

Twee wegen. De extensiebundel is de eenvoudigste; de git-route is bedoeld voor wie de code wil
volgen of aanpassen. Beide vereisen **Python 3.12 of hoger** (python.org of `winget install
Python.Python.3.12`), met "Add python.exe to PATH" aangevinkt.

De wheel in de bundel is platformonafhankelijk (`py3-none-any`); de dependencies worden bij de
eerste start van PyPI gehaald in de Windows-variant. Eén bundel werkt dus op macOS én Windows.

## Weg 1 — extensiebundel (Claude Desktop)

1. Haal `dist/be-biodiversiteit.mcpb` op (uit de repository, of van een collega).
2. Claude Desktop → Instellingen → Extensies → Geavanceerde instellingen → Extensie installeren.
3. Kies het `.mcpb`-bestand. De eerste start duurt ±1 minuut: de extensie maakt dan een eigen
   Python-omgeving aan (internet nodig). Daarna start ze direct.

Werkt het niet, klik dan op **View logs** en zoek de regels die met `[be-biodiversiteit]`
beginnen; die benoemen de oorzaak.

## Weg 2 — via git (Claude Code, of om te ontwikkelen)

De repository is privé; zorg dat `gh auth login` of een SSH-sleutel is ingesteld.

```powershell
git clone https://github.com/jefseghers-del/gbif-mcp.git
cd gbif-mcp
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[test]"
pytest -q
```

Aansluiten op Claude Code:

```powershell
claude mcp add be-biodiversiteit "C:\pad\naar\gbif-mcp\.venv\Scripts\gbif-mcp.exe"
```

Aansluiten op Claude Desktop zonder bundel: voeg dit toe aan
`%APPDATA%\Claude\claude_desktop_config.json` en herstart Claude Desktop.

```json
{
  "mcpServers": {
    "be-biodiversiteit": {
      "command": "C:\\pad\\naar\\gbif-mcp\\.venv\\Scripts\\gbif-mcp.exe"
    }
  }
}
```

Let op de dubbele backslashes in JSON.

Bijwerken:

```powershell
cd C:\pad\naar\gbif-mcp
git pull
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
```

Herstart daarna Claude Desktop of Claude Code.

## De bundel zelf bouwen op Windows

`mcpb-src/bouw.sh` is een zsh-script en draait niet op Windows. De stappen handmatig:

```powershell
cd C:\pad\naar\gbif-mcp
Remove-Item dist\gbif_mcp-*.whl, dist\gbif_mcp-*.tar.gz -ErrorAction SilentlyContinue
uv build
Remove-Item mcpb-src\wheels\gbif_mcp-*.whl -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force mcpb-src\wheels | Out-Null
Copy-Item dist\gbif_mcp-*-py3-none-any.whl mcpb-src\wheels\
npx --yes @anthropic-ai/mcpb validate mcpb-src\manifest.json
npx --yes @anthropic-ai/mcpb pack mcpb-src dist\be-biodiversiteit.mcpb
```

Vereist `uv` (`winget install astral-sh.uv`) en Node voor `npx`. Een bundel die op macOS is
gebouwd, werkt ongewijzigd op Windows: hem opnieuw bouwen is dus zelden nodig.

## Bekende aandachtspunten op Windows

- **Startcommando.** Op Windows start de bundel met `python`, niet met `python3`: de installatie
  van python.org levert geen `python3.exe`, alleen die uit de Microsoft Store.
- **Python uit de Microsoft Store.** Die Python leidt schrijfacties onder `AppData` om naar een
  eigen map (`...\Packages\PythonSoftwareFoundation.Python.3.1x_...\LocalCache`). Een bestand
  lezen op het gevraagde pad lukt dan wel, een proces starten niet; het log toont "Actual
  environment location may have moved". Sinds versie 0.9.1 volgt de bootstrap die omleiding (via
  `os.path.realpath`, zoals `venv` zelf) en meldt hij in het log dat Store-Python in gebruik is.
  De versie van python.org blijft de betrouwbaarste keuze.
- **Gelijktijdige starts.** Claude Desktop start de extensie vaak meermaals tegelijk, en sluit
  soms een instantie al na een fractie van een seconde weer af, ook als die net de installatie
  was begonnen. Precies één proces installeert de omgeving (lockbestand
  `server\.bootstrap.lock`); de andere wachten. Sinds versie 0.9.1 bewaart het slot de
  proces-ID's van de installeerder en van zijn pip-processen: zijn die allemaal gestopt, dan
  neemt een wachtend proces het slot meteen over (vroeger pas na 15 minuten, met "Request timed
  out" tot gevolg). Een slot ouder dan 15 minuten vervalt hoe dan ook.
- **Afgebroken installatie.** pip installeert niet atomair: een hard afgebroken pip kan een
  pakket half achterlaten, dat een volgende pip dan als "al geïnstalleerd" overslaat. Zolang de
  installatie loopt, staat er daarom een marker `server\.installatie_bezig`; vindt een volgende
  start die nog, dan bouwt hij de omgeving opnieuw op ("Een vorige installatie werd afgebroken"
  in het log).
- **Duurt de eerste installatie** langer dan Claude Desktop wil wachten, dan verschijnt "Request
  timed out"; de installatie loopt gewoon door en de volgende start werkt.
- **Geen echte `exec`.** De bootstrap start de server daarom als kindproces en geeft de exitcode
  door; op macOS en Linux vervangt hij het proces met `os.execve`.
- **Schijfcache** staat standaard in `%USERPROFILE%\.cache\gbif-mcp`. Met de omgevingsvariabele
  `GBIF_MCP_CACHE` zet u die elders.
- **Een oude installatie opruimen.** Lukt de eerste start blijvend niet: sluit Claude Desktop
  volledig af, verwijder de extensie, installeer ze opnieuw en wacht drie minuten. Gebruikte u
  Store-Python, verwijder dan ook de mappen `be-biodiversiteit` onder
  `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.1x_...\LocalCache\`.
- **PowerShell-uitvoeringsbeleid**: lukt `Activate.ps1` niet, gebruik dan
  `.\.venv\Scripts\activate.bat` in een gewone opdrachtprompt, of eenmalig
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
- **Lange paden**: klonen onder een kort pad (bv. `C:\dev\gbif-mcp`) voorkomt problemen met de
  260-tekenlimiet.
