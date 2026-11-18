"""Small story errands with a fixed script (one NPC, one item).

quest('tea'): the old woman in Celadon Mansion (Condominiums) 1F gives the Tea for free (FLAG_GOT_TEA 0x2A6, key item 369). Walk into a
Saffron gate house (Routes 5-8) and the thirsty guard drinks it and lets you into Saffron City for good (the item is consumed, the flag stays).
Decomp: CeladonCity_Condominiums_1F (EventScript_TeaWoman at (2,9)), Route5/6/7/8 gate scripts.

quest('flash'): Prof. Oak's Aide in the Route 2 east building (15,2) at (4,6) gives HM05 Flash once 10 species have been SEEN (FLAG_GOT_HM05 0x23B).
quest('fly'): the woman in the Route 16 house (25,0), at (4,2), just gives HM02 Fly (FLAG_GOT_HM02 0x238) — but the house is on Route 16's WEST end, behind the sleeping
Snorlax at (31,13) (Celadon's exit lands on the east end): it needs the Poké Flute and the Snorlax gone (FLAG_HIDE_ROUTE_16_SNORLAX 0x080, set when it is beaten,
caught or flees). Waking that Snorlax is not scripted yet (#272): quest('fly') says so and carries on once it is gone."""
from game.state import GameContext

CELADON_MANSION_1F = (10, 7)
FLAG_GOT_TEA = 0x2A6
TEA_ITEM = 369
TEA_WOMAN_SPOTS = (((2, 10), "Up"), ((3, 9), "Left"), ((1, 9), "Right"))      # she stands at (2,9)
ROUTE2_EAST_BUILDING, ROUTE16_HOUSE = (15, 2), (25, 0)
FLAG_GOT_HM05, FLAG_GOT_HM02 = 0x23B, 0x238
FLAG_HIDE_ROUTE16_SNORLAX, POKE_FLUTE_ITEM, FLAG_GOT_FLUTE = 0x080, 350, 0x23D
ROUTE16_SNORLAX = (31, 13)
AIDE_SPOTS = (((4, 7), "Up"), ((3, 6), "Right"), ((5, 6), "Left"))            # the Aide stands at (4,6)
FLY_WOMAN_SPOTS = (((4, 3), "Up"), ((3, 2), "Right"), ((5, 2), "Left"))      # the woman stands at (4,2)
AIDE_SEEN_NEEDED = 10


class ErrandsMixin:
    def _has_tea(self) -> bool:
        return bool(self.reader.read_flag(FLAG_GOT_TEA)) or TEA_ITEM in self.reader.read_key_items()

    def _get_tea(self, auto_trainers: bool = False) -> str:
        call = "quest('tea')"
        if self._has_tea():
            return "You already have (or already gave) the Tea — walk into a Saffron gate house (Routes 5, 6, 7 or 8) and the guard lets you in."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == CELADON_MANSION_1F:
                break
            out = self._go_to("Celadon Mansion 1F", mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if tuple(self.reader.read_current_map()) == CELADON_MANSION_1F:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "Can't get to" in out or "No route" in out:
                return f"Can't reach Celadon Mansion: {out}"
        if tuple(self.reader.read_current_map()) != CELADON_MANSION_1F:
            return f"Didn't reach Celadon Mansion yet — call {call} again to continue (it resumes)."
        if not self._talk_to(TEA_WOMAN_SPOTS):
            if (b := self._quest_battle(call, "the Tea lady")):
                return b
            return "Couldn't reach the old woman at (2,9) — walk_to (2,10), face up, press A."
        for _ in range(10):
            if self._has_tea():
                break
            self._advance_to_control(tries=30)
        if not self._has_tea():
            return f"Talked to the old woman but no Tea yet — call {call} again."
        self._advance_to_control(tries=24)
        return ("Got the Tea. Walk into a Saffron gate house (the buildings on Routes 5, 6, 7 and 8 next to Saffron): the thirsty guard "
                "drinks it and lets you into Saffron City. Silph Co. (quest('silph_co')) is the next story step there.")

    def _gift_errand(self, call: str, dest: str, dest_map: tuple, spots, flag: int, who: str, auto_trainers: bool) -> str | None:
        """Travel to `dest`, talk to `who` and run the dialogue until `flag` is set. None = the gift is in the bag; else the message to return."""
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == dest_map:
                break
            out = self._go_to(dest, mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if tuple(self.reader.read_current_map()) == dest_map:
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if "Can't get to" in out or "No route" in out or "Blocked" in out or "gated" in out:
                return f"Can't reach {dest}: {out}"
        if tuple(self.reader.read_current_map()) != dest_map:
            return f"Didn't reach {dest} yet — call {call} again to continue (it resumes)."
        if not self._talk_to(spots):
            if (b := self._quest_battle(call, who)):
                return b
            return f"Couldn't reach {who} — walk up to them, face them and press A."
        for _ in range(10):
            if self.reader.read_flag(flag):
                break
            if self._menus.choice_live():
                self._menus.answer_prompt("yes")              # "Would you like to…?" / "Do you have 10…?" — YES
                self.mgba.tick(30)
            else:
                self._advance_to_control(tries=30)
        if not self.reader.read_flag(flag):
            return f"Talked to {who} but nothing was given — call {call} again."
        self._advance_to_control(tries=24)
        return None

    def _get_flash(self, auto_trainers: bool = False) -> str:
        call = "quest('flash')"
        if self.reader.read_flag(FLAG_GOT_HM05):
            return "You already have HM05 Flash — teach_move('Flash') to a Pokémon, then use_hm('Flash') in a dark cave (Rock Tunnel)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        seen = self.reader.read_pokedex()[1]
        if seen < AIDE_SEEN_NEEDED:
            return (f"Prof. Oak's Aide wants {AIDE_SEEN_NEEDED} Pokémon species SEEN in the Pokédex and you have seen {seen}. Meet more (wild battles count, "
                    f"catching is not required), then call {call} again.")
        if (msg := self._gift_errand(call, "Route 2 East Building", ROUTE2_EAST_BUILDING, AIDE_SPOTS, FLAG_GOT_HM05, "Prof. Oak's Aide at (4,6)", auto_trainers)):
            return msg
        return "Got HM05 Flash from Prof. Oak's Aide. teach_move('Flash') to a Pokémon that can learn it, then use_hm('Flash') lights a dark cave (Rock Tunnel)."

    def _get_fly(self, auto_trainers: bool = False) -> str:
        call = "quest('fly')"
        if self.reader.read_flag(FLAG_GOT_HM02):
            return "You already have HM02 Fly — teach_move('Fly') to a Pokémon, then fly_to(<town>) (needs the Thunder Badge) goes to any town you have visited."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not (self.reader.read_flag(FLAG_GOT_FLUTE) or POKE_FLUTE_ITEM in self.reader.read_key_items()):
            return "The Fly house is on Route 16's far west end, behind a sleeping Snorlax: you need the Poké Flute first (Mr. Fuji: quest('poke_flute'))."
        if not self.reader.read_flag(FLAG_HIDE_ROUTE16_SNORLAX):
            return (f"A sleeping Snorlax at {ROUTE16_SNORLAX} on Route 16 blocks the way west to the Fly house (Celadon's exit lands on Route 16's east end). Walk up to it "
                    f"(go_to('Route 16'), then walk_to next to it), face it, press A and answer YES to play the Poké Flute, then beat or catch it (L30). Scripting that fight is "
                    f"not done yet; once it is gone, call {call} again and it walks to the house.")
        if (msg := self._gift_errand(call, "Route 16 House", ROUTE16_HOUSE, FLY_WOMAN_SPOTS, FLAG_GOT_HM02, "the woman at (4,2)", auto_trainers)):
            return msg
        return "Got HM02 Fly. teach_move('Fly') to a Pokémon that can learn it (Pidgeotto, Fearow…), then fly_to(<town>) — it needs the Thunder Badge and an outdoor spot."
