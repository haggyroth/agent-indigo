"""Menu / prompt / dialogue skills (see game.menu.MenuDriver). Mixed into AgentClient."""
from game.menu import MenuDriver


class MenuMixin:

    @property
    def _menus(self) -> MenuDriver:
        d = self._menu_driver
        if d is None:
            d = self._menu_driver = MenuDriver(self.mgba, self.reader)
        return d

    def _open_menu(self, name: str) -> str:
        return self._menus.open_menu(name)

    def _answer_prompt(self, answer: str) -> str:
        return self._menus.answer_prompt(answer)

    def _advance_dialog(self) -> str:
        from game.menu import forced_party_screen
        from game.state import GameContext
        # In a battle the "dialogue" is battle text: drive it to the next decision point
        # instead of refusing (the old reply — "a battle started" — pressed nothing).
        if (self.reader.detect_context() == GameContext.IN_BATTLE
                or forced_party_screen(self.mgba, self.reader)):
            return self._battle_settle()
        return self._menus.advance_dialog()

    def _save_game(self) -> str:
        """The in-game SAVE (a real cartridge save, unlike the emulator slots of save_state): Start → SAVE → YES, then YES again to
        overwrite the old file. Confirmed by gSaveCounter rising — the screen text is not readable — and recorded in long-term
        memory so readiness can say when the next save is due."""
        from agent import events
        from game.constants import Addr
        from game.state import GameContext
        from knowledge.readiness import battles_total
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "Save from the free overworld (not in a battle, a menu or a dialogue)."
        before = self.mgba.read32(Addr.SAVE_COUNTER)
        res = self._menus.open_menu("Save")
        if "Save prompt is up" not in res:
            self._menus.close_menus()
            return f"Couldn't open the Save prompt ({res})"
        for _ in range(8):                   # 'Would you like to save?' YES, then 'overwrite the previous file?' YES
            if self.mgba.read32(Addr.SAVE_COUNTER) != before:
                break
            if self._menus.choice_live():
                self._menus.answer_prompt("yes")
            else:
                self.mgba.tap("A")
            self.mgba.tick(120)
        self._advance_to_control(tries=24)   # 'X saved the game!' text and the fade back to the field
        after = self.mgba.read32(Addr.SAVE_COUNTER)
        if after == before:
            self._menus.close_menus()
            return "The game didn't save (the save counter didn't move). Try save_game() again."
        d = self.ltm.data
        d["saved_badges"] = d.get("badges_earned", 0)
        d["saved_battles"] = battles_total(d)
        self.ltm.save()
        events.emit("save", f"game saved to the cartridge (save #{after})")
        return f"Saved the game (save #{after}) with {d['saved_badges']} badge(s). This is the in-game save, separate from save_state."

    def _close_menus(self) -> str:
        return self._menus.close_menus()
