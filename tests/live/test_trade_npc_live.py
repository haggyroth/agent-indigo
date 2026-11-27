"""quest('trade farfetchd') on the real game (#362): walk to Elyssa in Vermilion's second house, give the Spearow, get CH'DING the Farfetch'd."""
import json


def test_quest_trade_gives_the_spearow_for_the_farfetchd(live):
    live.load("vermilion")                                      # outside in Vermilion City, one Pokémon
    live.patch_mon(0, species=21)                               # make it the Spearow Elyssa wants (the stats stay the old ones; only the species matters to the trade)
    c = live.c
    party = live.r.read_party()
    assert [p.species_id for p in party] == [21]
    assert not live.r.read_flag(0x24D)
    assert "FARFETCH'D for a SPEAROW" in c._execute("quest", json.dumps({"name": "trade"}))
    out = ""
    for _ in range(6):
        out = c._execute("quest", json.dumps({"name": "trade farfetchd", "auto_trainers": False}))
        if live.r.read_flag(0x24D):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._flee_battle()
    assert live.r.read_flag(0x24D), out
    species = [p.species_id for p in live.r.read_party()]
    assert 83 in species and 21 not in species and len(species) == 1, (species, out)
    assert "already made the trade" in c._execute("quest", json.dumps({"name": "trade farfetchd"}))


def test_quest_trade_gives_a_nidoran_f_for_mr_nido_in_the_underground_path_house(live):
    live.load("vermilion")
    live.patch_mon(0, species=29)                                # a Nidoran F
    c = live.c
    assert [p.species_id for p in live.r.read_party()] == [29] and not live.r.read_flag(0x24B)
    out = ""
    for _ in range(8):
        out = c._execute("quest", json.dumps({"name": "trade nidoran", "auto_trainers": False}))
        if live.r.read_flag(0x24B):
            break
        if live.r.detect_context().name == "IN_BATTLE":
            c._flee_battle()
    assert live.r.read_flag(0x24B), out
    assert [p.species_id for p in live.r.read_party()] == [32], out          # MR. NIDO, a Nidoran M
