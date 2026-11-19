"""Move tutors (#274): the generated table against the decomp, the name resolver, who is picked and the refusals (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from knowledge.tutors import LEARNSETS, TUTOR_MOVES, TUTORS


def test_the_generated_table_matches_the_decomp_for_known_cases():
    assert TUTOR_MOVES[3] == "Body Slam" and TUTOR_MOVES[14] == "Substitute" and len(TUTOR_MOVES) == 15
    assert LEARNSETS[1] == sum(1 << b for b in (1, 3, 4, 7, 14))                 # Bulbasaur: Swords Dance, Body Slam, Double-Edge, Mimic, Substitute
    assert TUTORS["substitute"] == ("Substitute", 14, (3, 7), (15, 11), 0x2C8, "Fuchsia City", "")
    assert TUTORS["thunder_wave"][2] == (1, 48) and TUTORS["double_edge"][2] == (1, 40) and TUTORS["rock_slide"][2] == (1, 82)
    assert TUTORS["mimic"][6] and "Poké Doll" in TUTORS["mimic"][6]
    assert len(TUTORS) == 12 and all(row[4] >= 0x2C0 for row in TUTORS.values())    # FLAG_TUTOR_* range


pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from game.state import GameContext                 # noqa: E402


def mon(name, level, species, moves=("Tackle", "", "", ""), hp=30):
    return NS(species_name=name, nickname="", level=level, species_id=species, move_names=list(moves), max_hp=hp)


def client(party, flags=(), items=(), ctx="OVERWORLD"):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_party=lambda: party, read_flag=lambda f: f in flags, count_item=lambda i: 1 if i in items else 0,
                  detect_context=lambda: getattr(GameContext, ctx), read_current_map=lambda: (3, 7))
    c._pick_party = lambda ref, p: ((next((i for i, m in enumerate(p) if m.species_name.lower() == str(ref).lower() or str(ref) == str(i + 1)), None)), "no such Pokémon")
    c._go_to = lambda *a, **k: pytest.fail("should have refused before travelling")
    return c


def test_names_resolve_loosely_and_unknown_moves_list_the_tutors():
    r = AgentClient._resolve_tutor
    assert r("Double-Edge") == "double_edge" and r("soft boiled") == "softboiled" and r("Seismic Toss") == "seismic_toss" and r("counter") == "counter"
    assert r("mega") is None                                                    # Mega Punch / Mega Kick: ambiguous, not guessed
    assert "No tutor teaches 'Surf'" in client([mon("Venusaur", 30, 3)])._tutor("Surf")


def test_the_best_capable_pokemon_is_picked_and_incapable_ones_are_reported():
    party = [mon("Venusaur", 30, 3), mon("Rattata", 40, 19), mon("Pikachu", 20, 25)]
    c = client(party)
    row = TUTORS["seismic_toss"]
    slot, err = c._tutor_pick(party, row, "")
    capable = [m for m in party if LEARNSETS.get(m.species_id, 0) & (1 << row[1])]
    assert capable and party[slot] is max(capable, key=lambda m: m.level)       # the highest-level capable Pokémon
    assert c._tutor_pick(party, row, "Venusaur")[0] is None and "can't learn Seismic Toss" in c._tutor_pick(party, row, "Venusaur")[1]
    knows = [mon("Pikachu", 20, 25, moves=("Seismic Toss", "", "", ""))]
    assert "already knows Seismic Toss" in client(knows)._tutor_pick(knows, row, "Pikachu")[1]


def test_a_taught_lesson_the_mimic_doll_and_battles_are_refused_before_any_travel():
    party = [mon("Venusaur", 30, 3)]
    assert "already taught Substitute" in client(party, flags={0x2C8})._tutor("Substitute")
    assert "Poké Doll" in client(party)._tutor("Mimic")
    assert "in a battle" in client(party, ctx="IN_BATTLE")._tutor("Substitute")
    assert "Nobody in your party can learn Rock Slide" in client(party)._tutor("Rock Slide")


def test_a_full_moveset_needs_a_safe_move_to_forget():
    full = [mon("Venusaur", 30, 3, moves=("Razor Leaf", "Vine Whip", "Sleep Powder", "Growth"))]
    c = client(full)
    out = c._tutor("Substitute", "Venusaur", forget="Surf")
    assert "doesn't know 'Surf'" in out
