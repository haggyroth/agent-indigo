"""quest('trade <species>'): one of Kanto's in-game NPC trades (knowledge/trades.py — #362).

Walk to the trader, talk, answer YES, pick the wanted Pokémon on the party screen and let the trade scene run (an evolution it triggers plays out like any other). Verified by the trader's
own FLAG_DID_*_TRADE. The model decides WHICH trade and WHICH spare (it must own the wanted species: the call says so when it does not); nothing is bought or caught here."""
from game.constants import SPECIES_NAMES, Addr
from game.state import GameContext


class TradeMixin:
    def _trade_npc(self, arg: str = "") -> str:
        from knowledge.dex_plan import name as dex_name
        from knowledge.trades import NPC_TRADES, find
        if not str(arg or "").strip():
            lines = [f"{dex_name(got).upper()} for a {dex_name(want).upper()} — {where}" + (" (done)" if self.reader.read_flag(flag) else "")
                     for got, (want, _mp, _npc, flag, where) in NPC_TRADES.items()]
            return "Kanto's in-game trades (one each; you give the Pokémon asked for): " + "; ".join(lines) + ". quest('trade <species you want>') runs one."
        got = find(arg, SPECIES_NAMES)
        if got is None:
            return f"No in-game trade gives {arg!r}. Call quest('trade') for the list."
        want, mp, npc, flag, where = NPC_TRADES[got]
        call = f"quest('trade {dex_name(got).lower()}')"
        if self.reader.read_flag(flag):
            return f"You already made the trade for {dex_name(got)} ({where}) — one each."
        if self.reader.detect_context() != GameContext.OVERWORLD:
            return "A trade works from the open field — finish what is on screen first (advance_dialog / close_menus / the battle)."
        slots = [i for i, p in enumerate(self.reader.read_party()) if p.species_id == want and not p.is_egg]
        if not slots:
            return (f"{dex_name(got)} is traded for a {dex_name(want)} ({where}) and your party has none — get one (catch it, or the PC: pc('withdraw')), then call {call}. "
                    "The trade is one-way: you keep the new Pokémon, the other leaves for good.")
        if (msg := self._go_to_map_tuple(tuple(mp), f"map:{mp[0]},{mp[1]}", call)):
            return msg
        if not self._approach_adjacent(*npc):
            return f"Couldn't reach the trader at {npc} — walk up, face them and press A, then call {call}."
        px, py = self.reader.read_player_pos()
        if (face := self._facing_dir(px, py, *npc)):
            self.mgba.tap(face)
        self.mgba.tap("A")
        self.mgba.tick(20)
        chose = False
        for _ in range(60):
            if self.reader.read_flag(flag):
                break
            cb2 = self.mgba.read32(Addr.GMAIN_CALLBACK2)
            if cb2 == Addr.CB2_PARTY_MENU and not chose:
                self.mgba.tick(30)
                slot = next((i for i, p in enumerate(self.reader.read_party()) if p.species_id == want and not p.is_egg), None)
                if slot is None or not self._party_cursor_to(slot):
                    self._menus.close_menus()
                    return f"Couldn't select the {dex_name(want)} on the party screen."
                self.mgba.tap("A")
                self.mgba.tick(60)
                chose = True
            elif self._menus.choice_live():
                self._menus.answer_prompt("yes" if not chose else "no")         # 'Do you have a X? Want to trade?' YES; later boxes (a nickname for the newcomer) NO
                self.mgba.tick(30)
            else:
                self.mgba.tap("A")
                self.mgba.tick(40)
        self._advance_to_control(tries=30)
        if not self.reader.read_flag(flag):
            return f"Talked to the trader but the trade did not happen — call {call} again (or do it by hand: face them, A, YES, choose the {dex_name(want)})."
        return (f"Traded your {dex_name(want)} for a {dex_name(got)} ({where}). It is level-matched and, as a traded Pokémon, obeys at any level; "
                "a trade evolution it was waiting for may have run.")
