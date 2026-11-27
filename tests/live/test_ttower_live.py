"""quest('trainer_tower') on the real game (#369): to Seven Island, the lobby's scene, the climb floor by floor, and the Owner's prize."""
import json
import sys

from game.constants import Addr


def _setvar(live, n, v):
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VARS_OFFSET + 2 * (n - 0x4000), v)


def _stage(live):
    live.load("vermilion")
    live.league_ready(100)                                       # the Tower's trainers are set to the best level: a L100 team ends each fight in a hit or two
    live.boost_party(hp=900, stat=700)                           # the lone fixture Pokémon, made strong enough to outlast every floor's L100 team
    live.set_badges(0xFF)
    live.patch_mon(0, moves=[57, 76, 15, 89], pps=[15, 10, 30, 10])        # Surf (to the Tower across the water), Solar Beam / Earthquake for the fights
    _setvar(live, 0x407E, 3)
    _setvar(live, 0x4076, 5)


def _run(live, what, rounds=140):
    sys.path.insert(0, "tests/live")
    from test_sweep_live import _end_battle
    out = ""
    for _ in range(rounds):
        live.repel()
        out = live.c._execute("quest", json.dumps({"name": what, "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            _end_battle(live)
            continue
        if "Challenge complete" in out or "already won" in out or "Can't" in out:
            break
    return out


def test_the_tower_lists_the_prizes_and_asks_which_challenge_before_starting(live):
    live.load("vermilion")
    out = live.c._execute("quest", json.dumps({"name": "trainer_tower"}))
    assert "Trainer Tower prizes: 0/4" in out and "single|double|knockout|mixed" in out, out


def test_a_single_challenge_is_started_climbed_and_won(live):
    _stage(live)
    out = _run(live, "trainer_tower single")
    assert "Challenge complete" in out, out
    assert live.r.read_trainer_tower()[0]["prize"], out
    assert "already won" in live.c._execute("quest", json.dumps({"name": "trainer_tower single"}))
