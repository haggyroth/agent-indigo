"""Lavender Town's story: quest('pokemon_tower') → quest('poke_flute') → quest('snorlax').

Pokémon Tower (maps (1,88)..(1,94), 1F..7F; decomp PokemonTower_*): the ghosts on 3F-6F need the Silph Scope (6F's Marowak ghost is a normal
fight with it); 2F has the rival's trigger tiles; 7F has three Rocket Grunts (9,10) (13,8) (9,6) whose sight lines start fights on the way to
Mr. Fuji at (11,4). Talking to Fuji sets FLAG_RESCUED_MR_FUJI (0x23C) and warps you to his house in Lavender (8,2) at (4,7).
Poké Flute: Fuji in the Volunteer Pokémon House at (3,3) gives it (FLAG_GOT_POKE_FLUTE 0x23D, key item 350).
Snorlax: Route 12's sleeper at (14,70) asks "play the Poké Flute?" when you face it with FLAG_GOT_POKE_FLUTE set; YES wakes it, a level-30 fight
follows, and FLAG_WOKE_UP_ROUTE_12_SNORLAX (0x253) is set (even if you run)."""
from game.state import GameContext

TOWER_7F, FUJI_HOUSE, ROUTE_12 = (1, 94), (8, 2), (3, 30)
SILPH_SCOPE_ITEM, FLUTE_ITEM = 359, 350
FLAG_RESCUED_FUJI, FLAG_GOT_FLUTE, FLAG_WOKE_ROUTE12 = 0x23C, 0x23D, 0x253
FUJI_TOWER_STAND = ((11, 5), "Up")                  # Fuji stands at (11,4) on 7F
FUJI_HOUSE_SPOTS = (((3, 4), "Up"), ((2, 3), "Right"), ((4, 3), "Left"))     # Fuji at (3,3) in his house
SNORLAX_STAND = ((14, 69), "Down")                  # Route 12's Snorlax at (14,70)
ROUTE12_GATE_IN, ROUTE12_GATE_ROW, GATE_HOUSE_SOUTH_DOOR = (14, 15), 20, (5, 11)
ROUTE_16 = (3, 34)
FLAG_HIDE_ROUTE16_SNORLAX = 0x080                   # set the moment the wake-up fight starts (beaten, caught or fled: it is gone for good)
SNORLAX16_STAND = ((32, 13), "Left")                # Route 16's Snorlax at (31,13): Celadon's side of the Cycling Road's gate house


def _interrupted(walk_result: str) -> bool:
    """A walk that returned because a battle / dialogue took over (the next loop turn yields it) — not a blocked path."""
    low = str(walk_result).lower()
    return "battle started" in low or "dialog opened" in low


class TowerMixin:
    def _walk_far(self, tile, tries: int = 8) -> str:
        """walk_to one long leg: a single call spends its 16 attempts, so repeat while it makes progress (stops on a battle / dialogue)."""
        out = ""
        for _ in range(tries):
            before = tuple(self.reader.read_player_pos())
            out = self._walk_to(*tile)
            if tuple(self.reader.read_player_pos()) in (tuple(tile), before) or _interrupted(out) or out.startswith(("Arrived", "Entered", "Exited")):
                break
        return out

    def _get_pokemon_tower(self, auto_trainers: bool = False) -> str:
        call = "quest('pokemon_tower')"
        if self.reader.read_flag(FLAG_RESCUED_FUJI):
            return "Mr. Fuji is already rescued — he is in his house in Lavender: quest('poke_flute')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if SILPH_SCOPE_ITEM not in self.reader.read_key_items():
            return "The ghosts on 6F can't be fought without the Silph Scope — get it first: quest('rocket_hideout')."
        for _ in range(30):
            if (b := self._quest_battle(call, "Pokémon Tower")):
                return b
            here = tuple(self.reader.read_current_map())
            if here == FUJI_HOUSE or self.reader.read_flag(FLAG_RESCUED_FUJI):
                return ("Rescued Mr. Fuji — he took you to his house in Lavender. Talk to him for the Poké Flute: quest('poke_flute'). "
                        "Heal first if the climb hurt.")
            if here != TOWER_7F:
                if (msg := self._hideout_travel("Pokemon Tower 7F", TOWER_7F, call, auto_trainers)):
                    return msg
                continue
            px, py = self.reader.read_player_pos()
            if (px, py) != FUJI_TOWER_STAND[0]:
                # the three Grunts' sight lines start their fights on the way up the middle
                out = self._walk_to(*FUJI_TOWER_STAND[0])
                if (b := self._hideout_fight(call, "the Rocket Grunts on 7F", auto_trainers)):
                    return b
                if tuple(self.reader.read_player_pos()) == (px, py) and not _interrupted(out):
                    return f"Couldn't walk up to Mr. Fuji on 7F ({out}) — walk_to (11,5), face up, press A."
                continue
            if not self._press_on_tile(*FUJI_TOWER_STAND):
                return "Couldn't talk to Mr. Fuji at (11,4) — walk_to (11,5), face up, press A."
            for _ in range(10):
                if self.reader.read_flag(FLAG_RESCUED_FUJI):
                    break
                self._advance_to_control(tries=30)
        return f"Made progress in Pokémon Tower — call {call} again to continue (it resumes)."

    def _get_poke_flute(self, auto_trainers: bool = False) -> str:
        call = "quest('poke_flute')"
        if self.reader.read_flag(FLAG_GOT_FLUTE) or FLUTE_ITEM in self.reader.read_key_items():
            return "You already have the Poké Flute — a sleeping Snorlax: quest('snorlax')."
        if not self.reader.read_flag(FLAG_RESCUED_FUJI):
            return "Mr. Fuji has to be rescued from Pokémon Tower 7F first: quest('pokemon_tower')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if (msg := self._hideout_travel("Lavender Volunteer House", FUJI_HOUSE, call, auto_trainers)):
            return msg
        if not self._talk_to(FUJI_HOUSE_SPOTS):
            if (b := self._quest_battle(call, "Mr. Fuji")):
                return b
            return "Couldn't reach Mr. Fuji at (3,3) — walk_to (3,4), face up, press A."
        for _ in range(12):
            if self.reader.read_flag(FLAG_GOT_FLUTE):
                break
            self._advance_to_control(tries=30)
        if not self.reader.read_flag(FLAG_GOT_FLUTE):
            return f"Talked to Mr. Fuji but no Poké Flute yet — call {call} again."
        self._advance_to_control(tries=24)
        return "Got the Poké Flute. Route 12's Snorlax (south of Lavender) is next: quest('snorlax')."

    def _get_snorlax_16(self, auto_trainers: bool = False) -> str:
        """Route 16's sleeper (31,13), the plug in the road to the Cycling Road's gate house. Same flute-and-fight script as Route 12's; reached from Celadon's exit (the east end)."""
        call = "quest('snorlax_16')"
        if self.reader.read_flag(FLAG_HIDE_ROUTE16_SNORLAX):
            return "Route 16's Snorlax is already gone from the road — the Cycling Road's gate house is open (it needs the Bicycle: quest('bike'))."
        if not self.reader.read_flag(FLAG_GOT_FLUTE):
            return "You need the Poké Flute (Mr. Fuji): quest('poke_flute')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(12):
            if (b := self._quest_battle(call, "Route 16's Snorlax")):
                return b
            if self.reader.read_flag(FLAG_HIDE_ROUTE16_SNORLAX):
                got = bool(self.reader.read_dex_owned(143))
                return ("The Snorlax woke up and is gone from the road" + (" — and you CAUGHT it: a L30 Snorlax is one of the best team members. " if got else
                        " (beaten or fled — it is in your Pokédex only if you caught it). ")
                        + "The way to the Cycling Road's gate house is open; Route 17 itself needs the Bicycle (quest('bike')).")
            if tuple(self.reader.read_current_map()) != ROUTE_16:
                if (msg := self._hideout_travel("Route 16", ROUTE_16, call, auto_trainers)):
                    return msg
                continue
            px, py = self.reader.read_player_pos()
            if (px, py) != SNORLAX16_STAND[0]:
                out = self._walk_far(SNORLAX16_STAND[0])
                if (b := self._quest_battle(call, "Route 16")):
                    return b
                if tuple(self.reader.read_player_pos()) == (px, py) and not _interrupted(out):
                    return f"Couldn't walk up to the Snorlax on Route 16 ({out}) — walk_to (32,13), face left, press A, answer YES."
                continue
            if not self._press_on_tile(*SNORLAX16_STAND, yesno=True):
                return "Couldn't reach the Snorlax at (31,13) — walk_to (32,13), face left, press A, answer YES."
            if (b := self._hideout_fight(call, "the Snorlax", False)):      # never the autopilot (knowledge.one_shot): it must be CAUGHT, not knocked out
                return b
        return f"Made progress on Route 16 — call {call} again to continue (it resumes)."

    def _get_snorlax(self, auto_trainers: bool = False) -> str:
        call = "quest('snorlax')"
        if self.reader.read_flag(FLAG_WOKE_ROUTE12):
            return "Route 12's Snorlax is already awake and gone — Routes 12 → 15 lead on to Fuchsia City."
        if not self.reader.read_flag(FLAG_GOT_FLUTE):
            return "You need the Poké Flute (Mr. Fuji): quest('poke_flute')."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(12):
            if (b := self._quest_battle(call, "Route 12's Snorlax")):
                return b
            if self.reader.read_flag(FLAG_WOKE_ROUTE12):
                got = bool(self.reader.read_dex_owned(143))
                return ("The Snorlax woke up and is gone from the road" + (" — and you CAUGHT it: a L30 Snorlax is one of the best team members. " if got else
                        " (beaten or fled — it is in your Pokédex only if you caught it; Route 16 has a second one). ")
                        + "Route 12 leads south: Routes 13, 14, 15 → Fuchsia City (Koga's gym: quest('koga')).")
            if tuple(self.reader.read_current_map()) != ROUTE_12:
                if (msg := self._hideout_travel("Route 12", ROUTE_12, call, auto_trainers)):
                    return msg
                continue
            px, py = self.reader.read_player_pos()
            if (px, py) != SNORLAX_STAND[0]:
                if py < ROUTE12_GATE_ROW:
                    # Route 12's north half is cut off from the road south by a gate house: in at (14,15), out at its south door (5,11)
                    self._walk_to(*ROUTE12_GATE_IN)
                    if tuple(self.reader.read_current_map()) == (23, 0):
                        self._walk_to(*GATE_HOUSE_SOUTH_DOOR)
                    if (b := self._quest_battle(call, "Route 12")):
                        return b
                    continue
                out = self._walk_far(SNORLAX_STAND[0])
                if (b := self._quest_battle(call, "Route 12")):
                    return b
                if tuple(self.reader.read_player_pos()) == (px, py) and not _interrupted(out):
                    return f"Couldn't walk up to the Snorlax on Route 12 ({out}) — walk_to (14,69), face down, press A, answer YES."
                continue
            if not self._press_on_tile(*SNORLAX_STAND, yesno=True):
                return "Couldn't reach the Snorlax at (14,70) — walk_to (14,69), face down, press A, answer YES."
            if (b := self._hideout_fight(call, "the Snorlax", False)):      # never the autopilot: it would knock the Snorlax out — it must be CAUGHT (knowledge.one_shot)
                return b
        return f"Made progress on Route 12 — call {call} again to continue (it resumes)."
