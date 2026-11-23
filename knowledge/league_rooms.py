"""The Elite Four's rooms (pure data): once inside, the door seals behind you.

From the decomp (PokemonLeague_*): entering a room plays a forced walk up and the door closes — no Pokémon Center, no leaving, no shop, until the Champion falls (the exit warp of
each room opens only when its trainer is beaten). The only heal is the Bag; a whiteout resets the League (every FLAG_DEFEATED_* cleared) and respawns the party, healed, at the
Plateau's Pokémon Center with the levels they earned."""

LEAGUE_ROOMS: dict[tuple[int, int], str] = {
    (1, 75): "Lorelei",
    (1, 76): "Bruno",
    (1, 77): "Agatha",
    (1, 78): "Lance",
    (1, 79): "the Champion",
}
LEAGUE_ROOM_MAPS = frozenset(LEAGUE_ROOMS)
# room -> the key knowledge.gym_advice.brief() knows the trainer by (the Champion's team depends on your starter: the brief names the shared core)
LEAGUE_TRAINER = {(1, 75): "Lorelei", (1, 76): "Bruno", (1, 77): "Agatha", (1, 78): "Lance", (1, 79): "Gary"}
LEAGUE_ORDER = ("Lorelei", "Bruno", "Agatha", "Lance", "Gary")
PLATEAU_CENTER_MAP = (13, 0)          # where the model preps (heal, shop, save) before the first door

SEALED = ("You are SEALED IN the Elite Four's rooms: the door closed behind you and there is no Pokémon Center, shop or way out until the Champion is beaten. "
          "Heal ONLY from the Bag — Full Restore / Revive / Potions: heal() does it for you (or use_item) — and press on with quest('elite_four'); "
          "win outright, or if the whole team faints the whiteout returns you to the Plateau's Center fully healed (the League resets, your levels stay).")


def league_notice(here, party=None, bag=None) -> str:
    """One observation line for a League room, or '' elsewhere. With the party / bag (a {item id: count} dict) it adds what is left to heal with."""
    if tuple(here) not in LEAGUE_ROOMS:
        return ""
    line = SEALED
    if bag is not None:
        revives = sum(n for i, n in bag.items() if i in (24, 25))
        restores = sum(n for i, n in bag.items() if i == 19)
        potions = sum(n for i, n in bag.items() if i in (13, 22, 21, 20))
        line += f" Left in the Bag: {restores} Full Restore, {revives} Revive, {potions} Potions."
    if party is not None:
        alive = sum(1 for p in party if p.current_hp > 0)
        line += f" Standing: {alive}/{len(party)}."
    return line
