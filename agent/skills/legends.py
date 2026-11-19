"""quest('zapdos'): the legendary bird in the Power Plant — travel in, walk up to it, press A, and hand the (one-shot) battle to the model.

Decomp (PowerPlant scripts): Zapdos is an object at (5,11) on the Power Plant map (1,95); talking to it plays "Gyaoo!" and starts a L50 legendary battle (StartLegendaryBattle). Win / run /
teleport all REMOVE it (EventScript_RemoveStaticMon / MonFlewAway) — only a catch keeps it, and losing leaves it there. So this is the one-shot protocol (knowledge.one_shot): the model catches
it with the Master Ball or Ultra Balls after the auto-saved battle-start state (slot 9). The Power Plant is across Route 10's water: Surf. FLAG_FOUGHT_ZAPDOS (0x2BF) is set when the fight ends."""
from game.state import GameContext

POWER_PLANT = (1, 95)
ZAPDOS_TILE = (5, 11)
FLAG_FOUGHT_ZAPDOS, FLAG_HIDE_ZAPDOS = 0x2BF, 0x05D
ZAPDOS = 145


class LegendsMixin:
    def _get_zapdos(self, auto_trainers: bool = False) -> str:
        call = "quest('zapdos')"
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if self.reader.read_dex_owned(ZAPDOS):
            return "You already caught Zapdos."
        if self.reader.read_flag(FLAG_FOUGHT_ZAPDOS) or self.reader.read_flag(FLAG_HIDE_ZAPDOS):
            return ("Zapdos is gone from the Power Plant (it was knocked out, fled or you faced it already) and it is not in your Pokédex. A legendary appears once: "
                    "load an earlier save (the battle-start state was in slot 9) if you want to try again.")
        for _ in range(10):
            if tuple(self.reader.read_current_map()) == POWER_PLANT:
                break
            out = self._go_to("Power Plant", mode="yield", auto_trainers=auto_trainers, resume_call=call)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if tuple(self.reader.read_current_map()) != POWER_PLANT and any(s in out for s in ("Can't get to", "No route", "Blocked", "gated", "no walking route")):
                return f"Can't get to the Power Plant: {out}"
        if tuple(self.reader.read_current_map()) != POWER_PLANT:
            return f"Didn't reach the Power Plant yet — call {call} again to continue (it resumes)."
        for _ in range(4):                                       # walk up to it (the Plant is big; a call can stop partway)
            if self._approach_adjacent(*ZAPDOS_TILE):
                break
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return self._quest_battle(call, "a Power Plant Pokémon") or ""
        else:
            return f"Couldn't walk up to Zapdos at {ZAPDOS_TILE} — walk_to next to it, face it and press A."
        px, py = self.reader.read_player_pos()
        face = self._facing_dir(px, py, *ZAPDOS_TILE)
        if face:
            self.mgba.tap(face)
        for _ in range(10):                                      # A → "Gyaoo!" → A → the battle
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                break
            self.mgba.tap("A")
            self.mgba.tick(40)
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            for _ in range(20):                                  # the battle intro runs before gEnemyParty is filled: the previous fight's mon is still there until it settles
                foe = self.reader.read_enemy_lead()
                if foe and foe.species_id == ZAPDOS:
                    break
                self.mgba.tick(30)
            return ("Zapdos (L50) is in front of you — ONE-SHOT: catch it, never knock it out. " + (self._quest_battle(call, "Zapdos") or ""))
        return f"Stood next to Zapdos but the battle didn't start — face it at {ZAPDOS_TILE} and press A, then call {call} again."
