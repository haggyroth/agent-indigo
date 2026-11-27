"""quest('safari <species>') on the real game (#362): pay at the gate, walk to the species' area and stop at the first wild Pokémon, handing the Safari menu to the model."""
import json


def test_quest_safari_enters_walks_to_the_area_and_stops_at_a_wild_pokemon(live):
    live.load("vermilion")
    live.fly_to("Fuchsia City")
    live.set_money(2000)
    c = live.c
    assert "Safari Zone grass:" in c._execute("quest", json.dumps({"name": "safari"}))
    out = ""
    for _ in range(8):
        out = c._execute("quest", json.dumps({"name": "safari chansey", "auto_trainers": False}))
        if c._in_safari_battle():
            break
    assert c._in_safari_battle(), out
    assert "Safari Balls" in out and "safari('ball'" in out, out
    assert live.r.read_money() == 1500                           # the ¥500 entry fee, once
    assert tuple(live.r.read_current_map())[0] == 1 and tuple(live.r.read_current_map())[1] in (63, 64, 65, 66)
    # the model's move: run — and the next call carries on from inside (no second fee)
    c._execute("safari", json.dumps({"action": "run"}))
    out2 = c._execute("quest", json.dumps({"name": "safari chansey", "auto_trainers": False}))
    assert live.r.read_money() == 1500, out2
