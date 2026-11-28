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
    for name, dest in (("mt_moon_1f", (1, 1)), ("rock_tunnel_1f", (1, 81)), ("silph_co_1f", (1, 47)), ("victory_road_1f", (1, 39))):
        fresh.load(name)
        assert tuple(fresh.r.read_current_map()) == dest and fresh.r.detect_context().name == "OVERWORLD", (name, fresh.r.read_current_map())
    assert fresh.r.read_badges()[0] == 8                                                      # the last one loaded: Victory Road's 8 badges


def test_warp_to_lands_on_a_map_with_control_back_and_the_agents_own_walker_works_there(live):
    """#279: `Live.warp_to` writes the position + map and hands the callback to the game's loader: from indoors (where Fly is refused) to a cave, and the walk skill then moves the player."""
    import json
    live.load("threemon")
    home = tuple(live.r.read_current_map()), tuple(live.r.read_player_pos())
    live.warp_to((1, 1))                                                                        # Mt. Moon 1F, at its entrance
    assert tuple(live.r.read_current_map()) == (1, 1)
    x, y = live.r.read_player_pos()
    live.defeat_all_trainers()
    live.repel()
    outs = []
    for dx, dy in ((0, -3), (0, -2), (-3, 0), (3, 0)):                                          # whichever neighbouring tile is open ground
        outs.append(live.c._execute("walk_to", json.dumps({"x": x + dx, "y": y + dy})))
        if tuple(live.r.read_player_pos()) != (x, y):
            break
    assert tuple(live.r.read_player_pos()) != (x, y), outs
    live.warp_to(home[0], *home[1])                                                             # and back outdoors, on the very tile it started from
    assert (tuple(live.r.read_current_map()), tuple(live.r.read_player_pos())) == home
