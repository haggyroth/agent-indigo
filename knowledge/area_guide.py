"""What to DO in each dungeon, puzzle gym and late-game stretch (pure).

The map graph says where doors lead and the gates table says what blocks a road; this says why you are here and what is in the way.
Each area is a hand-written goal / obstacles / tip (kept short: it is shown in the observation) on top of facts the decomp gives for free
(trainer counts, item balls and hidden items with their coordinates — `area_facts`, generated), so the numbers cannot drift.

`guide_for(map_key)` is the text for the map the player is standing on; `AREAS` is the registry the tests check against the story path."""
from dataclasses import dataclass

from knowledge.area_facts import AREA_FACTS, MAP_IDS


@dataclass(frozen=True)
class Area:
    key: str
    title: str
    maps: tuple               # decomp directory names (resolved to (bank, id) by MAP_IDS)
    goal: str
    watch: str = ""
    tip: str = ""


def _floors(prefix: str, *floors: str) -> tuple:
    return tuple(f"{prefix}_{f}" for f in floors)


AREAS: tuple[Area, ...] = (
    # ── caves and dungeons ────────────────────────────────────────────────────────────────────────────
    Area("mt_moon", "Mt. Moon", _floors("MtMoon", "1F", "B1F", "B2F"),
         "Cross it to Route 4 (the way to Cerulean): 1F → B1F → B2F, then the east exit.",
         "Zubats and Geodudes; Team Rocket grunts on B2F guard the two Fossils (take ONE, Helix or Dome — optional, a Cinnabar lab revives it).",
         "Bring Repels and Potions; the ladders loop, so trust go_to rather than walking the maze by hand."),
    Area("rock_tunnel", "Rock Tunnel", _floors("RockTunnel", "1F", "B1F"),
         "Get from Route 10 (north, Cerulean side) to Route 10 (south, Lavender side).",
         "It is dark: without Flash only a few tiles around you show. Many trainers, Zubats and Geodudes.",
         "HM05 Flash (from Oak's aide in the Route 2 gatehouse once you own 10 species) lights it; go_to still paths by map data. Heal first."),
    Area("diglett_cave", "Diglett's Cave", ("DiglettsCave_B1F", "DiglettsCave_NorthEntrance", "DiglettsCave_SouthEntrance"),
         "A tunnel between Route 2 (north of Viridian) and Route 11 (east of Vermilion) — a shortcut, no trainers.",
         "Only Diglett and Dugtrio live here.",
         "Catch a Diglett for a cheap Ground-type before Lt. Surge; skip it otherwise."),
    Area("power_plant", "Power Plant", ("PowerPlant",),
         "Optional: Zapdos (L50) waits at the far end. Reached from Route 10 across the water (needs Surf).",
         "Some 'item balls' are Voltorb / Electrode and explode; Electric wilds paralyse.",
         "Bring Ground or Rock types, Paralyze Heals and Ultra Balls; save before Zapdos."),
    Area("pokemon_mansion", "Pokémon Mansion (Cinnabar)", _floors("PokemonMansion", "1F", "2F", "3F", "B1F"),
         "Find the Secret Key on B1F — Blaine's Cinnabar Gym will not open without it.",
         "Statue switches open and close the walls on every floor; scientists and Burglars battle you; Growlithe / Ponyta / Grimer wilds.",
         "Use the floor switches (walk_to handles the switch doors); read the diary pages only if curious."),
    Area("seafoam", "Seafoam Islands", _floors("SeafoamIslands", "1F", "B1F", "B2F", "B3F", "B4F"),
         "Cross Route 20 by the cave: it needs Surf and Strength. Articuno (L50) is optional on B4F.",
         "Strong currents on the lower floors push you back; boulders must go into the holes to stop them.",
         "Push the boulders down the holes first (use_hm('strength')), then Surf across. Save before Articuno."),
    Area("victory_road", "Victory Road", _floors("VictoryRoad", "1F", "2F", "3F"),
         "Reach the Pokémon League: Route 23 (all 8 badges) → 1F → 2F → 3F → Indigo Plateau.",
         "Strength boulders and floor switches open the walls; wild L40+ Pokémon; trainers on every floor.",
         "Have a Strength user (quest('strength')) and heal up: this is the real test before the Elite Four."),
    Area("cerulean_cave", "Cerulean Cave", _floors("CeruleanCave", "1F", "2F", "B1F"),
         "Post-game only: a guard in Cerulean City blocks the way in. Mewtwo waits on B1F.",
         "Wild Pokémon L46-64; it is a maze of ledges and ladders.",
         "Ignore it until the Elite Four is beaten; bring Ultra Balls and a full team."),
    Area("safari", "Safari Zone", ("SafariZone_Center", "SafariZone_East", "SafariZone_North", "SafariZone_West",
                                   "SafariZone_SecretHouse", "FuchsiaCity_SafariZone_Entrance"),
         "quest('surf') and quest('strength') do the trip: Center → East → North → West (the only connections), the Secret House for HM03, "
         "the Gold Teeth for the Warden.",
         "30 Safari Balls and 600 steps per ¥500 visit; fights are safari('ball'|'bait'|'rock'|'run'), not moves.",
         "Item balls inside include TM47 Steel Wing, a Nugget, Max Potions and a Leaf Stone — pick them up if steps allow."),
    # ── Team Rocket and the story set pieces ──────────────────────────────────────────────────────────
    Area("rocket_hideout", "Rocket Hideout (under the Game Corner)", _floors("RocketHideout", "B1F", "B2F", "B3F", "B4F", "Elevator"),
         "Reach Giovanni on B4F for the Silph Scope. The way in is a hidden switch behind a poster in the Celadon Game Corner.",
         "Spinner-arrow mazes on B2F-B3F; grunts on every floor; the Lift Key (from a grunt on B4F) runs the elevator.",
         "Take the stairs/elevator as go_to routes them; beat the grunt who drops the Lift Key, then Giovanni gives the Silph Scope."),
    Area("silph_co", "Silph Co. (Saffron)", _floors("SilphCo", "1F", "2F", "3F", "4F", "5F", "6F", "7F", "8F", "9F", "10F", "11F", "Elevator"),
         "Giovanni is on 11F; the President there gives the Master Ball afterwards. Beat Team Rocket to free Saffron's gate guards.",
         "Card-key doors on most floors (the Card Key is an item ball on 5F), teleporter pads, a rival battle on 7F, scientists and Rockets.",
         "Pick up the Card Key on 5F first (go_to knows the doors); an employee on 7F gives a Lapras (L25); heal before Giovanni."),
    Area("pokemon_tower", "Pokémon Tower (Lavender)", _floors("PokemonTower", "1F", "2F", "3F", "4F", "5F", "6F", "7F"),
         "Climb to 7F, rescue Mr. Fuji from Team Rocket, then he gives you the Poké Flute (in his house).",
         "Ghosts on 6F are unidentifiable until you own the Silph Scope (Rocket Hideout); the Marowak ghost must be revealed and beaten; "
         "Channelers on 3F-5F; rival on 2F.",
         "Do the Rocket Hideout first. Normal and Fighting moves do nothing to Ghosts; use Psychic, Dark or neutral hits; 5F has a healing tile."),
    Area("ss_anne", "S.S. Anne", ("SSAnne_Exterior", "SSAnne_Deck", "SSAnne_1F_Corridor", "SSAnne_2F_Corridor", "SSAnne_3F_Corridor",
                                  "SSAnne_B1F_Corridor", "SSAnne_CaptainsOffice", "SSAnne_Kitchen"),
         "Board with the S.S. Ticket, reach the Captain's Office on 2F for HM01 Cut — quest('cut') does it. The ship sails afterwards.",
         "A rival fight in a corridor; sailors and gentlemen in the rooms; no wild Pokémon.",
         "Don't linger: items in the rooms are minor, and the ship leaves for good once you have Cut."),
    # ── puzzle gyms ───────────────────────────────────────────────────────────────────────────────────
    Area("sabrina_gym", "Saffron Gym (Sabrina)", ("SaffronCity_Gym",),
         "Reach Sabrina by the warp pads: each tile throws you to another room; the Leader sits in the middle room.",
         "Every room has a trainer; a Psychic-type team (Kadabra, Mr. Mime, Venomoth, Alakazam).",
         "The pad pairs are listed below as 'warp pads'; step on the pad whose partner is in the room you want. Bug / Dark / Ghost hit hardest."),
    Area("koga_gym", "Fuchsia Gym (Koga)", ("FuchsiaCity_Gym",),
         "Walk to Koga through the invisible walls: unseen barriers form a maze, and bumping into them is the only way to find out.",
         "Poison trainers who explode and use Toxic; Koga's Koffing / Muk / Weezing.",
         "The map data (walk_to) paths around the real walls; Ground and Psychic hit hardest. Bring Antidotes and Full Heals."),
    Area("blaine_gym", "Cinnabar Gym (Blaine)", ("CinnabarIsland_Gym",),
         "The door needs the Secret Key (Pokémon Mansion B1F). Inside, each machine asks a quiz — a right answer opens the way, a wrong one "
         "means fighting that trainer.",
         "Fire trainers and Blaine's Growlithe / Ponyta / Rapidash / Arcanine.",
         "Water and Ground moves; Burn Heals; answering the quiz is optional — fighting works too."),
    Area("giovanni_gym", "Viridian Gym (Giovanni)", ("ViridianCity_Gym",),
         "Opens only with 7 badges. Spinner-arrow tiles carry you across the floor to the Leader.",
         "Ground-type trainers; Giovanni's team ends with Rhydon (L50).",
         "Water, Grass and Ice moves; Ice Beam for Rhydon. After this badge, Route 22/23 and Victory Road open."),
    # ── routes and travel obstacles ───────────────────────────────────────────────────────────────────
    Area("kanto_east", "Routes 12-15 (Lavender south)", ("Route12", "Route13", "Route14", "Route15", "Route12_NorthEntrance_1F"),
         "Walk south along the east coast to Fuchsia. A Snorlax sleeps on Route 12 (it needs the Poké Flute, from Mr. Fuji).",
         "Fishermen and Cooltrainers all along the coast; Route 12 is a long pier with a Snorlax on it.",
         "Route 15's gatehouse gives Exp. Share to a trainer who has caught 50 species; Fuchsia is the goal."),
    Area("cycling_road", "Routes 16-18 (Cycling Road)", ("Route16", "Route17", "Route18", "Route16_NorthEntrance_1F", "Route18_EastEntrance_1F"),
         "Celadon → Fuchsia the quick way. Route 16 has a sleeping Snorlax (Poké Flute); Cycling Road (17) needs the Bicycle.",
         "The Bicycle comes from the Cerulean bike shop only with a Bike Voucher (Pokémon Fan Club, Vermilion); bikers on the slope.",
         "If you have no bike take Routes 12-15 instead. Fly to Fuchsia once you have visited it."),
    Area("saffron_access", "Saffron City and the Underground Path", ("SaffronCity_Connection", "UndergroundPath_NorthEntrance",
                                                                    "UndergroundPath_SouthEntrance", "UndergroundPath_EastEntrance",
                                                                    "UndergroundPath_WestEntrance", "UndergroundPath_NorthSouthTunnel",
                                                                    "UndergroundPath_EastWestTunnel"),
         "The gate guards on every road into Saffron want Tea (from the woman in the Celadon Condominiums) — or Fly in "
         "once you have visited. The Underground Path joins Routes 5-6 and 7-8 without passing Saffron.",
         "The Tea is free: the woman on the ground floor of the Celadon Condominiums gives it to you.",
         "Use the Underground Path to get between Cerulean and Celadon quickly."),
    Area("sea_route", "Routes 19-21 and Cinnabar Island", ("Route19", "Route20", "Route21_North", "Route21_South"),
         "Surf south from Fuchsia (Route 19) past Seafoam (Route 20) to Cinnabar, then north on Route 21 to Pallet.",
         "Open water: swimmers, Tentacool and Tentacruel; no way to rest until Cinnabar's Pokémon Center.",
         "Have a Surf user and Super Potions; Fly home from Cinnabar once you've been."),
    Area("league_approach", "Routes 22-23 and the Indigo Plateau", ("Route22", "Route22_NorthEntrance", "Route23", "IndigoPlateau_Exterior",
                                                                    "IndigoPlateau_PokemonCenter_1F"),
         "Route 22 (west of Viridian) has two rival fights; Route 23's guards check badges in order; Victory Road leads to the Plateau.",
         "All 8 badges are required beyond the Route 22 gate; the Plateau's Center is the last place to heal and save.",
         "Heal() and save_game() at the Indigo Plateau Center before entering the League — the doors lock behind you."),
    Area("elite_four", "Elite Four and the Champion", ("PokemonLeague_LoreleisRoom", "PokemonLeague_BrunosRoom", "PokemonLeague_AgathasRoom",
                                                       "PokemonLeague_LancesRoom", "PokemonLeague_ChampionsRoom", "PokemonLeague_HallOfFame"),
         "Lorelei → Bruno → Agatha → Lance → Gary, back to back. team_report shows each party; the Hall of Fame ends the game.",
         "You cannot leave or heal between rooms (the door locks), and a blackout restarts the whole gauntlet; no escaping trainer battles.",
         "Stock Full Restores / Revives / Full Heals first; save_state before every room; lead with your sturdiest Pokémon."),
)

_BY_MAP: dict[tuple[int, int], Area] = {MAP_IDS[m]: a for a in AREAS for m in a.maps if m in MAP_IDS}


def area_for(map_key) -> Area | None:
    return _BY_MAP.get(tuple(map_key))


def _label(item: str) -> str:
    """'Tm07' → 'TM07 Horn Drill'; other names unchanged."""
    if item.lower().startswith("tm") and item[2:4].isdigit():
        from knowledge.tmhm import TMHM
        for label, move, _mid in TMHM.values():
            if label == item[:4].upper():
                return f"{label} {move}"
    return item


def facts_line(map_key) -> str:
    fact = AREA_FACTS.get(tuple(map_key))
    if not fact:
        return ""
    _name, trainers, items, _exits, pads = fact
    bits = []
    if trainers:
        bits.append(f"{trainers} trainer{'s' if trainers != 1 else ''} here")
    if items:
        bits.append("items: " + ", ".join(f"{_label(n)} ({x},{y})" for n, x, y in items[:5]) + ("…" if len(items) > 5 else ""))
    if pads:
        bits.append("warp pads (from → to): " + ", ".join(f"({a},{b})→({c},{d})" for a, b, c, d in pads[:8]) + ("…" if len(pads) > 8 else ""))
    return "; ".join(bits)


def guide_for(map_key) -> str:
    """The observation text for the map the player is on ('' when it is not part of a covered area)."""
    a = area_for(map_key)
    if a is None:
        return ""
    text = f"AREA — {a.title}: {a.goal}"
    if a.watch:
        text += f" Watch for: {a.watch}"
    if a.tip:
        text += f" Tip: {a.tip}"
    facts = facts_line(map_key)
    return text + (f" On this map: {facts}." if facts else "")
