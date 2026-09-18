#!/usr/bin/env python3
"""Bootstrap-entry voor de MCPB-bundel van gbif-mcp (Claude Desktop).

Bouwt bij de eerste start een eigen venv naast de bundel en installeert daarin de
meegeleverde gbif-mcp-wheel (dependencies bevatten Python-minorversie-gebonden binaries,
zoals pydantic-core, dus een vooraf gebundelde lib zou alleen op exact dezelfde Python
werken). Daarna is elke start direct. Bij een nieuwe bundelversie wordt de venv bijgewerkt.

Werkt op macOS, Linux en Windows: de meegeleverde wheel is platformonafhankelijk
(py3-none-any) en de dependencies komen bij de eerste start van PyPI, dus in de juiste
variant voor het besturingssysteem. Alleen de paden binnen de venv verschillen.

Gelijktijdige starts. Claude Desktop start de extensie vaak meermaals tegelijk (het gewone
gesprek én de gedeelde pool voor Cowork- en Code-sessies). Zonder afspraak probeerden die
processen dezelfde venv tegelijk aan te maken, wat op Windows faalde met FileExistsError en
een half geïnstalleerde omgeving. Een lockbestand zorgt er nu voor dat precies één proces
installeert; de andere wachten tot de omgeving klaar is.

Stdio-hygiëne: stdout is het MCP-kanaal; alle bootstrap-uitvoer gaat naar stderr.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WINDOWS = sys.platform == "win32"
HIER = Path(__file__).resolve().parent
VENV = HIER / "venv"
VENV_PY = VENV / ("Scripts/python.exe" if WINDOWS else "bin/python")
WHEEL_SENTINEL = HIER / ".wheel_ok"
SLOT = HIER / ".bootstrap.lock"
SLOT_VERLOOPT_S = 15 * 60  # een slot ouder dan dit is achtergelaten door een afgebroken proces
NAAM = "be-biodiversiteit"
PIP_OPTIES = ("--quiet", "--disable-pip-version-check", "--no-input", "--prefer-binary")


def _meld(boodschap: str) -> None:
    print(f"[{NAAM}] {boodschap}", file=sys.stderr, flush=True)


def _fout(boodschap: str) -> None:
    _meld(boodschap)
    sys.exit(1)


def _bundelwheel() -> Path:
    wheels = sorted((HIER.parent / "wheels").glob("gbif_mcp-*.whl"))
    if not wheels:
        _fout("de gbif-mcp-wheel ontbreekt in de bundel — bundel opnieuw bouwen.")
    if len(wheels) > 1:
        _fout(f"meer dan één wheel in de bundel ({', '.join(w.name for w in wheels)}) — bundel opnieuw bouwen.")
    return wheels[0]


def _pip(*argumenten: str) -> int:
    return subprocess.run([str(VENV_PY), "-m", "pip", *argumenten], stdout=sys.stderr, stderr=sys.stderr).returncode


def _heeft_module(module: str) -> bool:
    """Is de module installeerbaar gevonden, ZONDER haar te importeren?

    Een echte import van gbif_mcp laadt shapely, pyproj, pydantic en mcp; op Windows kost dat
    bij de eerste keer tientallen seconden (pyc-compilatie, virusscanner). Die import gebeurde
    vroeger twee keer per start. find_spec kijkt alleen of het pakket er staat."""
    code = f"import importlib.util,sys; sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
    return subprocess.run([str(VENV_PY), "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def _zorg_voor_pip() -> bool:
    """Claude Desktop maakt de venv zelf aan (zonder pip); zet pip erin via ensurepip."""
    if _heeft_module("pip"):
        return True
    _meld("pip ontbreekt in de omgeving; wordt toegevoegd (ensurepip).")
    return subprocess.run([str(VENV_PY), "-m", "ensurepip", "--upgrade"], stdout=sys.stderr, stderr=sys.stderr).returncode == 0


def _klaar(wheel: Path) -> bool:
    try:
        return VENV_PY.exists() and WHEEL_SENTINEL.read_text().strip() == wheel.name
    except OSError:
        return False


class _Slot:
    """Exclusief lockbestand, zonder afhankelijkheden, werkt op elk besturingssysteem.

    `os.O_EXCL` maakt het aanmaken atomair: van twee gelijktijdige processen slaagt er precies één.
    Wie het slot niet krijgt, wacht tot het vrijkomt."""

    def __init__(self) -> None:
        self.fd: int | None = None

    def probeer(self) -> bool:
        try:
            self.fd = os.open(str(SLOT), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, f"{os.getpid()} {time.time():.0f}\n".encode())
            return True
        except FileExistsError:
            try:
                if time.time() - SLOT.stat().st_mtime > SLOT_VERLOOPT_S:
                    _meld("verlopen installatieslot gevonden; wordt opgeruimd.")
                    SLOT.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def los(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        SLOT.unlink(missing_ok=True)


def _maak_venv() -> None:
    import venv

    try:
        # Zonder pip: venv's eigen ensurepip-oproep faalde op Windows wanneer Claude Desktop de
        # map al had aangemaakt. _zorg_voor_pip doet dat daarna afzonderlijk en robuust.
        venv.create(VENV, with_pip=False)
    except FileExistsError:
        pass  # map bestond al (door Claude Desktop aangemaakt); de interpreter volgt hieronder
    if not VENV_PY.exists():
        venv.EnvBuilder(with_pip=False, clear=False, upgrade=True).create(VENV)


def _installeer(wheel: Path, eerste_keer: bool) -> None:
    """Enkel aanroepen met het slot in handen."""
    if eerste_keer:
        _meld("Eerste start: lokale omgeving wordt aangemaakt (eenmalig, 1 à 3 minuten, vergt internet).")
        if not VENV_PY.exists():
            _maak_venv()
    else:
        _meld(f"Nieuwe versie in de bundel ({wheel.name}); de lokale omgeving wordt bijgewerkt.")
    if not _zorg_voor_pip():
        shutil.rmtree(VENV, ignore_errors=True)
        _fout("pip kon niet in de omgeving worden gezet. Start Claude Desktop opnieuw; lukt het dan niet, "
              "installeer Python opnieuw via python.org.")
    if eerste_keer:
        ok = _pip("install", *PIP_OPTIES, str(wheel)) == 0
    else:
        ok = (_pip("install", *PIP_OPTIES, "--upgrade", str(wheel)) == 0
              and _pip("install", *PIP_OPTIES, "--force-reinstall", "--no-deps", str(wheel)) == 0)
    if not ok:
        if eerste_keer:
            WHEEL_SENTINEL.unlink(missing_ok=True)
            _fout("installatie mislukt. De eerste start vergt een internetverbinding (dependencies van PyPI); "
                  "start Claude Desktop daarna opnieuw.")
        _meld("Bijwerken mislukt; de server start met de vorige versie.")
        return
    WHEEL_SENTINEL.write_text(wheel.name + "\n")
    _meld("Omgeving klaar." if eerste_keer else "Bijgewerkt.")


def _zorg_voor_omgeving(wheel: Path) -> None:
    # Snel pad: alles staat er al.
    if _klaar(wheel) and _heeft_module("gbif_mcp"):
        return
    slot = _Slot()
    gewacht = False
    begin = time.time()
    while not slot.probeer():
        if not gewacht:
            _meld("Een ander proces zet de omgeving klaar; even wachten.")
            gewacht = True
        time.sleep(1.0)
        if _klaar(wheel) and not SLOT.exists():
            return  # het andere proces is klaar
        if time.time() - begin > SLOT_VERLOOPT_S + 60:
            _fout("wachten op de installatie duurde te lang. Start Claude Desktop opnieuw.")
    try:
        # Opnieuw kijken: misschien heeft een ander proces het werk gedaan terwijl we wachtten.
        if _klaar(wheel) and _heeft_module("gbif_mcp"):
            return
        eerste_keer = not (VENV_PY.exists() and WHEEL_SENTINEL.exists() and _heeft_module("gbif_mcp"))
        _installeer(wheel, eerste_keer=eerste_keer)
    finally:
        slot.los()


def main() -> None:
    if sys.version_info < (3, 12):
        _fout(f"Python 3.12 of hoger is vereist (gevonden: {sys.version.split()[0]}). Installeer een recente Python via python.org.")
    wheel = _bundelwheel()
    _zorg_voor_omgeving(wheel)
    argumenten = [str(VENV_PY), "-m", "gbif_mcp.server"]
    if WINDOWS:
        # Windows kent geen echte exec: het proces zou worden vervangen door een nieuw proces met
        # een eigen PID, wat de pipes van Claude Desktop verbreekt. Daarom als kindproces draaien
        # met overgeërfde stdio, en de exitcode doorgeven.
        sys.exit(subprocess.run(argumenten, env=os.environ.copy()).returncode)
    os.execve(str(VENV_PY), argumenten, os.environ.copy())


if __name__ == "__main__":
    main()
