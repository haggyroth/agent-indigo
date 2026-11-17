"""The game-event stream (#209): tool lines, snapshot-diff events, battle start/end, verbosity (no emulator)."""
import io
from types import SimpleNamespace as NS

import pytest

from agent import events
from game.constants import Addr
from game.state import GameContext, PokemonStatus


@pytest.fixture(autouse=True)
def _clean():
    events.reset()
    yield
    events.reset()


def mon(pid=1, species=1, name="Bulby", level=5, hp=20, mx=20, moves=("Tackle",)):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=mx, status="healthy", species_id=species,
                         species_name=name, nickname=name, personality=pid, move_names=list(moves))


class FakeReader:
    def __init__(self, party, ctx=GameContext.OVERWORLD, badges=0, trainer=False, foe=None, outcome=0):
        self.party, self.ctx, self.bits, self.trainer, self.foe, self.outcome = party, ctx, badges, trainer, foe, outcome
        self.settled = True
        self.client = NS(read32=self._read32, read8=lambda a: self.outcome if a == Addr.BATTLE_OUTCOME else 0)

    def _read32(self, a):
        if a == Addr.BATTLE_TYPE_FLAGS:
            return Addr.BATTLE_TYPE_TRAINER if self.trainer else 0
        if a == Addr.BATTLE_CTRL_FUNC:
            return Addr.CTRL_CHOOSE_ACTION if self.settled else 0
        return 0

    def read_party(self): return self.party
    def detect_context(self): return self.ctx
    def read_badges(self): return bin(self.bits).count("1"), self.bits
    def read_enemy_lead(self): return self.foe
    def read_current_map(self): return (3, 19)


def texts(kind=None):
    return [e["text"] for e in events.recent(kind)]


def test_tool_line_has_compact_args_a_one_line_result_and_slow_timing():
    rec = events.tool("use_move", '{"move": "Tackle"}', "Used Tackle.\n [foe RATTATA 5/14]", 2.4)
    assert rec["text"] == "use_move(move='Tackle') → Used Tackle. [foe RATTATA 5/14]  (2.4s)"
    long = events.tool("go_to", '{"destination": "Pewter City", "force": false}', "x" * 400, 0.2)["text"]
    assert long.startswith("go_to(destination='Pewter City') → ") and long.endswith("…") and len(long) < 230
    assert events.tool("heal", "", "ok", 0.1)["text"] == "heal() → ok"
    assert events.tool("x", "{not json", "ok", 0)["text"].startswith("x({not json")


def test_party_changes_become_levelups_evolutions_faints_and_new_moves():
    r = FakeReader([mon(1, 4, "Charmander", 15), mon(2, 19, "Rattata", 5, hp=10)])
    events.observe(r)                                           # first snapshot: nothing to report
    assert events.recent() == []
    r.party = [mon(1, 5, "Charmeleon", 16, moves=("Scratch", "Ember")), mon(2, 19, "Rattata", 5, hp=0)]
    events.observe(r)
    assert texts("evolve") == ["Charmander evolved into Charmeleon!"]
    assert texts("level_up") == ["Charmeleon reached L16"]
    assert texts("faint") == ["Rattata fainted"]
    assert sorted(texts("learn_move")) == ["Charmeleon learned Ember", "Charmeleon learned Scratch"]


def test_reordering_the_party_is_not_an_event_and_garbage_frames_are_ignored():
    a, b = mon(1, 1, "A", 10), mon(2, 19, "B", 7)
    r = FakeReader([a, b])
    events.observe(r)
    r.party = [b, a]
    events.observe(r)
    assert events.recent() == []
    r.party = [mon(1, 600, "Glitch", 90, mx=0), b]              # a battle-load frame: not a real party
    events.observe(r)
    r.party = [mon(1, 1, "A", 11), b]                           # …and the next real read is a clean +1
    events.observe(r)
    assert texts("level_up") == ["A reached L11"] and texts("faint") == []


def test_new_badge_names_the_leader():
    r = FakeReader([mon()])
    events.observe(r)
    r.bits = 0b1
    events.observe(r)
    assert texts("badge") == ["Boulder Badge #1 — beat Brock!"]


def test_battle_start_and_end_are_classified_from_the_outcome_byte():
    foe = NS(species_id=19, species_name="RATTATA", level=4, current_hp=14, max_hp=14)
    r = FakeReader([mon()], ctx=GameContext.IN_BATTLE, foe=foe)
    events.observe(r)
    assert texts("battle_start") == ["wild RATTATA L4 @ Route 1"]
    r.ctx, r.outcome = GameContext.OVERWORLD, Addr.B_OUTCOME_RAN
    events.observe(r)
    assert texts("battle_end") == ["fled vs RATTATA L4"]
    for code, word in ((Addr.B_OUTCOME_WON, "won"), (Addr.B_OUTCOME_CAUGHT, "caught"), (Addr.B_OUTCOME_LOST, "lost")):
        events.reset()
        r.ctx, r.outcome = GameContext.IN_BATTLE, code
        events.observe(r)
        r.ctx = GameContext.OVERWORLD
        events.observe(r)
        assert texts("battle_end") == [f"{word} vs RATTATA L4"]


def test_a_wiped_party_is_a_loss_whatever_the_byte_says_and_trainers_are_labelled():
    foe = NS(species_id=74, species_name="GEODUDE", level=12, current_hp=30, max_hp=30)
    r = FakeReader([mon(hp=20)], ctx=GameContext.IN_BATTLE, foe=foe, trainer=True)
    events.observe(r)
    assert texts("battle_start") == ["trainer battle GEODUDE L12 @ Route 1"]
    r.party, r.ctx, r.outcome = [mon(hp=0)], GameContext.OVERWORLD, Addr.B_OUTCOME_WON
    events.observe(r)
    assert texts("battle_end") == ["lost vs GEODUDE L12"]


def test_observe_never_raises_and_tolerates_no_reader():
    events.observe(None)
    events.observe(NS())                                        # a reader missing every method


def test_verbosity_levels_and_escaping():
    pytest.importorskip("rich")
    from rich.console import Console
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=False, width=200)
    events.configure(con, None, "quiet")
    events.emit("tool", "use_move(move='Tackle') → ok", major=False)
    events.emit("catch", "CAUGHT Rattata L4 [bold]odd[/] markup")
    out = buf.getvalue()
    assert "CAUGHT Rattata L4 [bold]odd[/] markup" in out and "use_move" not in out
    events.configure(con, None, "events")
    events.emit("tool", "heal() → ok", major=False)
    events.emit("note", "OBS: ...", debug=True)
    out = buf.getvalue()
    assert "heal() → ok" in out and "OBS: ..." not in out
    events.configure(con, None, "debug")
    events.emit("note", "OBS: ...", debug=True)
    assert "OBS: ..." in buf.getvalue()


def test_run_log_gets_a_structured_record():
    class RL:
        def __init__(self): self.rows = []
        def event(self, kind, **f): self.rows.append((kind, f))
    rl = RL()
    events.configure(None, rl, "events")
    events.emit("heal", "party healed")
    events.tool("heal", "{}", "ok", 0.1)                         # tool events keep their own richer record
    assert rl.rows == [("ev", {"ev": "heal", "text": "party healed"})]


def test_the_foe_is_only_announced_once_the_menu_is_up_and_an_unseen_battle_still_gets_an_end_line():
    stale = NS(species_id=10, species_name="CATERPIE", level=3, current_hp=0, max_hp=18)
    r = FakeReader([mon()], ctx=GameContext.IN_BATTLE, foe=stale)
    r.settled = False                                          # intro: the foe slot still holds the previous foe
    events.observe(r)
    assert events.recent("battle_start") == []
    r.foe = NS(species_id=13, species_name="WEEDLE", level=5, current_hp=20, max_hp=20)
    r.settled = True
    events.observe(r)
    assert texts("battle_start") == ["wild WEEDLE L5 @ Route 1"]
    events.reset()
    r2 = FakeReader([mon()], ctx=GameContext.IN_BATTLE, foe=stale)
    r2.settled = False
    events.observe(r2)
    r2.ctx, r2.outcome = GameContext.OVERWORLD, Addr.B_OUTCOME_RAN
    events.observe(r2)
    assert texts("battle_end") == ["wild battle fled"]
