"""Bag awareness (#205): TM upgrades, the bag digest, stone notes, the teach_move preview (no emulator)."""
from types import SimpleNamespace as P

import pytest

from knowledge.bag import bag_digest, stone_notes, tm_advice
from knowledge.readiness import assess

TM13, TM24, TM26, TM06 = 289 + 12, 289 + 23, 289 + 25, 289 + 5      # Ice Beam, Thunderbolt, Earthquake, Toxic
HM01, HM03 = 339, 341


def mon(sid, name, moves, ids=(), hp=40, level=30, nick=""):
    return P(species_id=sid, species_name=name, nickname=nick, max_hp=hp, current_hp=hp, level=level,
             move_names=list(moves), move_ids=list(ids), status="healthy", pp=[10, 10, 10, 10])


LAPRAS = lambda: mon(131, "Lapras", ["Water Gun", "Growl", "Sing", "Mist"])           # noqa: E731
PIKACHU = lambda: mon(25, "Pikachu", ["Thunder Shock", "Growl", "Thunder Wave", "Quick Attack"])   # noqa: E731


def test_a_clear_tm_upgrade_names_the_exact_call_and_what_it_replaces():
    adv = tm_advice([LAPRAS()], [(TM13, 1)])
    assert len(adv) == 1 and adv[0].move == "Ice Beam" and adv[0].forget == "Growl"
    assert "teach_move('TM13', pokemon='Lapras', forget='Growl')" in adv[0].text


def test_no_advice_for_incompatible_known_weak_or_marginal_tms():
    assert tm_advice([LAPRAS()], [(TM26, 1)]) == []                                  # Lapras can't learn Earthquake
    already = mon(131, "Lapras", ["Ice Beam", "Water Gun", "Sing", "Mist"])
    assert tm_advice([already], [(TM13, 1)]) == []                                   # already knows it
    assert tm_advice([LAPRAS()], [(TM06, 1)]) == []                                  # Toxic: a status move, not an upgrade
    strong = mon(131, "Lapras", ["Surf", "Ice Beam", "Body Slam", "Thunderbolt"])
    assert tm_advice([strong], [(TM24, 1)]) == []                                    # nothing worth replacing
    assert tm_advice([LAPRAS()], [(HM03, 1)]) == []                                  # HMs are field tools, never "upgrades"


def test_one_suggestion_per_pokemon_and_per_tm_and_a_cap():
    party = [LAPRAS(), PIKACHU()]
    adv = tm_advice(party, [(TM13, 1), (TM24, 1)])
    assert sorted((a.tm, a.mon) for a in adv) == [("TM13", "Lapras"), ("TM24", "Pikachu")]
    assert len(tm_advice(party, [(TM13, 1), (TM24, 1)], limit=1)) == 1


def test_a_free_slot_is_filled_only_when_the_move_is_worth_it():
    three = mon(131, "Lapras", ["Water Gun", "Growl", "Sing"])
    adv = tm_advice([three], [(TM13, 1)])
    assert adv and adv[0].forget is None and "empty move slot" in adv[0].text and "forget=" not in adv[0].text


def test_readiness_surfaces_tm_upgrades_as_a_should_item_but_never_over_a_must():
    needs = assess([LAPRAS()], balls=9, potions=9, money=0, gyms_beaten=["Brock", "Misty", "Lt. Surge", "Erika"],
                   tms=[(TM13, 1)])
    teach = [n for n in needs if n.code == "teach"]
    assert len(teach) == 1 and teach[0].level == "should" and "TM upgrade" in teach[0].text
    hurt = LAPRAS()
    hurt.current_hp = 1
    assert not [n for n in assess([hurt], tms=[(TM13, 1)]) if n.code == "teach"]      # heal first


def test_digest_lists_tms_hms_and_who_knows_them_and_stuff():
    party = [mon(1, "Ivysaur", ["Cut", "Tackle"]), PIKACHU()]
    line = bag_digest(party, [(TM13, 1), (HM01, 1), (HM03, 1)], [(96, 1), (68, 2), (13, 5)])
    assert line.startswith("BAG — ")
    assert "TM13 Ice Beam" in line and "HM01 Cut (known by Ivysaur)" in line and "HM03 Surf (NOT taught yet)" in line
    assert "Thunder Stone" in line and "Rare Candy×2" in line and "Potion" not in line
    assert bag_digest(party, [], [(13, 5)]) == ""


def test_stone_notes_pair_each_stone_with_the_pokemon_that_can_use_it():
    eevee = mon(133, "Eevee", ["Tackle"])
    notes = stone_notes([PIKACHU(), eevee], [(96, 1), (95, 1)])
    assert "Fire Stone: Eevee can evolve (→ Flareon)" in notes
    assert "Thunder Stone: Pikachu can evolve (→ Raichu)" in notes and "Thunder Stone: Eevee can evolve (→ Jolteon)" in notes
    assert stone_notes([LAPRAS()], [(96, 1)]) == []
    assert stone_notes([PIKACHU()], [(96, 0)]) == []


# ── the teach_move preview ──────────────────────────────────────────────────────────────────────
class FakeReader:
    def __init__(self, party):
        self.party = party

    def detect_context(self):
        from game.state import GameContext
        return GameContext.OVERWORLD

    def read_tmhm_pocket(self): return [(TM13, 1), (HM01, 1)]
    def read_key_items(self): return [364]
    def read_party(self): return self.party


def teach_client(party):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    from game.constants import Addr
    c = AgentClient.__new__(AgentClient)
    c.reader = FakeReader(party)
    Addr_TM = Addr.TM_CASE_ITEM
    c.reader.read_key_items = lambda: [Addr_TM]
    c._knows = lambda slot, move_id: False
    c._teach_once = lambda iid, slot, forget: (True, f"taught (forget={forget!r})")
    return c


def test_teach_move_previews_a_single_use_tm_that_would_cost_a_move():
    lap = LAPRAS()
    lap.move_ids = [55, 45, 47, 54]
    c = teach_client([lap])
    out = c._teach_move("TM13", "Lapras")
    assert out.startswith("Would teach Ice Beam to Lapras, forgetting Growl") and "forget='Growl'" in out
    assert c._teach_move("TM13", "Lapras", forget="Mist").startswith("taught (forget='Mist')")     # explicit choice commits
    assert c._teach_move("TM13", "Lapras", confirm=True).startswith("taught")                      # confirm commits the default


def test_no_preview_when_there_is_a_free_slot():
    lap = mon(131, "Lapras", ["Water Gun", "Growl", "Sing"])
    assert teach_client([lap])._teach_move("TM13", "Lapras").startswith("taught")
