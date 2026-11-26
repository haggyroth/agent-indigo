"""quest('old_amber') on the real game: from Pewter City through the museum's second door to the scientist and the free Old Amber."""
import json


def test_quest_old_amber_takes_the_amber_through_the_second_door(live):
    live.load("vermilion")
    live.fly_to("Pewter City")
    live.set_money(500)
    assert "Cut tree" in live.c._execute("quest", json.dumps({"name": "old_amber"}))       # nobody in the party knows Cut yet
    live.patch_mon(0, moves=[19, 15, 0, 0], pps=[15, 30, 0, 0])                          # Fly + Cut (the Cascade Badge is set by fly_to)
    c = live.c
    assert not live.r.read_flag(0x25E)
    out = ""
    for _ in range(6):
        out = c._execute("quest", json.dumps({"name": "old_amber", "auto_trainers": False}))
        if live.r.read_flag(0x25E):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._flee_battle()
    assert live.r.read_flag(0x25E), out
    assert 0 < len(live.r.read_key_items())
    assert live.r.read_money() == 500, "the right half of the museum needs no ticket"
    assert "already done" in c._execute("quest", json.dumps({"name": "old_amber"}))
