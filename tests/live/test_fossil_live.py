"""quest('fossil') on the real game (#362): hand a fossil to the Cinnabar Lab scientist, walk out and back, and the revived Pokémon arrives."""
import json


def _staged(live, *fossils):
    """In Cinnabar Island, owning `fossils` (key -> (flag, item id))."""
    live.load("vermilion")
    live.fly_to("Cinnabar Island", key_items=tuple(item for _flag, item in fossils))
    for flag, _item in fossils:
        live.set_flag(flag)


def _run(live, what, rounds=8):
    out = ""
    for _ in range(rounds):
        out = live.c._execute("quest", json.dumps({"name": what, "auto_trainers": False}))
        if live.r.detect_context().name == "IN_BATTLE":
            live.c._flee_battle()
            continue
        if "Revived the" in out:
            break
    return out


def test_the_old_amber_is_revived_into_an_aerodactyl(live):
    _staged(live, (0x25E, 354))
    before = len(live.r.read_party())
    out = _run(live, "fossil amber")
    assert live.r.read_flag(0x2EE), out
    assert any(p.species_id == 142 for p in live.r.read_party()) or len(live.r.read_party()) == before, out
    assert 354 not in live.r.read_key_items()                                   # the Amber was handed over
    assert "already revived" in live.c._execute("quest", json.dumps({"name": "fossil amber"}))


def test_with_two_fossils_the_second_in_the_list_can_be_chosen(live):
    _staged(live, (0x273, 357), (0x25E, 354))                                   # a Helix Fossil and the Old Amber: the list is [Helix, Amber, No]
    out = _run(live, "fossil amber")
    assert live.r.read_flag(0x2EE) and not live.r.read_flag(0x2ED), out
    species = [p.species_id for p in live.r.read_party()]
    assert 142 in species and 138 not in species, species                         # the Aerodactyl, not the Omanyte the first row would have given
