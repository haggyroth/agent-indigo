"""walk_to opens a Strength-boulder puzzle on its own (#435): quest('moltres') from Vermilion crosses Mt. Ember's two-boulder exterior, the Summit Path and arrives at the summit."""
import json

from game.constants import Addr


def _setvar(live, n, v):
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VARS_OFFSET + 2 * (n - 0x4000), v)


def test_quest_moltres_pushes_through_the_mt_ember_boulders(live):
    import sys
    sys.path.insert(0, "tests/live")

    def _end_battle(live):
        """Flee a wild fight; win a trainer's with the lead's moves (the first is not damaging, so cycle)."""
        live.c._flee_battle()
        moves = ["Vine Whip", "Surf", "Rock Smash", "Tackle"]                   # whichever of these the active Pokémon knows hits; the rest are refused harmlessly
        for turn in range(40):
            if live.r.detect_context().name != "IN_BATTLE":
                break
            live.c._execute("use_move", json.dumps({"move": moves[turn % len(moves)]}))
        live.c._advance_to_control(tries=20)

    live.load("vermilion")
    live.league_ready(45)
    live.patch_mon(0, moves=[57, 70, 15, 249], pps=[15, 15, 30, 15])
    live.set_badges(0xFF)
    live.set_flag(0x89B)
    _setvar(live, 0x407E, 3)
    _setvar(live, 0x4076, 5)
    c = live.c
    out = ""
    for _ in range(120):
        live.repel()
        out = c._execute("quest", json.dumps({"name": "moltres", "auto_trainers": False}))
        if tuple(live.r.read_current_map()) == (1, 101):                        # MtEmber_Summit: Moltres' own battle is the next test's business
            break
        if live.r.detect_context().name == "IN_BATTLE":
            _end_battle(live)
    assert tuple(live.r.read_current_map()) == (1, 101), out                    # the walker pushed the boulders aside, went up the Summit Path and came out at the summit
    for _ in range(4):                                                           # …and the next call walks up to Moltres and hands the one-shot fight over
        if live.r.detect_context().name == "IN_BATTLE":
            break
        out = c._execute("quest", json.dumps({"name": "moltres", "auto_trainers": False}))
    assert live.r.detect_context().name == "IN_BATTLE", out
    foe = live.r.read_enemy_lead()
    assert (foe.species_name, foe.level) == ("Moltres", 50), foe
