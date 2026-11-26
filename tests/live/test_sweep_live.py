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
