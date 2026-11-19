"""Town services (#277): rename_pokemon (the Name Rater in Lavender Town) and daycare (the Route 5 Day Care).

Both follow the Move Deleter's shape: travel to the house, stand below the NPC at (4,5), face Up, and drive the dialogue by what each screen IS (a live Yes/No box, the party screen,
the naming keyboard) — never by counting presses — stopping the moment the party shows the result.

* Name Rater (LavenderTown_House2): "Want me to rate nicknames?" YES → "Critique which Pokémon's nickname?" (party screen) → "Give it a nicer name?" YES → the naming keyboard.
  A traded Pokémon (other OT) is "truly impeccable" — no keyboard opens.
* Day Care (Route5_PokemonDayCare, data/scripts/day_care.inc): with nobody inside, "raise a Pokémon?" YES → party screen → he keeps it (the party needs a second Pokémon that can
  still fight). Collecting: he says how many levels it grew, the fee is ¥100 + ¥100 per level gained, "pay?" YES → it is back as the last party member. It gains 1 exp per step you walk."""
from game.constants import Addr
from game.state import GameContext

NAME_RATER_MAP, NAME_RATER_STAND = (8, 4), (4, 5)            # he stands at (4,4)
DAYCARE_MAP, DAYCARE_STAND = (17, 0), (4, 5)                 # the Day Care man stands at (4,4)


class ServicesMixin:
    def _reach_house(self, dest_name: str, target: tuple, stand: tuple, what: str):
        """Travel into the house and face the NPC. None = ready; else the message to return."""
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        for _ in range(6):
            if tuple(self.reader.read_current_map()) == target:
                break
            out = self._go_to(dest_name)
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if tuple(self.reader.read_current_map()) != target and ("Blocked" in out or "Can't get to" in out or "No route" in out or "gated" in out):
                return f"Can't reach {what}: {out}"
        if tuple(self.reader.read_current_map()) != target:
            return f"Didn't reach {what} yet — call the tool again to continue."
        self._walk_to(*stand)
        self.mgba.tap("Up")                                   # face him
        self.mgba.tick(10)
        return None

    def _close_talk(self) -> None:
        for _ in range(8):                                    # leftover text: B (never A: that talks to him again)
            self.mgba.tap("B")
            self.mgba.tick(40)
        self._advance_to_control(tries=10)

    # ── Name Rater ─────────────────────────────────────────────────────────────────────────────────────────────────────
    def _rename_pokemon(self, pokemon: str, nickname: str) -> str:
        from agent import events
        from game.naming import MAX_NAME, NamingDriver, typeable
        party = self.reader.read_party()
        slot, err = self._pick_party(pokemon, party)
        if slot is None:
            return err
        nick = str(nickname or "").strip()
        if not nick or len(nick) > MAX_NAME or not typeable(nick):
            return f"{nickname!r} can't be typed on the keyboard (1-{MAX_NAME} letters, digits, space and basic punctuation)."
        who = party[slot].nickname or party[slot].species_name
        if (party[slot].nickname or "") == nick:
            return f"{who} is already called {nick}."
        if (msg := self._reach_house("Name Rater's House", NAME_RATER_MAP, NAME_RATER_STAND, "the Name Rater (Lavender Town, the house next to the Mart)")):
            return msg
        nd = NamingDriver(self.mgba)

        def renamed() -> bool:
            now = self.reader.read_party()
            return slot < len(now) and (now[slot].nickname or "") == nick

        typed, why = False, ""
        self.mgba.tap("A")
        self.mgba.tick(50)
        for _ in range(80):
            if renamed():
                break
            if nd.active():
                out = nd.enter_name(nick)
                typed = True
                if not out.startswith("Named"):
                    why = out
                    nd.abort()
                    break
                self.mgba.tick(60)
                continue
            cb2 = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if cb2 == Addr.CB2_PARTY_MENU:                    # "Critique which Pokémon's nickname?"
                if not self._party_cursor_to(slot):
                    break
                self.mgba.tap("A")
                self.mgba.tick(60)
            elif cb2 != Addr.CB2_OVERWORLD:                   # a screen loading (the keyboard fades in): inputs there are lost — wait
                self.mgba.tick(20)
            elif self._menus.choice_live():                   # "Want me to rate nicknames?" / "Give it a nicer name?" — YES both times
                self._menus.answer_prompt("yes")
                self.mgba.tick(60)
            else:
                self.mgba.tap("A")                            # text
                self.mgba.tick(40)
        done = renamed()
        self._close_talk()
        if done:
            events.emit("note", f"{who} renamed {nick} (Name Rater)", log=False)
            return f"{who} is now called {nick}."
        self._menus.close_menus()
        if not typed:
            return (f"The Name Rater wouldn't take {who} — a Pokémon you got in a trade (other trainer) has a name he calls 'truly impeccable', and an Egg can't be named. "
                    "Nothing changed.")
        return f"Couldn't type {nick!r} on the keyboard ({why}); {who} keeps its name. Try a shorter, plainer name."

    # ── Day Care ───────────────────────────────────────────────────────────────────────────────────────────────────────
    def _daycare(self, action: str, pokemon: str = "") -> str:
        from agent import events
        act = str(action or "").strip().lower()
        if act not in ("deposit", "withdraw"):
            return "daycare(action='deposit', pokemon=…) leaves one with the Day Care man on Route 5 (it gains 1 exp per step you walk); daycare(action='withdraw') takes it back for ¥100 + ¥100 per level gained."
        party = self.reader.read_party()
        money0 = self.reader.read_money()
        if act == "deposit":
            slot, err = self._pick_party(pokemon, party)
            if slot is None:
                return err
            alive = [p for i, p in enumerate(party) if i != slot and p.current_hp > 0]
            if len(party) < 2 or not alive:
                return "He only takes a Pokémon if another one in your party can still battle."
            if party[slot].current_hp <= 0:
                return f"{party[slot].nickname or party[slot].species_name} has fainted — heal first."
        elif len(party) >= 6:
            return "The party is full: put a Pokémon in the PC first (pc), then collect it."
        label = (party[slot].nickname or party[slot].species_name) if act == "deposit" else ""
        if (msg := self._reach_house("Pokemon Day Care", DAYCARE_MAP, DAYCARE_STAND, "the Day Care (Route 5, the house by the south gate)")):
            return msg
        count0 = len(party)

        def moved() -> bool:
            n = len(self.reader.read_party())
            return n == count0 - 1 if act == "deposit" else n == count0 + 1

        self.mgba.tap("A")
        self.mgba.tick(50)
        gave_up = False
        for _ in range(80):
            if moved():
                break
            cb2 = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if cb2 == Addr.CB2_PARTY_MENU:                    # "Which Pokémon should I raise?"
                if not self._party_cursor_to(slot):
                    gave_up = True
                    break
                self.mgba.tap("A")
                self.mgba.tick(60)
            elif cb2 != Addr.CB2_OVERWORLD:
                self.mgba.tick(20)
            elif self._menus.choice_live():                   # "raise a Pokémon?" / "pay ¥X?" — YES
                self._menus.answer_prompt("yes")
                self.mgba.tick(60)
            else:
                self.mgba.tap("A")
                self.mgba.tick(40)
        done = moved()
        self._close_talk()
        self._menus.close_menus()
        if done and act == "deposit":
            events.emit("note", f"{label} left at the Day Care", log=False)
            return f"{label} is at the Day Care. It gains 1 exp per step you walk; come back and daycare(action='withdraw') (¥100 + ¥100 per level gained)."
        if done:
            back = self.reader.read_party()[-1]
            paid = money0 - self.reader.read_money()
            events.emit("note", f"{back.nickname or back.species_name} collected from the Day Care (¥{paid})", log=False)
            return f"{back.nickname or back.species_name} is back (L{back.level}); it cost ¥{paid}."
        if act == "withdraw":
            return ("The Day Care man didn't hand a Pokémon back: nobody is left with him, or you can't afford the fee (¥100 + ¥100 per level it gained) — "
                    f"you have ¥{self.reader.read_money()}.")
        return "The Day Care man didn't take it" + (" (the party cursor wouldn't move)" if gave_up else "") + ". Talk to him at (4,4) inside the Route 5 house and try again."
