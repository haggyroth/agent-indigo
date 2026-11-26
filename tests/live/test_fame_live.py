"""quest('fame') on the real game (#368): the Fame Checker is read from the save, and `fame go` walks to a sign and gets the entry."""


def test_the_fame_checker_reads_what_the_game_stored(live):
    live.load("post_hof")
    owned = live.r.read_fame_checker()
    assert owned[0] >= {1, 4}                                   # Oak #2 (the Pokédex scene) and #5 (Agatha's remark in the League) — both certain after the Hall of Fame
    assert owned[8] >= {1, 2}                                   # Blaine, from his Gym
    assert all(i < 6 for s in owned.values() for i in s)
    line = live.c._quest_tool("fame")
    assert "FAME CHECKER:" in line and "Missing, by person" in line


def test_fame_go_reads_a_sign_and_the_entry_arrives(live):
    live.load("post_hof")                                       # Pallet Town; Oak's Lab sign is the one open entry on this map
    live.c._advance_to_control()                                # (the fixture was saved mid-fade: the player ends up inside the house)
    assert 0 not in live.r.read_fame_checker()[0]
    out = live.c._quest_tool("fame go")
    assert 0 in live.r.read_fame_checker()[0], out
    assert "New entries: Oak #1" in out


def test_the_trainer_tower_records_read_from_the_save_without_a_prize_yet(live):
    live.load("post_hof")
    t = live.r.read_trainer_tower()
    assert len(t) == 4 and not any(x["prize"] for x in t)                      # nobody has been to Seven Island in the fixture
