"""Small story errands with a fixed script (one NPC, one item).

quest('tea'): the old woman in Celadon Mansion (Condominiums) 1F gives the Tea for free (FLAG_GOT_TEA 0x2A6, key item 369). Walk into a
Saffron gate house (Routes 5-8) and the thirsty guard drinks it and lets you into Saffron City for good (the item is consumed, the flag stays).
Decomp: CeladonCity_Condominiums_1F (EventScript_TeaWoman at (2,9)), Route5/6/7/8 gate scripts."""
from game.state import GameContext

CELADON_MANSION_1F = (10, 7)
FLAG_GOT_TEA = 0x2A6
TEA_ITEM = 369
TEA_WOMAN_SPOTS = (((2, 10), "Up"), ((3, 9), "Left"), ((1, 9), "Right"))      # she stands at (2,9)


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
