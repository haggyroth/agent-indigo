"""Battle accounting (#210): real outcomes, real journal rows, stable Pokémon identity (no emulator)."""
from types import SimpleNamespace as NS

import pytest

from agent import events
from game.constants import Addr
from game.state import GameContext, GameState, PokemonStatus


@pytest.fixture(autouse=True)
def _clean():
    events.reset()
    yield
    events.reset()


def mon(pid, species=1, level=5, hp=20, name="M", moves=("Tackle",)):
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=20, status="healthy", species_id=species,
                         species_name=name, nickname=name, personality=pid, move_names=list(moves))


# ── the end-of-battle hook ──────────────────────────────────────────────────────────────────
class R:
    def __init__(self, party, ctx=GameContext.OVERWORLD, foe=None, outcome=0, trainer=False):
        self.party, self.ctx, self.foe, self.outcome, self.trainer = party, ctx, foe, outcome, trainer
        self.settled = True
        self.client = NS(read32=self._r32, read8=lambda a: self.outcome if a == Addr.BATTLE_OUTCOME else 0)

    def _r32(self, a):
        if a == Addr.BATTLE_TYPE_FLAGS:
            return Addr.BATTLE_TYPE_TRAINER if self.trainer else 0
        return Addr.CTRL_CHOOSE_ACTION if a == Addr.BATTLE_CTRL_FUNC and self.settled else 0

    def read_party(self): return self.party
    def detect_context(self): return self.ctx
    def read_badges(self): return 0, 0
    def read_enemy_lead(self): return self.foe
    def read_current_map(self): return (3, 19)
    def read_active_battle_species(self): return self.party[0].species_id


FOE = NS(species_id=19, species_name="RATTATA", level=4, current_hp=14, max_hp=14)


def fight(outcome, moves=("Tackle", "Tackle", "Growl"), trainer=False, party=None, ends_party=None):
    r = R(party or [mon(1, name="Bulby", hp=20)], ctx=GameContext.IN_BATTLE, foe=FOE, outcome=outcome, trainer=trainer)
    events.observe(r)
    for m in moves:
        events.note_move(m)
    r.ctx = GameContext.OVERWORLD
    if ends_party is not None:
        r.party = ends_party
    events.observe(r)


def test_hook_fires_once_per_battle_with_turns_moves_foe_and_outcome():
    seen = []
    events.on_battle_end(seen.append)
    fight(Addr.B_OUTCOME_WON)
    assert len(seen) == 1
    s = seen[0]
    assert (s["outcome"], s["foe_name"], s["foe_level"], s["turns"], s["moves"], s["trainer"]) == \
        ("won", "RATTATA", 4, 3, ["Tackle", "Growl"], False)
    assert s["lead"] == "Bulby" and s["where"] == "Route 1" and s["hp_pct"] == 1.0


def test_a_failing_hook_never_breaks_the_stream_and_unseen_battles_still_book():
    calls = []
    events.on_battle_end(lambda s: 1 / 0)
    events.on_battle_end(calls.append)
    r = R([mon(1)], ctx=GameContext.IN_BATTLE, foe=FOE, outcome=Addr.B_OUTCOME_RAN)
    r.settled = False                                        # never reached the menu: fled in one tool call
    events.observe(r)
    r.ctx = GameContext.OVERWORLD
    events.observe(r)
    assert len(calls) == 1 and calls[0]["outcome"] == "fled" and calls[0]["announced"] is False


# ── _record_battle (main) ───────────────────────────────────────────────────────────────────
@pytest.fixture
def book():
    pytest.importorskip("openai")
    import main
    ltm = NS(data={"total_battles": 0, "battles_won": 0, "battles_lost": 0, "battles_fled": 0, "battles_caught": 0,
                   "pokemon_caught": 0}, save=lambda: None)
    rows = []
    journal = NS(log=rows.append)
    run = main._RunState()
    run.prev_dex_owned = 10
    dex = {"owned": 10}
    reader = NS(read_pokedex=lambda: (dex["owned"], 20))

    def record(summary):
        main._last_ltm_save = 0.0
        main._record_battle(summary, run, reader, ltm, journal)
    return NS(record=record, ltm=ltm, rows=rows, dex=dex, run=run)


def summary(outcome, trainer=False, **kw):
    s = {"outcome": outcome, "trainer": trainer, "foe_name": "Rattata", "foe_level": 4, "where": "Route 1", "turns": 3,
         "moves": ["Tackle", "Growl"], "lead": "Bulby", "active": "Bulby", "hp_pct": 0.5, "wiped": False,
         "announced": True}
    s.update(kw)
    return s


def test_only_a_real_win_counts_as_a_win(book):
    book.record(summary("won"))
    book.record(summary("fled"))
    book.record(summary("caught"))
    book.record(summary("lost", wiped=True))
    d = book.ltm.data
    assert (d["total_battles"], d["battles_won"], d["battles_fled"], d["battles_caught"], d["battles_lost"]) == (4, 1, 1, 1, 1)


def test_journal_rows_carry_real_data(book):
    book.record(summary("won", trainer=True))
    row = book.rows[0]
    assert (row.enemy_name, row.enemy_level, row.turns, row.moves_used, row.outcome) == \
        ("RATTATA", 4, 3, ["Tackle", "Growl"], "win")
    assert row.player_lead == "Bulby" and row.hp_remaining_pct == 0.5
    assert "trainer Rattata" in row.notes
    book.record(summary("lost", trainer=True, wiped=True))
    assert book.rows[1].outcome == "loss" and "whole party fainted" in book.rows[1].notes


def test_pokemon_caught_counts_catches_and_tracks_the_dex_baseline(book):
    book.record(summary("caught"))                          # a duplicate species: dex unchanged
    assert book.ltm.data["pokemon_caught"] == 1
    book.dex["owned"] = 11                                  # a new species
    book.record(summary("caught"))
    assert book.ltm.data["pokemon_caught"] == 2 and book.run.prev_dex_owned == 11


def test_old_journal_rows_with_a_reward_field_still_load(tmp_path):
    import json
    from memory.battle_journal import BattleJournal
    path = tmp_path / "battles.jsonl"
    path.write_text(json.dumps(dict(timestamp="t", location="Pewter", enemy_name="BROCK", enemy_level=14,
                                    player_lead="Bulbasaur", outcome="loss", turns=3, moves_used=["Tackle"],
                                    hp_remaining_pct=0.0, reward=-1.0, notes="fainted")) + "\n")
    assert "Past losses against BROCK" in BattleJournal(path).get_loss_lessons("BROCK")


# ── identity instead of slot index ───────────────────────────────────────────────────────────────
def test_faints_are_tracked_per_pokemon_not_per_slot():
    class Rd:
        def __init__(self, party): self.party = party
        def read_party(self): return self.party
        def read_badges(self): return 0, 0
        def detect_context(self): return GameContext.OVERWORLD
    a, b = mon(1, name="A", hp=20), mon(2, name="B", hp=20)
    r = Rd([a, b])
    events.observe(r)
    r.party = [mon(2, name="B", hp=0), mon(1, name="A", hp=20)]       # B fainted AND the party was reordered
    events.observe(r)
    assert [e["text"] for e in events.recent("faint")] == ["B fainted"]
    assert events.run_stats()["faints"] == 1


def state(party):
    return GameState(context=GameContext.OVERWORLD, badges=0, badge_bits=0, party=party, party_count=len(party),
                     map_bank=3, map_id=0, player_x=0, player_y=0, screen_fading=False)


def test_diff_pairs_by_personality_through_reorders_and_evolution():
    from game.memory_reader import LeafGreenReader
    r = LeafGreenReader.__new__(LeafGreenReader)
    before = state([mon(1, 4, 15, name="Charmander"), mon(2, 19, 5, name="Rattata")])
    swapped = state([mon(2, 19, 5, name="Rattata"), mon(1, 4, 15, name="Charmander")])
    assert r.diff(before, swapped).level_changed == []                    # a reorder is not 2 level-ups
    evolved = state([mon(1, 5, 16, name="Charmeleon"), mon(2, 19, 5, name="Rattata")])
    d = r.diff(before, evolved)
    assert d.level_changed == [0]                                          # same Pokémon despite the new species id
    joined = state([mon(1, 4, 15), mon(2, 19, 5), mon(3, 4, 15, name="Charmander")])
    assert r.diff(before, joined).level_changed == []                      # a second Charmander is not Charmander levelling


def test_use_move_notes_the_move_for_the_battle_summary():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    r = R([mon(1)], ctx=GameContext.IN_BATTLE, foe=FOE, outcome=Addr.B_OUTCOME_WON)
    c = AgentClient.__new__(AgentClient)
    c.reader = r
    replies = iter(["Used Vine Whip. [foe RATTATA 5/14]", "Used Tackle (battle ended).", "'Foo' is not a known move."])
    c._use_move_inner = lambda name: next(replies)
    seen = []
    events.on_battle_end(seen.append)
    for n in ("Vine Whip", "Tackle", "Foo"):
        c._use_move(n)
    r.ctx = GameContext.OVERWORLD
    events.observe(r)
    assert seen[0]["moves"] == ["Vine Whip", "Tackle"] and seen[0]["turns"] == 2       # a refused move is no turn
