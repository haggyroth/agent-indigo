"""tools/make_live_fixtures.py (#279): the recipes rebuild fixtures from work.sav with no model — each state loads and matches what its recipe promises."""
import os
import subprocess
import sys
from pathlib import Path

from live.harness import Live
from tools.make_live_fixtures import RECIPES

ROOT = Path(__file__).resolve().parents[2]


def test_the_fixture_recipes_generate_states_that_load_and_match_their_descriptions(live, tmp_path):
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "make_live_fixtures.py"), "--out", str(tmp_path)], capture_output=True, text=True, timeout=900, env={**os.environ, "LIVE_DIR": str(live.dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sorted(p.stem for p in tmp_path.glob("*.ss1")) == sorted(RECIPES)
    fresh = Live(live.rt, tmp_path)
    fresh.load("threemon")
    assert tuple(fresh.r.read_current_map()) == (3, 1) and [p.species_name for p in fresh.r.read_party()] == ["Bulbasaur", "Pikachu", "Caterpie"]
    fresh.load("vermilion")
    party = fresh.r.read_party()
    assert tuple(fresh.r.read_current_map()) == (3, 5) and (party[0].species_name, party[0].level) == ("Ivysaur", 30)
    assert 265 in set(fresh.r.read_key_items()) and fresh.r.read_badges()[0] == 2
    fresh.load("league_door")
    party = fresh.r.read_party()
    assert tuple(fresh.r.read_current_map()) == (3, 9) and len(party) == 6 and all(p.level == 70 for p in party) and fresh.r.read_badges()[0] == 8
