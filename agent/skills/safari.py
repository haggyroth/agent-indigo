"""quest('safari <species>'): hunt one Safari Zone species in its grass (#362).

Pays the ¥500 and walks in when you are outside (30 Safari Balls, about 600 steps), travels to an area where the species lives (knowledge/safari.py, from the decomp's encounter tables) without
walking out of the exit, then paces on its tall grass until ANY wild Pokémon appears — the call ends there and says whether it is the target, so the model plays the Safari menu itself
(safari('ball' | 'bait' | 'rock' | 'run')) and calls again. Bounded per call; the visit's steps / balls are the limit, and the call says when the visit has ended (re-entering costs ¥500 again)."""
from game.constants import SPECIES_NAMES
from game.state import GameContext

HUNT_STEPS = 80                  # grass steps per call


class SafariMixin:
    def _safari_hunt(self, query: str = "") -> str:
        from knowledge import safari as sf
        if not str(query or "").strip():
            return sf.listing(SPECIES_NAMES) + ". quest('safari <species>') hunts one (¥500 for 30 Safari Balls and about 600 steps)."
        sid = sf.species_by_name(query, SPECIES_NAMES)
        if sid is None:
            return f"No Safari Zone grass Pokémon called {query!r}. " + sf.listing(SPECIES_NAMES)
        name = SPECIES_NAMES[sid].title()
        call = f"quest('safari {name.lower()}')"
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return self._safari_encounter(sid, name, call) if self._in_safari_battle() else "You're in a battle — finish it first."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "A Safari hunt works from the open field — finish what is on screen first (advance_dialog / close_menus)."
        if (msg := self._enter_safari_zone(call)):
            return msg
        from agent.skills.quests import FUCHSIA_CITY, SAFARI_ENTRANCE
        areas = [m for m, _lo, _hi in sf.areas_for(sid)]
        here = tuple(self.reader.read_current_map())
        if here not in areas:
            target = min(areas, key=lambda m: abs(m[1] - here[1]))
            self._avoid_maps = (SAFARI_ENTRANCE, FUCHSIA_CITY)           # never walk out through the exit (it would end the visit)
            try:
                msg = self._go_to_map_tuple(tuple(target), f"map:{target[0]},{target[1]}", call)
            finally:
                self._avoid_maps = ()
            if msg:
                if self.reader.detect_context() == GameContext.IN_BATTLE and self._in_safari_battle():
                    return self._safari_encounter(sid, name, call)
                return msg
        st = {"stuck": 0, "reloc": 0}
        for _ in range(HUNT_STEPS):
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._safari_encounter(sid, name, call)
            if not self._in_safari_zone():
                return f"The Safari Zone visit ended (out of steps or Safari Balls) — call {call} again to re-enter (¥500)."
            if (abort := self._grass_step(st, call)):
                return abort
        return f"No wild Pokémon yet in {name}'s grass — {self.mgba.read16(self._safari_steps_addr())} steps left; call {call} again to keep looking."

    @staticmethod
    def _safari_steps_addr() -> int:
        from game.constants import Addr
        return Addr.SAFARI_STEPS

    def _safari_encounter(self, sid: int, name: str, call: str) -> str:
        from game.constants import Addr
        foe = self.reader.read_enemy_lead()
        found = (foe.species_name if foe else "a Pokémon").title()
        balls, steps = self.mgba.read8(Addr.SAFARI_BALLS), self.mgba.read16(Addr.SAFARI_STEPS)
        hit = foe is not None and foe.species_id == sid
        lead = f"★ A wild {found} (L{foe.level}) — the one you came for!" if hit else f"A wild {found} appeared — not {name}."
        how = "throw balls; bait makes it eat (harder to catch, less likely to flee)" if hit else "safari('run') to keep hunting"
        return f"{lead} {balls} Safari Balls and {steps} steps left. Play it with safari('ball' | 'bait' | 'rock' | 'run') ({how}), then call {call} again."
