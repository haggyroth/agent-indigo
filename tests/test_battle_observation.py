"""The battle observation carries the party-vs-foe roster, the switch tip and the low-HP advice (#246) — no emulator."""
from types import SimpleNamespace

import pytest

pytest.importorskip("openai")

from agent.observation import Tick, _battle                      # noqa: E402
from game.state import PokemonStatus                              # noqa: E402


def mon(species, sid, hp, mx, moves, stats, nick="", level=10):
    names = list(moves) + [""] * (4 - len(moves))
    return PokemonStatus(slot=0, level=level, current_hp=hp, max_hp=mx, status="healthy", species_id=sid, species_name=species,
                         nickname=nick, move_names=names, pp=[20 if n else 0 for n in names], stats=stats)


class FakeReader:
    """Just enough of LeafGreenReader for _battle: Kakuna (14) is out against a Raticate (L20), Potions in the bag."""
    def __init__(self, active=14):
        self.client = SimpleNamespace(read32=lambda a: 0, read8=lambda a: 0)
        self.active = active

    def read_active_battle_species(self): return self.active
    def read_active_battle_usable_pp(self): return [0] * 4, ["Poison Sting", "Harden", "", ""], [20, 20, 0, 0], None, 0
    def read_enemy_lead(self):
        return PokemonStatus(slot=0, level=20, current_hp=40, max_hp=40, status="healthy", species_id=20, species_name="RATICATE")
    def read_foe_battler(self): return {"moves": ("Tackle",), "attack": 40, "sp_attack": 30, "speed": 40, "ability": 0}
    def read_items_pocket(self): return [(13, 3), (22, 1)]                 # 3 Potions, 1 Super Potion
    def read_battle_volatiles(self, _b=0): return {}
    def read_dex_owned(self, _sid): return False
    def read_bag(self): return {4: 0}                                       # no Poké Balls: no catch advice to build


def tick(party, active=14):
    run = SimpleNamespace(current_enemy="RATICATE", battle_is_trainer=False, battle_started=True)
    stm = SimpleNamespace(action_history=[])
    return Tick(state=SimpleNamespace(party=party), diff=None, in_battle=True, run=run, reader=FakeReader(active),
                tilemap=None, ltm=SimpleNamespace(data={}), stm=stm, map_key=(0, 0))


def test_the_battle_observation_has_the_roster_and_low_hp_advice():
    ivy = mon("IVYSAUR", 2, 0, 50, ["Vine Whip"], (50, 20, 20, 20, 20, 20), level=16)
    kak = mon("KAKUNA", 14, 6, 25, ["Poison Sting", "Harden"], (25, 8, 12, 5, 6, 6), nick="Sir Wiggle", level=8)
    pid = mon("PIDGEY", 16, 22, 22, ["Gust", "Tackle"], (22, 10, 30, 20, 8, 25), nick="Sky High", level=6)
    text = " | ".join(_battle(tick([ivy, kak, pid])))
    assert "Party vs Raticate [Normal]" in text and "1 Ivysaur FAINTED" in text
    assert "2 Sir Wiggle(Kakuna) ACTIVE 6/25" in text and "3 Sky High(Pidgey) 22/22" in text
    assert "Low HP: Sir Wiggle(Kakuna) 6/25" in text and "enough to KO it" in text
    assert "switch_pokemon('Sky High')" in text and "use_item('Super Potion')" in text and "flee_battle()" in text   # wild: may flee


def test_a_healthy_active_mon_gets_no_low_hp_line():
    kak = mon("KAKUNA", 14, 25, 25, ["Poison Sting", "Harden"], (25, 8, 12, 5, 6, 6), nick="Sir Wiggle", level=8)
    pid = mon("PIDGEY", 16, 22, 22, ["Gust"], (22, 10, 30, 20, 8, 25), level=6)
    text = " | ".join(_battle(tick([kak, pid])))
    assert "Party vs Raticate" in text and "Low HP" not in text
