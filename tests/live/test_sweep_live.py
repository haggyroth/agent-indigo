"""quest('sweep <area>') on the real game (#366): Viridian Forest's four item balls from Viridian City, trainers already beaten, wild battles fled."""
from game.state import GameContext


def test_sweeping_viridian_forest_collects_every_item_ball(live):
    from knowledge import sweeps
    from knowledge.area_sweeps import AREAS
    live.load("threemon")                                       # Viridian City, Bulbasaur L8 / Pikachu L5 / Caterpie L5
    live.defeat_all_trainers()                                  # the test is about the walking and the picking up, not the fights
    flag = live.r.read_flag
    before = sweeps.progress("Viridian Forest", flag)
    assert before["items"][0] < before["items"][1]
    out = ""
    for _ in range(12):
        out = live.c._quest_tool("sweep Viridian Forest")
        if live.r.detect_context() == GameContext.IN_BATTLE:     # a wild encounter in the grass ends the call: play it (flee) and resume, like the model would
            live.c._flee_battle()
            continue
        if sweeps.progress("Viridian Forest", flag)["items"][0] == len(AREAS["Viridian Forest"]["items"]):
            break
    after = sweeps.progress("Viridian Forest", flag)
    assert after["items"][0] == after["items"][1] == 4, out      # every ball taken, read from the game's own flags
    assert "Viridian Forest:" in out and "every trainer and item ball is done" in out


def _end_battle(live) -> None:
    """What the model does with a fight the sweep handed back: flee a wild one, win a trainer's (a Rocket on B2F still fights) with the lead's first move."""
    import json
    if "Can't run" not in live.c._flee_battle() or live.r.detect_context() != GameContext.IN_BATTLE:
        return
    moves = [m for m in live.r.read_party()[0].move_names if m]
    for turn in range(16):
        if live.r.detect_context() != GameContext.IN_BATTLE:
            break
        live.c._execute("use_move", json.dumps({"move": moves[(turn + 1) % len(moves)]}))          # cycles the lead's moves: the first is Growl, a damaging one comes up
    live.c._advance_to_control(tries=20)


def test_sweeping_mt_moon_collects_its_item_balls_across_three_floors(live):
    """Mt. Moon (#366): 10 item balls over 1F / B1F / B2F, reached from Route 3 — the driver travels floor to floor (go_to map:), takes each ball and ends with the area's own progress line."""
    from knowledge import sweeps
    from knowledge.area_sweeps import AREAS
    live.load("route3_weak_team")                                # Route 3, west of Mt. Moon
    live.league_ready(40)                                        # every member L40, so a Repel (below) keeps Mt. Moon's L7-12 wild Pokémon away
    live.defeat_all_trainers()                                   # the walk and the pick-ups are the test, not the fights (the Super Nerd and the Rockets are "beaten")
    flag = live.r.read_flag
    total = len(AREAS["Mt. Moon"]["items"])
    assert total == 10 and sweeps.progress("Mt. Moon", flag)["items"][0] < total
    out = ""
    for _ in range(120):
        live.repel()                                             # (a test of the walk, not of Mt. Moon's encounter rate: wild fights are covered elsewhere)
        out = live.c._quest_tool("sweep Mt. Moon")
        if live.r.detect_context() == GameContext.IN_BATTLE:
            _end_battle(live)
            continue
        if "open field" in out:                                  # a dialogue / menu is up: the model would advance_dialog / close_menus
            print("STUCK", live.r.detect_context().name, live.r.read_current_map(), live.r.read_player_pos())
            live.c._advance_to_control(tries=20)
            continue
        if sweeps.progress("Mt. Moon", flag)["items"][0] >= total:
            break
    got, _t = sweeps.progress("Mt. Moon", flag)["items"]
    left = [(m, x, y) for f, m, x, y in AREAS["Mt. Moon"]["item_pos"] if not flag(f)]
    print("MTMOON_SWEEP", got, total, "LEFT", left, out[-200:])
    assert got == total, out                                     # all ten — including B2F's sealed corner room (entered by its ladder from B1F) and the balls a wild battle used to get skipped (#428)
    assert "Mt. Moon:" in out
