"""tutor(move, pokemon?, forget?): the Kanto move tutors (knowledge/tutors.py, generated from the decomp).

Each tutor is an NPC who teaches ONE move, once, free of charge, to a party Pokémon whose tutor learnset has that move (the party screen greys the others out). The flow, from
the decomp (data/scripts/move_tutors.inc): talk → "teach it?" YES → "it can only be learned once" YES → the party screen (gPartyMenu.slotId) → [a full moveset: "delete a move?" YES
→ the summary screen picks the move to forget] → the move is learned and FLAG_TUTOR_* is set. Driven by what the screen IS (callback2 / a live Yes-No box); the loop ends the moment the
move is in the Pokémon's list — one more A would talk to the NPC again."""
import re

from game.constants import Addr
from game.state import GameContext
from knowledge.tutors import LEARNSETS, TUTORS

_MIMIC_DOLL = 80                              # ITEM_POKE_DOLL (the Copycat only teaches Mimic for one)


def _norm(text) -> str:
    return re.sub(r"[^a-z]", "", str(text).lower())


class TutorMixin:
    @staticmethod
    def _resolve_tutor(move: str):
        key = _norm(move)
        hits = [k for k, row in TUTORS.items() if key in (_norm(k), _norm(row[0]))]
        hits = hits or [k for k, row in TUTORS.items() if key and (key in _norm(row[0]) or key in _norm(k))]
        return hits[0] if len(hits) == 1 else None

    def _tutor_pick(self, party, row, pokemon: str):
        """(slot, error): the Pokémon to teach — the named one, else the highest-level capable one that doesn't know the move yet."""
        name, bit = row[0], 1 << row[1]
        capable = [(i, p) for i, p in enumerate(party) if LEARNSETS.get(p.species_id, 0) & bit and name not in (p.move_names or []) and p.max_hp]
        if pokemon:
            slot, err = self._pick_party(pokemon, party)
            if slot is None:
                return None, err
            if slot not in [i for i, _p in capable]:
                who = party[slot].nickname or party[slot].species_name
                knows = name in (party[slot].move_names or [])
                return None, (f"{who} already knows {name}." if knows else f"{who} can't learn {name} from the tutor.")
            return slot, ""
        if not capable:
            return None, (f"Nobody in your party can learn {name} from its tutor (or they already know it). Species that can: "
                          f"{', '.join(sorted({p.species_name for p in party if LEARNSETS.get(p.species_id, 0) & bit})) or 'none of yours'}.")
        return max(capable, key=lambda ip: ip[1].level)[0], ""

    def _tutor(self, move: str, pokemon: str = "", forget: str = "") -> str:
        from agent import events
        from knowledge.leafgreen_data import MOVE_POWER
        from knowledge.navigation import MAP_NAMES
        from knowledge.tmhm import HM_MOVE_NAMES, pick_forget
        key = self._resolve_tutor(move)
        if key is None:
            return f"No tutor teaches {move!r}. Tutor moves: {', '.join(row[0] for row in TUTORS.values())}."
        name, _idx, tmap, (nx, ny), flag, place, note = TUTORS[key]
        if self.reader.read_flag(flag):
            return f"The {place} tutor already taught {name} (it is a one-time lesson)."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if key == "mimic" and not self.reader.count_item(_MIMIC_DOLL):
            return "The Copycat only teaches Mimic for a Poké Doll (buy one at the Celadon Dept. Store 2F, or find one): have it in the bag first."
        party = self.reader.read_party()
        slot, err = self._tutor_pick(party, TUTORS[key], pokemon)
        if slot is None:
            return err
        mon = party[slot]
        who = mon.nickname or mon.species_name
        before = list(mon.move_names or [])
        forget_idx = None
        if len([m for m in before if m]) >= 4:
            if forget:
                forget_idx = next((i for i, m in enumerate(before) if m and m.lower() == forget.strip().lower()), None)
                if forget_idx is None or before[forget_idx] in HM_MOVE_NAMES:
                    return f"{who} doesn't know {forget!r} or it is an HM move (moves: {', '.join(m for m in before if m)})."
            else:
                forget_idx = pick_forget(before, name, MOVE_POWER)
            if forget_idx is None:
                return (f"{who} knows four moves and none is safe to forget ({', '.join(before)}): call tutor('{name}', '{who}', forget='<move>').")
        dest = MAP_NAMES.get(tuple(tmap))
        for _ in range(8):
            if tuple(self.reader.read_current_map()) == tuple(tmap):
                break
            out = self._go_to(dest or place, mode="yield", resume_call=f"tutor({name!r})")
            if self.reader.detect_context() == GameContext.IN_BATTLE:
                return out
            if tuple(self.reader.read_current_map()) != tuple(tmap) and any(s in out for s in ("Can't get to", "No route", "Blocked", "gated", "no walking route")):
                return f"Can't reach the {name} tutor ({place}): {out}"
        if tuple(self.reader.read_current_map()) != tuple(tmap):
            return f"Didn't reach the {name} tutor ({place}) yet — call tutor({name!r}) again to continue."
        if not self._approach_adjacent(nx, ny):
            return f"Couldn't walk up to the {name} tutor at ({nx},{ny}) in {place}."
        px, py = self.reader.read_player_pos()
        face = self._facing_dir(px, py, nx, ny)
        if face:
            self.mgba.tap(face)
        self.mgba.tap("A")
        self.mgba.tick(40)

        def learned() -> bool:
            return name in (self.reader.read_party()[slot].move_names or [])

        asked, picked, gave_up = 0, 0, False
        for _ in range(90):
            if learned():
                break
            cb2 = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if cb2 == Addr.CB2_PARTY_MENU and self._menus.choice_live():       # a Yes/No box ON the party screen ("make it forget a move to learn X?") — YES
                self._menus.answer_prompt("yes")
                self.mgba.tick(50)
            elif cb2 == Addr.CB2_PARTY_MENU:                  # "Which POKéMON?" (the incapable ones are greyed out)
                picked += 1
                if picked > 14 or not self._party_cursor_to(slot):
                    gave_up = True
                    break
                self.mgba.tap("A")
                self.mgba.tick(60)
            elif cb2 == Addr.SUMMARY_CB2:                     # "forget which move?" — the same screen teach_move drives: settle, then walk the cursor (live-verified there)
                self.mgba.tick(60)
                idx = forget_idx if forget_idx is not None else 0
                for _ in range(12):
                    cur = self.mgba.read8(Addr.SUMMARY_MOVE_CURSOR)
                    if cur == idx:
                        break
                    self.mgba.tap("Down" if cur < idx else "Up")
                    self.mgba.tick(16)
                if forget_idx is None or self.mgba.read8(Addr.SUMMARY_MOVE_CURSOR) != idx:
                    gave_up = True
                    break
                self.mgba.tap("A")
                self.mgba.tick(70)
            elif cb2 != Addr.CB2_OVERWORLD:                   # a screen loading: inputs there act on whatever is highlighted — wait
                self.mgba.tick(20)
            elif self._menus.choice_live():                   # "teach it?" / "only once, OK?" / "delete a move?" — YES each time
                self._menus.answer_prompt("yes")
                asked += 1
                self.mgba.tick(50)
            else:
                self.mgba.tap("A")
                self.mgba.tick(40)
        for _ in range(12):                                   # the learning text ("1, 2 and... Poof!") finishes after the last press
            if learned():
                break
            self.mgba.tick(30)
        done = learned()
        for _ in range(6):                                    # the tutor's closing line: B, never A (that talks to him again)
            self.mgba.tap("B")
            self.mgba.tick(30)
        self._advance_to_control(tries=10)
        if done:
            events.emit("note", f"{who} learned {name} from the tutor", log=False)
            lost = [m for m in before if m and m not in (self.reader.read_party()[slot].move_names or [])]
            return f"{who} learned {name} from the {place} tutor" + (f", forgetting {lost[0]}." if lost else ".")
        self._menus.close_menus()
        return (f"The {place} tutor didn't teach {name} to {who}" + (" (the menu cursor wouldn't move or no move was safe to forget)" if gave_up else "")
                + f". Talk to the tutor at ({nx},{ny}) and answer YES, then pick {who}.")
