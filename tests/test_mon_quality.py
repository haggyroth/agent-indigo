"""IV / EV / nature awareness (#208): decoding, the stat formula, role-weighted quality, swaps, Hidden Power."""
from types import SimpleNamespace as P

import pytest

from game.constants import SPECIES_NAMES
from game.memory_reader import SUBSTRUCT_ORDER, LeafGreenReader, parse_evs, parse_ivs
from knowledge.battle import annotate_moves
from knowledge.mon_quality import (assess, calc_stat, compare_text, describe, hidden_power, nature_effect, nature_name,
                                   projected_stats, role_weights, upgrade_swaps)
from knowledge.move_semantics import move_score

ID = {v: k for k, v in SPECIES_NAMES.items()}
BULBA, PIDGEY, MACHOP = ID["Bulbasaur"], ID["Pidgey"], ID["Machop"]


# ── decoding ───────────────────────────────────────────────────────────────────────────────────
def pack_ivs(ivs, ability=0, egg=0):
    v = sum(iv << (5 * i) for i, iv in enumerate(ivs)) | (egg << 30) | (ability << 31)
    return v.to_bytes(4, "little")


def test_iv_and_ev_substructs_unpack_per_the_decomp_layout():
    sub = {"E": bytes([1, 2, 3, 4, 5, 6, 0, 0, 0, 0, 0, 0]), "M": bytes(4) + pack_ivs((31, 0, 17, 5, 22, 9), ability=1) + bytes(4)}
    assert parse_evs(sub) == (1, 2, 3, 4, 5, 6)
    assert parse_ivs(sub) == ((31, 0, 17, 5, 22, 9), 1)


def boxmon(species, ivs, evs=(0,) * 6, pid=0x11223344, exp=135, friendship=70):
    ot = 0x55667788
    key = pid ^ ot
    sub = {k: bytearray(12) for k in "GAEM"}
    sub["G"][0:2] = species.to_bytes(2, "little")
    sub["G"][4:8] = exp.to_bytes(4, "little")
    sub["G"][9] = friendship
    sub["A"][0:2] = (33).to_bytes(2, "little")
    sub["E"][0:6] = bytes(evs)
    sub["M"][4:8] = pack_ivs(ivs)
    blob = bytearray()
    for letter in SUBSTRUCT_ORDER[pid % 24]:
        blob += sub[letter]
    for i in range(0, 48, 4):
        blob[i:i + 4] = (int.from_bytes(blob[i:i + 4], "little") ^ key).to_bytes(4, "little")
    raw = bytearray(80)
    raw[0:4], raw[4:8] = pid.to_bytes(4, "little"), ot.to_bytes(4, "little")
    raw[32:80] = blob
    return bytes(raw)


def test_boxed_pokemon_carry_ivs_evs_friendship_and_personality():
    r = LeafGreenReader.__new__(LeafGreenReader)
    m = r._decode_box_mon(boxmon(PIDGEY, (31, 3, 4, 28, 9, 20), (4, 0, 0, 8, 0, 0), pid=0x0102030D), 0, 0)
    assert m["ivs"] == (31, 3, 4, 28, 9, 20) and m["evs"] == (4, 0, 0, 8, 0, 0)
    assert m["friendship"] == 70 and m["personality"] == 0x0102030D


# ── the formula ────────────────────────────────────────────────────────────────────────────────
def test_stat_formula_and_natures():
    assert projected_stats(BULBA, (31,) * 6, (0,) * 6, 0, 50) == (120, 69, 69, 65, 85, 85)          # neutral Hardy
    adamant = 3                                                                                          # +Atk −SpA
    assert nature_name(adamant) == "Adamant" and nature_effect(adamant) == (1, 4)
    assert projected_stats(BULBA, (31,) * 6, (0,) * 6, adamant, 50) == (120, 75, 69, 65, 76, 85)
    assert nature_effect(0) == (None, None) and nature_effect(24) == (None, None)                     # Hardy / Quirky
    assert nature_effect(13) == (3, 4) and nature_name(13) == "Jolly"                                  # +Spe −SpA
    assert calc_stat(45, 31, 252, 100, 0) > calc_stat(45, 31, 0, 100, 0)                               # EVs matter at L100
    assert projected_stats(BULBA, (), (), 0, 50) == ()


def test_hidden_power_follows_the_iv_low_bits():
    assert hidden_power((31,) * 6) == ("DRK", 70)
    assert hidden_power((0,) * 6) == ("FIG", 30)
    assert hidden_power((31, 30, 31, 30, 30, 30))[0] == "FLY"
    assert hidden_power(()) is None


# ── quality ──────────────────────────────────────────────────────────────────────────────────
def mon(species=PIDGEY, ivs=(20,) * 6, pid=0, moves=("Tackle",), level=10, name="Pidgey", nick="", evs=(0,) * 6):
    return P(species_id=species, species_name=name, nickname=nick, ivs=tuple(ivs), evs=evs, personality=pid,
             move_names=list(moves), level=level, stats=(), current_hp=20, max_hp=20)


def test_roles_come_from_base_stats_and_the_moves_known():
    assert role_weights(MACHOP, ["Karate Chop"])[1] > role_weights(MACHOP, ["Karate Chop"])[4]       # physical
    assert role_weights(BULBA, ["Tackle", "Razor Leaf"])[4] > role_weights(BULBA, ["Tackle", "Razor Leaf"])[1]   # special
    mixed = role_weights(ID["Pikachu"], ["Thunder Shock", "Quick Attack"])
    assert mixed[1] == mixed[4] > 0


def test_a_dead_stat_does_not_count_against_a_specimen_but_a_useful_one_does():
    phys = ("Karate Chop", "Low Kick")
    lopsided = assess(mon(MACHOP, (31, 31, 31, 31, 0, 31), moves=phys, name="Machop"))        # SpA IV 0, irrelevant
    even = assess(mon(MACHOP, (16, 16, 16, 16, 16, 16), moves=phys, name="Machop"))
    weak_atk = assess(mon(MACHOP, (31, 0, 31, 31, 31, 31), moves=phys, name="Machop"))
    assert lopsided.score > even.score > 0.4
    assert weak_atk.score < lopsided.score - 0.15
    assert lopsided.grade in ("excellent", "good") and assess(mon(ivs=(2,) * 6)).grade == "below average"


def test_nature_fit_rewards_boosting_the_role_and_punishes_lowering_it():
    ivs = (20,) * 6
    phys = ("Karate Chop",)
    adamant = assess(mon(MACHOP, ivs, pid=3, moves=phys))      # +Atk −SpA: ideal
    modest = assess(mon(MACHOP, ivs, pid=15, moves=phys))      # +SpA −Atk: wrong way round
    neutral = assess(mon(MACHOP, ivs, pid=0, moves=phys))
    assert adamant.nature_fit > 0 > modest.nature_fit and neutral.nature_fit == 0
    assert adamant.score > neutral.score > modest.score


def test_unreadable_ivs_give_no_quality_and_describe_says_so():
    assert assess(mon(ivs=())) is None
    assert "couldn't be read" in describe(mon(ivs=()))


def test_describe_lists_stats_evs_hidden_power_and_grade():
    m = mon(BULBA, (31, 30, 31, 31, 30, 31), pid=0, moves=("Tackle", "Razor Leaf"), level=50, name="Bulbasaur",
            evs=(0, 0, 0, 0, 100, 0))
    out = describe(m)
    assert out.startswith("Bulbasaur (Bulbasaur L50):") and "IV" in out
    assert "Stats: HP 120" in out and "EVs (100/510): SpA 100" in out and "Hidden Power would be" in out


# ── swaps and comparisons ───────────────────────────────────────────────────────────────────────
def box(species, ivs, slot, level=8, pid=0, name="Pidgey"):
    return {"species_id": species, "species_name": name, "nickname": "", "box": 0, "slot": slot, "level": level,
            "ivs": tuple(ivs), "evs": (0,) * 6, "personality": pid, "move_names": ["Gust", "Tackle"]}


def test_a_clearly_better_boxed_specimen_is_offered_as_an_exact_swap():
    party = [mon(PIDGEY, (8, 5, 10, 6, 9, 7), moves=("Gust", "Tackle"), level=14)]
    boxes = [box(PIDGEY, (31, 28, 29, 30, 26, 27), 4, level=7), box(PIDGEY, (9, 6, 10, 7, 9, 8), 5)]
    out = upgrade_swaps(party, boxes)
    assert len(out) == 1 and "pc_swap('Pidgey', '1:4')" in out[0] and "7 levels lower" in out[0]
    assert upgrade_swaps(party, [box(PIDGEY, (9, 6, 10, 7, 9, 8), 5)]) == []              # not clearly better
    assert upgrade_swaps(party, [box(ID["Rattata"], (31,) * 6, 6)]) == []                 # another species is not a swap


def test_catch_comparison_against_the_same_species_or_the_team():
    old = mon(PIDGEY, (8, 5, 10, 6, 9, 7), pid=1, moves=("Gust", "Tackle"))
    new = mon(PIDGEY, (30, 28, 29, 31, 27, 26), pid=2, moves=("Gust", "Tackle"))
    assert "a clear upgrade" in compare_text(new, [old])
    assert "a clear downgrade" in compare_text(old, [new])
    other = mon(ID["Rattata"], (15,) * 6, pid=3, name="Rattata")
    assert compare_text(new, [other]).startswith("team average")


# ── Hidden Power in the battle ranker / observation ─────────────────────────────────────────────────────
def test_hidden_power_scores_and_displays_its_real_type_once_known():
    unknown = move_score("Hidden Power", (), ("GHO",))
    known = move_score("Hidden Power", (), ("GHO",), hidden_power=("GHO", 70))
    assert known > unknown and known == pytest.approx(70 * 2)             # Ghost into a Ghost: the real power × super effective
    out = annotate_moves(["Hidden Power"], "GASTLY", [15], hidden_power=("GHO", 70))
    assert "Ghost" in out and "Hidden Power is Ghost 70" in out


# ── catch report ───────────────────────────────────────────────────────────────────────────────────
def test_the_catch_report_finds_the_new_pokemon_by_personality():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    old = mon(PIDGEY, (8, 5, 10, 6, 9, 7), pid=1, moves=("Gust", "Tackle"), nick="Peck")
    new = mon(PIDGEY, (30, 28, 29, 31, 27, 26), pid=2, moves=("Gust", "Tackle"))
    c.reader = P(read_party=lambda: [old, new], read_boxes=lambda: [])
    out = c._caught_quality(2)
    assert out.startswith("Quality: ") and "vs your Peck" in out and "a clear upgrade" in out
    c.reader = P(read_party=lambda: [old], read_boxes=lambda: [box(PIDGEY, (30, 28, 29, 31, 27, 26), 3, pid=9)])
    assert c._caught_quality(9).startswith("Quality: ")                    # went to the PC: found in the boxes
    assert c._caught_quality(0) == ""


def test_readiness_flags_a_better_specimen_in_the_pc_as_a_should_item():
    from knowledge.readiness import assess as readiness
    party = [mon(PIDGEY, (8, 5, 10, 6, 9, 7), moves=("Gust", "Tackle"), level=14)]
    party[0].current_hp = party[0].max_hp = 40
    party[0].status, party[0].pp, party[0].move_ids = "healthy", [10, 10], []
    boxes = [box(PIDGEY, (31, 28, 29, 30, 26, 27), 4, level=12)]
    needs = readiness(party, 9, 9, 0, ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine", "Giovanni"],
                      boxes=boxes)
    up = [n for n in needs if n.code == "upgrade"]
    assert len(up) == 1 and up[0].level == "should" and "pc_swap" in up[0].text
