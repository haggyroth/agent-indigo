"""#269 (no emulator): the rod / bike acquisition errands' early returns, the rod choice, the shoes flag and the bike's refusals."""
from types import SimpleNamespace as NS

import pytest

from knowledge import story_beats as sb

pytest.importorskip("openai")
from agent.lm_studio_client import AgentClient   # noqa: E402
from agent.skills import errands                   # noqa: E402
from game.state import GameContext                 # noqa: E402


def client(flags=(), keys=(), ctx="OVERWORLD", surfing=False, biking=False):
    c = AgentClient.__new__(AgentClient)
    c.reader = NS(read_flag=lambda f: f in flags, read_key_items=lambda: list(keys), detect_context=lambda: getattr(GameContext, ctx),
                  is_biking=lambda: biking, read_player_facing=lambda: "Down")
    c._surfing = lambda: surfing
    c._gift_errand = lambda *a, **k: pytest.fail("should not have travelled")
    return c


def test_the_new_beats_exist_with_their_flags_and_the_shoes_beat_is_guide_only():
    for key, flag in (("old_rod", 0x240), ("good_rod", 0x244), ("super_rod", 0x255), ("bike", 0x271)):
        b = sb.BY_KEY[key]
        assert b.driver == key and b.optional and ("flag", flag) in b.done, key
    shoes = sb.BY_KEY["running_shoes"]
    assert shoes.driver == "" and ("flag", errands.FLAG_B_DASH) in shoes.done and errands.FLAG_B_DASH == 0x82F         # FLAG_SYS_B_DASH


def test_each_acquisition_says_so_when_it_is_already_yours():
    assert "already have the Old Rod" in client(flags={errands.FLAG_OLD_ROD})._get_rod("old")
    assert "already have the Good Rod" in client(flags={errands.FLAG_GOOD_ROD})._get_rod("good")
    assert "already have the Super Rod" in client(flags={errands.FLAG_SUPER_ROD})._get_rod("super")
    assert "already have the Bicycle" in client(flags={errands.FLAG_BICYCLE})._get_bike()
    assert "in a battle" in client(ctx="IN_BATTLE")._get_rod("old")


def test_the_best_rod_wins_and_fishing_needs_one():
    from agent.skills.fishing import GOOD_ROD, OLD_ROD, SUPER_ROD
    assert client(keys=[OLD_ROD, GOOD_ROD])._best_rod() == (GOOD_ROD, "Good Rod")
    assert client(keys=[OLD_ROD, SUPER_ROD, GOOD_ROD])._best_rod() == (SUPER_ROD, "Super Rod")
    assert client(keys=[])._best_rod() == (None, "")
    assert "no fishing rod" in client(keys=[])._fish()
    assert "from the shore" in client(keys=[OLD_ROD], surfing=True)._fish()


def test_the_bicycle_refuses_without_one_in_a_battle_or_on_water():
    assert "no Bicycle" in client(keys=[])._use_bicycle()
    assert "on the field" in client(ctx="IN_BATTLE", keys=[360])._use_bicycle()
    assert "while surfing" in client(keys=[360], surfing=True)._use_bicycle()


def test_use_item_bicycle_is_routed_to_the_mount_skill():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "agent" / "lm_studio_client.py").read_text()
    assert '("bicycle", "bike")' in src and "self._use_bicycle()" in src
    assert "self._fish(" in src
