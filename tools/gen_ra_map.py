#!/usr/bin/env python3
"""Generate knowledge/ra_map.py: what the agent checks for each RetroAchievements achievement of LeafGreen (#358).

Usage: python tools/gen_ra_map.py [path-to-pokefirered] > knowledge/ra_map.py

The Web API gives only a hash of each achievement's conditions (tools/gen_ra_set.py), so the mapping is curated here by hand — every achievement title read against the decomp — and every flag /
trainer / item / species NAME below is resolved to its number from the decomp's constants, so a typo fails the generation instead of mapping to the wrong flag.

Spec kinds in CURATED (an achievement is unlocked when ALL of its specs hold):
  ("flag", NAME|int)              a game flag is set            ("trainer", (NAME, ...))     any of these trainers is beaten
  ("beat", key)                   a story beat is done          ("badge", bit)               a gym badge
  ("item", NAME)                  a key item is in the bag      ("caught", NAME)             the species is caught (Kanto dex bits only)
  ("sweep", area)                 every trainer + item ball of a sweep area (knowledge/area_sweeps)     ("sweep_trainers", area)   only its trainers      ("sweep_items", area)   only its items
  ("tower", index)                a Trainer Tower challenge's prize was received (0 single, 1 double, 2 knockout, 3 mixed)
PARTIAL = checks that are necessary but may not be sufficient (the achievement can need more than we can read); MANUAL = no check yet, with the reason."""
import os
import re
import sys

CURATED: dict[int, tuple] = {
    34776: (("flag", "FLAG_BEAT_RIVAL_IN_OAKS_LAB"),),
    541899: (("flag", "FLAG_SYS_POKEDEX_GET"),),
    541900: (("item", "ITEM_TOWN_MAP"),),
    541901: (("flag", "FLAG_GOT_POTION_ON_ROUTE_1"),),
    541902: (("item", "ITEM_TEACHY_TV"),),
    34777: (("trainer", ("TRAINER_RIVAL_ROUTE22_EARLY_SQUIRTLE", "TRAINER_RIVAL_ROUTE22_EARLY_BULBASAUR", "TRAINER_RIVAL_ROUTE22_EARLY_CHARMANDER")),),
    541904: (("trainer", ("TRAINER_CAMPER_LIAM",)),),
    34785: (("badge", 0),),
    541906: (("flag", "FLAG_GOT_FOSSIL_FROM_MT_MOON"),),
    541937: (("sweep", "Mt. Moon"),),
    34778: (("trainer", ("TRAINER_RIVAL_CERULEAN_SQUIRTLE", "TRAINER_RIVAL_CERULEAN_BULBASAUR", "TRAINER_RIVAL_CERULEAN_CHARMANDER")),),
    541907: (("sweep_trainers", "Cerulean Gym"),),
    34786: (("badge", 1),),
    541908: (("beat", "ss_ticket"),),
    541915: (("sweep", "S.S. Anne"),),
    34779: (("trainer", ("TRAINER_RIVAL_SS_ANNE_SQUIRTLE", "TRAINER_RIVAL_SS_ANNE_BULBASAUR", "TRAINER_RIVAL_SS_ANNE_CHARMANDER")),),
    541909: (("flag", "FLAG_GOT_OLD_ROD"),),
    541910: (("flag", "FLAG_GOT_BIKE_VOUCHER"),),
    541913: (("flag", "FLAG_GOT_BICYCLE"),),
    541916: (("sweep_trainers", "Vermilion Gym"),),
    34787: (("badge", 2),),
    34780: (("trainer", ("TRAINER_RIVAL_POKEMON_TOWER_SQUIRTLE", "TRAINER_RIVAL_POKEMON_TOWER_BULBASAUR", "TRAINER_RIVAL_POKEMON_TOWER_CHARMANDER")),),
    541921: (("flag", "FLAG_GOT_EEVEE"),),
    541922: (("flag", "FLAG_GOT_COIN_CASE"),),
    541923: (("flag", "FLAG_GOT_10_COINS_FROM_GAMBLER"), ("flag", "FLAG_GOT_20_COINS_FROM_GAMBLER"), ("flag", "FLAG_GOT_20_COINS_FROM_GAMBLER_2"),
             ("flag", "FLAG_HIDDEN_ITEM_CELADON_CITY_GAME_CORNER_COINS"), ("flag", "FLAG_HIDDEN_ITEM_CELADON_CITY_GAME_CORNER_COINS_2"), ("flag", "FLAG_HIDDEN_ITEM_CELADON_CITY_GAME_CORNER_COINS_3")),
    541924: (("sweep_trainers", "Celadon Gym"),),
    34788: (("badge", 3),),
    541926: (("beat", "tea"),),
    34783: (("beat", "rocket_hideout"),),
    541929: (("sweep", "Rocket Hideout"),),
    541930: (("sweep", "Pokémon Tower"),),
    541931: (("beat", "poke_flute"),),
    541932: (("caught", "SNORLAX"),),
    541944: (("sweep_trainers", "Fuchsia Gym"),),
    34789: (("badge", 4),),
    34781: (("trainer", ("TRAINER_RIVAL_SILPH_SQUIRTLE", "TRAINER_RIVAL_SILPH_BULBASAUR", "TRAINER_RIVAL_SILPH_CHARMANDER")),),
    541953: (("sweep", "Silph Co."),),
    541959: (("flag", "FLAG_GOT_LAPRAS_FROM_SILPH"),),
    34784: (("beat", "silph_co"),),
    541954: (("flag", "FLAG_GOT_HITMON_FROM_DOJO"),),
    541955: (("sweep_trainers", "Saffron Gym"),),
    34790: (("badge", 5),),
    541956: (("beat", "pokemon_mansion"),),
    541957: (("sweep_trainers", "Cinnabar Gym"),),
    34791: (("badge", 6),),
    34810: (("flag", "FLAG_RESCUED_LOSTELLE"),),
    541958: (("sweep_trainers", "Viridian Gym"),),
    34792: (("badge", 7),),
    34782: (("trainer", ("TRAINER_RIVAL_ROUTE22_LATE_SQUIRTLE", "TRAINER_RIVAL_ROUTE22_LATE_BULBASAUR", "TRAINER_RIVAL_ROUTE22_LATE_CHARMANDER")),),
    34797: (("flag", "FLAG_SYS_GAME_CLEAR"),),
    541973: (("flag", "FLAG_SYS_NATIONAL_DEX"),),
    541975: (("flag", "FLAG_GOT_RUBY"),),
    34811: (("beat", "icefall_cave"),),
    34813: (("flag", "FLAG_DEFEATED_ROCKETS_IN_WAREHOUSE"),),
    541984: (("beat", "network_machine"),),
    541991: (("beat", "sevii_sapphire"),),
    34807: (("caught", "MEWTWO"),),
    34814: (("tower", 0),),
    34815: (("tower", 1),),
    34816: (("tower", 2),),
    34817: (("tower", 3),),
    34803: (("caught", "CHANSEY"),),
    34806: (("caught", "ARTICUNO"),),
    34805: (("caught", "ZAPDOS"),),
    34804: (("caught", "MOLTRES"),),
    541905: (("flag", "FLAG_BOUGHT_MAGIKARP"),),
    541911: (("flag", 0x24D),),                                    # NPC_TRADES: Farfetch'd for a Spearow
    541912: (("flag", "FLAG_DID_MIMIEN_TRADE"),),
    541917: (("flag", "FLAG_GOT_HM05"),),
    541918: (("flag", "FLAG_GOT_OLD_AMBER"),),
    541920: (("flag", "FLAG_GOT_EVERSTONE_FROM_OAKS_AIDE"),),
    541925: (("flag", "FLAG_GOT_HM02"),),
    541927: (("flag", "FLAG_GOT_VS_SEEKER"),),
    541928: (("flag", "FLAG_GOT_POWDER_JAR"),),
    541933: (("flag", "FLAG_GOT_HM03"), ("flag", "FLAG_GOT_HM04")),
    541934: (("flag", "FLAG_GOT_ITEMFINDER"),),
    541935: (("flag", "FLAG_HIDDEN_ITEM_ROUTE12_LEFTOVERS"), ("flag", "FLAG_HIDDEN_ITEM_ROUTE16_LEFTOVERS")),
    541936: (("flag", "FLAG_HIDDEN_ITEM_POKEMON_TOWER_7F_SOOTHE_BELL"),),
    541940: (("flag", "FLAG_GOT_GOOD_ROD"),),
    541941: (("flag", "FLAG_GOT_AMULET_COIN_FROM_OAKS_AIDE"),),
    541942: (("flag", "FLAG_GOT_SUPER_ROD"),),
    541943: (("flag", "FLAG_GOT_EXP_SHARE_FROM_OAKS_AIDE"),),
    541961: (("flag", "FLAG_HIDDEN_ITEM_VIRIDIAN_CITY_GYM_MACHO_BRACE"),),
    541962: (("flag", "FLAG_GOT_RECORD_SETTING_MAGIKARP"),),
    541964: (("flag", 0x276), ("flag", 0x274), ("flag", 0x275)),     # NPC_TRADES: the three Cinnabar Lab trades (Seel, Electrode, Tangela)
    541965: (("flag", "FLAG_DID_MS_NIDO_TRADE"), ("flag", "FLAG_DID_NINA_TRADE")),
    541966: (("flag", "FLAG_DID_ZYNX_TRADE"),),
    541967: (("flag", "FLAG_DID_MARC_TRADE"),),
    541969: (("flag", "FLAG_GOT_HM06"),),
    541970: (("flag", "FLAG_HIDDEN_ITEM_TWO_ISLAND_CAPE_BRINK_PP_MAX"),),
    541974: (("flag", "FLAG_GOT_NUGGET_FROM_DUNSPARCE_TUNNEL"),),
    541977: (("flag", "FLAG_HIDE_FOUR_ISLAND_ICEFALL_CAVE_1F_HM07"),),
    541981: (("flag", "FLAG_GOT_TOGEPI_EGG"),),
    541982: (("flag", "FLAG_GOT_NEST_BALL_FROM_WATER_PATH_HOUSE_1"),),
    541990: (("flag", "FLAG_GOT_TM33_FROM_THIRSTY_GIRL"), ("flag", "FLAG_GOT_TM20_FROM_THIRSTY_GIRL"), ("flag", "FLAG_GOT_TM16_FROM_THIRSTY_GIRL")),
    541914: (("sweep", "Viridian Forest"),),
    541919: (("sweep", "Rock Tunnel"),),
    541938: (("sweep", "Routes 2-4, Viridian, Pewter, Cerulean"),),
    541939: (("sweep", "Routes 24-25"),),
    541945: (("sweep_items", "Safari Zone"),),
    541946: (("sweep", "Routes 9-10"),),
    541947: (("sweep_items", "Power Plant"),),
    541948: (("sweep", "Routes 6-8, Saffron, Vermilion"),),
    541949: (("sweep", "Routes 11-15, Fuchsia"),),
    541950: (("sweep", "Routes 19-21"),),
    541951: (("sweep_items", "Seafoam Islands"),),
    541952: (("sweep", "Pokémon Mansion"),),
    541960: (("sweep", "Routes 16-18, Celadon (Cycling Road)"),),
    541963: (("sweep", "Victory Road"),),
    541968: (("sweep", "Kindle Road / Mt. Ember"),),
    541971: (("sweep", "Two-Three Island (Cape Brink, Bond Bridge, Berry Forest)"),),
    541976: (("sweep_items", "Four Island / Icefall Cave"),),
    541978: (("sweep", "Five Island region"),),
    541979: (("sweep", "Six Island region"),),
    541980: (("sweep", "Seven Island region"),),
    541987: (("sweep_items", "Cerulean Cave"),),
    541988: tuple(("flag", f"FLAG_TUTOR_{t}") for t in ("DOUBLE_EDGE", "THUNDER_WAVE", "ROCK_SLIDE", "EXPLOSION", "MEGA_PUNCH", "MEGA_KICK", "DREAM_EATER", "SOFT_BOILED", "SUBSTITUTE",
                                                         "SWORDS_DANCE", "SEISMIC_TOSS", "COUNTER", "METRONOME", "MIMIC", "BODY_SLAM")),
    541903: (("flag", "FLAG_SYS_MYSTERY_GIFT_ENABLED"),),
}

# Necessary but maybe not sufficient: the check can be true before the achievement unlocks (shown as "probably", never as a sure unlock).
PARTIAL = {
    541937: "Mt. Moon's hidden items count except the mushrooms; the sweep here is trainers + item balls",
    541926: "the flag says the Tea was obtained, not that it was handed to the guards",
    541954: "the Dojo's trainers are not a sweep area; only the Hitmon gift is read",
    541988: "the 15 Kanto/Sevii tutors; the three Sevii starter-move tutors may count too",
    541963: "Route 23 is not in the Victory Road sweep area",
}
for _area_ach in (541914, 541919, 541938, 541939, 541946, 541948, 541949, 541950, 541952, 541960, 541968, 541971, 541978, 541979, 541980):
    PARTIAL.setdefault(_area_ach, "hidden items (an Itemfinder finds them) may count; the sweep reads trainers + item balls")
for _items_ach in (541945, 541947, 541951, 541976, 541987):
    PARTIAL.setdefault(_items_ach, "hidden items may count; the check reads item balls")

MANUAL = {
    541983: "needs the 'Selphy asked for' Pokémon — the quiz answer is not a flag we know",
    541986: "the Trainer Card machine's state is not a flag we read yet",
    541989: "triple 7s on the slots: a one-off event with no flag",
    541972: "renewable berries in Berry Forest: no flag",
    541985: "the Fame Checker's entries are not read yet",
    541992: "VS Seeker rematch levels: needs the rematch records",
    34802: "the second Champion title (the Hall of Fame twice) has no flag",
    34812: "Selphy's rescue flag is not verified",
    34808: "the roaming beasts are beyond the Kanto Pokédex bits the reader sees",
    34809: "171 species need the Sevii dex bits (> 151), which the reader does not see",
}


def resolve_defines(*texts: str) -> dict:
    """{NAME: int} for every `#define NAME expr` of the headers whose expr is a sum / difference of numbers and other (resolvable) names."""
    raw = dict(m for text in texts for m in re.findall(r"#define (\w+)\s+(.+?)\s*(?://.*)?$", text, re.M))
    cache: dict = {}

    def value(name: str):
        if name in cache:
            return cache[name]
        cache[name] = None                                           # a self-reference stays unresolved
        total, sign = 0, 1
        for tok in re.findall(r"[A-Za-z_0-9]+|[+-]", raw[name]):
            if tok in "+-":
                sign = 1 if tok == "+" else -1
                continue
            if re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", tok):
                v = int(tok, 0)
            elif tok in raw:
                v = value(tok)
                if v is None:
                    return None
            else:
                return None
            total += sign * v
            sign = 1
        cache[name] = total
        return total
    return {n: v for n in raw if (v := value(n)) is not None}


def main():
    pf = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Projects/pokefirered")
    opponents = open(f"{pf}/include/constants/opponents.h").read()
    flags = resolve_defines(open(f"{pf}/include/constants/flags.h").read(), opponents)         # TRAINER_FLAGS_END uses MAX_TRAINERS_COUNT
    trainers = resolve_defines(opponents)
    items = resolve_defines(open(f"{pf}/include/constants/items.h").read())
    species = resolve_defines(open(f"{pf}/include/constants/species.h").read())
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from knowledge.area_sweeps import AREAS
    from knowledge.ra_set import ACHIEVEMENTS
    from knowledge.story_beats import BY_KEY
    trainer_base = flags["TRAINER_FLAGS_START"]
    known = {a[0] for a in ACHIEVEMENTS}
    out: dict[int, tuple] = {}

    def num(table, name, what):
        if isinstance(name, int):
            return name
        if name not in table:
            sys.exit(f"unknown {what} {name!r}")
        return table[name]

    for aid, specs in CURATED.items():
        if aid not in known:
            sys.exit(f"achievement {aid} is not in knowledge/ra_set.py")
        rows = []
        for kind, *arg in specs:
            a = arg[0]
            if kind == "flag":
                rows.append(("flag", num(flags, a, "flag")))
            elif kind == "trainer":
                rows.append(("trainer", tuple(trainer_base + num(trainers, t, "trainer") for t in a)))
            elif kind == "item":
                rows.append(("item", num(items, a, "item")))
            elif kind == "caught":
                rows.append(("caught", num(species, "SPECIES_" + a, "species")))
            elif kind in ("sweep", "sweep_trainers", "sweep_items"):
                if a not in AREAS:
                    sys.exit(f"unknown sweep area {a!r}")
                rows.append((kind, a))
            elif kind == "beat":
                if a not in BY_KEY:
                    sys.exit(f"unknown story beat {a!r}")
                rows.append(("beat", a))
            elif kind in ("badge", "tower"):
                rows.append((kind, a))
            else:
                sys.exit(f"unknown spec kind {kind!r}")
        out[aid] = tuple(rows)
    both = set(out) & set(MANUAL)
    missing = known - set(out) - set(MANUAL)
    if both or missing:
        sys.exit(f"every achievement is mapped or manual, never both: both={sorted(both)} missing={sorted(missing)}")
    print('"""What the agent checks for each RetroAchievements achievement of LeafGreen. GENERATED by tools/gen_ra_map.py (curated against the decomp) — do not edit."""\n')
    print("# achievement id -> specs, ALL of which must hold; see tools/gen_ra_map.py for the kinds")
    print("CHECKS: dict[int, tuple] = {")
    for aid in sorted(out, key=lambda i: [a[0] for a in ACHIEVEMENTS].index(i)):
        print(f"    {aid}: {out[aid]!r},")
    print("}\n")
    print("# achievement id -> why the check can be true before the achievement unlocks")
    print("PARTIAL: dict[int, str] = {")
    for aid, why in sorted(PARTIAL.items()):
        print(f"    {aid}: {why!r},")
    print("}\n")
    print("# achievement id -> why it has no check yet")
    print("MANUAL: dict[int, str] = {")
    for aid, why in sorted(MANUAL.items()):
        print(f"    {aid}: {why!r},")
    print("}")


if __name__ == "__main__":
    main()
