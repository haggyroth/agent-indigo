"""The RetroAchievements map and the local evaluator (#358) — pure."""
from knowledge import ra_progress
from knowledge.ra_map import CHECKS, MANUAL, PARTIAL
from knowledge.ra_set import ACHIEVEMENTS
from knowledge.area_sweeps import AREAS
from knowledge.story_beats import BY_KEY

KINDS = {"flag", "trainer", "item", "caught", "sweep", "sweep_trainers", "sweep_items", "beat", "badge", "tower"}


def test_every_achievement_is_mapped_or_manual_never_both():
    ids = {a[0] for a in ACHIEVEMENTS}
    assert set(CHECKS) | set(MANUAL) == ids and not set(CHECKS) & set(MANUAL)
    assert set(PARTIAL) <= set(CHECKS)                                      # only a mapped check can be partial


def test_every_spec_is_well_formed_and_points_at_something_real():
    for aid, specs in CHECKS.items():
        assert specs
        for kind, value in specs:
            assert kind in KINDS, (aid, kind)
            if kind in ("flag", "item", "caught"):
                assert isinstance(value, int) and value > 0
            elif kind == "trainer":
                assert value and all(isinstance(f, int) and 0x500 <= f <= 0x7FF for f in value), (aid, value)       # a trainer defeat flag
            elif kind.startswith("sweep"):
                assert value in AREAS, (aid, value)
            elif kind == "beat":
                assert value in BY_KEY, (aid, value)
            elif kind == "badge":
                assert 0 <= value <= 7
            elif kind == "tower":
                assert 0 <= value <= 3
            if kind == "caught":
                assert value <= 151                                          # the reader sees only the Kanto dex bits


def test_a_known_flag_matches_the_decomp_value():
    assert ("flag", 0x829) in CHECKS[541899]                                # FLAG_SYS_POKEDEX_GET
    assert ("flag", 0x840) not in CHECKS[541899]


def test_evaluate_needs_every_spec_and_reports_partial_manual_and_errors():
    everything = ra_progress.evaluate(lambda spec: True)
    assert everything[541899] == "yes" and everything[541937] == "probably" and everything[541985] == "unknown"
    nothing = ra_progress.evaluate(lambda spec: False)
    assert nothing[541899] == "no" and nothing[541985] == "unknown"
    only_one_of_two = ra_progress.evaluate(lambda spec: spec == ("flag", 0x239))        # Surf+Strength needs both HM flags
    assert only_one_of_two[541933] == "no"
    def boom(spec):
        raise RuntimeError("unreadable")
    assert ra_progress.evaluate(boom)[541899] == "no"                      # an unreadable state is 'no', never a crash


def test_totals_and_the_line_add_up():
    states = ra_progress.evaluate(lambda spec: spec[0] == "badge")
    t = ra_progress.totals(states)
    assert t["all"] == (128, 781) and sum(t[k][0] for k in ("yes", "probably", "no", "unknown")) == 128
    assert t["yes"][0] == 8 and t["yes"][1] == 80                          # the eight gym badges, 10 points each
    assert ra_progress.line(states).startswith("Achievements 8/128 (80/781 pts)")


def test_open_ones_lists_missables_first_and_leaves_out_the_done():
    states = ra_progress.evaluate(lambda spec: spec[0] == "badge")
    rows = ra_progress.open_ones(states)
    assert len(rows) == 120 and rows[0][4] == "missable"
    assert all(r[5] != "yes" for r in rows)
    first_non_missable = next(i for i, r in enumerate(rows) if r[4] != "missable")
    assert all(r[4] != "missable" for r in rows[first_non_missable:])


def _tick(flags, achievements, points, run=None):
    from types import SimpleNamespace
    reader = SimpleNamespace(read_flag=lambda n: n in flags, read_key_items=lambda: [], read_badges=lambda: (0, 0), read_dex_owned=lambda s: False,
                             read_trainer_tower=lambda: [{"prize": False}] * 4)
    ltm = SimpleNamespace(data={"achievements": achievements, "achievement_points": points, "milestones": []})
    return SimpleNamespace(run=run or SimpleNamespace(achv_sig=None, achv_seen=None), reader=reader, ltm=ltm)


def test_the_achievement_line_shows_the_baseline_once_then_only_unlocks():
    from agent import observation as obs
    t = _tick({0x829}, 1, 1)                                                       # the Pokédex is in hand
    first = obs._achievement_line(t)
    assert len(first) == 1 and first[0].startswith("Achievements 1/128") and "quest('achievements')" in first[0]
    assert obs._achievement_line(t) == []                                          # unchanged: silent
    unlocked = _tick({0x829, 0x240}, 2, 2, run=t.run)                              # + FLAG_GOT_OLD_ROD: 'A Stick, Some String, and Some Glue to Hold It Together'
    line = obs._achievement_line(unlocked)
    assert len(line) == 1 and line[0].startswith("★ Achievement unlocked") and "Some Glue to Hold It Together" in line[0] and "(+1)" in line[0] and "2/128" in line[0]
    assert obs._achievement_line(unlocked) == []
    drifted = _tick({0x829, 0x240}, 3, 3, run=t.run)                               # the journal moved but nothing new is held: no line
    assert obs._achievement_line(drifted) == []


def test_the_achievement_line_names_at_most_three_unlocks():
    from agent import observation as obs
    t = _tick({0x829}, 1, 1)
    obs._achievement_line(t)
    many = _tick({0x829, 0x240, 0x244, 0x255, 0x241, 0x271}, 6, 6, run=t.run)      # Old / Good / Super Rod, the Bike Voucher, the Bicycle
    line = obs._achievement_line(many)[0]
    assert line.count("(+") == 3 and "and 2 more" in line
