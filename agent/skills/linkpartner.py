"""trade_evolve(pokemon) and link_trade(want, give): the Cable Club with a scripted partner (#363).

trade_evolve evolves a trade-evolution Pokémon (Kadabra, Machoke, Graveler, Haunter); link_trade trades one of yours for a FireRed-only Pokémon (knowledge/exclusives.py) held by a FireRed partner core.

A second emulator core — the partner, restored from `saves/partner/partner_counter.ss1` — is linked to the running game through libmgba's SIO lockstep (game/link.py), and the game's own Cable
Club runs between them: the Pokémon goes to the partner for a throwaway Rattata, evolves on the partner's side (a trade evolution happens on the RECEIVER), and comes back for the Rattata. Only
buttons are pressed; the link, the trades and the evolution scene are the game's. Nothing but the partner's own save is touched; the partner core is destroyed afterwards.

Where: a Pokémon Center's 2F (every Center has the Cable Club upstairs: the stairs at (1,6) on 1F, the Direct Corner attendant across the counter from (10,4))."""
import os
from pathlib import Path

from game.state import GameContext

STAIRS, COUNTER = (1, 6), (10, 4)
PARTNER_STATE = Path(__file__).resolve().parents[2] / "saves" / "partner" / "partner_counter.ss1"
PARTNER_FIRERED_DIR = Path(__file__).resolve().parents[2] / "saves" / "partner"      # partner_firered_<group>.ss1: a FireRed core at the same counter
FIRERED_ROM = "~/mgba-http/Pokemon_FireRed.gba"
GROUP_SIZE = 5                                               # the FireRed partner's party: Bulbasaur + up to five exclusives
FLAG_POKEDEX = 0x829                                         # FLAG_SYS_POKEDEX_GET: the Cable Club's tutorial is set up by Oak's lab scene


def trade_evolutions() -> dict[int, int]:
    """species id -> the species it evolves into by trade alone (an item-holding trade is not handled)."""
    from knowledge.dex_sources import EVOLVES_FROM
    return {pre: sid for sid, (pre, how) in EVOLVES_FROM.items() if how == "a trade"}


def partner_slot(species_id: int) -> tuple[int, int]:
    """Where the FireRed partner holds `species_id`: (state group 1.., party slot 1..5). The exclusives, in species order, are dealt five to a state (slot 0 is the partner's own lead)."""
    from knowledge.exclusives import FIRERED_ONLY
    i = sorted(FIRERED_ONLY).index(species_id)
    return i // GROUP_SIZE + 1, i % GROUP_SIZE + 1


def partner_groups() -> dict[int, list[int]]:
    """group -> the species ids its state holds, in slot order."""
    from knowledge.exclusives import FIRERED_ONLY
    ids = sorted(FIRERED_ONLY)
    return {g + 1: ids[g * GROUP_SIZE:(g + 1) * GROUP_SIZE] for g in range((len(ids) + GROUP_SIZE - 1) // GROUP_SIZE)}


class LinkPartnerMixin:
    def _trade_evolve(self, pokemon: str) -> str:
        from game import link
        from knowledge.dex_plan import name
        party = self.reader.read_party()
        slot, err = self._pick_party(pokemon, party)
        if slot is None:
            return err
        mon = party[slot]
        who = mon.nickname or mon.species_name
        evo = trade_evolutions().get(mon.species_id)
        if evo is None:
            able = ", ".join(sorted({p.species_name for p in party if p.species_id in trade_evolutions()})) or "none in your party"
            return f"{who} does not evolve by trade (Kadabra, Machoke, Graveler and Haunter do; in your party: {able})."
        if len(party) < 2:
            return "The Cable Club needs two Pokémon in the party to link up."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_POKEDEX):
            return "The Cable Club opens once Oak has given you the Pokédex."
        state = Path(os.environ.get("PARTNER_STATE", PARTNER_STATE))
        if not link.available():
            return "The two-core link module is not built: python -m game._mgba_link_build."
        if not state.exists():
            return f"The partner's save {state} is missing: python tools/make_live_fixtures.py --only partner_counter --out {state.parent} (needs work.sav)."
        if (err := self._reach_cable_counter("trade_evolve")):
            return err
        rom = os.path.expanduser(os.environ.get("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))
        pair = None
        try:
            pair = link.TwoCoreLink.with_partner(self.mgba, rom, str(state))
            link.trade_evolve(pair, give0=slot, give1=1)
        except link.LinkError as e:
            return f"The link-up failed: {e}. The game may be in the Trade Center: close_menus / advance_dialog, then try again."
        finally:
            if pair is not None:
                pair.close()
        after = self.reader.read_party()[slot]
        if after.species_id != evo:
            return f"The trade ran but {who} is {after.species_name} now, not {name(evo)}."
        return f"{who} evolved into {after.species_name} (traded to the partner and back through the Cable Club)."

    def _link_trade(self, want: str, give: str) -> str:
        from game import link
        from game.constants import SPECIES_NAMES
        from knowledge.exclusives import FIRERED_ONLY
        menu = "; ".join(f"{SPECIES_NAMES.get(s, '?').title()} (L{lv}, FireRed: {where})" for s, (lv, where) in sorted(FIRERED_ONLY.items()))
        wanted = {n.lower(): s for s, n in SPECIES_NAMES.items()}.get(want.strip().lower())
        if wanted not in FIRERED_ONLY:
            return f"{want!r} is not a FireRed exclusive. A FireRed partner can trade you: {menu}."
        party = self.reader.read_party()
        slot, err = self._pick_party(give, party)
        if slot is None:
            return err
        who = party[slot].nickname or party[slot].species_name
        if len(party) < 2:
            return "The Cable Club needs two Pokémon in the party to link up."
        if self.reader.detect_context() == GameContext.IN_BATTLE:
            return "You're in a battle — finish it first."
        if not self.reader.read_flag(FLAG_POKEDEX):
            return "The Cable Club opens once Oak has given you the Pokédex."
        if not link.available():
            return "The two-core link module is not built: python -m game._mgba_link_build."
        rom = Path(os.path.expanduser(os.environ.get("FIRERED_ROM_PATH", FIRERED_ROM)))
        group, pslot = partner_slot(wanted)
        state = Path(os.environ.get("PARTNER_FIRERED_DIR", PARTNER_FIRERED_DIR)) / f"partner_firered_{group}.ss1"
        if not rom.exists():
            return f"A FireRed partner needs a FireRed ROM: {rom} (FIRERED_ROM_PATH)."
        if not state.exists():
            return f"The FireRed partner's save {state} is missing: python tools/make_live_fixtures.py --only partner_firered_{group} --out {state.parent} (needs a FireRed counter state, FIRERED_STATE)."
        if (err := self._reach_cable_counter("link_trade")):
            return err
        pair = None
        try:
            pair = link.TwoCoreLink.with_partner(self.mgba, str(rom), str(state))
            link.cable_club_trade(pair, give0=slot, give1=pslot)
        except link.LinkError as e:
            return f"The link-up failed: {e}. The game may be in the Trade Center: close_menus / advance_dialog, then try again."
        finally:
            if pair is not None:
                pair.close()
        got = self.reader.read_party()[slot]
        if got.species_id != wanted:
            return f"The trade ran but slot {slot + 1} holds {got.species_name} now, not {SPECIES_NAMES[wanted].title()}."
        lv, where = FIRERED_ONLY[wanted]
        return f"Traded {who} to the FireRed partner for {got.species_name} L{got.level} (found in FireRed at {where}, L{lv}+). {who} stays with the partner."

    def _reach_cable_counter(self, tool: str) -> str:
        """Walk to the Direct Corner counter on the nearest Pokémon Center's 2F, facing the attendant. "" on success, else what went wrong."""
        from knowledge.map_graph import MAP_WARPS, nearest_of_kind, node_for
        # Up the stairs of the nearest Pokémon Center and across to the counter.
        here = tuple(self.reader.read_current_map())
        if here not in self._center_2f_maps(MAP_WARPS):
            pos = tuple(self.reader.read_player_pos())
            hit = nearest_of_kind(node_for(here[0], here[1], pos[0], pos[1]), "pokecenter")
            if hit is None:
                return "No Pokémon Center to reach from here."
            for _ in range(6):
                if tuple(self.reader.read_current_map()) == hit[0]:
                    break
                out = self._go_to(f"map:{hit[0][0]},{hit[0][1]}")
                if self.reader.detect_context() == GameContext.IN_BATTLE:
                    return out
            if tuple(self.reader.read_current_map()) != hit[0]:
                return f"Didn't reach a Pokémon Center yet — call {tool} again to continue."
            self._walk_to(*STAIRS)
        self._advance_to_control(tries=10)
        if tuple(self.reader.read_current_map()) not in self._center_2f_maps(MAP_WARPS):
            return f"Couldn't get up to the Pokémon Center's second floor (at {self.reader.read_current_map()})."
        self._walk_to(*COUNTER)
        self.mgba.tap("Up")                                    # face the Direct Corner attendant across the counter
        self.mgba.tick(20)
        if tuple(self.reader.read_player_pos()) != COUNTER:
            return f"Couldn't reach the Direct Corner counter at {COUNTER} (at {self.reader.read_player_pos()})."
        return ""

    @staticmethod
    def _center_2f_maps(map_warps) -> set:
        """The Pokémon Centers' second floors: where each Center's 1F stairs warp (1,6) leads."""
        from knowledge.map_graph import MAP_KIND
        return {tuple(dest) for mp, warps in map_warps.items() if MAP_KIND.get(mp) == "pokecenter" for (x, y, dest) in warps if (x, y) == STAIRS}
