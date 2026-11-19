"""The main storyline, start to Elite Four, as an ordered chain of BEATS (pure data + logic; no I/O).

Why: the model only had a few scripted quests (ss_ticket, cut, surf, strength, coin_case, rocket_hideout) and, after Erika, nothing told
it what comes next — it ground wild Pokémon for 700 s with no story step in sight. Each beat here says WHAT it is, WHERE, what must come
first, how to tell it is DONE (flags / key items / badges read from the game, verified against the pret/pokefirered decomp), and the STEPS.
`quest()` lists the chain with ✔ done / ▶ next / … blocked; `quest('<key>')` runs the script when there is a driver, else prints the plan
(state-aware: it names what is still missing). The observation shows the next beat in one line.

Flags and item ids below are the decomp's (constants/flags.h, constants/items.h); gym badges are bits of the badge byte
(Boulder 0, Cascade 1, Thunder 2, Rainbow 3, Soul 4, Marsh 5, Volcano 6, Earth 7)."""
from dataclasses import dataclass

# done-spec kinds: ("flag", id) · ("item", key-item id) · ("badge", bit) · ("milestone", name) — a beat is done if ANY holds
TEA, POKE_FLUTE, SECRET_KEY, CARD_KEY, LIFT_KEY, SILPH_SCOPE, SS_TICKET, COIN_CASE_ITEM = 369, 350, 351, 355, 356, 359, 265, 260
BADGE_NAMES = ("Boulder", "Cascade", "Thunder", "Rainbow", "Soul", "Marsh", "Volcano", "Earth")


@dataclass(frozen=True)
class Beat:
    key: str
    title: str
    where: str
    needs: tuple = ()          # beat keys that must be done first
    done: tuple = ()           # done-specs (any)
    steps: tuple = ()          # the plan, in order
    driver: str = ""           # quest() key when a script exists (quest('key') does it), else "" = guide only
    optional: bool = False     # not required to reach the Elite Four (but useful)
    tip: str = ""


BEATS: tuple[Beat, ...] = (
    Beat("parcel", "Oak's Parcel → Pokédex", "Viridian City Mart → Pallet Town (Oak's Lab)",
         done=(("milestone", "delivered_oaks_parcel"), ("flag", 0x829)),                          # FLAG_SYS_POKEDEX_GET: a save from after the parcel has no milestone
         steps=("Take the starter, then the clerk at Viridian's Poké Mart gives you Oak's Parcel.",
                "Deliver it to Prof. Oak in Pallet Town: you get the Pokédex and Poké Balls. Only then does the Route 2 / Viridian Forest road open.")),
    Beat("brock", "Boulder Badge — Brock (Rock)", "Pewter City Gym", needs=("parcel",), driver="brock", done=(("badge", 0),),
         steps=("Viridian Forest (Route 2 north) → Pewter City.", "go_to('gym'), heal(), save_state(), challenge_leader(). Grass / Water / Fighting beat Onix.")),
    Beat("misty", "Cascade Badge — Misty (Water)", "Cerulean City Gym", needs=("brock",), driver="misty", done=(("badge", 1),),
         steps=("Pewter → Route 3 → Mt. Moon (two floors) → Route 4 → Cerulean City.", "Grass / Electric beat Starmie and Staryu.")),
    Beat("dig", "TM28 Dig back from the Cerulean thief (optional)", "Cerulean City, behind the robbed house", needs=("misty",), driver="dig", optional=True,
         done=(("flag", 0x23F),),
         steps=("The Rocket grunt at (33,6) behind the burgled house stole TM28; beat him and he returns it. Dig is a strong Ground move and an escape from caves.",)),
    Beat("magikarp", "Magikarp for ¥500 (optional)", "Route 4 Pokémon Center, the salesman at (1,3)", needs=("brock",), driver="magikarp", optional=True,
         done=(("flag", 0x249),),
         steps=("A L5 Magikarp for ¥500: a Pokédex entry and, at L20, a Gyarados. Decline the nickname.",
                "Best done on the way to Mt. Moon (the Center is the one before the cave): from Cerulean the trip back west through Mt. Moon is long and go_to can stall at the east end of Route 4.")),
    Beat("ss_ticket", "SS Anne ticket from Bill", "Route 25, Bill's Sea Cottage", needs=("misty",), driver="ss_ticket",
         done=(("item", SS_TICKET), ("flag", 0x234)),
         steps=("Cerulean's south and east exits stay blocked until you have it.", "quest('ss_ticket') walks Nugget Bridge to the cottage and runs Bill's computer.")),
    Beat("cut", "HM01 Cut from the S.S. Anne's Captain", "Vermilion City harbor → S.S. Anne 2F", needs=("ss_ticket",), driver="cut",
         done=(("flag", 0x237),),
         steps=("quest('cut') boards with the ticket, takes HM01 from the seasick Captain and teaches it.", "Cut trees (Vermilion Gym's door, Celadon, Route 9) then clear with use_hm('cut').")),
    Beat("surge", "Thunder Badge — Lt. Surge (Electric)", "Vermilion City Gym", needs=("cut",), driver="surge", done=(("badge", 2),),
         steps=("Cut the tree at the Gym door; challenge_leader() solves the two trash-can switches for you.", "Ground (Diglett's Cave, Route 2) is immune to his attacks.")),
    Beat("flash", "HM05 Flash (optional, lights Rock Tunnel)", "Route 2 east building (Oak's Aide)", needs=("surge",), optional=True, driver="flash",
         done=(("flag", 0x23B),),
         steps=("The Aide gives HM05 once you have CAUGHT 10 species (complete Pokédex data).", "Rock Tunnel is dark without it but passable — bring Repels.")),
    Beat("erika", "Rainbow Badge — Erika (Grass)", "Celadon City Gym", needs=("surge",), driver="erika", done=(("badge", 3),),
         steps=("Vermilion → Cerulean → Route 9 (Cut the tree) → Rock Tunnel → Lavender Town → Route 8 → the Underground Path → Route 7 → Celadon City.",
                "Fire / Flying / Ice / Poison beat her Grass team; cut the trees at the Gym.")),
    Beat("fly", "HM02 Fly (optional, fast travel)", "Route 16 house, just west of Celadon", needs=("erika",), optional=True, driver="fly",
         done=(("flag", 0x238),),
         steps=("From Celadon's west exit: cut the tree at (41,11), take the upper gatehouse and walk west to the house; the woman gives HM02. No Poké Flute needed (the Snorlax guards only the lower road).",
                "Fly needs the Thunder Badge — then fly_to() any visited town.")),
    Beat("coin_case", "Coin Case (optional, Game Corner prizes)", "Celadon Restaurant", needs=("erika",), driver="coin_case", optional=True,
         done=(("flag", 0x243),),
         steps=("quest('coin_case') gets it from the man in the corner of the Restaurant. The Prize Corner sells TMs for coins.",)),
    Beat("rocket_hideout", "Silph Scope from Giovanni (Rocket Hideout)", "Celadon Game Corner → B4F", needs=("erika",), driver="rocket_hideout",
         done=(("item", SILPH_SCOPE),),
         steps=("quest('rocket_hideout') does all of it: beat the Grunt by the poster, press the poster switch, go down four floors (the B3F spinner maze, "
                "the Lift Key from the B4F Grunt, the elevator), beat the two door Grunts and Giovanni, take the Silph Scope.",
                "Bring a healed team: about a dozen Rocket trainers (L20-29)."),
         tip="Without the Silph Scope the ghosts in Pokémon Tower cannot be seen or fought."),
    Beat("tea", "Tea for the Saffron gate guards", "Celadon Mansion (Condominiums) 1F — the old woman", needs=("erika",), driver="tea",
         done=(("flag", 0x2A6), ("item", TEA)),
         steps=("quest('tea') walks to Celadon Mansion 1F and takes the Tea from the old woman (she gives it freely).",
                "Walk into any Saffron gate house (Routes 5, 6, 7, 8): the thirsty guard drinks it and lets you into Saffron City for good."),
         tip="go_to Saffron says 'gate guards want Tea' until you have it."),
    Beat("pokemon_tower", "Pokémon Tower: rescue Mr. Fuji", "Lavender Town, the tall tower (1F-7F)", needs=("rocket_hideout",), driver="pokemon_tower",
         done=(("flag", 0x23C),),
         steps=("Needs the Silph Scope (without it 6F's ghost is invisible). Heal and carry Antidotes / Paralyze Heals / Revives.",
                "2F: your rival fights you on the way up. 3F-5F: Channelers and wild Gastly/Haunter (Ghost: Normal and Fighting moves do nothing — "
                "use Psychic / Ground / Ghost / Dark, or just Poké Doll/run).",
                "6F: the Marowak ghost — with the Silph Scope it becomes a normal fight; defeat it.",
                "7F: three Rocket Grunts guard Mr. Fuji at (11,4): beat them and he is freed (he walks home to Lavender)."),
         tip="Mr. Fuji's reward is the Poké Flute — see the next beat."),
    Beat("poke_flute", "Poké Flute from Mr. Fuji", "Lavender Town, Volunteer Pokémon House (west side)", needs=("pokemon_tower",), driver="poke_flute",
         done=(("flag", 0x23D), ("item", POKE_FLUTE)),
         steps=("Walk into the Volunteer Pokémon House next to the Pokémon Center in Lavender; Mr. Fuji is at (3,3) — talk to him and take the Poké Flute.",)),
    Beat("snorlax", "Wake the Snorlax (Route 12 → Fuchsia)", "Route 12, south of Lavender", needs=("poke_flute",), driver="snorlax", done=(("flag", 0x253),),
         steps=("Walk south from Lavender down Route 12 until the sleeping Snorlax blocks the path at (14,70).",
                "Face it and press A: with the Poké Flute in the bag the game asks to play it → YES, then fight it (L30 Snorlax: weaken, then throw Ultra Balls, or just win).",
                "Routes 12 → 13 → 14 → 15 lead on to Fuchsia City. (Route 16's Snorlax, west of Celadon, blocks the Cycling Road — also needs the flute and a Bicycle; "
                "the Route 12 road is the way.)"),
         tip="Do this fight at full HP; it hits hard and has lots of HP."),
    Beat("koga", "Soul Badge — Koga (Poison)", "Fuchsia City Gym", needs=("snorlax",), driver="koga", done=(("badge", 4),),
         steps=("Fuchsia City via Routes 12-15 (after the Snorlax).", "The Gym has invisible walls; challenge_leader() walks it. Bring Antidotes and Full Heals.",
                "Ground / Psychic beat his Poison team.")),
    Beat("surf", "HM03 Surf (Safari Zone Secret House)", "Fuchsia City → Safari Zone", needs=("snorlax",), driver="surf",
         done=(("flag", 0x239),), steps=("quest('surf'): pays the ¥500 entry, crosses the Safari Zone's four areas and takes HM03 from the Secret House.",)),
    Beat("strength", "HM04 Strength (Gold Teeth → the Warden)", "Safari Zone West → Fuchsia, the Warden's house", needs=("snorlax",), driver="strength",
         done=(("flag", 0x23A),), steps=("quest('strength'): fetches the Gold Teeth in Safari Zone West and returns them to the Warden for HM04.",)),
    Beat("silph_co", "Silph Co.: beat Giovanni, get the Master Ball", "Saffron City, Silph Co. (11 floors)", needs=("tea", "pokemon_tower"), driver="silph_co",
         done=(("flag", 0x250),),
         steps=("Saffron City needs the Tea (a gate guard drinks it). The Rockets have taken Silph Co.; the Gym and Dojo stay closed until they are gone.",
                "Silph Co.'s door is blocked by a Rocket guard until Mr. Fuji is rescued in Pokémon Tower (quest('pokemon_tower')); after that he sleeps beside the door.",
                "1F → take the elevator or stairs; the Card Key is an item ball on 5F at (22,21). With it, the card-key doors (puzzle tiles) open — face the door and press A.",
                "7F: your rival (Blue) fights you; once Giovanni is beaten, the worker at (0,7) gives you a Lapras (L25, knows Surf-line water moves).",
                "11F: Giovanni fights you; beat him and the President gives you the Master Ball (use it on a legendary).",
                "Heal at the Saffron Pokémon Center between floors; the Rocket trainers here are L25-37.")),
    Beat("hitmon", "Hitmonchan or Hitmonlee from the Fighting Dojo (optional)", "Saffron City, the Dojo", needs=("tea",), driver="hitmon", optional=True,
         done=(("flag", 0x278),),
         steps=("Beat Master Koichi (L37-38 Fighting types), then choose ONE ball: Hitmonlee (kicks) or Hitmonchan (punches: Thunder / Ice / Fire Punch coverage) — the other is gone. quest('hitmon') takes Hitmonchan.",)),
    Beat("copycat", "Mimic from Saffron's Copycat (optional)", "Celadon Dept. Store 2F (Poké Doll) → Saffron City, the Copycat's house", needs=("silph_co",), driver="copycat", optional=True,
         done=(("flag", 0x2CD),),
         steps=("A Rocket grunt stands at the Copycat house's door until Silph Co. is cleared (quest('silph_co')). The girl upstairs then teaches Mimic ONCE, for a Poké Doll (¥1000 at the Celadon Dept. Store 2F). quest('copycat') buys the doll and runs the lesson.",
                "Mimic copies the foe's last move — rarely worth a slot; this is mostly for completeness.")),
    Beat("running_shoes", "Running Shoes from Oak's Aide in Pewter City", "Pewter City (a forced scene after Brock)", needs=("brock",), optional=True,
         done=(("flag", 0x82F),),
         steps=("Oak's Aide meets you in Pewter City after the Gym (a forced scene, nothing to drive) and the Running Shoes arrive: FLAG_SYS_B_DASH. Holding B then runs at about twice walking speed.",)),
    Beat("old_rod", "Old Rod from the Vermilion Fishing Guru (optional)", "Vermilion City, house 1", needs=("misty",), driver="old_rod", optional=True,
         done=(("flag", 0x240),), steps=("\"Do you like to fish?\" YES: the Old Rod (Magikarp-grade fishing). Needs nothing else.",)),
    Beat("good_rod", "Good Rod from the Fuchsia Fishing Guru (optional)", "Fuchsia City, house 2", needs=("snorlax",), driver="good_rod", optional=True,
         done=(("flag", 0x244),), steps=("\"Do you like to fish?\" YES: the Good Rod (Goldeen, Krabby, Poliwag line).",)),
    Beat("super_rod", "Super Rod from the Route 12 Fishing Guru (optional)", "Route 12, the fishing house", needs=("poke_flute",), driver="super_rod", optional=True,
         done=(("flag", 0x255),), steps=("The fishing house on Route 12 (south half, past the gate house): the Super Rod, the best Kanto rod.",)),
    Beat("bike", "Bicycle: Fan Club voucher → Cerulean Bike Shop (optional)", "Vermilion Pokémon Fan Club → Cerulean City", needs=("misty",), driver="bike", optional=True,
         done=(("flag", 0x271),), steps=("The chairman of the Vermilion Pokémon Fan Club tells his story and gives the Bike Voucher; the Cerulean Bike Shop swaps it for the Bicycle.",
                                         "Twice walking speed; the Cycling Road (Routes 16-18) needs it. Not usable indoors, in caves or on water.")),
    Beat("itemfinder", "Itemfinder from Oak's Aide, 30 caught (optional)", "Route 11, the gatehouse's 2nd floor", needs=("surge",), driver="itemfinder", optional=True,
         done=(("flag", 0x252),),
         steps=("Oak's Aide on the 2nd floor of Route 11's east gatehouse trades the Itemfinder for 30 species CAUGHT.",)),
    Beat("exp_share", "Exp. Share from Oak's Aide, 50 caught (optional)", "Route 15, the west gatehouse's 2nd floor", needs=("snorlax",), driver="exp_share", optional=True,
         done=(("flag", 0x256),),
         steps=("Oak's Aide on the 2nd floor of Route 15's west gatehouse trades the Exp. Share for 50 species CAUGHT; hold it on the Pokémon that lags behind.",)),
    Beat("zapdos", "Zapdos in the Power Plant (optional, a legendary)", "Route 10 → the Power Plant (Surf)", needs=("surf",), driver="zapdos", optional=True,
         done=(("flag", 0x2BF),),
         steps=("The Power Plant is across Route 10's water: Surf. Zapdos (L50, Electric/Flying) sits at (5,11) and appears ONCE — win, run or teleport and it is gone; only a catch keeps it.",
                "Heal, save_state, bring Ultra Balls (or the Master Ball from Silph Co.): quest('zapdos') walks up and starts the fight; the one-shot protocol (slot 9 auto-save, gentle weakening, status, catch) does the rest.",
                "Ground types shrug off its Electric moves; Ice / Rock / Electric hit it hard but must not knock it out.")),
    Beat("articuno", "Articuno in the Seafoam Islands (optional, a legendary)", "Route 20 → Seafoam Islands B3F boulders → B4F (Surf, Strength)", needs=("surf", "strength"),
         driver="articuno", optional=True, done=(("flag", 0x2BE),),
         steps=("Route 20 is open water (Surf). Seafoam's B4F is swept by currents until two boulders from B3F's south-west room fall through its holes: quest('articuno') does the pushes (Strength).",
                "Back on B4F the current is gone: surf north to Articuno (L50, Ice/Flying) at (9,2). It appears ONCE — only a catch keeps it.",
                "Heal, save_state, bring Ultra Balls (or the Master Ball): the one-shot protocol (slot 9 auto-save, gentle weakening, status, catch) does the rest. Fire / Electric / Rock hit it hard but must not knock it out.")),
    Beat("sabrina", "Marsh Badge — Sabrina (Psychic)", "Saffron City Gym", needs=("silph_co",), driver="sabrina", done=(("badge", 5),),
         steps=("The Gym opens once Silph Co. is cleared. The gym is a teleport-pad maze: challenge_leader() uses the pads.",
                "Bug / Ghost / Dark beat Psychic; her Alakazam is fast — Dark types or strong Ghost moves are best.")),
    Beat("pokemon_mansion", "Pokémon Mansion: the Secret Key", "Cinnabar Island, the burnt mansion (1F-3F, B1F)", needs=("surf",), driver="pokemon_mansion",
         done=(("item", SECRET_KEY),),
         steps=("Surf south from Fuchsia (Routes 19-20) to Cinnabar Island; the Mansion is the large building in the north-west.",
                "The Secret Key is an item ball on B1F at (5,7). The Mansion is full of statue switches (press A facing a statue: it flips every barrier) — "
                "the router solves them when a route needs them.",
                "Without the Secret Key the Cinnabar Gym door stays locked.")),
    Beat("blaine", "Volcano Badge — Blaine (Fire)", "Cinnabar Island Gym", needs=("pokemon_mansion",), driver="blaine", done=(("badge", 6),),
         steps=("Open the Gym door with the Secret Key. Inside, answer Blaine's quiz correctly (or fight the trainers) to reach him.",
                "Water / Ground / Rock beat his Fire team.")),
    Beat("giovanni", "Earth Badge — Giovanni (Ground)", "Viridian City Gym", needs=("blaine", "sabrina", "koga"), driver="giovanni", done=(("badge", 7),),
         steps=("Fly or walk back to Viridian City. The Gym is closed until you hold the other seven badges.",
                "It is a spinner-tile maze; challenge_leader() plans the slides. Water / Grass / Ice beat his Ground team.")),
    Beat("victory_road", "Route 22 → Route 23 → Victory Road → Indigo Plateau", "Viridian City → Route 22 / 23 → Victory Road → Indigo Plateau",
         needs=("giovanni",), driver="victory_road", done=(("flag", 0x899),),                      # FLAG_VISITED_INDIGO_PLATEAU (the Fly-town flag)
         steps=("Route 22 (west of Viridian): your rival fights you at the entrance. Route 23: the badge checkpoints check them in order — all eight.",
                "Victory Road (3 floors) needs Strength for its boulders (use_hm('strength'), then walk into the boulder); Route 23's middle is a river — Surf crosses it (go_to does that). Bring Revives and Max Potions — "
                "its trainers and wild Pokémon are L36-45.",
                "Indigo Plateau: heal and save at the Pokémon Center, stock Full Restores / Revives, then talk to the Elite Four's door. Aim for L50+ across the team."),
         tip="After this there is only the Elite Four (Lorelei, Bruno, Agatha, Lance) and your rival as Champion."),
    Beat("elite_four", "Pokémon League: the Elite Four and the Champion", "Indigo Plateau, north door of the Pokémon Center",
         needs=("victory_road",), driver="elite_four", done=(("flag", 0x82C),),                       # FLAG_SYS_GAME_CLEAR: set in the Hall of Fame
         steps=("Prep BEFORE the first door: heal, shop (Full Restores, Revives, Max Potions), save_state — the League's doors seal behind you, there is no healing or leaving until the Champion.",
                "Lorelei (Ice, L51-56) → Bruno (Fighting/Rock) → Agatha (Ghost/Poison) → Lance (Dragon/Flying, L56-62) → your rival the Champion (L53-65, a mixed team that counters your starter).",
                "Every room: walk up to the leader and talk; each win opens the next door. After the Champion: the Hall of Fame, Oak's speech and the credits."),
         tip="A loss resets the whole League (the decomp's EventScript_ResetEliteFourEnd clears every defeated flag), heals the party, costs some money and respawns you in the Plateau's Center: quest('elite_four') starts again from the first door (load_state(3) restores the pre-door save if you prefer)."),
)
BY_KEY = {b.key: b for b in BEATS}
CHAIN_KEYS = tuple(b.key for b in BEATS)
# extra aliases accepted by quest('…')
ALIASES = {"tower": "pokemon_tower", "mansion": "pokemon_mansion", "flute": "poke_flute", "pokeflute": "poke_flute",
           "silph": "silph_co", "silphco": "silph_co", "hideout": "rocket_hideout", "scope": "rocket_hideout", "silph_scope": "rocket_hideout",
           "saffron": "silph_co", "elite4": "elite_four", "league_rooms": "elite_four", "champion": "elite_four", "hall_of_fame": "elite_four", "snorlax_12": "snorlax", "victory": "victory_road", "league": "victory_road", "oak": "parcel"}


def resolve(name):
    """Beat for a quest name (exact key, alias, or a unique substring of key/title); None when unknown."""
    key = str(name or "").lower().strip().replace("é", "e").replace(".", "").replace("'", "").replace(" ", "_").replace("-", "_")
    if not key:
        return None
    key = ALIASES.get(key, key)
    if key in BY_KEY:
        return BY_KEY[key]
    hits = [b for b in BEATS if key in b.key or key in b.title.lower()]
    return hits[0] if len(hits) == 1 else None


def evaluate(done_check, overrides=None) -> dict:
    """{key: 'done' | 'next' | 'blocked'} for the whole chain. `done_check(spec)` -> bool for one done-spec; `overrides` = {key: bool} where
    a driver knows better than the flags (quest('cut') is only done once Cut is TAUGHT, not when HM01 is merely in the bag).
    'next' = every need is done."""
    overrides = overrides or {}
    done = {b.key for b in BEATS if (overrides[b.key] if b.key in overrides else any(done_check(s) for s in b.done))}
    out = {}
    for b in BEATS:
        if b.key in done:
            out[b.key] = "done"
        elif all(n in done for n in b.needs):
            out[b.key] = "next"
        else:
            out[b.key] = "blocked"
    return out


def next_beats(status: dict, include_optional: bool = False) -> list:
    """The beats to do next: not done, every need met. Required ones first, in chain order."""
    ready = [b for b in BEATS if status.get(b.key) == "next" and (include_optional or not b.optional)]
    return ready


def missing_needs(beat: Beat, status: dict) -> list:
    return [BY_KEY[n] for n in beat.needs if status.get(n) != "done"]


def story_line(status: dict) -> str:
    """One line for the observation: the next required beat (and how), or '' when the chain is finished."""
    ready = next_beats(status)
    if not ready:
        return ""
    b = ready[0]
    how = f"quest('{b.driver}')" if b.driver else f"quest('{b.key}') for the plan"
    more = f" (also open: {', '.join(x.key for x in ready[1:3])})" if len(ready) > 1 else ""
    return f"STORY NEXT: {b.title} — {b.where}. {how}{more}"


def listing(status: dict) -> str:
    """The whole chain for quest(): ✔ done / ▶ next / … blocked, scripted beats marked."""
    lines = []
    for b in BEATS:
        st = status.get(b.key, "blocked")
        mark = {"done": "✔", "next": "▶", "blocked": "…"}[st]
        tag = f" [quest('{b.driver}') runs it]" if b.driver and st != "done" else (" [guide]" if not b.driver and st != "done" else "")
        opt = " (optional)" if b.optional else ""
        from knowledge.beat_readiness import NEEDS
        if st != "done" and b.key in NEEDS:
            opt += f" [rec. L{NEEDS[b.key].top}+]"
        need = ""
        if st == "blocked":
            need = " — first: " + ", ".join(n.key for n in missing_needs(b, status))
        lines.append(f"{mark} {b.key}: {b.title}{opt}{tag}{need}")
    return "Story, start to Elite Four (quest('<name>') = the script or the plan):\n" + "\n".join(lines)


def plan(beat: Beat, status: dict) -> str:
    """The plan for one beat, state-aware: done / blocked-by / steps / tip."""
    st = status.get(beat.key, "blocked")
    head = f"{beat.title} — {beat.where}."
    if st == "done":
        return head + " Already done."
    out = [head]
    if st == "blocked":
        out.append("Not yet: first " + ", ".join(f"{n.title} (quest('{n.key}'))" for n in missing_needs(beat, status)) + ".")
    if beat.driver:
        out.append(f"quest('{beat.driver}') runs it.")
    out += [f"{i}. {s}" for i, s in enumerate(beat.steps, 1)]
    from knowledge.beat_readiness import recommendation
    if rec := recommendation(beat.key):
        out.append(rec)
    if beat.tip:
        out.append(beat.tip)
    return "\n".join(out)
