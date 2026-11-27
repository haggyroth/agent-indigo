"""The main storyline, start to Elite Four, as an ordered chain of BEATS (pure data + logic; no I/O).

Why: the model only had a few scripted quests (ss_ticket, cut, surf, strength, coin_case, rocket_hideout) and, after Erika, nothing told
it what comes next — it ground wild Pokémon for 700 s with no story step in sight. Each beat here says WHAT it is, WHERE, what must come
first, how to tell it is DONE (flags / key items / badges read from the game, verified against the pret/pokefirered decomp), and the STEPS.
`quest()` lists the chain with ✔ done / ▶ next / … blocked; `quest('<key>')` runs the script when there is a driver, else prints the plan
(state-aware: it names what is still missing). The observation shows the next beat in one line.

Flags and item ids below are the decomp's (constants/flags.h, constants/items.h); gym badges are bits of the badge byte
(Boulder 0, Cascade 1, Thunder 2, Rainbow 3, Soul 4, Marsh 5, Volcano 6, Earth 7)."""
from dataclasses import dataclass, replace
from typing import NamedTuple

# done-spec kinds: ("flag", id) · ("item", key-item id) · ("badge", bit) · ("milestone", name) · ("tower", n Trainer Tower prizes received) — a beat is done if ANY holds
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
    gate: tuple = ()           # availability conditions BESIDES `needs` (side quests): ("owned", n) species caught · ("badges", n) · ("gameclear",) the Hall of Fame
    payoff: str = ""           # one line: what finishing it is worth (side quests)

    @property
    def tier(self) -> str:
        """main = on the road to the Elite Four · side = optional, doable before the Hall of Fame · post = only after it."""
        return "post" if ("gameclear",) in self.gate else ("side" if self.optional else "main")


BEATS: tuple[Beat, ...] = (
    Beat("parcel", "Oak's Parcel → Pokédex", "Viridian City Mart → Pallet Town (Oak's Lab)", driver="new_game",
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
         steps=("Cut the tree at the Gym door; challenge_leader() solves the two trash-can switches for you.", "Ground-type Pokémon are immune to his Electric attacks.")),
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
                "Routes 12 → 13 → 14 → 15 lead on to Fuchsia City. (Route 16's Snorlax, west of Celadon, blocks the shortcut — the Cycling Road — see quest('snorlax_16') and quest('bike'); "
                "the Route 12 road is the way without them.)"),
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
         steps=("Beat Master Koichi (L37-38 Fighting types), then choose ONE ball: Hitmonlee (kicks) or Hitmonchan (punches) — the other is gone for good. The choice is yours: quest('hitmon lee') or quest('hitmon chan').",)),
    Beat("eevee", "Eevee from Celadon Mansion's roof room (optional)", "Celadon City, the Mansion: 3F -> the roof -> the room (7,3)", needs=("tea",), driver="eevee", optional=True,
         done=(("flag", 0x263),),                                                              # FLAG_GOT_EEVEE
         steps=("The Poké Ball in the little room on top of Celadon Mansion is a free level 25 Eevee (the party, or the PC when it is full).",
                "A Water / Thunder / Fire Stone evolves it (Vaporeon / Jolteon / Flareon): the choice, and the stone, are yours.")),
    Beat("mt_moon_fossil", "A fossil from Mt. Moon B2F: Helix or Dome (optional)", "Mt. Moon B2F, the two fossils at (13,7) and (14,7)", needs=("brock",), driver="mt_moon_fossil", optional=True,
         done=(("flag", 0x232),),                                                              # FLAG_GOT_FOSSIL_FROM_MT_MOON
         steps=("On Mt. Moon's lowest floor two fossils sit side by side behind a Super Nerd (a trainer battle): you may take ONE — the Dome Fossil (Kabuto, Kabutops: Rock / Water, strong attacker) or the Helix Fossil (Omanyte, Omastar: Rock / Water, bulky). He takes the other for good.",
                "The choice is yours: quest('mt_moon_fossil dome') or quest('mt_moon_fossil helix'). The Cinnabar Pokémon Lab revives it later (quest('fossil'))."),
         tip="Dex-wise only one of the two lines is reachable this way; the other needs a trade partner."),
    Beat("old_amber", "Old Amber from the Pewter Museum scientist (optional)", "Pewter City, the Museum's second (right-hand) door -> the scientist at (21,3)", needs=("cut",), driver="old_amber", optional=True,
         done=(("flag", 0x25E),),                                                              # FLAG_GOT_OLD_AMBER
         steps=("Use the Pewter Museum's second door (the right-hand one, Pewter City (25,4)) — no ticket needed on that side, but a Cut tree stands in front of it (quest('cut')) — and talk to the scientist at (21,3): he gives the Old Amber free.",
                "The Cinnabar Pokémon Lab revives it into an Aerodactyl (L5; Rock / Flying) — the revival machine sits behind the Secret Key (Pokémon Mansion). It is a dex entry and a fast, hard-hitting attacker; Mt. Moon's Helix / Dome Fossil is the either-or alternative.")),
    Beat("copycat", "Mimic from Saffron's Copycat (optional)", "Celadon Dept. Store 2F (Poké Doll) → Saffron City, the Copycat's house", needs=("silph_co",), driver="copycat", optional=True,
         done=(("flag", 0x2CD),),
         steps=("A Rocket grunt stands at the Copycat house's door until Silph Co. is cleared (quest('silph_co')). The girl upstairs then teaches Mimic ONCE, for a Poké Doll (¥1000 at the Celadon Dept. Store 2F). quest('copycat') buys the doll and runs the lesson.",
                "Mimic copies the foe's last move — rarely worth a slot; this is mostly for completeness.")),
    Beat("vs_seeker", "VS Seeker from the woman in Vermilion's Pokémon Center (optional)", "Vermilion City, Pokémon Center 1F", needs=("misty",), optional=True,
         done=(("flag", 0x292),),                                                            # FLAG_GOT_VS_SEEKER
         steps=("Talk to the woman in Vermilion City's Pokémon Center: she gives the VS Seeker, free.",
                "Used outdoors (Bag > VS Seeker) after about 100 steps of charge, it makes the trainers you have beaten who are in range ready for a rematch; walk to each and fight (quest('rematch') drives the loop: it charges the battery, uses it, walks up to every flagged trainer and hands each battle to you).",
                "Each trainer has a ladder of stronger parties that opens as the story advances (the Celadon / Fuchsia visits, the Hall of Fame, the Sevii Islands' Network Machine): the observation's REMATCHES line counts where every ladder stands."),
         tip="A long loop (charge, use, fight, repeat) — worth it for experience and money when the team needs levels, and for the 'top team of every rematchable trainer' completion goal."),
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
    Beat("snorlax_16", "Wake Route 16's Snorlax (the Cycling Road, optional)", "Route 16, Celadon's side", needs=("poke_flute",), driver="snorlax_16", optional=True,
         done=(("flag", 0x080),), steps=("Celadon's west exit lands on Route 16's east end; the second sleeping Snorlax plugs the road at (31,13) — a second chance at a catch (the one-shot protocol applies).",
                                         "Face it from (32,13), press A: play the Poké Flute → YES, then fight (weaken, then catch). Beyond it the Cycling Road's gate house needs the Bicycle: quest('bike')."),
         tip="Optional: Fuchsia is reached by Routes 12-15 without it. The Cycling Road (Celadon → Fuchsia in a few minutes) needs this plus the Bicycle."),
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
    Beat("sevii_one_island", "One Island: Bill's forced sail, then Celio (the Sevii Islands)", "Cinnabar Island after Blaine -> One Island, Pokémon Center", needs=("blaine",), optional=True,
         done=(("flag", 0x89B),),                                                            # FLAG_WORLD_MAP_ONE_ISLAND
         steps=("Beating Blaine starts a forced scene: Bill is at Cinnabar and sails you to One Island (the Seagallop). Celio in One Island's Pokémon Center gives the Tri-Pass and a Town Map page.",
                "A first detour then ends at Three Island's port (FLAG_SEVII_DETOUR_FINISHED). The Seagallop from Vermilion / Cinnabar then takes the Tri-Pass to One-Three Island.",
                "Celio's real request waits for the National Pokédex (the National Dex beat): after the Hall of Fame, 60 species caught and this visit."),
         tip="Information only: the ferry scenes are not driven yet — go_to / fly_to work on the islands you have visited."),
    Beat("berry_forest", "Berry Forest on Three Island: rescue Lostelle", "Three Island -> Bond Bridge -> Berry Forest (the Tri-Pass ferry)", needs=("sevii_one_island",), optional=True,
         done=(("flag", 0x2A3),),                                                            # FLAG_RESCUED_LOSTELLE
         steps=("Past the Bond Bridge the forest is a maze of trees with wild Pokémon and a few trainers; Lostelle (a little girl who ran off) is at the far end.",
                "Talk to her: the rescue sets FLAG_RESCUED_LOSTELLE, she hands over an Iapapa Berry and the forest's hidden path home opens."),
         tip="The forest's item balls are in the Three Island sweep (quest('sweep Two-Three Island')); a Repel keeps the trip short."),
    Beat("moltres", "Moltres on Mt. Ember's summit (legendary, appears once)", "One Island -> Mt. Ember -> the Summit", needs=("sevii_one_island",), driver="moltres", optional=True,
         done=(("flag", 0x2BD),),                                                            # FLAG_FOUGHT_MOLTRES
         steps=("A level 50 Fire / Flying static encounter at the top of Mt. Ember (Sevii). Talking to it starts the fight; it is gone for good once you win or catch it (FLAG_FOUGHT_MOLTRES), but if you run it stays.",
                "Weaken it without fainting it (False Swipe, a status move), then throw Ultra / Master Balls; save_state first so a faint or a bad throw can be retried."),
         tip="Needs the Sevii islands open (One Island) and the way up Mt. Ember; the Ruby Path (Celio's Ruby) is a different cave."),
    Beat("elite_four", "Pokémon League: the Elite Four and the Champion", "Indigo Plateau, north door of the Pokémon Center",
         needs=("victory_road",), driver="elite_four", done=(("flag", 0x82C),),                       # FLAG_SYS_GAME_CLEAR: set in the Hall of Fame
         steps=("Prep BEFORE the first door: heal, shop (Full Restores, Revives, Max Potions), save_state — the League's doors seal behind you, there is no healing or leaving until the Champion. Inside, heal() heals from the Bag only (Revives, Full Restores, Potions), and the quest tops the team up before each leader.",
                "Lorelei (Ice, L51-56) → Bruno (Fighting/Rock) → Agatha (Ghost/Poison) → Lance (Dragon/Flying, L56-62) → your rival the Champion (L53-65, a mixed team that counters your starter).",
                "Every room: walk up to the leader and talk; each win opens the next door. After the Champion: the Hall of Fame, Oak's speech and the credits."),
         tip="A loss resets the whole League (the decomp's EventScript_ResetEliteFourEnd clears every defeated flag), heals the party, costs some money and respawns you in the Plateau's Center: quest('elite_four') starts again from the first door. You keep every level the losing fights gave you — train first if the shortfall is large; don't load_state (it discards that Exp)."),
    Beat("national_dex", "National Pokédex from Prof. Oak (post-game)", "Pallet Town, Oak's Lab — after the Hall of Fame, with 60 species caught and One Island visited",
         needs=("elite_four",), optional=True, done=(("flag", 0x840),),                       # FLAG_SYS_NATIONAL_DEX
         steps=("Only after the Hall of Fame. The scene needs 60 species CAUGHT and the Sevii Islands reached (One Island: Celio's Network Machine, then the Seagallop from Vermilion).",
                "Then talk to Prof. Oak in his lab in Pallet Town: he asks a favour, your rival joins, and the Pokédex is extended beyond Kanto (EnableNationalPokedex).",
                "It adds no new wild Pokémon by itself; it is progress for a completion run (Pokédex entries, the Sevii Islands)."),
         tip="Nothing here is scripted yet: reach One Island yourself (go_to / fly_to), then talk to Oak."),
    Beat("sevii_ruby", "Celio's Ruby from Mt. Ember (Sevii)", "One Island: Celio -> Mt. Ember, Ruby Path", needs=("sevii_one_island", "national_dex"), optional=True,
         done=(("flag", 0x2DD),),                                                            # FLAG_GOT_RUBY
         steps=("Needs the National Pokédex: Celio then asks for a special gemstone (the Ruby) and sets Mt. Ember going.",
                "Mt. Ember's Ruby Path (down to its lowest floor) holds the Ruby (FLAG_GOT_RUBY). Bring it back to Celio: he puts it in the Network Machine and trades your Tri-Pass for the Rainbow Pass (and a Town Map page for Four-Seven Island)."),
         tip="Mt. Ember also has Moltres at its summit (legendaries issue); the Ruby Path is a separate cave."),
    Beat("sevii_sapphire", "Celio's Sapphire from the Five Island warehouse (Sevii)", "Five Island: the Rocket Warehouse (Scientist Gideon)", needs=("sevii_ruby",), optional=True,
         done=(("flag", 0x2DC),),                                                            # FLAG_RECOVERED_SAPPHIRE
         steps=("With the Rainbow Pass the Seagallop reaches Four-Seven Island. The Sapphire is held by Team Rocket in Five Island's Rocket Warehouse: beat Scientist Gideon there (FLAG_RECOVERED_SAPPHIRE) and keep the Sapphire."),
         tip="Gideon's fight is the one that matters; the grunts around him are optional experience."),
    Beat("network_machine", "Network Machine linked (Sevii)", "One Island, Pokémon Center: Celio", needs=("sevii_sapphire",), optional=True,
         done=(("flag", 0x844),),                                                            # FLAG_SYS_CAN_LINK_WITH_RS
         steps=("Give Celio the Sapphire. The Network Machine links with Hoenn: the Cerulean Cave guard leaves (Cerulean Cave opens), Lorelei's house is empty, the roaming beast starts roaming, and every trainer's later rematch teams open (the VS Seeker).",),
         tip="This is the gate for the post-game: Cerulean Cave (Mewtwo), the roamer, and the strongest rematch teams."),
    Beat("mewtwo", "Mewtwo in Cerulean Cave (legendary, appears once)", "Cerulean City -> Cerulean Cave B1F", needs=("network_machine",), driver="mewtwo", optional=True,
         done=(("flag", 0x2BC),),                                                            # FLAG_FOUGHT_MEWTWO
         steps=("The Network Machine (Celio, One Island) makes the Cerulean Cave guard leave: the cave north-west of Cerulean City opens. Mewtwo, level 70, waits on B1F; it is gone for good once you win or catch it (FLAG_FOUGHT_MEWTWO).",
                "Bring a full team, plenty of Hyper Potions / Revives and the Master Ball (Silph Co.) or a stack of Ultra Balls; save_state before the fight."),
         tip="The roaming beast the Network Machine starts is chosen by your starter: Raikou for Squirtle, Entei for Bulbasaur, Suicune for Charmander (level 50, roaming the Kanto routes); it runs, so Mean Look / a speed lead / a sleep move helps."),
    Beat("icefall_cave", "Icefall Cave on Four Island: rescue Lorelei", "Four Island -> Icefall Cave (the Rainbow Pass ferry), through to its back chamber", needs=("sevii_ruby",), optional=True,
         done=(("flag", 0x08E),),                                                            # FLAG_HIDE_RUIN_VALLEY_SCIENTIST: set by the rescue scene
         steps=("Team Rocket grunts hold Lorelei in the cave's back chamber: reach it from the south entrance (the cave is a slippery ice maze with item balls on the way) and beat the three grunts.",
                "Lorelei thanks you and goes home to Four Island; the scene sets VAR_MAP_SCENE_ICEFALL_CAVE_BACK."),
         tip="The Icefall Cave sweep (quest('sweep Four Island / Icefall Cave')) lists its items; bring a healed team for the grunts."),
    Beat("tanoby_ruins", "Tanoby Ruins on Seven Island: open the chambers (the Unown)", "Seven Island -> Sevault Canyon (the Tanoby Key) -> Tanoby Ruins", needs=("sevii_ruby",), optional=True,
         done=(("flag", 0x849),),                                                            # FLAG_SYS_UNLOCKED_TANOBY_RUINS
         steps=("In Sevault Canyon the Tanoby Key room is a switch puzzle: press the seven switches (the boulders move to their solved places) and take the Tanoby Key.",
                "With the key the Tanoby Ruins' seven chambers open (Monean, Liptoo, Weepth, Dilford, Scufib, Rixy, Viapois): each holds a wall puzzle and a room of Unown forms — a long tail of Pokédex entries and the Hoenn-style Unown letters."),
         tip="Unown is a Dex entry for a completion run; the chambers' wild forms are in the generated encounter data (quest('dex') lists where)."),
    Beat("trainer_tower", "Trainer Tower on Seven Island: win all four challenges", "Seven Island -> Trainer Tower (the Rainbow Pass ferry)", needs=("sevii_ruby",), driver="trainer_tower", optional=True,
         done=(("tower", 4),),                                                               # the Owner's prize for Single, Double, Knockout and Mixed
         steps=("A TIME ATTACK: from the reception counter up eight floors (up to three trainers each) to the Owner on the roof, against the clock (it stops at 59:59). Doing it with the Owner's prize in hand wins that challenge.",
                "Four challenge types — Single, Double, Knockout and Mixed — each its own record and its own prize (SaveBlock1 trainerTower[0..3]; the progress line counts the prizes received).",
                "The trainers' Pokémon are set to your party's highest level (so a stronger team does not make it easier) and winning gives no Exp or money; a loss sends you back to the lobby."),
         tip="quest('trainer_tower single|double|knockout|mixed') runs one challenge (every battle is yours to play; there is no fleeing). Bring a deep, healed team: there is no Center on the way."),
)
# Gate flags beyond the badges/owned counts, with the reason shown while they are unmet (agent.story.side_ctx reads exactly these).
FLAG_GATES = {0x89B: "needs a visit to One Island (the Sevii Islands) first"}      # FLAG_WORLD_MAP_ONE_ISLAND

# What each optional beat is worth, and any gate beyond its `needs` (the Oak's Aide counts are knowledge/aides.py). Information for the model, never a wall.
SIDE_INFO = {
    "dig": ("TM28 Dig", ()), "magikarp": ("a Magikarp for ¥500 (a slow starter, a strong finish)", ()), "flash": ("HM05 Flash (lights the caves)", (("owned", 10),)),
    "fly": ("HM02 Fly (fast travel to any visited town)", ()), "coin_case": ("the Coin Case (Game Corner prizes)", ()), "hitmon": ("Hitmonlee or Hitmonchan — your choice", ()),
    "copycat": ("the move Mimic", ()), "eevee": ("an Eevee (L25; stone evolutions for the Pokédex)", ()), "mt_moon_fossil": ("a Helix or Dome Fossil (Omanyte or Kabuto once revived; one of the two)", ()), "old_amber": ("the Old Amber (an Aerodactyl once revived at Cinnabar)", ()), "running_shoes": ("the Running Shoes (hold B to run)", ()), "old_rod": ("the Old Rod (fishing)", ()),
    "good_rod": ("the Good Rod (better fishing)", ()), "super_rod": ("the Super Rod (the best Kanto rod)", ()), "bike": ("the Bicycle (twice the speed; the Cycling Road)", ()),
    "snorlax_16": ("a second Snorlax to catch (Cycling Road)", ()), "itemfinder": ("the Itemfinder (hidden items)", (("owned", 30),)),
    "exp_share": ("the Exp. Share", (("owned", 50),)),
    "vs_seeker": ("the VS Seeker: rematches with beaten trainers (experience, money; every top team is an achievement)", ()),
    "trainer_tower": ("Trainer Tower: four challenge prizes (a Time Attack; 5 points each in the RetroAchievements set)", (("gameclear",),)),
    "berry_forest": ("Lostelle's rescue: an Iapapa Berry and Berry Forest's wild Pokémon", ()),
    "icefall_cave": ("Lorelei's rescue (and Icefall Cave's items and wild Pokémon)", (("gameclear",),)),
    "tanoby_ruins": ("the Tanoby Ruins' chambers: the Unown and their Pokédex entries", (("gameclear",),)),
    "moltres": ("Moltres, a legendary (appears once)", ()),
    "mewtwo": ("Mewtwo, a legendary (appears once)", (("gameclear",), ("badges", 8))),
    "sevii_one_island": ("the Sevii Islands open (Tri-Pass, Celio, the island towns to fly to)", ()),
    "sevii_ruby": ("the Ruby and the Rainbow Pass (Four-Seven Island)", (("gameclear",),)),
    "sevii_sapphire": ("the Sapphire (completes the Network Machine's gems)", (("gameclear",),)),
    "network_machine": ("the Network Machine: Cerulean Cave, the roaming beast and the top rematch teams open", (("gameclear",),)),
    "national_dex": ("the National Pokédex (the Pokédex goes beyond Kanto)", (("gameclear",), ("owned", 60), ("flag", 0x89B))), "zapdos": ("Zapdos, a legendary (appears once)", ()), "articuno": ("Articuno, a legendary (appears once)", ()),
}
BEATS = tuple(replace(b, payoff=SIDE_INFO[b.key][0], gate=SIDE_INFO[b.key][1]) if b.key in SIDE_INFO else b for b in BEATS)
BY_KEY = {b.key: b for b in BEATS}
CHAIN_KEYS = tuple(b.key for b in BEATS)
# extra aliases accepted by quest('…')
ALIASES = {"tower": "pokemon_tower", "mansion": "pokemon_mansion", "flute": "poke_flute", "pokeflute": "poke_flute",
           "silph": "silph_co", "silphco": "silph_co", "hideout": "rocket_hideout", "scope": "rocket_hideout", "silph_scope": "rocket_hideout",
           "saffron": "silph_co", "elite4": "elite_four", "league_rooms": "elite_four", "champion": "elite_four", "hall_of_fame": "elite_four", "snorlax_12": "snorlax", "snorlax16": "snorlax_16", "route16_snorlax": "snorlax_16", "victory": "victory_road", "league": "victory_road", "oak": "parcel", "new_game": "parcel", "newgame": "parcel", "start": "parcel", "start_game": "parcel", "intro": "parcel"}


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


def first_open(key: str, status: dict):
    """The beat to run FIRST on the way to `key`: follow the unmet needs down the chain to the first one whose own needs are all met (None when `key` is done). quest('flash') needs the Thunder
    Badge (surge) → Cut → the SS Ticket → Misty: this names the one to run now, not just the next link."""
    b = BY_KEY[key]
    if status.get(key) == "done":
        return None
    for n in b.needs:
        if status.get(n) != "done":
            return first_open(n, status)
    return b


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


class SideCtx(NamedTuple):
    """What the availability gates read from the game."""
    badges: int = 0
    owned: int = 0            # species CAUGHT
    game_clear: bool = False  # the Hall of Fame (FLAG_SYS_GAME_CLEAR)
    flags: tuple = ()         # the game flags the gates ask about that are SET (see FLAG_GATES)


def gate_unmet(beat: Beat, ctx: SideCtx) -> str:
    """Why `beat`'s extra gate is not met yet ('' when it is)."""
    for kind, *arg in beat.gate:
        if kind == "owned" and ctx.owned < arg[0]:
            return f"needs {arg[0]} species caught (you have {ctx.owned})"
        if kind == "badges" and ctx.badges < arg[0]:
            return f"needs {arg[0]} badges (you have {ctx.badges})"
        if kind == "gameclear" and not ctx.game_clear:
            return "after the Hall of Fame"
        if kind == "flag" and arg[0] not in ctx.flags:
            return FLAG_GATES.get(arg[0], f"needs game flag {arg[0]:#x}")
    return ""


def side_quests(status: dict, ctx: SideCtx) -> dict:
    """The optional beats by availability: {'now': [Beat], 'locked': [(Beat, why)], 'done': [Beat]}. 'now' = every need done AND the gate met."""
    out: dict = {"now": [], "locked": [], "done": []}
    for b in BEATS:
        if b.tier == "main":
            continue
        if status.get(b.key) == "done":
            out["done"].append(b)
        elif (why := gate_unmet(b, ctx)) or status.get(b.key) != "next":
            out["locked"].append((b, why or "first: " + ", ".join(n.key for n in missing_needs(b, status))))
        else:
            out["now"].append(b)
    return out


def digest(status: dict, ctx: SideCtx) -> str:
    """One observation line: the side quests open right now (and how many more unlock later). '' when none are open — silent, never nagging."""
    sq = side_quests(status, ctx)
    if not sq["now"]:
        return ""
    names = ", ".join(f"{b.key} ({b.payoff})" if b.payoff else b.key for b in sq["now"][:6])
    more = f" (+{len(sq['now']) - 6} more)" if len(sq["now"]) > 6 else ""
    later = f"; {len(sq['locked'])} more unlock as the story advances" if sq["locked"] else ""
    return f"SIDE QUESTS you can do now (optional — your call): {names}{more}{later}. quest() lists them all."


def league_advice(status: dict, ctx: SideCtx) -> str:
    """Before the League: how many pre-Hall-of-Fame side quests are still open — advice, not a wall."""
    sq = side_quests(status, ctx)
    open_ = [b for b in sq["now"] if b.tier == "side"]
    if not open_:
        return ""
    return (f"{len(open_)} side quest{'s' if len(open_) != 1 else ''} you could still do before the Hall of Fame: "
            + ", ".join(f"{b.key} ({b.payoff})" for b in open_[:8]) + " — optional, your call (they give items, levels and Pokédex entries).")


def listing(status: dict, ctx: SideCtx | None = None) -> str:
    """The whole chain for quest(): MAIN, then the side quests (available now / locked), then post-game; ✔ done / ▶ next / … blocked, scripted beats marked."""
    ctx = ctx or SideCtx()

    def line(b: Beat, mark: str, extra: str = "") -> str:
        st = status.get(b.key, "blocked")
        tag = f" [quest('{b.driver}') runs it]" if b.driver and st != "done" else (" [guide]" if not b.driver and st != "done" else "")
        rec = ""
        from knowledge.beat_readiness import NEEDS
        if st != "done" and b.key in NEEDS:
            rec = f" [rec. L{NEEDS[b.key].top}+]"
        pay = f" — {b.payoff}" if b.payoff and st != "done" else ""
        return f"{mark} {b.key}: {b.title}{rec}{tag}{pay}{extra}"
    marks = {"done": "✔", "next": "▶", "blocked": "…"}
    main = [line(b, marks[status.get(b.key, "blocked")],
                 (" — first: " + ", ".join(n.key for n in missing_needs(b, status))) if status.get(b.key, "blocked") == "blocked" else "")
            for b in BEATS if b.tier == "main"]
    sq = side_quests(status, ctx)
    out = ["Story, start to Elite Four (quest('<name>') = the script or the plan):", "MAIN"] + main
    if sq["now"]:
        out += ["SIDE QUESTS — available now (optional: they are yours to choose, never forced)"] + [line(b, "▶") for b in sq["now"] if b.tier == "side"]
    if sq["locked"]:
        out += ["SIDE QUESTS — not yet"] + [line(b, "…", f" — {why}") for b, why in sq["locked"] if b.tier == "side"]
    if sq["done"]:
        out.append("SIDE QUESTS — done: " + ", ".join(b.key for b in sq["done"] if b.tier == "side"))
    post = [(b, why) for b, why in sq["locked"] if b.tier == "post"] + [(b, "") for b in sq["now"] if b.tier == "post"]
    if post:
        out += ["POST-GAME"] + [line(b, "▶" if not why else "…", f" — {why}" if why else "") for b, why in post]
    return "\n".join(out)


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
