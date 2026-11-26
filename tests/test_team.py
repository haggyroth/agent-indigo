"""Team composition (#207): coverage, weaknesses, HM carriers, gym fit and the NEEDS the team has — never which species to get (no emulator)."""
from types import SimpleNamespace as P

from game.constants import SPECIES_NAMES
from knowledge.catch_policy import evaluate
from knowledge.gym_teams import TRAINER_TEAMS
from knowledge.readiness import assess
from knowledge.team import HM_NEEDS, coverage, gaps, hm_status, next_gym_fit, shared_weaknesses, team_report

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
    assert len(TRAINER_TEAMS) == 15           # 8 leaders + 4 Elite Four + the Champion's three starter variants


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


# ── the next gym ─────────────────────────────────────────────────────────────────────────────
def test_grass_answers_brock_but_not_surge():
    fit = next_gym_fit([IVY()], [])
    assert fit.leader == "Brock" and fit.answers and fit.covered == fit.total == 2
    fit = next_gym_fit([IVY(), PIDGEY()], MISTY)
    assert fit.leader == "Lt. Surge" and not fit.answers and fit.covered == 0
    assert fit.uncovered_species and "Raichu" in fit.uncovered_species
    assert next_gym_fit([IVY()], ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine", "Giovanni"]) is None


# ── what the team lacks: a need, never a species ───────────────────────────────────────────────────
def test_the_surge_gap_states_the_need_and_names_no_pokemon_to_get():
    g = [x for x in gaps([IVY(), PIDGEY()], None, MISTY) if x.code == "gym"]
    assert len(g) == 1
    assert "Lt. Surge's gym (Electric)" in g[0].text and "hits only 0/" in g[0].text
    for fixed_pick in ("Diglett", "Sandshrew", "Geodude", "catch a counter", "Cave"):      # an earlier version told the model which counter to catch and where
        assert fixed_pick not in g[0].text, g[0].text
    assert not hasattr(g[0], "species")


def test_a_stored_pokemon_that_could_help_is_never_singled_out_for_a_gym():
    box = [{"species_id": ID["Diglett"], "species_name": "Diglett", "box": 0, "slot": 7}]
    g = [x for x in gaps([IVY(), PIDGEY()], box, MISTY) if x.code == "gym"][0]
    assert "Diglett" not in g.text and "pc('list', detail=true)" in g.text                  # it points at the model's own box, not at a pick


def test_no_gym_hint_when_the_team_already_answers_it():
    assert [x for x in gaps([IVY()], None, []) if x.code == "gym"] == []             # Brock is answered


def test_surf_is_only_a_gap_once_the_story_needs_it_and_nobody_can_carry_it():
    four = ["Brock", "Misty", "Lt. Surge", "Erika"]
    assert HM_NEEDS["Surf"][0] == 4
    early = [x for x in gaps([IVY(), PIDGEY()], None, MISTY) if x.code == "hm"]
    assert not [x for x in early if "Surf" in x.text]
    late = [x for x in gaps([IVY(), PIDGEY()], None, four) if x.code == "hm"]
    assert any("Surf" in x.text and "must join the team" in x.text for x in late)
    box = [{"species_id": ID["Squirtle"], "species_name": "Squirtle", "box": 0, "slot": 3}]
    stored = [x for x in gaps([IVY(), PIDGEY()], box, four) if "Surf" in x.text]
    assert stored and "in the PC that can: Squirtle (1:3)" in stored[0].text                  # what the model OWNS that can do it (a fact), not a species to go and get
    with_surfer = [mon("Squirtle", ["Tackle"]), IVY()]
    assert not [x for x in gaps(with_surfer, None, four) if "Surf" in x.text]


# ── catch policy + readiness + report ────────────────────────────────────────────────────────────────
def test_catch_policy_never_prefers_a_species_because_a_gym_needs_it():
    """The old `wanted` list made Diglett 'fill a team gap' for Surge whatever its quality; the verdict is now generic (line strength, type, upgrade) only."""
    import inspect
    assert "wanted" not in inspect.signature(evaluate).parameters
    party = [mon("Ivysaur", level=24), mon("Pidgey", level=20)]
    assert "fills a team gap" not in evaluate(party, ID["Diglett"], 18).reason


def test_readiness_carries_team_gaps_as_should_items():
    needs = assess([IVY(), PIDGEY()], balls=9, potions=9, money=0, gyms_beaten=MISTY)
    hunt = [n for n in needs if n.code == "hunt"]
    assert len(hunt) == 1 and hunt[0].level == "should" and "Lt. Surge" in hunt[0].text and "Diglett" not in hunt[0].text


def test_team_report_is_a_readable_summary():
    out = team_report([IVY(), PIDGEY()], None, MISTY)
    assert out.startswith("Team (2):") and "Hits super effectively:" in out
    assert "Cut: Ivysaur can learn it" in out and "Surf: nobody can learn it" in out
    assert "Next: Lt. Surge (Electric)" in out and "NOT answered" in out and "Gap (gym)" in out
    assert team_report([], None, []) == "No party to analyse."


def test_the_report_says_how_the_team_answers_each_elite_four_room():
    """After eight badges the report lists the Elite Four AND, per trainer, how many of their Pokémon the team hits super effectively (a run threw itself at the League blind)."""
    from knowledge.team import league_fits
    party = [mon("Pikachu", ["Thunder Shock", "Thunder"], 50), mon("Charizard", ["Flamethrower", "Rock Slide"], 52), mon("Machamp", ["Cross Chop", "Rock Slide"], 50)]
    fits = {f.leader: f for f in league_fits(party)}
    assert list(fits) == ["Lorelei", "Bruno", "Agatha", "Lance", "the Champion"] and all(f.total >= 4 for f in fits.values())
    assert fits["Lorelei"].covered >= 3                                  # Electric / Rock / Fighting against Water / Ice
    out = team_report(party, None, ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine", "Giovanni"])
    assert "Elite Four, in order (and how this team answers each)" in out and "→ your team hits" in out and "Lorelei" in out and "the Champion's Pokémon" in out


def test_the_league_observation_rooms_have_scouting_briefs():
    from knowledge.gym_advice import brief
    from knowledge.league_rooms import LEAGUE_ORDER, LEAGUE_ROOMS, LEAGUE_TRAINER
    assert set(LEAGUE_TRAINER) == set(LEAGUE_ROOMS) and list(LEAGUE_TRAINER.values()) == list(LEAGUE_ORDER)
    for name in LEAGUE_ORDER:
        assert brief(name).startswith(name + ":"), name                  # every room's trainer has a team brief to show


def test_the_boss_lead_is_the_best_matchup_not_just_the_highest_level():
    """Charizard (L54) leading Lorelei's Water / Ice team eats a super-effective hit on turn one and cannot answer it; Pikachu (L45, Thunder) hits most of her team for double."""
    from knowledge.party import boss_lead, boss_lead_vs
    zard = mon("Charizard", ["Flamethrower", "Slash"], 54)
    pika = mon("Pikachu", ["Thunder", "Thunder Shock"], 45)
    lapras = mon("Lapras", ["Surf", "Ice Beam"], 50)
    for m in (zard, pika, lapras):
        m.pp = [10, 10, 0, 0]
    party = [zard, pika, lapras]
    assert boss_lead(party) == 0                                         # the old rule: the strongest
    assert boss_lead_vs(party, "Lorelei") == 1                           # the matchup: Pikachu
    assert boss_lead_vs(party, "Brock") in (1, 2)                        # vs Rock / Ground: Water or Electric… not the Fire starter
    assert boss_lead_vs(party, "Nobody") == boss_lead(party)             # no team data: the old rule
    pika.current_hp = 0
    assert boss_lead_vs(party, "Lorelei") in (0, 2)                      # a fainted Pokémon never leads
    assert boss_lead_vs([], "Lorelei") is None


def test_a_status_only_pokemon_never_leads():
    from knowledge.party import boss_lead_vs
    growl = mon("Pikachu", ["Growl", "Tail Whip"], 60)
    growl.pp = [10, 10, 0, 0]
    solid = mon("Charizard", ["Flamethrower"], 40)
    solid.pp = [10, 0, 0, 0]
    assert boss_lead_vs([growl, solid], "Lorelei") == 1
