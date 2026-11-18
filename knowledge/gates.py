"""Story / capability gates the router must respect (pure data + logic; no I/O).

A gate says "entering this map needs X". go_to asks `unmet_gates(route, have)` BEFORE walking, so it can
pick another route or tell the model what to get first (instead of marching into a locked road, a
Snorlax, a guard or open water and stalling). Requirements are stable facts of the game; the hint
says where to get the thing."""
from dataclasses import dataclass

# key item ids (pokefirered constants/items.h)
SILPH_SCOPE, POKE_FLUTE, SECRET_KEY, CARD_KEY, TEA, BICYCLE = 359, 350, 351, 355, 369, 360
# HM move id -> (name, badge bit index that lets you use it in the field)
HM_BADGE = {"Cut": (15, 1), "Fly": (19, 2), "Strength": (70, 3), "Surf": (57, 4), "Flash": (148, 0)}


@dataclass(frozen=True)
class Req:
    kind: str            # "key_item" | "hm" | "badges" | "flag" | "level"
    value: object        # item id | HM name | badge count | world-map flag | the party's best level
    hint: str
    alt_flag: int | None = None   # satisfied if this system flag is set (e.g. already visited)


SS_TICKET = 265
_SS_HINT = ("Cerulean's exits stay blocked (a Slowbro + Lass south, a policeman east) until you have the "
            "SS Anne ticket — call quest('ss_ticket') (Bill's Sea Cottage, Route 25).")

_PEWTER_HINT = ("Pewter City's east side is closed until Brock is beaten: the Gym Guide grabs you on the way ('Brock's looking for challengers! "
                "Follow me!') and walks you to the gym door again and again, so heading east just loops. Win the Boulder Badge first: "
                "go_to('gym'), heal(), save_state(), then challenge_leader().")

_RIVAL_HINT = ("Your rival ambushes you at Cerulean's north exit on the way to Route 24 (Pidgeotto L17, Abra L16, Rattata L15 and a starter L18 that "
               "counters yours) and you must WIN — a loss sends you to the Center and he is waiting again. Don't grind on Route 24 or Route 25 and don't "
               "send an autopilot there: raise your best Pokémon to L21 first (grind on Route 4 / Route 3 / Route 2, not north), heal(), save_state(), then "
               "walk north yourself (walk_to / go_to_map('Up') from Cerulean) and fight him by hand with use_move / switch_pokemon (Fire beats a Grass "
               "starter's counter, Flying hits Grass).")

MAP_GATES: dict[tuple[int, int], list[Req]] = {
    (3, 43): [Req("level", 21, _RIVAL_HINT, alt_flag=0x29B)],     # Route 24: Cerulean's rival ambush; FLAG_GOT_FAME_CHECKER is set when that scene ends
    (3, 21): [Req("badges", 1, _PEWTER_HINT)],           # Route 3, Pewter's east exit (checked against the GAME's badge byte, not memory)
    (9, 6): [Req("hm", "Cut", "Vermilion Gym's door is blocked by a Cut tree: get HM01 Cut from the captain "
                 "of the S.S. Anne (board at Vermilion's harbor with the SS Ticket), teach it "
                 "(teach_move) to a Pokémon, then use_hm('Cut') on the tree. quest('cut') does the first two steps.")],
    (3, 23): [Req("key_item", SS_TICKET, _SS_HINT)],     # Route 5 (Cerulean's south exit)
    (3, 27): [Req("key_item", SS_TICKET, _SS_HINT)],     # Route 9 (Cerulean's east exit)
    (1, 94): [Req("key_item", SILPH_SCOPE,
                  "Pokémon Tower 7F is blocked by ghosts until you have the Silph Scope "
                  "(Celadon Rocket Hideout B4F: quest('rocket_hideout') does it).")],
    (3, 10): [Req("key_item", TEA,
                  "Saffron City's gate guards want Tea — the old woman in Celadon Mansion (Condominiums) 1F gives it away: quest('tea'). "
                  "Then walk into any Saffron gate house (Routes 5-8): the guard drinks it and lets you through for good.",
                  alt_flag=0x2A6)],           # FLAG_GOT_TEA stays set after the guard consumes the item
    (3, 30): [Req("key_item", POKE_FLUTE,
                  "A Snorlax blocks Route 12 — you need the Poké Flute (Mr. Fuji in Lavender Town, after rescuing him from the Pokémon "
                  "Tower: quest('pokemon_tower') then quest('poke_flute')), then face the Snorlax, press A and answer YES.",
                  alt_flag=0x253)],           # FLAG_WOKE_UP_ROUTE_12_SNORLAX
    (3, 34): [Req("key_item", POKE_FLUTE,
                  "A Snorlax blocks Route 16 — you need the Poké Flute (Mr. Fuji, Lavender Town: quest('poke_flute')).")],
    (3, 8): [Req("hm", "Surf", "Cinnabar Island is across the sea: teach Surf (HM03 from the Safari "
                 "Zone — quest('surf')) to a Pokémon, then use_hm('Surf') / go_to.",
                 alt_flag=0x898)],           # FLAG_VISITED_CINNABAR: once you have been there (Fly lands you on it) the island is reachable
    (3, 37): [Req("hm", "Surf", "Route 19 is open water — you need Surf.")],
    (3, 38): [Req("hm", "Surf", "Route 20 is open water — you need Surf.")],
    (1, 83): [Req("hm", "Surf", "Seafoam Islands needs Surf (and Strength for its boulders).")],
    (1, 39): [Req("hm", "Strength", "Victory Road's boulders need Strength (HM04 — quest('strength')).")],
    (3, 42): [Req("badges", 8, "Route 23's checkpoints only let you through with all 8 badges.")],
}


def unmet_gates(route, satisfied) -> list[tuple[int, Req]]:
    """[(step index, Req)] for every step of `route` that enters a gated map whose requirement
    `satisfied(req)` rejects. `route` is route_to()'s step list (dest node = step[2])."""
    out = []
    for i, step in enumerate(route or []):
        dest = tuple(step[2][:2])
        for req in MAP_GATES.get(dest, []):
            if not satisfied(req):
                out.append((i, req))
    return out
