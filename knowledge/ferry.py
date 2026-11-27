"""The Seagallop ferry's destinations and menus (pure; read from the decomp — data/scripts/seagallop.inc, src/script_menu.c DrawSeagallopDestinationMenu — #360).

Islands: 0 Vermilion, 1-7 One..Seven Island. With the Rainbow Pass (the Network Machine stage, VAR_MAP_SCENE_ONE_ISLAND_POKEMON_CENTER_1F >= 5) every dock shows ONE drawn menu in two pages:
page 0 = the first four destinations among Vermilion / One / Two / Three / Four except where you stand, then OTHER and EXIT; OTHER opens page 1 = three destinations among Four..Seven (Five, Six, Seven from the
north half; Four, Five, Six, Seven minus yours from Five, Six or Seven), then OTHER and EXIT. With only the Tri-Pass (stage 1-4) Vermilion offers One / Two / Three / Exit and an island One / Two / Three
minus its own (plus Vermilion once the Cinnabar scene is past 3), then Exit."""
NAMES = {0: "Vermilion City", 1: "One Island", 2: "Two Island", 3: "Three Island", 4: "Four Island", 5: "Five Island", 6: "Six Island", 7: "Seven Island"}
HARBORS = {1: (32, 4), 2: (33, 4), 3: (38, 0), 4: (35, 5), 5: (36, 2), 6: (37, 2), 7: (31, 6)}       # island -> its Harbor map (the Seagallop dock); the sailor stands at (8,6) in each
VERMILION_SAILOR = (3, 5), (24, 33)                                                                  # the pier on Vermilion City's own map
ISLAND_OF_GROUP = {32: 1, 33: 2, 34: 3, 38: 3, 35: 4, 36: 5, 39: 5, 37: 6, 31: 7}                    # map group -> the island it belongs to (non-harbor maps)
RAINBOW_STAGE = 5


def island_of_map(mp) -> int | None:
    """0 on Vermilion's pier map, 1-7 for a Sevii map (by its map group), None elsewhere."""
    mp = tuple(mp)
    if mp == VERMILION_SAILOR[0]:
        return 0
    return ISLAND_OF_GROUP.get(mp[0])


def page0(origin: int) -> list[int]:
    return [d for d in (0, 1, 2, 3, 4) if d != origin][:4]                # the drawn list holds four rows: from the islands Four is pushed to page 1


def page1(origin: int) -> list[int]:
    start = 5 if origin < 5 else 4
    return [d for d in range(start, 8) if d != origin][:3]


def rainbow_menu(origin: int, dest: int) -> list[tuple[int, str]]:
    """[(page, key)] presses to reach `dest` from `origin`: ('down' n times then 'A') on page 0, or OTHER (row index of OTHER) then the same on page 1. Returned as [(row index on the page, page)]."""
    p0 = page0(origin)
    if dest in p0:
        return [(p0.index(dest), 0)]
    p1 = page1(origin)
    if dest in p1:
        return [(len(p0), 0), (p1.index(dest), 1)]                    # OTHER is the row after the page-0 destinations
    return []


def tri_pass_rows(origin: int, vermilion_open: bool) -> list[int]:
    """The destination rows (before EXIT) of the Tri-Pass lists (islands One-Three only)."""
    rows = [d for d in (1, 2, 3) if d != origin]
    return ([0] if (origin != 0 and vermilion_open) else []) + rows


def route_text(origin: int, stage: int) -> str:
    reach = [0, 1, 2, 3, 4, 5, 6, 7] if stage >= RAINBOW_STAGE else [0, 1, 2, 3]
    return ", ".join(NAMES[d] for d in reach if d != origin)
