"""The opening of the game (before Oak's Pokédex): no shop()/grind() nudges, the parcel is pointed at, the closed Viridian Mart says so — all without an emulator."""
from types import SimpleNamespace as NS

import pytest

from knowledge import readiness as rd


def mon(hp=20, level=7):
    return NS(species_name="Bulbasaur", nickname="", level=level, current_hp=hp, max_hp=20, move_names=["Tackle"], pp=[35], move_ids=[33], species_id=1)


def test_before_the_pokedex_the_only_advice_is_to_heal():
    party = [mon()]
    open_game = rd.assess(party, balls=0, potions=0, money=3000, gyms_beaten=[], pokedex=True)
    opening = rd.assess(party, balls=0, potions=0, money=3000, gyms_beaten=[], pokedex=False)
    kinds = {n.code for n in open_game}
    assert {"shop", "catch", "level"} <= kinds                                  # the normal game nags about all of these…
    assert opening == []                                                         # …the opening does not (the Viridian Mart is closed, Oak gives the balls)
    hurt = rd.assess([mon(hp=3)], balls=0, potions=0, money=3000, gyms_beaten=[], pokedex=False)
    assert [n.code for n in hurt] == ["heal"] and hurt[0].level == "must"        # but a hurt lead is still worth a Pokémon Center


def test_pokedex_is_the_default_so_every_existing_caller_is_unchanged():
    assert rd.assess([mon()], balls=0, potions=0, money=3000, gyms_beaten=[]) == rd.assess([mon()], balls=0, potions=0, money=3000, gyms_beaten=[], pokedex=True)
    assert rd.FLAG_POKEDEX == 0x829


pytest.importorskip("openai")


def test_the_opening_line_points_at_oak_when_the_parcel_is_in_the_bag():
    from agent.observation import _opening_line
    carrying = _opening_line(NS(reader=NS(read_key_items=lambda: [349])))
    assert "OAK'S PARCEL is in your bag" in carrying and "quest('parcel')" in carrying and "do NOT shop() or grind()" in carrying
    fetching = _opening_line(NS(reader=NS(read_key_items=lambda: [])))
    assert fetching.startswith("OPENING:") and "quest('parcel')" in fetching


def test_shop_says_why_inside_the_closed_viridian_mart():
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    flags = set()
    c.reader = NS(read_current_map=lambda: (5, 3), read_flag=lambda f: f in flags)
    msg = c._shop("")
    assert "doesn't sell anything yet" in msg and "quest('parcel')" in msg
    assert "doesn't sell" in c._shop("Poke Ball", 5)                                # a specific item is refused the same way
    flags.add(0x829)
    assert c._viridian_mart_closed() == ""                                          # once Oak has the parcel the Mart is an ordinary one
    c.reader.read_current_map = lambda: (5, 2)
    flags.clear()
    assert c._viridian_mart_closed() == ""                                          # and any other map is untouched


def test_the_rival_fight_helper_leaves_other_battles_alone():
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(detect_context=lambda: NS(name="IN_BATTLE"), read_current_map=lambda: (3, 19))
    c._battle_settle = lambda **k: pytest.fail("a wild battle on Route 1 must not be auto-played")
    assert c._ng_battle("a wild Rattata") == "a wild Rattata"
