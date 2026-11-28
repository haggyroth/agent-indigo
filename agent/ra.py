"""Reads the game into the RetroAchievements progress (knowledge.ra_progress): the glue that answers one check spec from the reader. No I/O beyond what the reader already exposes (#358)."""
from agent.story import make_done_check, story_status
from knowledge import ra_progress, sweeps


def make_check(reader, ltm):
    """check(spec) -> bool for one spec of knowledge/ra_map.py."""
    done = make_done_check(reader, ltm)
    status = None
    tower = None

    def flag(n) -> bool:
        return bool(reader.read_flag(n))

    def check(spec) -> bool:
        nonlocal status, tower
        kind, value = spec
        if kind in ("flag", "item", "badge"):
            return done(spec)
        if kind == "trainer":
            return any(flag(f) for f in value)
        if kind == "caught":
            return bool(reader.read_dex_owned_national(value))
        if kind == "caught_any":
            return any(reader.read_dex_owned_national(n) for n in value)
        if kind == "dex_national":                       # at least this many national dex numbers registered as caught
            return (reader.read_dex_owned_count_national() or 0) >= value
        if kind == "stat":                               # a game stat reached a value: (constants/game_stat.h index, minimum)
            index, least = value
            return (reader.read_game_stat(index) or 0) >= least
        if kind == "fame_full":                          # the Fame Checker holds all 6 flavor texts of all 16 people
            return all(len(texts) == 6 for texts in reader.read_fame_checker().values())
        if kind == "rematch_top":                        # every VS Seeker ladder is at its top party
            from knowledge import rematches
            return rematches.status(flag)["at_top"] == len(rematches.REMATCHES)
        if kind == "tower":
            if tower is None:
                tower = reader.read_trainer_tower()
            return bool(tower[value]["prize"])
        if kind == "beat":
            if status is None:
                status = story_status(reader, ltm)
            return status.get(value) == "done"
        if kind in ("sweep", "sweep_trainers", "sweep_items"):
            prog = sweeps.progress(value, flag)
            if kind == "sweep_trainers":
                prog = {"trainers": prog["trainers"]}
            elif kind == "sweep_items":
                prog = {"items": prog["items"]}
            return sweeps.complete(prog, hidden=False)
        return False
    return check


def states(reader, ltm) -> dict:
    """{achievement id: 'yes' | 'probably' | 'no' | 'unknown'} for the whole set, from the live game."""
    return ra_progress.evaluate(make_check(reader, ltm))
