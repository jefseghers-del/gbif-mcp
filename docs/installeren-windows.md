# Installeren op Windows

> **Betaversie, zonder garantie.** De gebruiker is zelf verantwoordelijk voor het gebruik van de resultaten.
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

- **Eerste start.** Claude Desktop start de extensie op Windows meermaals tegelijk. Sinds versie
  0.6.1 installeert precies één proces de omgeving en wachten de andere (lockbestand
  `server/.bootstrap.lock`). Duurt de installatie langer dan Claude Desktop wil wachten, dan
  verschijnt "Request timed out"; de installatie loopt gewoon door en de volgende start werkt.
- **Startcommando.** Op Windows start de bundel met `python`, niet met `python3`: de installatie
  van python.org levert geen `python3.exe`, alleen die uit de Microsoft Store.
- **Geen echte `exec`.** De bootstrap start de server daarom als kindproces en geeft de exitcode
  door; op macOS en Linux vervangt hij het proces met `os.execve`.
- **Schijfcache** staat standaard in `%USERPROFILE%\.cache\gbif-mcp`. Met de omgevingsvariabele
  `GBIF_MCP_CACHE` zet u die elders.
- **PowerShell-uitvoeringsbeleid**: lukt `Activate.ps1` niet, gebruik dan
  `.\.venv\Scripts\activate.bat` in een gewone opdrachtprompt, of eenmalig
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
- **Lange paden**: klonen onder een kort pad (bv. `C:\dev\gbif-mcp`) voorkomt problemen met de
  260-tekenlimiet.
