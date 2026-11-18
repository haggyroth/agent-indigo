"""forget_move(pokemon, move): the Move Deleter in Fuchsia City (house 3) — the only way to remove an HM move.

Live-verified flow: talk to him at (4,4) from (4,5) facing Up → "Would you like me to do that?" YES → "Which POKéMON should forget a move?" → the field
party screen (cursor = gPartyMenu.slotId) → "Which move should be forgotten?" → the summary screen (SUMMARY_MOVE_CURSOR 0-3) → "…forgotten completely?" YES →
the move is gone and the list compacts. Driven by what the screens ARE (callback2 / a live Yes-No box), and the loop stops the moment the move is gone:
one more A would talk to him again."""
from game.constants import Addr
from game.state import GameContext
from knowledge.tmhm import HM_MOVE_NAMES

DELETER_MAP = (11, 9)
DELETER_STAND = (4, 5)               # he stands at (4,4)


class MoveDeleterMixin:
    def _forget_move(self, pokemon: str, move: str, force: bool = False) -> str:
        from agent import events
        party = self.reader.read_party()
        slot, err = self._pick_party(pokemon, party)
        if slot is None:
            return err
        mon = party[slot]
        who = mon.nickname or mon.species_name
        names = list(mon.move_names or [])
        key = str(move or "").strip().lower()
        idx = next((i for i, m in enumerate(names) if m and m.lower() == key), None)
        if idx is None:
            return f"{who} doesn't know {move!r} (moves: {', '.join(m for m in names if m)})."
        label = names[idx]
        if sum(1 for m in names if m) <= 1:
            return f"{who} only knows {label} — the Move Deleter won't delete a Pokémon's last move."
        if label in HM_MOVE_NAMES and not force and not any(label in (p.move_names or []) for i, p in enumerate(party) if i != slot):
            return (f"{who} is the only one who knows {label}, and the story still needs it (Cut / Surf / Strength / Flash / Fly). Teach it to another "
                    f"Pokémon first (teach_move), or pass force=true to delete it anyway.")
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(6):
            if tuple(self.reader.read_current_map()) == DELETER_MAP:
                break
            out = self._go_to("Move Deleter's House")
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if tuple(self.reader.read_current_map()) != DELETER_MAP and ("Blocked" in out or "Can't get to" in out or "No route" in out or "gated" in out):
                return f"Can't reach the Move Deleter (Fuchsia City, the house by the Pokémon Center): {out}"
        if tuple(self.reader.read_current_map()) != DELETER_MAP:
            return "Didn't reach the Move Deleter's house yet (Fuchsia City) — call forget_move again to continue."
        self._walk_to(*DELETER_STAND)
        self.mgba.tap("Up")                                   # face him
        self.mgba.tick(10)

        start_names = [m for m in names if m]

        def gone() -> bool:
            now = list(self.reader.read_party()[slot].move_names or [])
            return label not in now

        def wrong() -> list:
            """Moves OTHER than the target that have vanished (a mis-aimed A deletes the highlighted row): never keep going after one."""
            now = [m for m in (self.reader.read_party()[slot].move_names or []) if m]
            return [m for m in start_names if m != label and m not in now]

        gives_up = False
        self.mgba.tap("A")
        self.mgba.tick(50)
        for _ in range(80):
            if gone() or wrong():
                break
            cb2 = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if cb2 == Addr.CB2_PARTY_MENU:                    # "Which POKéMON?"
                if not self._party_cursor_to(slot):
                    gives_up = True
                    break
                self.mgba.tap("A")
                self.mgba.tick(60)
            elif cb2 == Addr.SUMMARY_CB2:                     # "Which move?"
                self.mgba.tick(70)
                # SUMMARY_MOVE_CURSOR keeps its OLD value until the first key is pressed here (a live run read the stale value, saw it equal the
                # target and pressed A on row 0: Cut, Surf and Strength went). The screen opens on the first move, so nudge Down and Up once to
                # make the variable live, then trust it.
                self.mgba.tap("Down")
                self.mgba.tick(16)
                self.mgba.tap("Up")
                self.mgba.tick(16)
                for _ in range(10):
                    cur = self.mgba.read8(Addr.SUMMARY_MOVE_CURSOR)
                    if cur == idx:
                        break
                    self.mgba.tap("Down" if cur < idx else "Up")
                    self.mgba.tick(16)
                if self.mgba.read8(Addr.SUMMARY_MOVE_CURSOR) != idx:
                    gives_up = True
                    break
                self.mgba.tap("A")
                self.mgba.tick(70)
            elif cb2 != Addr.CB2_OVERWORLD:                   # a screen loading (the summary passes through 0x08135C0D): inputs there act on row 0 — wait
                self.mgba.tick(20)
            elif self._menus.choice_live():                   # "Would you like me to do that?" / "…forgotten completely?" — YES both times
                self._menus.answer_prompt("yes")
                self.mgba.tick(60)
            else:
                self.mgba.tap("A")                            # text
                self.mgba.tick(40)
        lost = wrong()
        done = gone() and not lost
        for _ in range(8):                                    # the "forgot it completely" text: B (never A: that talks to him again)
            self.mgba.tap("B")
            self.mgba.tick(40)
        self._advance_to_control(tries=10)
        if done:
            events.emit("note", f"{who} forgot {label} (Move Deleter)", log=False)
            return f"{who} forgot {label}. It now knows: {', '.join(m for m in self.reader.read_party()[slot].move_names if m)}."
        self._menus.close_menus()
        if lost:
            return (f"STOPPED: the Move Deleter removed {', '.join(lost)} from {who} instead of {label} (the menu cursor was misread). "
                    f"{who} now knows: {', '.join(m for m in self.reader.read_party()[slot].move_names if m)}. Re-teach with teach_move if needed.")
        return (f"The Move Deleter didn't take {label} off {who}" + (" (the menu cursor wouldn't move)" if gives_up else "")
                + ". Talk to him at (4,4) in Fuchsia's house 3 and try again.")
