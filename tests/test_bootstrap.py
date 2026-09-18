# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de bootstrap van de MCPB-bundel (mcpb-src/server/main.py), zonder netwerk.

De echte Windows-paden (Store-Python, OpenProcess) kunnen op macOS niet worden uitgevoerd;
de logica errond wordt hier wel getoetst, met een symlink als nabootsing van de omleiding.
De volledige installatie met gelijktijdige starts wordt apart getest op een uitgepakte bundel.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

MAIN = Path(__file__).parent.parent / "mcpb-src" / "server" / "main.py"


@pytest.fixture()
def boot(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bundel_main", MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "SLOT", tmp_path / ".bootstrap.lock")
    return module


def _dood_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# -- slot ------------------------------------------------------------------------------------
def test_proces_leeft(boot):
    assert boot._proces_leeft(os.getpid()) is True
    assert boot._proces_leeft(_dood_pid()) is False
    assert boot._proces_leeft(0) is False


def test_slot_van_gestopt_proces_wordt_meteen_overgenomen(boot):
    boot.SLOT.write_text(f"{_dood_pid()} {time.time():.0f}\n")
    slot = boot._Slot()
    assert slot.probeer() is False  # ruimt het achtergelaten slot op
    assert slot.probeer() is True
    slot.los()
    assert not boot.SLOT.exists()


def test_slot_van_levend_proces_blijft_staan(boot):
    boot.SLOT.write_text(f"{os.getpid()} {time.time():.0f}\n")
    assert boot._Slot().probeer() is False
    assert boot.SLOT.exists()


def test_te_oud_slot_vervalt_ook_bij_levend_proces(boot):
    boot.SLOT.write_text(f"{os.getpid()} 0\n")
    oud = time.time() - boot.SLOT_VERLOOPT_S - 10
    os.utime(boot.SLOT, (oud, oud))
    slot = boot._Slot()
    assert slot.probeer() is False
    assert slot.probeer() is True
    slot.los()


def test_leeg_slot_is_niet_achtergelaten(boot):
    # Net aangemaakt door een ander proces dat zijn PID nog niet schreef: niet afpakken.
    boot.SLOT.write_text("")
    assert boot._Slot().probeer() is False
    assert boot.SLOT.exists()


def test_met_slot_doet_niets_als_alles_klaar_is(boot):
    uitgevoerd = []
    boot._met_slot(klaar=lambda: True, werk=lambda: uitgevoerd.append(1))
    assert uitgevoerd == []
    assert not boot.SLOT.exists()


def test_met_slot_neemt_slot_van_gestopt_proces_over_en_ruimt_op(boot):
    boot.SLOT.write_text(f"{_dood_pid()} {time.time():.0f}\n")
    uitgevoerd = []
    boot._met_slot(klaar=lambda: bool(uitgevoerd), werk=lambda: uitgevoerd.append(1))
    assert uitgevoerd == [1]
    assert not boot.SLOT.exists()


def test_slot_blijft_staan_zolang_kindproces_leeft(boot):
    # De bootstrap is hard gestopt, maar zijn pip loopt als wees door: niet overnemen.
    boot.SLOT.write_text(f"{_dood_pid()} {time.time():.0f}\n{os.getpid()}\n")
    assert boot._Slot().probeer() is False
    assert boot.SLOT.exists()


def test_slot_vervalt_als_eigenaar_en_kindprocessen_gestopt_zijn(boot):
    boot.SLOT.write_text(f"{_dood_pid()} {time.time():.0f}\n{_dood_pid()}\n{_dood_pid()}\n")
    slot = boot._Slot()
    assert slot.probeer() is False
    assert slot.probeer() is True
    slot.los()


def test_draai_noteert_kindproces_in_slot(boot):
    slot = boot._Slot()
    assert slot.probeer() is True
    assert boot._draai([sys.executable, "-c", "pass"]) == 0
    regels = boot.SLOT.read_text().splitlines()
    assert regels[0].split()[0] == str(os.getpid())
    assert len(regels) == 2 and int(regels[1]) != os.getpid()
    slot.los()


# -- afgebroken installatie ------------------------------------------------------------------
@pytest.fixture()
def installatie(boot, tmp_path, monkeypatch):
    """Bootstrap met venv, sentinel en marker in tmp_path, en zonder echte pip."""
    monkeypatch.setattr(boot, "WINDOWS", False)
    monkeypatch.setattr(boot, "VENV", tmp_path / "venv")
    monkeypatch.setattr(boot, "WHEEL_SENTINEL", tmp_path / ".wheel_ok")
    monkeypatch.setattr(boot, "BEZIG", tmp_path / ".installatie_bezig")

    def maak_venv():
        (boot.VENV / "bin").mkdir(parents=True, exist_ok=True)
        (boot.VENV / "bin" / "python").write_text("")

    boot.pip_oproepen = []
    monkeypatch.setattr(boot, "_maak_venv", maak_venv)
    monkeypatch.setattr(boot, "_zorg_voor_pip", lambda: True)
    monkeypatch.setattr(boot, "_heeft_module", lambda module: True)
    monkeypatch.setattr(boot, "_pip", lambda *a: boot.pip_oproepen.append(a) or 0)
    return boot


def test_afgebroken_installatie_bouwt_venv_opnieuw_op(installatie, tmp_path):
    boot = installatie
    boot._maak_venv()
    rest = boot.VENV / "lib" / "numpy-2.5.3.dist-info"  # half geïnstalleerd pakket
    rest.mkdir(parents=True)
    boot.WHEEL_SENTINEL.write_text("gbif_mcp-0.9.0-py3-none-any.whl\n")
    boot.BEZIG.write_text("12345\n")
    wheel = tmp_path / "gbif_mcp-0.9.1-py3-none-any.whl"
    boot._installeer(wheel)
    assert not rest.exists()
    assert boot.pip_oproepen == [("install", *boot.PIP_OPTIES, str(wheel))]
    assert boot.WHEEL_SENTINEL.read_text().strip() == wheel.name
    assert not boot.BEZIG.exists()


def test_venv_van_claude_desktop_zonder_marker_blijft_staan(installatie, tmp_path):
    boot = installatie
    boot._maak_venv()
    eigen = boot.VENV / "pyvenv.cfg"
    eigen.write_text("")
    boot._installeer(tmp_path / "gbif_mcp-0.9.1-py3-none-any.whl")
    assert eigen.exists()
    assert not boot.BEZIG.exists()


def test_mislukte_eerste_installatie_laat_marker_staan(installatie, tmp_path, monkeypatch):
    boot = installatie
    monkeypatch.setattr(boot, "_pip", lambda *a: 1)
    with pytest.raises(SystemExit):
        boot._installeer(tmp_path / "gbif_mcp-0.9.1-py3-none-any.whl")
    assert boot.BEZIG.exists()  # de volgende start begint opnieuw
    assert not boot.WHEEL_SENTINEL.exists()


def test_mislukte_update_houdt_vorige_versie(installatie, tmp_path, monkeypatch):
    boot = installatie
    boot._maak_venv()
    boot.WHEEL_SENTINEL.write_text("gbif_mcp-0.9.0-py3-none-any.whl\n")
    monkeypatch.setattr(boot, "_pip", lambda *a: 1)
    boot._installeer(tmp_path / "gbif_mcp-0.9.1-py3-none-any.whl")
    assert boot.WHEEL_SENTINEL.read_text().strip() == "gbif_mcp-0.9.0-py3-none-any.whl"
    assert not boot.BEZIG.exists()


# -- venv-pad en Store-Python ----------------------------------------------------------------
def test_venv_pad_windows_volgt_de_omleiding(boot, tmp_path, monkeypatch):
    # Nabootsing van Store-Python: het gevraagde pad verwijst naar een andere echte locatie.
    echt = tmp_path / "LocalCache" / "venv"
    (echt / "Scripts").mkdir(parents=True)
    (echt / "Scripts" / "python.exe").write_text("")
    gevraagd = tmp_path / "bundel" / "venv"
    gevraagd.parent.mkdir()
    gevraagd.symlink_to(echt, target_is_directory=True)
    monkeypatch.setattr(boot, "WINDOWS", True)
    monkeypatch.setattr(boot, "VENV", gevraagd)
    assert boot._venv_py() == Path(os.path.realpath(echt / "Scripts" / "python.exe"))


def test_venv_pad_windows_zonder_venv_blijft_het_gevraagde_pad(boot, tmp_path, monkeypatch):
    monkeypatch.setattr(boot, "WINDOWS", True)
    monkeypatch.setattr(boot, "VENV", tmp_path / "venv")
    assert boot._venv_py() == tmp_path / "venv" / "Scripts" / "python.exe"


def test_venv_pad_macos_volgt_de_symlink_niet(boot, tmp_path, monkeypatch):
    # Op macOS/Linux is bin/python een symlink naar de basis-Python: niet oplossen.
    monkeypatch.setattr(boot, "WINDOWS", False)
    monkeypatch.setattr(boot, "VENV", tmp_path / "venv")
    assert boot._venv_py() == tmp_path / "venv" / "bin" / "python"


def test_store_python_herkend(boot, monkeypatch):
    store = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
    monkeypatch.setattr(boot, "WINDOWS", True)
    monkeypatch.setattr(boot.sys, "executable", store)
    assert boot._is_store_python() is True
    monkeypatch.setattr(boot, "WINDOWS", False)
    assert boot._is_store_python() is False
