"""trade_evolve('Kadabra') on the real game (#363): from Viridian City the tool walks to the Pokémon Center, climbs to the Cable Club, links a scripted partner core and brings the Kadabra back as an Alakazam."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from game import link

ROM = os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not (link.available() and os.path.exists(ROM)), reason="needs the link module (python -m game._mgba_link_build), the main binding and the ROM")
def test_trade_evolve_turns_a_kadabra_into_an_alakazam_at_the_cable_club(live, tmp_path, monkeypatch):
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_live_fixtures.py"), "--only", "partner_counter", "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=600, env={**os.environ, "LIVE_DIR": str(live.dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    monkeypatch.setenv("PARTNER_STATE", str(tmp_path / "partner_counter.ss1"))
    live.load("threemon")                                                  # Viridian City, Bulbasaur L8 / Pikachu L5 / Caterpie L5
    live.set_flag(0x829)                                                   # the Pokédex
    live.set_var(0x407C, 2)                                                # the Cable Club's first-visit tutorial is over
    live.patch_mon(1, species=64, level=30, exp=125000, moves=[100, 93, 0, 0], pps=[20, 25, 0, 0])      # the Pikachu slot is a Kadabra now
    live.defeat_all_trainers()
    assert [m.species_name for m in live.r.read_party()][:2] == ["Bulbasaur", "Kadabra"]
    outs = []
    for _ in range(4):
        live.repel()
        outs.append(live.c._execute("trade_evolve", json.dumps({"pokemon": "2"})))
        if "evolved" in outs[-1] or live.r.detect_context().name == "IN_BATTLE":
            break
    assert any("evolved into Alakazam" in o for o in outs), outs
    assert [m.species_name for m in live.r.read_party()][:2] == ["Bulbasaur", "Alakazam"]
    assert tuple(live.r.read_current_map()) == (5, 5)                      # back upstairs in Viridian's Pokémon Center
    out2 = live.c._execute("trade_evolve", json.dumps({"pokemon": "1"}))
    assert "does not evolve by trade" in out2, out2
