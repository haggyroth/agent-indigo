"""quest('rematch') on the real game (#367): the VS Seeker's state, using the item from the Bag, and walking up to a flagged trainer to fight — on Route 3, east end."""
from game.constants import Addr
from game.state import GameContext


def _prepare(live):
    """On Route 3 with the VS Seeker in the Bag, fully charged, and every trainer beaten once (each ladder on its first rung)."""
    from knowledge.rematch_data import REMATCHES
    from knowledge.rematches import ladder
    live.load("route3_weak_team")
    live.defeat_all_trainers()
    for _name, _mp, tiers in REMATCHES:
        for _j, f in ladder(tiers)[1:]:
            live.set_flag(f, False)
    live.give_key_item(362)
    live.set_flag(0x292)
    live.m.write16(live.m.read32(Addr.SAVEBLOCK1_PTR) + Addr.VSSEEKER_STEPS_OFFSET, 100)


def test_the_vs_seeker_state_reads_what_the_game_holds(live):
    live.load("route3_weak_team")
    sb1 = live.m.read32(Addr.SAVEBLOCK1_PTR)
    live.m.write16(sb1 + Addr.VSSEEKER_STEPS_OFFSET, 37 | (12 << 8))
    live.m.write8(sb1 + Addr.VSSEEKER_TABLE_OFFSET + 5, 2)
    st = live.r.read_vs_seeker()
    assert st["bag_steps"] == 37 and st["charge_steps"] == 12 and st["ready"] == {5: 2}
    assert 0xFF not in live.r.read_objects_by_local() and 1 in live.r.read_objects_by_local()      # the NPC on screen is there, the player is not


def test_rematch_uses_the_item_and_reports_when_nobody_is_ready(live):
    _prepare(live)
    out = live.c._quest_tool("rematch")
    assert live.r.detect_context() == GameContext.OVERWORLD, out         # the "no trainers within range" message was dismissed
    assert "found nobody" in out or live.r.read_vs_seeker()["ready"], out


def test_rematch_walks_up_to_a_flagged_trainer_and_the_fight_starts(live):
    _prepare(live)
    JANICE = 7                                                           # Lass Janice, Route 3 (localId 7 at (19,9)): a three-team ladder, first rung beaten
    live.c._walk_to(22, 10)                                              # into view: the table only matters for NPCs on screen
    assert JANICE in live.r.read_objects_by_local()
    live.m.write8(live.m.read32(Addr.SAVEBLOCK1_PTR) + Addr.VSSEEKER_TABLE_OFFSET + JANICE, 1)      # what the item writes: this NPC wants her next team
    out = live.c._quest_tool("rematch")
    assert live.r.detect_context() == GameContext.IN_BATTLE, out
    assert live.m.read32(0x02022B4C) & 0x08, "a TRAINER battle"          # gBattleTypeFlags
    assert "play it" in out


def test_rematch_end_to_end_charge_use_and_fight(live):
    _prepare(live)
    live.m.write16(live.m.read32(Addr.SAVEBLOCK1_PTR) + Addr.VSSEEKER_STEPS_OFFSET, 100 - 5)   # five steps short: the driver walks them first
    live.c._walk_to(22, 10)                                              # the three-team ladders on Route 3 (Ben, Colton, Janice) are around here
    live.m.write16(live.m.read32(Addr.SAVEBLOCK1_PTR) + Addr.VSSEEKER_STEPS_OFFSET, 100 - 5)   # (the walk charged it): back to five short
    out = ""
    for _ in range(4):
        out = live.c._quest_tool("rematch")
        if live.r.detect_context() == GameContext.IN_BATTLE:
            break
    assert live.r.detect_context() == GameContext.IN_BATTLE, out
    assert live.m.read32(0x02022B4C) & 0x08
