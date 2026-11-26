"""Reads the game's state into the story chain (knowledge.story_beats): which beats are done, which is next.

Pure glue — the only I/O is what the reader / long-term memory already expose (flags, key items, badge byte, milestones)."""
from knowledge import story_beats


def make_done_check(reader, ltm):
    """done_check(spec) -> bool for one done-spec of a Beat: ("flag", n) / ("item", id) / ("badge", bit) / ("milestone", name) / ("party", min size)."""
    items = None
    badges = None

    def check(spec) -> bool:
        nonlocal items, badges
        kind, value = spec
        try:
            if kind == "flag":
                return bool(reader.read_flag(value))
            if kind == "item":
                if items is None:
                    items = set(reader.read_key_items())
                return value in items
            if kind == "badge":
                if badges is None:
                    badges = int(reader.read_badges()[1])
                return bool(badges >> value & 1)
            if kind == "party":
                return len(reader.read_party()) >= value
            if kind == "milestone":
                return value in set(getattr(ltm, "data", {}).get("milestones", []))
        except Exception:
            return False
        return False
    return check


def story_status(reader, ltm, overrides=None) -> dict:
    """{beat key: 'done' | 'next' | 'blocked'} for the whole chain, from the live game. `overrides` = {key: bool} for beats whose driver
    has a stricter notion of done (Cut taught, Surf taught)."""
    return story_beats.evaluate(make_done_check(reader, ltm), overrides)


def side_ctx(reader):
    """What the side-quest gates read from the live game: badges, species caught, the Hall of Fame flag (any unreadable value counts as 'not yet')."""
    def safe(fn, default):
        try:
            return fn()
        except Exception:
            return default
    return story_beats.SideCtx(badges=safe(lambda: int(reader.read_badges()[0]), 0), owned=safe(lambda: int(reader.read_pokedex()[0]), 0),
                               game_clear=safe(lambda: bool(reader.read_flag(0x82C)), False))      # FLAG_SYS_GAME_CLEAR
