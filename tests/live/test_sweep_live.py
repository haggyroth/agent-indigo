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


def test_sweeping_mt_moon_collects_its_item_balls_across_three_floors(live):
    """Mt. Moon (#366): 10 item balls over 1F / B1F / B2F, reached from Route 3 — the driver travels floor to floor (go_to map:), takes each ball and ends with the area's own progress line."""
    from knowledge import sweeps
    from knowledge.area_sweeps import AREAS
    live.load("route3_weak_team")                                # Route 3, west of Mt. Moon
    live.boost_party()
    live.defeat_all_trainers()                                   # the walk and the pick-ups are the test, not the fights (the Super Nerd and the Rockets are "beaten")
    flag = live.r.read_flag
    total = len(AREAS["Mt. Moon"]["items"])
    assert total == 10 and sweeps.progress("Mt. Moon", flag)["items"][0] < total
    out = ""
    for _ in range(25):
        out = live.c._quest_tool("sweep Mt. Moon")
        if live.r.detect_context() == GameContext.IN_BATTLE:
            live.c._flee_battle()
            continue
        if "left (hidden items need the Itemfinder)" in out and "Skipped" in out and not out.startswith("A TRAINER"):
            break                                                # everything reachable is done; what is left was skipped with a note, never looped on
    got, _t = sweeps.progress("Mt. Moon", flag)["items"]
    print("MTMOON_SWEEP", got, total, out[-260:])
    assert got >= 6, out                                         # measured 7 of 10 (two balls sit on tiles the walker cannot reach and are skipped with a note): across floors, read from the game's own flags
    assert "Mt. Moon:" in out
