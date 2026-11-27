# Canonical GBA buttons plus the synonyms models actually emit. The observation
# labels tiles by compass (N/S/E/W), so the model routinely asks for "West" or
# "N" — accept those instead of erroring and wasting a step.
_BUTTON_ALIASES = {
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "north": "Up", "south": "Down", "east": "Right", "west": "Left",
    "n": "Up", "s": "Down", "e": "Right", "w": "Left",
    "a": "A", "b": "B", "l": "L", "r": "R",
    "select": "Select", "start": "Start",
}


def normalize_button(name: str) -> str:
    """Map a button name (incl. compass synonyms like 'West'/'N') to a canonical
    GBA button. Unknown names pass through unchanged so the backend still raises a
    clear 'invalid button' error rather than this masking a typo silently."""
    if not isinstance(name, str):
        return name
    return _BUTTON_ALIASES.get(name.strip().lower(), name)


TOOLS = [
    {"type": "function", "function": {
        "name": "press_button",
        "description": "Press a GBA button. Use for menus, battle, and movement. "
                       "For movement, Up/Down/Left/Right map to North/South/West/East.",
        "parameters": {"type": "object", "properties": {
            "button": {"type": "string",
                       "enum": ["A","B","Start","Select","Up","Down","Left","Right","L","R"]},
            "times": {"type": "integer", "default": 1, "minimum": 1, "maximum": 10},
        }, "required": ["button"]},
    }},
    {"type": "function", "function": {
        "name": "walk_to",
        "description": "Walk the player to tile (x, y) on the CURRENT map. Finds a "
                       "path around walls/obstacles automatically and moves there — "
                       "use this for overworld navigation instead of pressing "
                       "direction buttons one at a time. To leave a building, walk_to "
                       "a door/exit tile. Stops early if the map changes (you crossed "
                       "an edge or entered a door) or the target can't be reached.",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        }, "required": ["x", "y"]},
    }},
    {"type": "function", "function": {
        "name": "go_to_map",
        "description": "Leave the current map by crossing a seamless connection on the "
                       "given edge (see 'Map edges' in the observation). Walks to the "
                       "opening on that edge and steps across into the adjacent map. "
                       "direction is North/South/East/West. Use this to travel between "
                       "towns and routes.",
        "parameters": {"type": "object", "properties": {
            "direction": {"type": "string",
                          "enum": ["North", "South", "East", "West"]},
        }, "required": ["direction"]},
    }},
    {"type": "function", "function": {
        "name": "go_to",
        "description": "Travel to a named map ('Pewter City') or waypoint ('Pokemon Center', 'Mart', 'Gym'). Travel "
                       "only — it won't heal, restock, catch or level, and refuses to start while your party is hurt "
                       "or out of attack PP (heal() first; force=true overrides). A wild Pokémon or trainer ENDS the "
                       "call: play the fight (use_move / catch / switch_pokemon / flee_battle), then go_to() with no "
                       "destination resumes the trip. auto_trainers=true fights trainers for you on a long march. "
                       "Also stops when the way is blocked.",
        "parameters": {"type": "object", "properties": {
            "destination": {"type": "string",
                            "description": "Map name (e.g. 'Viridian City') or waypoint "
                                           "('Pokemon Center', 'Mart', 'Gym'). Omit to resume the "
                                           "trip that an encounter interrupted."},
            "force": {"type": "boolean",
                      "description": "skip the pre-flight check (hurt / out of PP). Rarely right."},
            "auto_trainers": {"type": "boolean",
                              "description": "auto-fight trainers met on the way instead of handing each "
                                             "to you (wild Pokémon are always handed to you)."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "challenge_leader",
        "description": "Walk up to the Gym Leader and start the battle (inside the gym, healed and save_state'd "
                       "first). Then attack with use_move.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "heal",
        "description": "Restore the whole party (HP, PP, status) at the nearest Pokémon Center — or at home with Mom in Pallet Town when that is nearer (free; once Gary is beaten) — travels there, "
                       "fleeing wild battles on the way (never a shiny: catch it). Call it when HP or PP is low and you're not in a battle.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "shop",
        "description": "Restock at a Poké Mart (travels there if needed): buys the badge-scaled par levels of Balls, "
                       "Potions and cures with the money you have. The MART line in the observation shows the plan. With "
                       "`item`, buy that specific thing instead from the nearest clerk who sells it — a TM ('TM28' or 'Dig'), "
                       "a stone, a vitamin (Protein…), an X-item, Super Repel… (the Celadon Dept. Store sells TMs, stones, "
                       "vitamins and X-items). With `sell`: sell spare treasure (Nugget, Star Piece, Pearl…) or the "
                       "named `item`; healing items, stones, vitamins and balls are never sold.",
        "parameters": {"type": "object", "properties": {
            "sell": {"type": "boolean", "description": "true = sell instead of buy"},
            "item": {"type": "string", "description": "optional: one item to buy (or sell), e.g. 'TM28', 'Fire Stone', 'X Attack', 'Nugget'"},
            "quantity": {"type": "integer", "description": "how many (default 1; limited by your money)"}}},
    }},
    {"type": "function", "function": {
        "name": "switch_pokemon",
        "description": "Switch your active Pokémon (species name or 1-based slot). Costs your turn — the foe gets a "
                       "free hit — so use it for a type advantage or to save a low one, not casually. Also answers "
                       "the forced replacement after a faint.",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string",
                       "description": "Party member to send in: a species name or a 1-based slot."},
        }, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "use_item",
        "description": "Use a Bag item. In battle: on your ACTIVE Pokémon (costs your turn) — a Potion or a status "
                       "cure; Elixir restores every move's PP. Out of battle: Potions, status cures, Revive, Ether / Elixir (PP), Repel, evolution stones (Thunder Stone "
                       "on Pikachu evolves it), Rare Candy and vitamins, Escape Rope (caves only: back to the entrance). `target` = species or 1-based slot; omit it "
                       "to auto-pick whoever needs the item (Rare Candy and vitamins require a target). The 'Bag:' "
                       "line shows what you have.",
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string",
                     "description": "Item name, e.g. 'Potion', 'Super Potion', 'Antidote', "
                                    "'Revive', 'Repel'."},
            "target": {"type": "string",
                       "description": "Optional (field use): species name or 1-based party "
                                      "slot. Omit to auto-pick whoever needs it."},
            "move": {"type": "string",
                     "description": "Optional, Ether / Max Ether only: which move to refill (default: the one most short of PP)."},
        }, "required": ["item"]},
    }},
    {"type": "function", "function": {
        "name": "give_item",
        "description": "Make a party Pokémon HOLD a Bag item (Leftovers, Exp. Share, Quick Claw, a type-boost item…; a held item "
                       "already there is swapped back into the Bag). The 'Held items:' line suggests who should carry what.",
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string", "description": "e.g. 'Leftovers', 'Exp. Share', 'Mystic Water'"},
            "pokemon": {"type": "string", "description": "species name or 1-based slot"},
        }, "required": ["item", "pokemon"]},
    }},
    {"type": "function", "function": {
        "name": "pick_up_items",
        "description": "Collect the item balls on this map (see 'Items on the ground:' in the observation). "
                       "Overworld only.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "use_move",
        "description": "Use one of your active Pokémon's moves by name (the 'Your moves' list). Drives the whole "
                       "menu for you; prefer it to press_button.",
        "parameters": {"type": "object", "properties": {
            "move": {"type": "string", "description": "Exact move name, e.g. 'Tackle'."},
        }, "required": ["move"]},
    }},
    {"type": "function", "function": {
        "name": "grind",
        "description": "Level up on wild Pokémon in tall grass (or the Mansion floor). It walks to a route whose wild levels fit the "
                       "Pokémon being trained; each wild encounter then ENDS the call — you fight it, then call "
                       "grind again (the session persists). grind(level=13) raises your best Pokémon to L13; grind() "
                       "with no level BALANCES the team up to a floor fixed at the start (best − 7, capped at the "
                       "next gym's level): the weakest member leads and the ACE IS BENCHED. It "
                       "heals itself at a Center when HP/PP run low and stops with a diagnosis if the ace is taking "
                       "the XP. Boring wild fights autopilot (balancing mode: 12 per call; auto_battles=N overrides).",
        "parameters": {"type": "object", "properties": {
            "level": {"type": "integer",
                      "description": "target level for your BEST Pokémon, e.g. 13. Omit (or 0) to balance the whole team."},
            "catch": {"type": "boolean",
                      "description": "point out wild Pokémon worth a ball (default true) and never autopilot "
                                     "them. Pass false to only fight."},
            "auto_battles": {"type": "integer", "minimum": 0, "maximum": 50,
                             "description": "autopilot this many boring wild fights before handing "
                                            "encounters to you (default: 12 when balancing the team, 0 when "
                                            "grinding to a level; 0 = you play every one)."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "quest",
        "description": "The story, start to Elite Four. quest() lists every beat: ✔ done / ▶ next / … blocked. quest('<name>') runs "
                       "its script when it has one (ss_ticket, cut, coin_case, rocket_hideout = the Silph Scope, tea, surf, strength) "
                       "or prints the plan (pokemon_tower, poke_flute, snorlax, silph_co, pokemon_mansion, the gyms…). A wild "
                       "Pokémon or trainer on the way ENDS the call — play it, then call quest again to resume. "
                       "auto_trainers=true fights the trainers on the way for you.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "a beat from the list (e.g. rocket_hideout, pokemon_tower, silph_co); omit to list them"},
            "auto_trainers": {"type": "boolean",
                              "description": "auto-fight trainers met on the way (wild Pokémon are still handed to you)."},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "inspect_pokemon",
        "description": "Look closely at ONE Pokémon: real stats, IVs, EVs, nature, Hidden Power and a quality grade "
                       "for what its species is used for, compared with your team. `pokemon` = party slot or name, "
                       "or 'box:slot' for a boxed one. Use it right after a catch and when choosing who to keep, "
                       "withdraw or swap.",
        "parameters": {"type": "object", "properties": {
            "pokemon": {"type": "string", "description": "party slot number, name, or 'box:slot'"}}, "required": ["pokemon"]},
    }},
    {"type": "function", "function": {
        "name": "team_report",
        "description": "Read-only team analysis: the types your KNOWN moves hit super effectively, shared "
                       "weaknesses, who can carry each HM, whether the team answers the NEXT gym and — if not — what "
                       "to catch and where (or which PC Pokémon to swap in with pc). Use it when planning catches and "
                       "before a gym.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "pc",
        "description": "The Pokémon PC (box storage). action='list' shows what is stored (reads memory, works anywhere; "
                       "detail=true adds box:slot, types, moves, HM ability and a quality grade — use it to pick who to "
                       "withdraw). 'deposit' stores party `pokemon`; 'withdraw' takes `pokemon` (species, nickname or "
                       "a reference like '1:4' = box 1, slot 4) out into a free party slot; 'swap' deposits `pokemon` and withdraws `box_pokemon` in one "
                       "go (both checked first). These travel to a Center if needed. A name matching several Pokémon returns "
                       "the list — use the reference (e.g. '1:4'). It won't store your last battle-ready Pokémon, or the only HM "
                       "carrier unless force=true.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["list", "deposit", "withdraw", "swap"]},
            "pokemon": {"type": "string", "description": "deposit/swap: party slot or name; withdraw: boxed species, nickname or 'box:slot'"},
            "box_pokemon": {"type": "string", "description": "swap only: boxed species, nickname or 'box:slot' to bring out"},
            "detail": {"type": "boolean", "description": "list only: include box:slot, types, moves, HM ability"},
            "force": {"type": "boolean", "description": "deposit even if it is the only HM-move carrier"}},
            "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "reorder_party",
        "description": "Out of battle, swap two party members (Start → POKéMON → SWITCH, driven for you) — or, with "
                       "`second` omitted, make `first` your LEAD (slot 1, fights first; a fainted one can't lead). "
                       "`first`/`second` are a 1-based slot or a species/nickname. In a battle use switch_pokemon.",
        "parameters": {"type": "object", "properties": {
            "first": {"type": "string", "description": "slot number or name"},
            "second": {"type": "string", "description": "slot number or name; omit to make `first` the lead"},
        }, "required": ["first"]},
    }},
    {"type": "function", "function": {
        "name": "teach_move",
        "description": "Teach a TM/HM to a party Pokémon via the TM Case. `tm` is 'TM09', 'HM01' or the move name; "
                       "`pokemon` (species or 1-based slot) is optional — otherwise each member is tried in order. A "
                       "single-use TM that would make a four-move Pokémon forget something first returns a PREVIEW: "
                       "repeat with forget='<move>' or confirm=true to commit. Use it for Cut / Surf / Strength / "
                       "Flash / Fly, then use_hm.",
        "parameters": {"type": "object", "properties": {
            "tm": {"type": "string", "description": "e.g. 'HM01', 'TM09', 'Surf'"},
            "pokemon": {"type": "string", "description": "optional species name or 1-based slot"},
            "forget": {"type": "string", "description": "optional move to replace when full"},
            "confirm": {"type": "boolean", "description": "commit without naming a move to forget (the default pick)"},
        }, "required": ["tm"]},
    }},
    {"type": "function", "function": {
        "name": "forget_move",
        "description": "Delete a move at the Move Deleter in Fuchsia (travels there): the only way to remove an HM move. Keeps the "
                       "party's last copy of an HM unless force=true.",
        "parameters": {"type": "object", "properties": {
            "pokemon": {"type": "string", "description": "species or slot"},
            "move": {"type": "string"},
            "force": {"type": "boolean"},
        }, "required": ["pokemon", "move"]},
    }},
    {"type": "function", "function": {
        "name": "rename_pokemon",
        "description": "Change a Pokémon's nickname at the Name Rater in Lavender Town (travels there). Not for traded Pokémon or Eggs.",
        "parameters": {"type": "object", "properties": {
            "pokemon": {"type": "string", "description": "species or slot"}, "nickname": {"type": "string"}}, "required": ["pokemon", "nickname"]},
    }},
    {"type": "function", "function": {
        "name": "daycare",
        "description": "Route 5 Day Care (travels there): action='deposit' leaves one Pokémon (it gains 1 exp per step you walk; another must be able to fight); 'withdraw' takes it back for ¥100 + ¥100 per level gained.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["deposit", "withdraw"]}, "pokemon": {"type": "string", "description": "for deposit: species or slot"}}, "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "tutor",
        "description": "Learn a move from its Kanto or Sevii tutor (free, once each; travels there, by ferry to an island): Counter, Rock Slide, Explosion, Swords Dance, Substitute… `pokemon` optional.",
        "parameters": {"type": "object", "properties": {
            "move": {"type": "string"}, "pokemon": {"type": "string"}, "forget": {"type": "string"}}, "required": ["move"]},
    }},
    {"type": "function", "function": {
        "name": "fish",
        "description": "Cast your best rod at the nearest water (walks to a shore) up to `casts` times; a wild Pokémon on the hook becomes a battle. Needs a rod: quest('old_rod').",
        "parameters": {"type": "object", "properties": {"casts": {"type": "integer"}}},
    }},
    {"type": "function", "function": {
        "name": "fly_to",
        "description": "Fly to a visited town (needs a Pokémon that knows Fly + the Thunder Badge, outdoors): "
                       "Pallet, Viridian, Pewter, Cerulean, Lavender, Vermilion, Celadon, Fuchsia, Cinnabar, "
                       "Saffron, Indigo Plateau. A fast way back to a Center or gym.",
        "parameters": {"type": "object", "properties": {
            "town": {"type": "string"},
        }, "required": ["town"]},
    }},
    {"type": "function", "function": {
        "name": "use_hm",
        "description": "Use a field move: Surf (at the nearest shore, then walk_to / go_to_map cross water), Cut "
                       "(nearest tree), Rock Smash, Strength (then walk into the boulder), Flash (lights a cave). A Pokémon "
                       "must know the move and you need the badge; walk_to starts Surf by itself when only water blocks the "
                       "route. Dig = leave a cave/forest/dungeon for its entrance (same as an Escape Rope); Teleport = outdoors "
                       "only, warps to the last Pokémon Center you healed at.",
        "parameters": {"type": "object", "properties": {
            "move": {"type": "string", "enum": ["Surf", "Cut", "Rock Smash", "Strength", "Flash", "Dig", "Teleport"]},
        }, "required": ["move"]},
    }},
    {"type": "function", "function": {
        "name": "open_menu",
        "description": "Open a Start-menu entry and land on its screen: Pokemon, Bag, Pokedex, Player, Save, Option "
                       "or Exit. Navigate inside with press_button; close_menus() exits.",
        "parameters": {"type": "object", "properties": {
            "menu": {"type": "string",
                     "enum": ["Pokemon", "Bag", "Pokedex", "Player", "Save", "Option", "Exit"]},
        }, "required": ["menu"]},
    }},
    {"type": "function", "function": {
        "name": "answer_prompt",
        "description": "Answer an open YES/NO box (e.g. 'Would you like to save?', shop or "
                       "NPC questions). Waits for the box to take input, sets the cursor, "
                       "and confirms. Not for battle menus.",
        "parameters": {"type": "object", "properties": {
            "answer": {"type": "string", "enum": ["yes", "no"]},
        }, "required": ["answer"]},
    }},
    {"type": "function", "function": {
        "name": "advance_dialog",
        "description": "Press A through NPC/sign/system dialogue until it finishes or a "
                       "choice (Yes/No / menu) needs your decision. Safer than mashing A.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "close_menus",
        "description": "Back out of every open menu, prompt and dialogue with B until you "
                       "are on the free field again. Use when stuck in a menu.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "flee_battle",
        "description": "Run from a WILD battle (trainer battles can't be fled). The escape can fail — try again or "
                       "fight.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "safari",
        "description": "One turn of a SAFARI ZONE battle (the menu is BALL / BAIT / GO NEAR / RUN — no moves, party or Bag). "
                       "action='ball' throws a Safari Ball (30 per visit; the 'nickname' works like catch's), 'bait' halves the "
                       "catch rate but calms it (flees less), 'rock' doubles the catch rate but angers it (flees more), 'run' "
                       "leaves. A common line: rock, rock, ball. Steps are limited too (see the SAFARI line).",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["ball", "bait", "rock", "run"]},
            "nickname": {"type": "string", "description": "for action='ball': a funny nickname to give if it is caught"}},
            "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "catch",
        "description": "Throw a Poké Ball at the WILD Pokémon you're fighting (never a trainer's) — ALWAYS catch a SHINY. Weaken it first — "
                       "low HP, or sleep / paralysis — it may break free, so throw again. ALWAYS pass a `nickname` "
                       "you invent: memorable, a bit funny, max 10 chars, letters / digits / space . , ! ? only, "
                       "never the species name, no two alike. The result reports the new Pokémon's quality (IVs / "
                       "nature).",
        "parameters": {"type": "object", "properties": {
            "nickname": {"type": "string",
                         "description": "name YOU invent for this catch — inventive/funny, max 10 chars, "
                                        "not the species name. Omit only to skip naming."},
        }},
    }},
    {"type": "function", "function": {
        "name": "enter_name",
        "description": "Type a name on the naming screen when one is open (a nickname, or "
                       "the player/rival name in a new game) and confirm it. Types key by "
                       "key, switching UPPER/lower/symbol pages and verifying every letter.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "letters, digits, space . , ! ?"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "read_game_state",
        "description": "Read current game state: party HP, battle status, badges, location.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "game_corner",
        "description": "The Celadon Game Corner (needs the Coin Case: quest('coin_case')). action='status' shows coins and prices; "
                       "'buy_coins' (amount = coins, ¥20 each) buys them from the clerk; 'slots' (amount = spins, a full 3-coin "
                       "bet each) plays a machine and stops on a streak of losses. Spend coins on prizes with shop(item='TM24' | "
                       "'Abra' | 'Smoke Ball'…).",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["status", "buy_coins", "slots"]},
            "amount": {"type": "integer", "description": "coins to buy, or number of spins"}}},
    }},
    {"type": "function", "function": {
        "name": "save_game",
        "description": "Write a REAL cartridge save (the in-game SAVE: Start → Save → Yes → Yes), confirmed by the game's save "
                       "counter. Survives a crash or restart, unlike save_state's emulator slots. The READINESS block says when "
                       "one is due (a new badge, many battles since the last, or never). Overworld only.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "save_state",
        "description": "Save state to a slot. Call before gym leaders and Elite Four.",
        "parameters": {"type": "object", "properties": {
            "slot": {"type": "integer", "default": 0},
        }},
    }},
    {"type": "function", "function": {
        "name": "load_state",
        "description": "Load a save state — to retry a CATCH (slot 9). NOT after a loss: that discards the Exp it earned.",
        "parameters": {"type": "object", "properties": {
            "slot": {"type": "integer", "default": 0},
        }},
    }},
    {"type": "function", "function": {
        "name": "wait_frames",
        "description": "Wait N frames (60fps). Use during animations and transitions.",
        "parameters": {"type": "object", "properties": {
            "frames": {"type": "integer"},
        }, "required": ["frames"]},
    }},
    {"type": "function", "function": {
        "name": "record_milestone",
        "description": "Record a story milestone to long-term memory right after it happens: starter_chosen, "
                       "delivered_oaks_parcel, got_cut, got_flash, cleared_rock_tunnel, got_silph_scope, "
                       "rescued_mr_fuji, got_poke_flute, got_surf, got_strength, got_fly, woke_snorlax_12, woke_snorlax_16. "
                       "Not for gym wins — those are automatic.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "note": {"type": "string", "default": ""},
        }, "required": ["name"]},
    }},
]


# ── Context-gated tool lists ───────────────────────────────────────────────────────────────────────
# Sending all 37 schemas on every call costs ~4.6k tokens and invites wrong-context calls (use_move on the overworld,
# go_to inside a gym). In a battle only the battle tools are offered; on the free overworld the battle tools and the
# naming-screen tool are left out. Every other context (menus, dialog, transitions, unknown) gets EVERYTHING — a
# mis-read screen must never leave the model without the tool that gets it out. The list is stable within a context so a
# provider's prompt cache survives a whole battle or a whole walk.
BATTLE_TOOLS = ("use_move", "switch_pokemon", "use_item", "catch", "flee_battle", "inspect_pokemon", "team_report",
                "press_button", "advance_dialog", "answer_prompt", "close_menus")
_BATTLE_ONLY = frozenset({"use_move", "switch_pokemon", "catch", "flee_battle", "safari"})
SAFARI_TOOLS = ("safari", "inspect_pokemon", "team_report", "press_button", "advance_dialog", "answer_prompt", "close_menus")
SAFARI_CONTEXT = "SAFARI_BATTLE"          # a battle whose gBattleTypeFlags has the Safari bit: its own menu, its own tools
_NAMING_ONLY = frozenset({"enter_name"})          # naming screens are never the free overworld or a battle

_USE_ITEM_BATTLE = ("Use a Bag item on your ACTIVE Pokémon — a Potion (Super / Hyper / Max) or a status cure "
                    "(Antidote, Paralyze Heal, Awakening, Burn Heal, Ice Heal, Full Heal) — or a booster: X Attack / X Defend / "
                    "X Speed / X Special / X Accuracy / Dire Hit. It costs your turn. The 'Bag:' line shows what you have.")


def _with_description(tool: dict, description: str) -> dict:
    fn = {**tool["function"], "description": description}
    return {**tool, "function": fn}


def tools_for(context=None) -> list:
    """The tool schemas to offer in `context` (a game.state.GameContext, its name, or None = everything)."""
    from game.state import GameContext
    name = getattr(context, "name", context)
    if name == SAFARI_CONTEXT:
        return [t for t in TOOLS if t["function"]["name"] in SAFARI_TOOLS]
    if name == GameContext.IN_BATTLE.name:
        out = [t for t in TOOLS if t["function"]["name"] in BATTLE_TOOLS]
        return [_with_description(t, _USE_ITEM_BATTLE) if t["function"]["name"] == "use_item" else t for t in out]
    if name == GameContext.OVERWORLD.name:
        return [t for t in TOOLS if t["function"]["name"] not in _BATTLE_ONLY | _NAMING_ONLY]
    return list(TOOLS)


def tool_schema(name: str) -> dict | None:
    """The JSON-schema `parameters` of tool `name` (None for an unknown tool)."""
    for t in TOOLS:
        if t["function"]["name"] == name:
            return t["function"].get("parameters")
    return None

