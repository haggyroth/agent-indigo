"""link_trade on the real game (#363): from Viridian City the tool walks to the Pokémon Center's Cable Club, links a FireRed partner core (the user's FireRed ROM + a FireRed counter state) and trades
one of the player's Pokémon for a FireRed-only one — the exclusives are staged into the partner's party by `make_live_fixtures.py --only partner_firered_<n>`."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from game import link

LG_ROM = os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))
FR_ROM = os.path.expanduser(os.environ.get("FIRERED_ROM_PATH", "~/mgba-http/Pokemon_FireRed.gba"))
FR_STATE = os.path.expanduser(os.environ.get("FIRERED_STATE", "~/mgba-http/firered_trade_counter.ss0"))
ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(not (link.available() and all(os.path.exists(p) for p in (LG_ROM, FR_ROM, FR_STATE))),
                                reason="needs the link module, both ROMs and a FireRed counter state (FIRERED_STATE)")


@pytest.fixture
def partner_dir(live, tmp_path, monkeypatch):
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_live_fixtures.py"), "--only", "partner_firered_1,partner_firered_2", "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=600, env={**os.environ, "LIVE_DIR": str(live.dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    monkeypatch.setenv("PARTNER_FIRERED_DIR", str(tmp_path))
    return tmp_path


def _stage(live):
    live.load("threemon")                                                  # Viridian City, Bulbasaur L8 / Pikachu L5 / Caterpie L5
    live.set_flag(0x829)                                                   # the Pokédex
    live.set_var(0x407C, 2)                                                # the Cable Club's first-visit tutorial is over
    live.defeat_all_trainers()


def _trade(live, want, give="2"):
    outs = []
    for _ in range(6):
        live.repel()
        outs.append(live.c._execute("link_trade", json.dumps({"want": want, "give": give})))
        if "Traded" in outs[-1]:
            break
        if live.r.detect_context().name == "IN_BATTLE":                   # a wild encounter on the way (the tool stops at every one): run, then call again
            outs.append(live.c._execute("flee_battle", "{}"))
    return outs


@pytest.mark.parametrize("want", ["Ekans", "Electabuzz"])                  # one from each partner state (group 1 slot 1, group 2 slot 2)
def test_link_trade_gets_a_firered_exclusive_for_a_party_member(live, partner_dir, want):
    _stage(live)
    outs = _trade(live, want)
    assert any(o.startswith("Traded") for o in outs), outs
    party = [m.species_name for m in live.r.read_party()]
    assert party[:2] == ["Bulbasaur", want], party                          # the Pikachu slot now holds the exclusive
    assert "Pikachu" not in party                                          # and Pikachu stayed with the partner
    from game.constants import SPECIES_NAMES
    from knowledge.exclusives import FIRERED_ONLY
    from knowledge.movelearn import moves_at
    sid = next(s for s in FIRERED_ONLY if SPECIES_NAMES[s].title() == want)
    got = live.r.read_party()[1]
    assert (got.level, [m for m in got.move_ids if m]) == (FIRERED_ONLY[sid][0], moves_at(sid, FIRERED_ONLY[sid][0])), (got.level, got.move_ids)   # a wild one's level and level-up moves
    assert tuple(live.r.read_current_map()) == (5, 5)                                                         # back upstairs in Viridian's Pokémon Center


def test_link_trade_refuses_what_is_not_a_firered_exclusive(live, partner_dir):
    _stage(live)
    out = live.c._execute("link_trade", json.dumps({"want": "Sandshrew", "give": "2"}))
    assert "not a FireRed exclusive" in out and "Ekans" in out, out
    assert [m.species_name for m in live.r.read_party()][:2] == ["Bulbasaur", "Pikachu"]
