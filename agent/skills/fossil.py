"""quest('fossil [helix|dome|amber]'): revive a fossil at the Cinnabar Pokémon Lab (#362).

From the decomp (CinnabarIsland_PokemonLab_ExperimentRoom): the scientist at (12,3) lists the fossils you own and have not revived — a Mt. Moon fossil (Helix or Dome) first, the Old Amber
after it — and you pick one and say YES (the item is taken, REVIVE_STATE 1). It "takes time": entering the Lab's ENTRANCE map (the room's only door, (7,9)) moves the state to 2, and the
next talk to him gives the level 5 Pokémon (Omanyte / Kabuto / Aerodactyl; the party, or the PC when full) — flags REVIVED_HELIX 0x2ED / DOME 0x2EC / AMBER 0x2EE. One fossil at a time;
a one-time EITHER-OR between Helix and Dome is made at Mt. Moon (only one can be taken), not here. The nickname box is declined."""
from game.state import GameContext

EXPERIMENT_ROOM, LAB_ENTRANCE = (12, 4), (12, 1)
SCIENTIST_SPOTS = (((12, 4), "Up"), ((11, 3), "Right"), ((13, 3), "Left"))
VAR_REVIVE_STATE = 0x406A
FOSSILS = {                                          # key -> (name, species revived, got flag, revived flag)
    "helix": ("Helix Fossil", "Omanyte", 0x273, 0x2ED),
    "dome": ("Dome Fossil", "Kabuto", 0x272, 0x2EC),
    "amber": ("Old Amber", "Aerodactyl", 0x25E, 0x2EE),
}


class FossilMixin:
    def _fossil_pick(self, arg: str) -> str | None:
        flag = self.reader.read_flag
        owned = [k for k, (_n, _s, got, rev) in FOSSILS.items() if flag(got) and not flag(rev)]
        a = str(arg or "").strip().lower()
        if a:
            return next((k for k in FOSSILS if a in (k, FOSSILS[k][0].lower(), FOSSILS[k][1].lower()) or a in FOSSILS[k][0].lower()), None)
        return owned[0] if owned else None

    def _fossil(self, arg: str = "") -> str:
        flag = self.reader.read_flag
        state = self.reader.read_var(VAR_REVIVE_STATE)
        key = self._fossil_pick(arg)
        if key is None:
            return ("No fossil to revive: you hold none that is not already revived (Helix / Dome Fossil: Mt. Moon B2F — one of the two; Old Amber: quest('old_amber')). "
                    "The Cinnabar Pokémon Lab does the revival.") if not str(arg or "").strip() else f"No fossil called {arg!r}: helix, dome or amber."
        name, species, got, rev = FOSSILS[key]
        call = f"quest('fossil {key}')"
        if flag(rev):
            return f"The {name} was already revived ({species}) — it is in your party or the PC."
        if state == 0 and not flag(got):
            return f"You do not have the {name} yet."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "A revival works from the open field — finish what is on screen first (advance_dialog / close_menus / the battle)."
        notes = []
        if state == 0:
            if (msg := self._go_to_map_tuple(EXPERIMENT_ROOM, "map:12,4", call)):
                return msg
            if not self._talk_scientist():
                return f"Couldn't reach the Lab scientist at (12,3) — walk up, face him and press A, then call {call}."
            listed = [k for k, (_n, _s, g, r) in FOSSILS.items() if flag(g) and not flag(r)]
            want = listed.index(key) if key in listed else 0
            self._fossil_dialogue(want)
            if self.reader.read_var(VAR_REVIVE_STATE) != 1:
                return f"The scientist did not take the {name} — call {call} again."
            notes.append(f"handed over the {name}")
            state = 1
        if state == 1:
            # "go for a walk": enter the Lab's entrance map and come back — that moves the state to 2
            self._walk_to(7, 9)
            self._advance_to_control(tries=30)
            if (msg := self._go_to_map_tuple(EXPERIMENT_ROOM, "map:12,4", call)):
                return msg
            if self.reader.read_var(VAR_REVIVE_STATE) != 2:
                return f"The {name} is not ready yet — call {call} again after walking out of the Lab and back."
            notes.append("walked out and back")
            state = 2
        if state == 2:
            if tuple(self.reader.read_current_map()) != EXPERIMENT_ROOM and (msg := self._go_to_map_tuple(EXPERIMENT_ROOM, "map:12,4", call)):
                return msg
            if not self._talk_scientist():
                return f"Couldn't reach the Lab scientist — call {call} again."
            self._fossil_dialogue(0)
            if not flag(rev):
                return f"The {species} did not arrive — call {call} again."
            notes.append(f"got the {species} (L5)")
        return f"Revived the {name}: " + ", ".join(notes) + ". It is level 5 and needs levelling (grind balances it); the next fossil is a separate quest('fossil')."

    def _talk_scientist(self) -> bool:
        """Walk up to the Lab scientist (local id 2) WHERE HE IS NOW — he wanders around his spot — face him and press A. True once a dialogue is open (the context left the free field)."""
        for _ in range(4):
            pos = self.reader.read_objects_by_local().get(2)
            if pos is None or not self._approach_adjacent(*pos):
                continue
            px, py = self.reader.read_player_pos()
            if self.reader.read_objects_by_local().get(2) != pos:
                continue                                              # he stepped while we walked: look again
            if (face := self._facing_dir(px, py, *pos)):
                self.mgba.tap(face)
            self.mgba.tap("A")
            self.mgba.tick(30)
            if self.reader.detect_context() != GameContext.OVERWORLD:
                return True
        return False

    def _fossil_dialogue(self, option: int) -> None:
        """Run the scientist's dialogue. At REVIVE_STATE 0 the fossil list appears BY ITSELF once "Have you a fossil for me?" has printed (a script `message` + `multichoice`, no button
        between; the text has three paragraphs before it) and it is not the small-menu cursor the Yes/No probe reads — so wait for the text, move to row `option` (0 = first) and press A; then A through the text and YES to the
        confirmation. Later conversations (REVIVE_STATE 2) just advance the text and say NO to the nickname."""
        if self.reader.read_var(VAR_REVIVE_STATE) == 0:
            for _ in range(3):                                         # "Hiya!" / "I am important doctor…" / "Here, I study…" — three paragraphs, then "Have you a fossil for me?" and the list
                self.mgba.tap("A")
                self.mgba.tick(60)
            self.mgba.tick(90)
            for _ in range(option):
                self.mgba.tap("Down")
                self.mgba.tick(12)
            self.mgba.tap("A")
            self.mgba.tick(40)
        for _ in range(60):
            if self._menus.choice_live():
                self._menus.answer_prompt("no" if self.reader.read_var(VAR_REVIVE_STATE) == 2 else "yes")
                self.mgba.tick(30)
            elif self.reader.detect_context() == GameContext.OVERWORLD and self.reader.read_var(VAR_REVIVE_STATE) != 0:
                break
            else:
                self.mgba.tap("A")
                self.mgba.tick(25)
        self._advance_to_control(tries=10)
