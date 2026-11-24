"""grind() rework (#203): fixed floor, benched ace, level-fit routes, encounter hand-off, stop-loss (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from game.constants import Addr
from game.state import GameContext, PokemonStatus
from knowledge.grind_routes import best_grass, is_misfit, route_fit
from knowledge.party import ace_index, ace_runaway, grind_floor, lagging_mons, pick_finisher


def mon(level, sid=1, hp=40, name="Mon"):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=40, status="healthy", species_id=sid,
                         species_name=f"{name}{sid}", nickname=f"{name}{sid}")


# ── pure helpers ──────────────────────────────────────────────────────────────────────
def test_floor_is_fixed_by_the_starting_top_and_capped_by_the_next_gym():
    assert grind_floor(38) == 31
    assert grind_floor(38, gym_target=20) == 20            # nobody needs to out-level the next gym
    assert grind_floor(30, balance=False) == 23            # target mode: target − 7


def test_lagging_uses_a_fixed_floor_not_the_moving_top():
    party = [mon(40, 1), mon(25, 2), mon(30, 3)]
    assert [p.species_id for _, p in lagging_mons(party)] == [2, 3]          # moving rule: floor 33
    assert [p.species_id for _, p in lagging_mons(party, floor=25)] == []      # fixed floor 25: balanced


def test_pick_finisher_keeps_the_ace_out_unless_nobody_else_is_fit():
    party = [mon(8, 1), mon(30, 2), mon(9, 3)]
    assert pick_finisher(party, 0, foe_level=10) == 1                         # only the ace is capable…
    assert pick_finisher(party, 0, foe_level=10, bench=(1,)) == 2             # …but it is benched
    hurt = [mon(8, 1), mon(30, 2), mon(9, 3, hp=1)]
    assert pick_finisher(hurt, 0, foe_level=10, bench=(1,)) == 1              # nobody else fit: ace as a last resort


def test_ace_runaway_flags_a_grind_that_feeds_the_ace():
    start = {1: 30, 2: 8}
    assert ace_runaway(start, [mon(34, 1), mon(8, 2)], battles=25) != ""
    assert ace_runaway(start, [mon(34, 1), mon(8, 2)], battles=10) == ""      # too early to judge
    assert ace_runaway(start, [mon(31, 1), mon(15, 2)], battles=25) == ""     # the trainee is moving
    assert ace_index([mon(8, 1), mon(30, 2, hp=0), mon(12, 3)]) == 2


def test_route_fit_prefers_wild_levels_near_the_trainee():
    route22, route25 = (3, 22), (3, 25)                  # avg L9.4 vs L19.0
    assert route_fit(route22, 8) < route_fit(route25, 8)
    assert is_misfit(route25, 8) and not is_misfit(route22, 8)
    assert is_misfit((3, 19), 25)                         # Route 1 is far too cold for a L25
    assert best_grass((3, 2), 8)[0] != route25            # never the L17-22 route for a L8
    assert best_grass((3, 2), 0) is not None              # no level → plain nearest grass


# ── the session ──────────────────────────────────────────────────────────────────────
class FakeWorld:
    def __init__(self, party, ctx=GameContext.OVERWORLD, trainer=False, foe_level=6):
        self.party, self.ctx, self.trainer = party, ctx, trainer
        self.foe = NS(species_id=19, species_name="RATTATA", level=foe_level, current_hp=14, max_hp=14)

    # reader + mgba surface used by the grind loop
    def read_party(self): return self.party
    def detect_context(self): return self.ctx
    def read32(self, addr): return Addr.BATTLE_TYPE_TRAINER if (addr == Addr.BATTLE_TYPE_FLAGS and self.trainer) else 0
    def read_enemy_lead(self): return self.foe
    def read_current_map(self): return (3, 22)
    def read_active_battle_species(self): return self.party[0].species_id
    def read_player_pos(self): return (5, 5)
    def tap(self, *_): pass
    def tick(self, *_): pass


ALL_GYMS = ["Brock", "Misty", "Lt. Surge", "Erika", "Koga", "Sabrina", "Blaine", "Giovanni"]   # no gym cap on the floor


def grind_client(world, gyms=ALL_GYMS):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = c.mgba = world
    c.ltm = NS(data={"gyms_beaten": list(gyms)})
    c._nearest_grass = lambda: (5, 5)
    c._relocate_to_grass = lambda **kw: True
    c._ball_count = lambda: 0
    c._grass_step = lambda st, again: None
    c._restock = lambda why: None
    c._lead_trainee = lambda t: True
    c._restore_ace_lead = lambda: None
    c._close_menus = lambda: None
    c._training_swapped = False
    c._grind_run = None
    return c


def test_wild_encounter_ends_the_call_and_the_session_persists():
    w = FakeWorld([mon(8, 1, name="Rat"), mon(30, 2, name="Ace")], ctx=GameContext.IN_BATTLE)
    c = grind_client(w)
    fought = []
    c._auto_fight = lambda: fought.append(1)
    c._train_fight = lambda sig: fought.append(2)
    out = c._grind(0, True, 0)
    assert "wild RATTATA L6" in out and "Keep Ace2 OUT" in out and "grind()" in out
    assert fought == [] and c._grind_run["battles"] == 1 and c._grind_run["floor"] == 23
    again = c._grind(0, True, 0)                       # calling grind AGAIN while that battle is still going: refused, not recounted
    assert "still going" in again and c._grind_run["battles"] == 1 and fought == [] and c._grind_run["floor"] == 23
    w.ctx = GameContext.OVERWORLD
    seen = []
    c._restock = lambda why: seen.append(c._grind_run["yielded"]) or "stop here"            # the battle is over: the session resumes
    assert c._grind(0, True, 0) == "stop here" and seen == [False]


def test_the_floor_does_not_follow_the_ace_up():
    w = FakeWorld([mon(8, 1), mon(30, 2)], ctx=GameContext.IN_BATTLE)
    c = grind_client(w)
    c._grind(0, True, 0)
    w.party = [mon(8, 1), mon(37, 2)]                  # the ace levelled a lot
    assert c._grind_run["floor"] == 23                 # moving rule would now say 30
    assert [p.species_id for _, p in c._lagging_mons(w.party)] == [1]


def test_balanced_party_reports_the_floor_and_starts_no_session():
    w = FakeWorld([mon(25, 1), mon(30, 2)])
    c = grind_client(w)
    out = c._grind(0, True, 0)
    assert "balanced" in out and "L23" in out and c._grind_run is None


def test_auto_battles_plays_only_boring_fights_itself():
    w = FakeWorld([mon(8, 1), mon(30, 2)], ctx=GameContext.IN_BATTLE, foe_level=7)
    c = grind_client(w)
    fights = []

    def train(sig):                                    # the fight ends and the trainee jumps to the floor
        fights.append(sig)
        w.ctx = GameContext.OVERWORLD
        w.party = [mon(25, 1), mon(30, 2)]
    c._train_fight = train
    out = c._grind(0, True, 3)
    assert len(fights) == 1 and out.startswith("Party balanced") and c._grind_run is None

    w2 = FakeWorld([mon(8, 1), mon(30, 2)], ctx=GameContext.IN_BATTLE, foe_level=15)   # too strong to autopilot
    c2 = grind_client(w2)
    c2._train_fight = lambda sig: pytest.fail("should have been handed to the model")
    assert "wild RATTATA L15" in c2._grind(0, True, 3)


def test_a_balancing_grind_autopilots_boring_fights_by_default():
    """Watched run: every L13 Spearow cost ~30 s / 60k tokens of LLM turns, so the trainees crawled while the ace out-levelled them
    2x. grind() with no auto_battles now autopilots (a balancing session only); an explicit 0 still means 'I play every one'."""
    def trainee_world():
        return FakeWorld([mon(8, 1), mon(30, 2)], ctx=GameContext.IN_BATTLE, foe_level=7)
    w = trainee_world()
    c = grind_client(w)
    fights = []

    def train(sig):
        fights.append(sig)
        w.ctx = GameContext.OVERWORLD
        w.party = [mon(25, 1), mon(30, 2)]
    c._train_fight = train
    assert c._grind(0, True, None).startswith("Party balanced") and len(fights) == 1      # omitted → autopilot
    w0 = trainee_world()
    c0 = grind_client(w0)
    c0._train_fight = lambda sig: pytest.fail("an explicit 0 means the model plays it")
    assert "wild RATTATA L7" in c0._grind(0, True, 0)
    w1 = trainee_world()
    c1 = grind_client(w1)
    c1._train_fight = lambda sig: pytest.fail("a level-target grind stays model-driven unless asked")
    assert "wild RATTATA L7" in c1._grind(40, True, None)


def test_worth_a_ball_is_never_autopiloted_and_is_pointed_out():
    w = FakeWorld([mon(8, 1), mon(30, 2)], ctx=GameContext.IN_BATTLE, foe_level=7)
    w.foe = NS(species_id=25, species_name="PIKACHU", level=7, current_hp=14, max_hp=14)   # a new type
    w.read_dex_owned = lambda sid: False
    c = grind_client(w)
    c._ball_count = lambda: 5
    c._train_fight = lambda sig: pytest.fail("a catch-worthy foe must go to the model")
    out = c._grind(0, True, 3)
    assert "Worth a ball" in out and "5 Poké Balls" in out


def test_trainer_battles_are_always_handed_over():
    w = FakeWorld([mon(8, 1), mon(30, 2)], ctx=GameContext.IN_BATTLE, trainer=True)
    c = grind_client(w)
    c._train_fight = lambda sig: pytest.fail("trainers go to the model")
    assert "TRAINER battle" in c._grind(0, True, 5)


def test_session_stops_when_the_grind_is_feeding_the_ace():
    w = FakeWorld([mon(8, 1), mon(30, 2)])
    c = grind_client(w)
    c._grind_run = None
    c._grind_inner  # noqa: B018  (session is created by the first call; seed it, then let the ace run away)
    w.ctx = GameContext.IN_BATTLE
    c._grind(0, True, 0)                                # creates the session (floor 23)
    c._grind_run["battles"] = 25
    w.ctx = GameContext.OVERWORLD
    w.party = [mon(8, 1), mon(34, 2)]
    out = c._grind(0, True, 0)
    assert out.startswith("Grinding stopped") and "feeding the ace" in out and c._grind_run is None


def test_abandoning_a_session_drops_it_and_restores_the_ace_in_the_overworld():
    w = FakeWorld([mon(8, 1), mon(30, 2)])
    c = grind_client(w)
    c._grind_run = {"floor": 23}
    c._training_swapped = True
    restored = []
    c._restore_ace_lead = lambda: restored.append(1)
    c._grind_abandon()
    assert c._grind_run is None and restored == [1] and c._training_swapped is False


# ── findings from a watched run: gated grass, the lead's moves, a fragile lead, grind() mid-battle ──
def test_grass_behind_the_pewter_gate_is_never_chosen_without_the_badge():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    badges = {"n": 0}
    c.reader = NS(read_player_pos=lambda: (5, 5), read_badges=lambda: (badges["n"], (1 << badges["n"]) - 1),
                  read_key_items=lambda: [], read_flag=lambda f: False)
    assert c._grass_route_gated((3, 1), (3, 22)) and c._grass_route_gated((3, 1), (3, 21))     # Viridian → Route 3 / 4: Brock first
    assert not c._grass_route_gated((3, 1), (3, 20))                                           # Route 2 is open
    badges["n"] = 1
    assert not c._grass_route_gated((3, 1), (3, 22))


def test_the_yield_text_lists_the_active_pokemons_moves():
    w = FakeWorld([mon(8, 1, name="Rat"), mon(30, 2, name="Ace")], ctx=GameContext.IN_BATTLE)
    w.party[0].move_names = ["Scratch", "Leer", "", ""]
    c = grind_client(w)
    out = c._grind(0, True, 0)
    assert "Rat1 knows: Scratch, Leer." in out


def test_a_nearly_fainted_lead_is_told_to_switch_to_a_fit_teammate():
    from knowledge.party import low_hp_switch_hint
    party = [mon(3, 1, hp=3, name="Mankey"), mon(9, 2, hp=30, name="Bulba")]
    hint = low_hp_switch_hint(party, 0, cur=3, mx=16, foe_level=4)
    assert "Mankey1 is at 3/16" in hint and "switch_pokemon('Bulba2')" in hint
    assert low_hp_switch_hint(party, 0, cur=12, mx=16, foe_level=4) == ""                      # healthy enough: no nag
    assert low_hp_switch_hint([mon(3, 1, hp=3)], 0, cur=3, mx=16) == ""                        # nobody to switch to
    assert low_hp_switch_hint(party, 0, cur=0, mx=16) == ""                                    # already fainted


def test_a_level_target_grind_is_refused_when_no_open_grass_gives_xp(monkeypatch):
    """Watched run: grind(42) at L38 spent ~700 s on Route 7/8 (wild L17-22): the ace gained nothing. Refused up front now."""
    w = FakeWorld([mon(32, 1), mon(38, 2)])
    c = grind_client(w)
    w.read_current_map = lambda: (3, 6)
    c._best_open_grass = lambda here, level, avoid=(): ((3, 26), [])            # Route 8: wild L18-22
    out = c._grind(42, True, None)
    assert "can't get your L38" in out and "Route 8" in out and c._grind_run is None
    c._best_open_grass = lambda here, level, avoid=(): ((3, 42), [])            # Route 23: wild L32-44 → worth it
    assert "can't get your" not in c._grind(42, True, None)


# ── a watched run: grind() walked into Cerulean's rival ambush again and again ──────────────────────────────────────────────────
def _cerulean_client(best_level, flags=(), party_levels=None):
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    levels = party_levels or [best_level, 8, 7]
    c.reader = NS(read_player_pos=lambda: (22, 20), read_badges=lambda: (1, 1), read_key_items=lambda: [265],
                  read_flag=lambda f: f in flags, read_current_map=lambda: (3, 3),
                  read_party=lambda: [NS(level=lv, current_hp=10, max_hp=10) for lv in levels])
    return c


def test_route_24_is_gated_by_the_rival_until_the_best_pokemon_is_21_or_the_scene_is_done():
    assert _cerulean_client(19)._grass_route_gated((3, 3), (3, 43))                  # the ace is L19: the rival (L18 starter, 4 Pokémon) would win again
    assert not _cerulean_client(21)._grass_route_gated((3, 3), (3, 43))
    assert not _cerulean_client(10, flags={0x29B})._grass_route_gated((3, 3), (3, 43))       # FLAG_GOT_FAME_CHECKER: the scene is over


def test_a_failed_grind_says_why_the_nearest_grass_was_skipped_once():
    c = _cerulean_client(19)
    assert c._grass_route_gated((3, 3), (3, 43))
    why = c._why_no_grass()
    assert "rival" in why and "L21" in why and "walk north yourself" in why
    assert c._why_no_grass() == ""                                                      # told once, not on every later message


def test_gate_ok_level_compares_the_best_party_member():
    from knowledge.gates import Req
    req = Req("level", 21, "x")
    assert not _cerulean_client(20)._gate_ok(req) and _cerulean_client(21)._gate_ok(req)
    assert _cerulean_client(5, flags={0x29B})._gate_ok(Req("level", 21, "x", alt_flag=0x29B))


def test_a_route_that_beat_us_is_skipped_until_we_are_three_levels_stronger(monkeypatch):
    import knowledge.grind_routes as gr
    seen = []
    monkeypatch.setattr(gr, "best_grass", lambda start, level, exclude_current=False, avoid=(), objective=None, fly_towns=(): seen.append(set(avoid)) or None)
    c = _cerulean_client(19)
    c._lost_goals = {(3, 43): 19}
    assert c._relocate_to_grass() is False
    assert (3, 43) in seen[-1]                                                          # still L19: not worth another loss
    c = _cerulean_client(22)
    c._lost_goals = {(3, 43): 19}
    c._relocate_to_grass()
    assert (3, 43) not in seen[-1]                                                      # 3 levels stronger: it may try again


def test_route_21_is_gated_behind_surf():
    """A watched run called grind(20) from Pallet and spent 14 x 100 game-minutes walking toward Route 21, which is open water."""
    from knowledge.gates import unmet_gates
    from knowledge.map_graph import route_to
    unmet = unmet_gates(route_to((3, 0), (3, 39)), lambda req: False)
    assert unmet and unmet[0][1].value == "Surf"
