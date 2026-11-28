"""The FireRed exclusives (#363): the generated table, how the partner states deal them out, and that the tool's description names exactly them."""
from agent.skills.linkpartner import GROUP_SIZE, partner_groups, partner_slot
from agent.tools import TOOLS
from game.constants import SPECIES_NAMES
from knowledge.dex_sources import EVOLVES_FROM
from knowledge.exclusives import FIRERED_ONLY


def test_the_exclusives_are_the_seven_base_forms():
    assert sorted(SPECIES_NAMES[s].title() for s in FIRERED_ONLY) == ["Ekans", "Electabuzz", "Growlithe", "Oddish", "Psyduck", "Scyther", "Shellder"]
    assert not set(FIRERED_ONLY) & set(EVOLVES_FROM)                       # an evolved form is evolved, not traded for
    assert all(1 <= lv <= 100 and where for lv, where in FIRERED_ONLY.values())


def test_every_exclusive_has_one_slot_in_one_partner_state():
    groups = partner_groups()
    assert sorted(s for ids in groups.values() for s in ids) == sorted(FIRERED_ONLY)
    assert all(1 <= len(ids) <= GROUP_SIZE for ids in groups.values())
    for sid in FIRERED_ONLY:
        group, slot = partner_slot(sid)
        assert groups[group][slot - 1] == sid and 1 <= slot <= GROUP_SIZE   # slot 0 is the partner's own lead


def test_the_tool_description_names_every_exclusive():
    tool = next(t["function"] for t in TOOLS if t["function"]["name"] == "link_trade")
    for sid in FIRERED_ONLY:
        assert SPECIES_NAMES[sid].title() in tool["description"], sid


def test_a_wild_moveset_follows_the_game_level_up_order_and_drops_the_oldest():
    from game.constants import MOVE_NAMES
    from knowledge.movelearn import moves_at
    names = lambda sid, lv: [MOVE_NAMES[m] for m in moves_at(sid, lv)]       # noqa: E731
    assert names(1, 10) == ["Tackle", "Growl", "Leech Seed", "Vine Whip"]
    assert names(1, 15) == ["Leech Seed", "Vine Whip", "Poison Powder", "Sleep Powder"]    # two moves at 15: the oldest two make room
    assert moves_at(1, 0) == [] and moves_at(999, 50) == []


def test_every_exclusive_knows_something_at_the_level_it_is_found():
    from knowledge.movelearn import moves_at
    for sid, (lv, _where) in FIRERED_ONLY.items():
        assert 1 <= len(moves_at(sid, lv)) <= 4, sid
