"""quest('eevee') on the real game: from Celadon City up through the Mansion to the roof room and the free Eevee."""
import json


def test_quest_eevee_walks_to_the_roof_room_and_takes_the_eevee(live):
    live.load("vermilion")
    live.fly_to("Celadon City", flags=(0x2A6,))                       # in Celadon City (the Tea errand's flag is only there to satisfy the beat's prerequisite)
    c = live.c
    assert not live.r.read_flag(0x263)
    before = len(live.r.read_party())
    out = ""
    for _ in range(6):
        out = c._execute("quest", json.dumps({"name": "eevee", "auto_trainers": False}))
        if live.r.read_flag(0x263) or live.r.detect_context().name == "IN_BATTLE":
            if live.r.detect_context().name == "IN_BATTLE":
                c._flee_battle()
                continue
            break
    assert live.r.read_flag(0x263), out
    party = live.r.read_party()
    in_party = any(p.species_id == 133 for p in party)
    assert in_party or len(party) == before, (party, out)         # a full party sends it to the PC box instead
    assert "Eevee" in out
