"""The Seagallop ferry's destinations and menus (pure; read from the decomp — data/scripts/seagallop.inc, src/script_menu.c DrawSeagallopDestinationMenu — #360).

Islands: 0 Vermilion, 1-7 One..Seven Island. With the Rainbow Pass (the Network Machine stage, VAR_MAP_SCENE_ONE_ISLAND_POKEMON_CENTER_1F >= 5) every dock shows ONE drawn menu in two pages:
page 0 = the first four destinations among Vermilion / One / Two / Three / Four except where you stand, then OTHER and EXIT; OTHER opens page 1 = three destinations among Four..Seven (Five, Six, Seven from the
north half; Four, Five, Six, Seven minus yours from Five, Six or Seven), then OTHER and EXIT. With only the Tri-Pass (stage 1-4) Vermilion offers One / Two / Three / Exit and an island One / Two / Three
minus its own (plus Vermilion once the Cinnabar scene is past 3), then Exit."""
NAMES = {0: "Vermilion City", 1: "One Island", 2: "Two Island", 3: "Three Island", 4: "Four Island", 5: "Five Island", 6: "Six Island", 7: "Seven Island"}
HARBORS = {1: (32, 4), 2: (33, 4), 3: (38, 0), 4: (35, 5), 5: (36, 2), 6: (37, 2), 7: (31, 6)}       # island -> its Harbor map (the Seagallop dock); the sailor stands at (8,6) in each
VERMILION_SAILOR = (3, 5), (24, 33)                                                                  # the pier on Vermilion City's own map
ISLAND_MAPS: dict[tuple[int, int], list[int]] = {                   # (map group, island) -> map ids: every Sevii map by its decomp folder prefix (OneIsland*/MtEmber* = 1 … SevenIsland*/TrainerTower* = 7)
    (1, 1): [96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108],
    (1, 3): [109],
    (1, 4): [110, 111, 112, 113],
    (1, 5): [114],
    (1, 6): [115, 116, 117, 118, 119, 120, 121, 122],
    (2, 1): [57],
    (2, 3): [34],
    (2, 5): [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
    (2, 7): [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 27, 28, 29, 30, 31, 32, 33, 35],
    (3, 1): [12, 45, 46],
    (3, 2): [13, 47],
    (3, 3): [14, 48, 49],
    (3, 4): [15],
    (3, 5): [16, 54, 55, 56, 57],
    (3, 6): [18, 58, 59, 60, 61],
    (3, 7): [17, 62, 63, 64, 65],
    (31, 7): [0, 1, 2, 3, 4, 5, 6],
    (32, 1): [0, 1, 2, 3, 4],
    (33, 2): [0, 1, 2, 3, 4],
    (34, 3): [0, 1, 2, 3, 4, 5, 6, 7],
    (35, 4): [0, 1, 2, 3, 4, 5, 6, 7],
    (36, 5): [0, 1, 2, 3, 4],
    (37, 6): [0, 1, 2, 3, 4],
    (38, 3): [0],
    (39, 5): [0],
    (40, 2): [0],
    (41, 6): [0, 1],
    (42, 7): [0],
}
ISLAND_OF_MAP = {(g, n): isl for (g, isl), ids in ISLAND_MAPS.items() for n in ids}
RAINBOW_STAGE = 5


def island_of_map(mp) -> int | None:
    """0 on Vermilion's pier map, 1-7 for any Sevii map (town, route, cave, harbor), None elsewhere."""
    mp = tuple(mp)
    return 0 if mp == VERMILION_SAILOR[0] else ISLAND_OF_MAP.get(mp)


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


def on_sevii(mp) -> bool:
    return tuple(mp) in ISLAND_OF_MAP
