"""What is left after the Hall of Fame (pure data + logic; no I/O) — information for the model, never a wall (#357).

`RUN_GOAL=completion` keeps a run going past the Hall of Fame; this module says what "complete" means and describes the remainder, ordered by what is available now.
The target is data: the Kanto Pokédex (151 caught) plus every side quest in `knowledge.story_beats` (and, later, the RetroAchievements list)."""
from knowledge import story_beats as sb

KANTO_DEX = 151
NATIONAL_DEX_FLAG = 0x840          # FLAG_SYS_NATIONAL_DEX (set by EnableNationalPokedex, with nationalMagic 0xB9 and VAR_NATIONAL_DEX 0x6258)
ONE_ISLAND_FLAG = 0x89B            # FLAG_WORLD_MAP_ONE_ISLAND: Oak's National Dex scene needs it (the Sevii Islands visited) AND 60 species caught, after the Hall of Fame
NATIONAL_DEX_CAUGHT = 60
GAME_CLEAR_FLAG = 0x82C            # FLAG_SYS_GAME_CLEAR

RUN_GOALS = ("hall_of_fame", "completion")


def open_side_quests(status: dict, ctx: sb.SideCtx) -> list[str]:
    """Keys of the side quests (not post-game) that are neither done nor out of reach: the ones a completion run still has to do."""
    sq = sb.side_quests(status, ctx)
    return [b.key for b in sq["now"] if b.tier == "side"] + [b.key for b, _why in sq["locked"] if b.tier == "side"]


def reached(game_clear: bool, dex_owned: int, status: dict, ctx: sb.SideCtx) -> bool:
    """The completion target: the Hall of Fame, the whole Kanto Pokédex and every side quest done."""
    return bool(game_clear) and dex_owned >= KANTO_DEX and not open_side_quests(status, ctx)


def post_game_text(dex_owned: int, national: bool, status: dict, ctx: sb.SideCtx) -> str:
    """The post-game briefing (one paragraph, information only): what is left, ordered by availability now."""
    parts = [f"POST-GAME (the game is cleared — nothing forces you to stop): Pokédex {dex_owned}/{KANTO_DEX} caught"]
    now = [b for b in sb.side_quests(status, ctx)["now"]]
    if now:
        parts.append("side quests open now: " + ", ".join(b.key for b in now[:6]) + (f" (+{len(now) - 6} more)" if len(now) > 6 else ""))
    left = len(open_side_quests(status, ctx)) - len([b for b in now if b.tier == "side"])
    if left > 0:
        parts.append(f"{left} more not open yet (quest() says why)")
    if not national:
        need = []
        if dex_owned < NATIONAL_DEX_CAUGHT:
            need.append(f"{NATIONAL_DEX_CAUGHT - dex_owned} more species caught")
        if ONE_ISLAND_FLAG not in ctx.flags:
            need.append("a visit to the Sevii Islands (One Island)")
        parts.append("the National Pokédex: talk to Prof. Oak once you have " + (" and ".join(need) if need else "everything it asks for — he is waiting in Pallet Town"))
    parts.append("the Sevii Islands, the legendaries (Moltres, Mewtwo) and the roaming beasts have no script yet — explore them yourself with go_to / fly_to")
    return "; ".join(parts) + "."
