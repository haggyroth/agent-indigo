"""Team composition (#207): coverage, weaknesses, HM carriers, gym fit, hunt hints, catch-policy gap bonus (no emulator)."""
from types import SimpleNamespace as P

from game.constants import SPECIES_NAMES
from knowledge.catch_policy import PREMIUM_DEBT, evaluate
from knowledge.gym_teams import TRAINER_TEAMS
from knowledge.readiness import assess
from knowledge.team import (GYM_COUNTERS, HM_NEEDS, coverage, gaps, hm_candidates, hm_status, next_gym_fit,
                            shared_weaknesses, team_report, wanted_species, where_to_find)
from knowledge.wild_locations import WILD_LOCATIONS

ID = {v: k for k, v in SPECIES_NAMES.items()}
BROCK, MISTY = ["Brock"], ["Brock", "Misty"]


def mon(name, moves=("Tackle",), level=20, hp=40):
    return P(species_id=ID[name], species_name=name, nickname="", level=level, move_names=list(moves),
             move_ids=[], max_hp=hp, current_hp=hp, status="healthy", pp=[10, 10, 10, 10])


IVY = lambda: mon("Ivysaur", ["Tackle", "Vine Whip", "Razor Leaf", "Growl"])        # noqa: E731
PIDGEY = lambda: mon("Pidgey", ["Gust", "Tackle"])                                   # noqa: E731


# ── the generated data ─────────────────────────────────────────────────────────────────────
def test_gym_and_e4_teams_come_from_the_decomp():
    assert [ID_ for ID_, _l, _m in TRAINER_TEAMS["Brock"]] == [ID["Geodude"], ID["Onix"]]
    assert TRAINER_TEAMS["Lt. Surge"][-1][:2] == (ID["Raichu"], 24)
    assert len(TRAINER_TEAMS) == 12


def test_every_counter_on_the_shortlist_really_exists_in_leafgreen():
    for leader, names in GYM_COUNTERS.items():
        assert leader in TRAINER_TEAMS
        for n in names:
            assert ID[n] in WILD_LOCATIONS, (leader, n)       # a hunt hint must never name something uncatchable


def test_where_to_find_reads_the_encounter_tables():
    assert where_to_find(ID["Diglett"]) == "Diglett's Cave B1F (grass L15-22)"
    assert "Route 4" in where_to_find(ID["Sandshrew"])
    assert where_to_find(ID["Eevee"]) == ""                   # gift only


# ── coverage / weaknesses / HMs ───────────────────────────────────────────────────────────────
def test_coverage_uses_the_moves_actually_known():
    cov = coverage([IVY()])
    assert {"WAT", "GRD", "ROC"} <= cov and "FIR" not in cov and "FLY" not in cov
    assert "FLY" in coverage([IVY(), mon("Pikachu", ["Thunder Shock"])])


def test_three_members_sharing_a_weakness_is_flagged():
    flyers = [PIDGEY(), mon("Spearow"), mon("Zubat")]
    assert ("ROC", 3) in shared_weaknesses(flyers) or ("ELE", 3) in shared_weaknesses(flyers)
    assert shared_weaknesses([IVY(), PIDGEY()]) == []


def test_hm_status_names_the_knower_and_the_capable():
    cutter = mon("Ivysaur", ["Cut", "Tackle"])
    assert hm_status([cutter, PIDGEY()], "Cut")[0] == "Ivysaur"
    knower, capable = hm_status([PIDGEY()], "Surf")
    assert knower is None and capable == []
    assert hm_status([PIDGEY()], "Fly")[1] == ["Pidgey"]
    cands = hm_candidates("Surf")
    assert cands and all(c in WILD_LOCATIONS for c in cands)


# ── the next gym ─────────────────────────────────────────────────────────────────────────────
def test_grass_answers_brock_but_not_surge():
    fit = next_gym_fit([IVY()], [])
    assert fit.leader == "Brock" and fit.answers and fit.covered == fit.total == 2
    fit = next_gym_fit([IVY(), PIDGEY()], MISTY)
    assert fit.leader == "Lt. Surge" and not fit.answers and fit.covered == 0
    assert fit.uncovered_species and "Raichu" in fit.uncovered_species
    assert next_gym_fit([IVY()], ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine", "Giovanni"]) is None


# ── hunt hints ───────────────────────────────────────────────────────────────────────────────
def test_the_surge_hint_names_a_ground_type_and_where_to_get_it():
    g = [x for x in gaps([IVY(), PIDGEY()], None, MISTY) if x.code == "gym"]
    assert len(g) == 1
    assert "Lt. Surge's gym (Electric)" in g[0].text and "Diglett — Diglett's Cave B1F" in g[0].text
    assert ID["Diglett"] in g[0].species


def test_a_counter_already_in_the_pc_is_swapped_in_not_hunted():
    box = [{"species_id": ID["Diglett"], "species_name": "Diglett", "box": 0, "slot": 7}]
    g = [x for x in gaps([IVY(), PIDGEY()], box, MISTY) if x.code == "gym"][0]
    assert "pc_swap" in g.text and "1:7" in g.text and "Diglett's Cave" not in g.text


def test_no_gym_hint_when_the_team_already_answers_it():
    assert [x for x in gaps([IVY()], None, []) if x.code == "gym"] == []             # Brock is answered


def test_surf_is_only_a_gap_once_the_story_needs_it_and_nobody_can_carry_it():
    four = ["Brock", "Misty", "Lt. Surge", "Erika"]
    assert HM_NEEDS["Surf"][0] == 4
    early = [x for x in gaps([IVY(), PIDGEY()], None, MISTY) if x.code == "hm"]
    assert not [x for x in early if "Surf" in x.text]
    late = [x for x in gaps([IVY(), PIDGEY()], None, four) if x.code == "hm"]
    assert any("Surf" in x.text and "catch one that can" in x.text for x in late)
    with_surfer = [mon("Squirtle", ["Tackle"]), IVY()]
    assert not [x for x in gaps(with_surfer, None, four) if "Surf" in x.text]


# ── catch policy + readiness + report ────────────────────────────────────────────────────────────────
def test_filling_a_gap_makes_a_catch_worthwhile_even_for_a_weak_line():
    party = [mon("Ivysaur", level=24), mon("Pidgey", level=20)]
    plain = evaluate(party, ID["Diglett"], 18)
    wanted = wanted_species(party, None, MISTY)
    assert ID["Diglett"] in wanted
    v = evaluate(party, ID["Diglett"], 18, wanted=wanted)
    assert v.catch and v.reason.startswith("fills a team gap")
    assert v.debt <= PREMIUM_DEBT
    far = evaluate([mon("Ivysaur", level=60)], ID["Diglett"], 15, wanted=wanted)       # hopelessly under-levelled
    assert not far.catch
    full = [mon("Ivysaur", level=24)] + [mon("Pidgey", level=20)] * 5
    assert "pc_swap" in evaluate(full, ID["Diglett"], 18, wanted=wanted).reason
    assert plain.reason != v.reason


def test_readiness_carries_team_gaps_as_should_items():
    needs = assess([IVY(), PIDGEY()], balls=9, potions=9, money=0, gyms_beaten=MISTY)
    hunt = [n for n in needs if n.code == "hunt"]
    assert len(hunt) == 1 and hunt[0].level == "should" and "Diglett" in hunt[0].text


def test_team_report_is_a_readable_summary():
    out = team_report([IVY(), PIDGEY()], None, MISTY)
    assert out.startswith("Team (2):") and "Hits super effectively:" in out
    assert "Cut: Ivysaur can learn it" in out and "Surf: nobody can learn it" in out
    assert "Next: Lt. Surge (Electric)" in out and "NOT answered" in out and "Gap (gym)" in out
    assert team_report([], None, []) == "No party to analyse."
