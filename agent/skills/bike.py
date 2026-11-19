"""use_item('Bicycle'): mount / dismount the Bicycle (a key item) from the Bag.

Bag → Key Items → Bicycle → USE (the first row of the context menu); gPlayerAvatar.flags bit1/2 (is_biking) is the proof. The game refuses indoors and in a few other
places ("It's not the time to use that" / no effect), says so by not changing the flag, and auto-dismounts at doors. Surf needs the player off the bike (_surf dismounts first).
Not done: bike-aware routing (the Cycling Road), and running with B."""
from game.state import GameContext

BICYCLE = 360


class BikeMixin:
    def _use_bicycle(self) -> str:
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "use_item('Bicycle') works on the field (not in a battle or a menu)."
        keys = self.reader.read_key_items()
        if BICYCLE not in keys:
            return "You have no Bicycle: quest('bike') (the Fan Club chairman's voucher, then the Cerulean Bike Shop)."
        if self._surfing():
            return "You can't ride while surfing: step onto land first."
        was = self.reader.is_biking()
        res = self._menus.open_menu("Bag")
        if "Bag screen open" not in res:
            return f"Couldn't open the Bag ({res})"
        self.mgba.tick(40)
        if not self._bag_pocket_open(1) or not self._bag_cursor_to(keys.index(BICYCLE), pocket=1):
            self._menus.close_menus()
            return "Couldn't select the Bicycle in the Key Items pocket."
        self.mgba.tap("A")                                   # context menu: USE first
        self.mgba.tick(30)
        self.mgba.tap("A")
        for _ in range(40):
            self.mgba.tick(10)
            if self.reader.detect_context() == GameContext.OVERWORLD:
                break
        self._advance_to_control(tries=6)
        now = self.reader.is_biking()
        if now == was:
            return ("The Bicycle did nothing here — it can't be ridden (or dismounted) indoors, in some caves, on the Cycling Road slope or on water."
                    if not was else "Couldn't get off the Bicycle here (the Cycling Road keeps you on it).")
        return "You are riding the Bicycle (about twice walking speed; use_item('Bicycle') again to get off)." if now else "You got off the Bicycle."
