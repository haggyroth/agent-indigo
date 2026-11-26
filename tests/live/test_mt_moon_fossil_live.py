"""quest('mt_moon_fossil') on the real game (#362): through Mt. Moon to the B2F fossils; the model's pick is taken, the other is gone."""
import json


def test_the_choice_is_the_models_and_the_dome_fossil_is_taken(live):
    live.load("route3_weak_team")                               # Route 3, west of Mt. Moon, no fossil yet
    live.boost_party()
    live.defeat_all_trainers()                                  # the dungeon's trainers (and the Super Nerd) are beaten: this test is about the walk and the pick
    c = live.c
    assert not live.r.read_flag(0x232)
    ask = c._execute("quest", json.dumps({"name": "mt_moon_fossil"}))
    assert "Choose: quest('mt_moon_fossil dome')" in ask and not live.r.read_flag(0x232)       # nothing was taken: the pick is the model's
    out = ""
    for _ in range(14):
        out = c._execute("quest", json.dumps({"name": "mt_moon_fossil dome", "auto_trainers": False}))
        if live.r.read_flag(0x232):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._flee_battle()
    assert live.r.read_flag(0x232), out
    assert live.r.read_flag(0x272) and not live.r.read_flag(0x273), out                       # the Dome Fossil, not the Helix
    assert "already done" in c._execute("quest", json.dumps({"name": "mt_moon_fossil helix"}))
