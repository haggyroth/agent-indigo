"""trade_evolve on the real game (#363): from Viridian City the tool walks to the Pokémon Center, climbs to the Cable Club, links a scripted partner core and brings the Pokémon back evolved —
Kadabra → Alakazam, Machoke → Machamp, Graveler → Golem, Haunter → Gengar."""
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
@pytest.mark.parametrize("species, evolved", [(64, "Alakazam"), (67, "Machamp"), (75, "Golem"), (93, "Gengar")])
def test_trade_evolve_evolves_at_the_cable_club(live, tmp_path, monkeypatch, species, evolved):
    from knowledge.growth import exp_for_level
    from knowledge.growth_data import GROWTH_RATE
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_live_fixtures.py"), "--only", "partner_counter", "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=600, env={**os.environ, "LIVE_DIR": str(live.dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    monkeypatch.setenv("PARTNER_STATE", str(tmp_path / "partner_counter.ss1"))
    live.load("threemon")                                                  # Viridian City, Bulbasaur L8 / Pikachu L5 / Caterpie L5
    live.set_flag(0x829)                                                   # the Pokédex
    live.set_var(0x407C, 2)                                                # the Cable Club's first-visit tutorial is over
    live.patch_mon(1, species=species, level=30, exp=exp_for_level(GROWTH_RATE.get(species, 0), 30), moves=[33, 0, 0, 0], pps=[35, 0, 0, 0])      # the Pikachu slot becomes the one to evolve
    live.defeat_all_trainers()
    before = [m.species_name for m in live.r.read_party()][:2]
    assert before[0] == "Bulbasaur" and before[1] != "Pikachu", before
    outs = []
    for _ in range(6):
        live.repel()
        outs.append(live.c._execute("trade_evolve", json.dumps({"pokemon": "2"})))
        if "evolved" in outs[-1]:
            break
        if live.r.detect_context().name == "IN_BATTLE":                   # a wild encounter on the way (the tool stops at every one): run, then call again
            outs.append(live.c._execute("flee_battle", "{}"))
    assert any(f"evolved into {evolved}" in o for o in outs), outs
    assert [m.species_name for m in live.r.read_party()][:2] == ["Bulbasaur", evolved]
    assert tuple(live.r.read_current_map()) == (5, 5)                      # back upstairs in Viridian's Pokémon Center
    out2 = live.c._execute("trade_evolve", json.dumps({"pokemon": "1"}))
    assert "does not evolve by trade" in out2, out2
